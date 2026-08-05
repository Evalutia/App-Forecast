#!/usr/bin/env python3
import json, os, pymysql, datetime as dt
from decimal import Decimal, InvalidOperation

def norm_fecha(s):
    if not s: return None
    s = str(s).strip()[:19]
    for f in ("%Y-%m-%dT%H:%M:%S","%d/%m/%Y","%Y-%m-%d"):
        try:
            d = dt.datetime.strptime(s, f)
            if d.year < 1900 or d.year > 2100:
                return None
            return d.strftime("%Y-%m-%d")
        except Exception:
            pass
    return None

def to_decimal(x, default="0"):
    if x is None: x = default
    s = str(x).replace(",", ".").strip()
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal(default)

def clamp_nonneg_int(x):
    try:
        n = int(Decimal(str(x)).to_integral_value(rounding="ROUND_HALF_UP"))
    except Exception:
        n = 0
    return max(0, n)

def clamp_signed_int(x):
    # Issue #80: a diferencia de clamp_nonneg_int, preserva el signo -- una
    # nota de credito (venta neta negativa) no debe aplastarse a 0.
    try:
        n = int(Decimal(str(x)).to_integral_value(rounding="ROUND_HALF_UP"))
    except Exception:
        n = 0
    return n

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]


def procesar_payload(conn, payload, deposito_forzado=None, grupo_id=None):
    """
    Inserta/actualiza en ventas_historicas_stage y stock_diario a partir de
    un payload ya parseado de ConsStockVenta. Retorna (rows_ins, rows_skip,
    rows_stock_ins).

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
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        for it in payload:
            if not isinstance(it, dict):
                rows_skip += 1
                continue
            fecha = norm_fecha(it.get('Fecha') or it.get('fecha'))
            sku   = it.get('IdArticulo') or it.get('Articulo') or it.get('SKU') or it.get('sku')
            venta = None
            for k in ['Venta','VentaQty','Cantidad','CantVenta','CantidadVta','CantVta','CantidadVenta','CANTIDAD','CANT_VENTA']:
                if it.get(k) is not None:
                    venta = it.get(k); break
            stock = None
            for k in ['Stock','StockDisp','StockDisponible','Existencia','Existencias','CantidadStock']:
                if it.get(k) is not None:
                    stock = it.get(k); break
            if not fecha or not sku:
                rows_skip += 1
                continue
            sku = trunc(sku, 128)
            fuente = "ws_consstockventa"
            if cantidad_is_decimal:
                cant_val = str(to_decimal(venta, "0"))
            else:
                cant_val = clamp_signed_int(venta)

            values = {"fecha": fecha, "sku": sku, "cantidad": cant_val, "fuente": fuente}
            if has_stock:
                if stock_is_decimal:
                    values["stock"] = str(to_decimal(stock, "0"))
                else:
                    values["stock"] = clamp_nonneg_int(stock)
            if has_deposito:
                values["deposito_id"] = deposito_id
            if has_grupo:
                values["grupo_id"] = grupo_val

            try:
                cur.execute(sql, tuple(values[c] for c in insert_cols))
                rows_ins += 1
            except Exception:
                rows_skip += 1
                continue

            if stock is not None and deposito_forzado:
                try:
                    cur.execute(sql_stock_diario, (sku, fecha, clamp_nonneg_int(stock), deposito_forzado, fuente))
                    rows_stock_ins += 1
                except Exception:
                    pass
        conn.commit()

    return rows_ins, rows_skip, rows_stock_ins


def main():
    json_path = os.environ.get("TMP_JSON_PATH")
    if not json_path or not os.path.exists(json_path):
        print("[ERROR] TMP_JSON_PATH no existe")
        raise SystemExit(2)

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

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

    rows_ins, rows_skip, rows_stock_ins = procesar_payload(
        conn, payload, deposito_forzado=deposito_forzado, grupo_id=grupo_id
    )

    print(f"[INFO] Inserted {rows_ins} rows into ventas_historicas_stage (skipped {rows_skip})")
    print(f"[INFO] Upserted {rows_stock_ins} rows into stock_diario (fuente={('ws_consstockventa' if rows_stock_ins else '-')})")


if __name__ == "__main__":
    main()
