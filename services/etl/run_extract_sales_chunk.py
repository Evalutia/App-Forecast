#!/usr/bin/env python3
import html, json, os, pymysql

import parsers

# Issue #159: nombres alternativos de campo que el WS puede usar para venta y
# stock -- listados una sola vez (antes vivian inline en el loop de parseo,
# duplicados si hacia falta consultarlos desde otro lado).
CAMPOS_VENTA = ['Venta', 'VentaQty', 'Cantidad', 'CantVenta', 'CantidadVta',
                'CantVta', 'CantidadVenta', 'CANTIDAD', 'CANT_VENTA']
CAMPOS_STOCK = ['Stock', 'StockDisp', 'StockDisponible', 'Existencia',
                'Existencias', 'CantidadStock']


class ContractDriftError(Exception):
    """Issue #159: ninguna fila del payload trae un campo reconocible (venta
    o stock) -- firma de un cambio de contrato del WS (renombre de campo),
    no de una ausencia de dato puntual (ver _campo_ausente_en_todas)."""


def _campo_ausente_en_todas(payload, candidatos):
    """
    True si el payload tiene al menos un item de tipo dict y NINGUNO trae
    ninguno de los campos candidatos con un valor no-nulo.

    La señal es la ausencia TOTAL del campo, no el valor que trae: un dia
    real sin ventas (domingo) tiene el campo presente con valor 0, y
    it.get(k) is not None ya es True para 0 -- eso cuenta como "encontrado".
    Un payload vacio (sin items) no dice nada sobre el contrato -- devuelve
    False, no es la clase de fallo que este chequeo busca (ver #124/#133
    para el manejo de respuesta vacia/legitimamente sin datos).
    """
    items = [it for it in payload if isinstance(it, dict)]
    if not items:
        return False
    return not any(
        any(it.get(k) is not None for k in candidatos)
        for it in items
    )


def procesar_payload(conn, payload, deposito_forzado=None, grupo_id=None):
    """
    Inserta/actualiza en ventas_historicas_stage y stock_diario a partir de
    un payload ya parseado de ConsStockVenta. Retorna (rows_ins, rows_skip,
    rows_stock_ins, rows_failed, rows_stock_failed) -- rows_failed/
    rows_stock_failed son excepciones reales de MySQL al escribir (Issue
    #154), distintas de rows_skip (descarte legitimo de datos).

    Issue #159: si NINGUNA fila del payload trae un campo de venta
    reconocible, levanta ContractDriftError ANTES de escribir nada -- sin
    este chequeo, parse_entero(None) defaultea a 0 y esas filas pisarian
    ventas buenas via ON DUPLICATE KEY UPDATE, sistematicamente, sin
    ningun error. Mismo criterio para stock, pero solo si deposito_forzado
    esta seteado (sin eso, stock_diario nunca se escribe de todos modos).

    Issue #114: idempotente por (fecha, sku, deposito_id). Antes, el INSERT
    era plano y sin clave unica -- un articulo devuelto por varios grupos
    del loop de #42 insertaba una fila por grupo, y el merge (SUM GROUP BY
    fecha,sku) multiplicaba la venta por la cantidad de grupos. Ahora la
    segunda escritura del mismo articulo/fecha/deposito pisa la fila
    existente en vez de sumar una nueva.

    deposito_id NUNCA es NULL: un deposito_forzado vacio o None se
    normaliza al mismo sentinel '' que usa la columna (NOT NULL DEFAULT
    ''), porque MySQL no colisiona NULL contra NULL en una UNIQUE -- un
    deposito nulo reabriria el mismo bug por otra puerta.

    grupo_id es solo trazabilidad: NO participa de la clave unica, asi que
    la fila se pisa igual si el mismo articulo/fecha/deposito vuelve por
    otro grupo (ese pisado es exactamente lo que resuelve el bug). Sirve
    para poder responder "de que llamada vino esta fila" en el proximo
    diagnostico, cosa que #114 no pudo hacer y tuvo que reconstruir por
    correlacion.

    Requiere que la migracion 19-ventas-stage-deposito-grupo.sql ya haya
    corrido: si la columna deposito_id no existe todavia, cae a un INSERT
    plano (compatible con el esquema viejo) pero avisa fuerte por stdout,
    porque en ese modo la ingesta vuelve a NO ser idempotente.
    """
    # Chequeo explicito (no truthy): un deposito_forzado=0 entero no deberia
    # colapsar al sentinel de "sin deposito" solo porque 0 es falsy en Python.
    # En la practica los depositos reales nunca son 0 (1,5,8,9,10,11), pero la
    # correctitud de la clave unica no deberia depender de esa suposicion.
    deposito_id = str(deposito_forzado) if deposito_forzado not in (None, "") else ""
    grupo_val = None
    if grupo_id not in (None, ""):
        try:
            grupo_val = int(grupo_id)
        except (TypeError, ValueError):
            grupo_val = None

    # Issue #159: chequeo de contract drift ANTES de tocar la DB -- si esto
    # dispara, no debe quedar ninguna fila a medio escribir con datos malos.
    if _campo_ausente_en_todas(payload, CAMPOS_VENTA):
        raise ContractDriftError(
            "ninguna fila del payload trae un campo de venta reconocible -- "
            f"se probaron: {', '.join(CAMPOS_VENTA)}. Posible cambio de "
            "contrato del WS (renombre de campo), no una ausencia de dato "
            "puntual (un dia sin ventas real trae el campo presente en 0)."
        )
    if deposito_forzado and _campo_ausente_en_todas(payload, CAMPOS_STOCK):
        raise ContractDriftError(
            "ninguna fila del payload trae un campo de stock reconocible -- "
            f"se probaron: {', '.join(CAMPOS_STOCK)}. Posible cambio de "
            "contrato del WS (renombre de campo), no una ausencia de dato "
            "puntual (un dia con stock en 0 real trae el campo presente)."
        )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """, ("ventas_historicas_stage",))
        meta = {row[0].lower(): row[1].lower() for row in cur.fetchall()}

    has_stock = "stock" in meta
    has_deposito = "deposito_id" in meta
    has_grupo = "grupo_id" in meta
    cantidad_is_decimal = ("cantidad" in meta and meta["cantidad"] in ("decimal","numeric","fixed"))
    stock_is_decimal = (has_stock and meta["stock"] in ("decimal","numeric","fixed"))

    insert_cols = ["fecha", "sku", "cantidad"]
    if has_stock:
        insert_cols.append("stock")
    if has_deposito:
        insert_cols.append("deposito_id")
    if has_grupo:
        insert_cols.append("grupo_id")
    insert_cols.append("fuente")

    placeholders = ",".join(["%s"] * len(insert_cols))
    # Issue #125 (code-review post-implement): si el stock no se puede
    # interpretar, no hay que pisar un valor bueno que ya estaba en stage
    # con un 0/NULL -- se arma una variante del mismo INSERT que omite la
    # columna stock (ni se inserta ni se actualiza esa columna) en vez de
    # defaultear a "0" como hacia antes de este fix. Solo hace falta en la
    # rama con ON DUPLICATE KEY UPDATE: la otra rama siempre inserta una
    # fila nueva, no hay valor previo que proteger.
    sql_sin_stock = None
    if has_deposito:
        update_cols = ["cantidad"]
        if has_stock: update_cols.append("stock")
        if has_grupo: update_cols.append("grupo_id")
        update_cols.append("fuente")
        update_clause = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
        sql = (
            f"INSERT INTO ventas_historicas_stage({','.join(insert_cols)}) "
            f"VALUES({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_clause}"
        )
        if has_stock:
            insert_cols_sin_stock = [c for c in insert_cols if c != "stock"]
            placeholders_sin_stock = ",".join(["%s"] * len(insert_cols_sin_stock))
            update_cols_sin_stock = [c for c in update_cols if c != "stock"]
            update_clause_sin_stock = ", ".join(f"{c} = VALUES({c})" for c in update_cols_sin_stock)
            sql_sin_stock = (
                f"INSERT INTO ventas_historicas_stage({','.join(insert_cols_sin_stock)}) "
                f"VALUES({placeholders_sin_stock}) "
                f"ON DUPLICATE KEY UPDATE {update_clause_sin_stock}"
            )
    else:
        print("[WARN] ventas_historicas_stage sin columna deposito_id -- falta correr "
              "infra/sql/19-ventas-stage-deposito-grupo.sql. La ingesta NO es idempotente "
              "por deposito (Issue #114 reabierto hasta que corra la migracion).")
        sql = f"INSERT INTO ventas_historicas_stage({','.join(insert_cols)}) VALUES({placeholders})"

    sql_stock_diario = """
        INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente, ts_carga)
        VALUES (%s, %s, %s, %s, %s, NOW(6))
        ON DUPLICATE KEY UPDATE
          cantidad = VALUES(cantidad),
          fuente   = VALUES(fuente),
          ts_carga = VALUES(ts_carga)
    """

    rows_ins = 0
    rows_skip = 0
    rows_stock_ins = 0
    # Issue #154 (mismo patron que #141 en run_extract_stockxml.py): antes,
    # una excepcion real de MySQL al escribir stage o stock_diario se
    # contaba junto con los descartes legitimos (rows_skip) o se ignoraba
    # del todo (`except Exception: pass` en stock_diario) -- en los dos
    # casos el script terminaba en exit 0 con el job 'exitoso' aunque la
    # escritura hubiera fallado. rows_failed/rows_stock_failed separan el
    # error real del descarte esperado (sin fecha, venta no interpretable).
    rows_failed = 0
    rows_stock_failed = 0
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        for it in payload:
            if not isinstance(it, dict):
                rows_skip += 1
                continue
            sku_raw = it.get('IdArticulo') or it.get('Articulo') or it.get('SKU') or it.get('sku')
            sku = parsers.normalize_sku(sku_raw)
            try:
                fecha = parsers.parse_fecha(it.get('Fecha') or it.get('fecha'))
            except parsers.ParseError as e:
                print(f"[WARN] fila descartada, fecha no interpretable sku={sku_raw!r}: {e}")
                rows_skip += 1
                continue
            venta = None
            for k in CAMPOS_VENTA:
                if it.get(k) is not None:
                    venta = it.get(k); break
            stock = None
            for k in CAMPOS_STOCK:
                if it.get(k) is not None:
                    stock = it.get(k); break
            if not fecha or not sku:
                rows_skip += 1
                continue
            fuente = "ws_consstockventa"

            # Issue #125: antes, un valor de venta no interpretable (p. ej.
            # '1,5' vía el bypass que tenia clamp_signed_int) caia en un 0
            # silencioso -- peor que perder la fila, porque ademas pisaba
            # stock correcto ya cargado. Ahora la fila entera se descarta
            # con un log visible en vez de escribir un 0 que nadie audita.
            try:
                if cantidad_is_decimal:
                    venta_dec = parsers.parse_decimal(venta)
                    cant_val = str(venta_dec) if venta_dec is not None else "0"
                else:
                    cant_val = parsers.parse_entero(venta, signed=True)
            except parsers.ParseError as e:
                print(f"[WARN] fila descartada, venta no interpretable sku={sku} fecha={fecha}: {e}")
                rows_skip += 1
                continue

            values = {"fecha": fecha, "sku": sku, "cantidad": cant_val, "fuente": fuente}
            stock_parseable = True
            if has_stock:
                try:
                    if stock_is_decimal:
                        stock_dec = parsers.parse_decimal(stock)
                        values["stock"] = str(stock_dec) if stock_dec is not None else "0"
                    else:
                        values["stock"] = parsers.parse_entero(stock, contexto=f"sku={sku} fecha={fecha}")
                except parsers.ParseError as e:
                    stock_parseable = False
                    if sql_sin_stock is not None:
                        print(f"[WARN] stock no interpretable sku={sku} fecha={fecha}: {e}; se inserta/actualiza sin tocar stock")
                    else:
                        # Rama sin ON DUPLICATE KEY UPDATE (deposito_id no
                        # existe todavia): siempre inserta fila nueva, no
                        # hay valor previo que proteger -- NULL, no 0.
                        print(f"[WARN] stock no interpretable sku={sku} fecha={fecha}: {e}; se inserta con stock NULL")
                        values["stock"] = None
            if has_deposito:
                values["deposito_id"] = deposito_id
            if has_grupo:
                values["grupo_id"] = grupo_val

            active_sql = sql
            active_cols = insert_cols
            if has_stock and not stock_parseable and sql_sin_stock is not None:
                active_sql = sql_sin_stock
                active_cols = [c for c in insert_cols if c != "stock"]

            try:
                cur.execute(active_sql, tuple(values[c] for c in active_cols))
                # Issue #154: commit por fila, no uno solo al final del lote.
                # InnoDB resuelve un deadlock con ROLLBACK de la transaccion
                # ENTERA -- con un commit unico al final, la fila que dispara
                # el deadlock se llevaba puestas todas las filas previas del
                # lote, ya contadas como escritas (rows_ins/rows_stock_ins),
                # sin que el script se enterara. Comitear apenas se escribe
                # la deja durable de inmediato: una falla posterior solo
                # puede perder su propia fila.
                conn.commit()
                rows_ins += 1
            except Exception as e:
                conn.rollback()
                print(f"[ERROR] fila no escrita en stage, excepcion de MySQL sku={sku} fecha={fecha}: {e}")
                rows_failed += 1
                continue

            if stock is not None and deposito_forzado:
                try:
                    # Reusa el valor ya parseado arriba cuando coincide el tipo
                    # (evita parsear el mismo string dos veces por fila en el
                    # camino comun) -- en decimal son columnas de tipos
                    # distintos (stage puede ser DECIMAL, stock_diario es
                    # entero), ahi se mantiene el parseo independiente.
                    if not stock_is_decimal and stock_parseable:
                        stock_diario_val = values["stock"]
                    else:
                        stock_diario_val = parsers.parse_entero(stock, contexto=f"sku={sku} fecha={fecha}")
                except parsers.ParseError as e:
                    print(f"[WARN] stock_diario no actualizado, stock no interpretable sku={sku} fecha={fecha}: {e}")
                else:
                    try:
                        cur.execute(sql_stock_diario, (sku, fecha, stock_diario_val, deposito_forzado, fuente))
                        conn.commit()
                        rows_stock_ins += 1
                    except Exception as e:
                        conn.rollback()
                        print(f"[ERROR] fila no escrita en stock_diario, excepcion de MySQL sku={sku} fecha={fecha}: {e}")
                        rows_stock_failed += 1

    return rows_ins, rows_skip, rows_stock_ins, rows_failed, rows_stock_failed


def main():
    json_path = os.environ.get("TMP_JSON_PATH")
    if not json_path or not os.path.exists(json_path):
        print("[ERROR] TMP_JSON_PATH no existe")
        raise SystemExit(2)

    with open(json_path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Issue #125: el desescape de entities HTML se centraliza aca (via
    # html.unescape) en vez del sed en el .sh -- ese sed desescapaba de mas
    # (orden quot/amp/lt/gt convertia &amp;lt; en < en vez de &lt;).
    raw = html.unescape(raw)
    # Issue #124: una respuesta bien formada del punto de vista SOAP puede
    # ser JSON ilegible (el WS devuelve texto libre en el campo de error).
    # Sin este chequeo, un JSONDecodeError sin capturar quedaba invisible
    # para el caller (ver .claude/CONTEXTO.md, seccion #124).
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON ilegible en respuesta del WS: {e}")
        raise SystemExit(1)

    if isinstance(payload, dict):
        payload = [payload]
    elif not isinstance(payload, list):
        payload = []

    conn = pymysql.connect(
        host=os.environ['MYSQL_HOST'],
        port=int(os.environ.get('MYSQL_PORT','3306')),
        user=os.environ['MYSQL_USER'],
        password=os.environ['MYSQL_PASSWORD'],
        database=os.environ['MYSQL_DB'],
        autocommit=False,
        charset='utf8mb4'
    )

    # Issue #114: deposito_id/grupo_id llegan por env (mismo mecanismo que
    # ya existia para __FORCED_DEPOSITO; __FORCED_GRUPO lo exporta el .sh
    # dentro de call_for_grupo_deposito).
    deposito_forzado = os.environ.get("__FORCED_DEPOSITO") or None
    grupo_id = os.environ.get("__FORCED_GRUPO") or None

    try:
        rows_ins, rows_skip, rows_stock_ins, rows_failed, rows_stock_failed = procesar_payload(
            conn, payload, deposito_forzado=deposito_forzado, grupo_id=grupo_id
        )
    except ContractDriftError as e:
        # Issue #159: nada se escribio (el chequeo corre antes de la
        # primera escritura) -- falla fuerte en vez de dejar que el resto
        # del pipeline reciba ceros silenciosos.
        print(f"[ERROR] posible cambio de contrato del WS: {e}")
        raise SystemExit(1)

    print(f"[INFO] Inserted {rows_ins} rows into ventas_historicas_stage (skipped {rows_skip}, failed {rows_failed})")
    print(f"[INFO] Upserted {rows_stock_ins} rows into stock_diario (fuente={('ws_consstockventa' if rows_stock_ins else '-')}, failed {rows_stock_failed})")

    # Issue #154: una excepcion real de MySQL al escribir (stage o
    # stock_diario) ya no puede terminar en exit 0 -- antes se contaba como
    # skip legitimo o se ignoraba del todo, y el job quedaba 'exitoso' en
    # jobs_historial pese a haber perdido datos.
    if rows_failed or rows_stock_failed:
        print(f"[ERROR] {rows_failed} fila(s) de stage y {rows_stock_failed} fila(s) de stock_diario "
              "no se pudieron escribir por una excepcion de MySQL")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
