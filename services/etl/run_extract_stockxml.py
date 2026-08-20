#!/usr/bin/env python3
import os
import json
import html
import datetime as dt
import xml.etree.ElementTree as ET
import pymysql

import parsers

# Issue #173: mismo patron de contract-drift que #159 establecio para
# run_extract_sales_chunk.py, nunca replicado en este script hermano.
# Nombres alternativos de campo que el WS puede usar para el stock, en cada
# formato de payload (mismos que ya se prueban mas abajo en cada rama).
CAMPOS_STOCK_XML = ["Stock", "Existencia", "Cantidad"]
CAMPOS_STOCK_JSON = ["Stock", "StockDisp", "Cantidad"]


class ContractDriftError(Exception):
    """Ninguna fila del payload trae un campo de stock reconocible -- firma
    de un cambio de contrato del WS (renombre de campo), no de un dia real
    con stock en 0 (ver _campo_stock_ausente_en_todas)."""


def _campo_stock_ausente_en_todas(stock_field_presente):
    """
    True si hay al menos una fila Y NINGUNA trajo un campo de stock
    reconocible. La señal es la ausencia TOTAL del campo, no el valor: un
    dia real con stock en 0 trae el campo presente (valor "0"/0), y
    `mv.find(k) is not None` / `it.get(k) is not None` ya cuentan eso como
    "encontrado". Un payload sin filas no dice nada sobre el contrato -- no
    dispara este chequeo (mismo criterio que el helper analogo de #159).
    """
    if not stock_field_presente:
        return False
    return not any(stock_field_presente)


def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

json_path = os.environ.get("TMP_JSON_PATH")
if not json_path or not os.path.exists(json_path):
    print("[ERROR] TMP_JSON_PATH no existe")
    raise SystemExit(2)

with open(json_path, "r", encoding="utf-8") as f:
    content = f.read().strip()

# Issue #125: el desescape de entities HTML se centraliza aca (via
# html.unescape de la stdlib, igual que run_extract_articulos.py) en vez de
# hacerse en el .sh con sed -- el orden manual de reemplazos en bash
# desescapaba de mas (&amp;lt; -> &lt; -> < en vez de quedarse en &lt;).
content = html.unescape(content)

rows = []
stock_field_presente = []
forced_dep = os.environ.get("__FORCED_DEPOSITO")
es_xml = content.startswith("<")

# Parse XML o JSON
if es_xml:
    try:
        root = ET.fromstring(content)
    except Exception as e:
        print("[ERROR] parseando XML:", e)
        raise

    for mv in root.findall(".//MovStockTotal"):
        sku = (mv.findtext("IdArticulo") or mv.findtext("Id_Articulo") or
               mv.findtext("Articulo") or mv.findtext("Id") or mv.findtext("SKU"))
        stock = mv.findtext("Stock") or mv.findtext("Existencia") or mv.findtext("Cantidad") or "0"
        # Issue #173: presencia del TAG (no del valor) -- mv.find(...) es
        # None solo si el tag no existe; un tag <Stock>0</Stock> real
        # cuenta como encontrado igual que arriba con findtext.
        stock_field_presente.append(any(mv.find(c) is not None for c in CAMPOS_STOCK_XML))
        deposito = (mv.findtext("IdDeposito") or mv.findtext("Deposito") or mv.findtext("Id_Deposito"))
        if (not deposito or str(deposito).strip() == "") and forced_dep:
            deposito = forced_dep
        rows.append((sku, stock, deposito))
else:
    try:
        payload = json.loads(content)
    except Exception as e:
        print("[ERROR] JSONDecodeError:", e)
        raise SystemExit(3)

    if isinstance(payload, dict):
        if "Rows" in payload and isinstance(payload["Rows"], list):
            payload = payload["Rows"]
        elif "Data" in payload and isinstance(payload["Data"], list):
            payload = payload["Data"]
        else:
            payload = [payload]
    elif not isinstance(payload, list):
        payload = []

    for it in payload:
        if not isinstance(it, dict):
            continue
        sku = it.get("IdArticulo") or it.get("Articulo") or it.get("SKU") or it.get("Codigo")
        stock = it.get("Stock") or it.get("StockDisp") or it.get("Cantidad") or 0
        stock_field_presente.append(any(it.get(c) is not None for c in CAMPOS_STOCK_JSON))
        deposito = it.get("IdDeposito") or it.get("Deposito") or it.get("Id_Deposito")
        if (not deposito or str(deposito).strip() == "") and forced_dep:
            deposito = forced_dep
        rows.append((sku, stock, deposito))

# Issue #173: chequeo de contract drift ANTES de tocar la DB -- si esto
# dispara, no debe quedar ninguna fila a medio escribir con datos malos
# (mismo criterio de placement que #159).
try:
    if _campo_stock_ausente_en_todas(stock_field_presente):
        campos_probados = CAMPOS_STOCK_XML if es_xml else CAMPOS_STOCK_JSON
        raise ContractDriftError(
            "ninguna fila del payload trae un campo de stock reconocible -- "
            f"se probaron: {', '.join(campos_probados)}. No es una ausencia de "
            "dato puntual (un dia con stock en 0 real trae el campo presente) "
            "-- puede ser un renombre de campo en el WS."
        )
except ContractDriftError as e:
    print(f"[ERROR] posible cambio de contrato del WS: {e}")
    raise SystemExit(1)

# Fecha de carga: preferir CHUNK_END (o CHUNK_START), sino hoy
chunk_end = os.environ.get("CHUNK_END") or os.environ.get("CHUNK_START") or None
try:
    fecha = parsers.parse_fecha(chunk_end)
except parsers.ParseError as e:
    print(f"[WARN] CHUNK_END/CHUNK_START no interpretable ({e}); uso fecha de hoy")
    fecha = None
fecha = fecha or dt.date.today().strftime("%Y-%m-%d")

# DB connect
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DB"],
    autocommit=False,
    charset="utf8mb4",
)
# Issue #122: mismo motivo que run_extract_articulos.py -- sin esto ts_carga
# usa hora local del servidor en vez de UTC, como el resto de los scripts.
with conn.cursor() as cur:
    cur.execute("SET time_zone = '+00:00'")

def get_columns(table_name: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            """,
            (os.environ["MYSQL_DB"], table_name),
        )
        return {row[0].lower() for row in cur.fetchall()}

# Detect columnas de stock_diario
stock_cols = get_columns("stock_diario")
has_deposito = ("deposito_id" in stock_cols) or ("deposito" in stock_cols)

# SQL correcto según columnas
if has_deposito:
    insert_sql = """
    INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente, ts_carga)
    VALUES (%s, %s, %s, %s, %s, NOW(6))
    ON DUPLICATE KEY UPDATE
      cantidad = VALUES(cantidad),
      deposito_id = VALUES(deposito_id),
      fuente = VALUES(fuente),
      ts_carga = VALUES(ts_carga)
    """
else:
    insert_sql = """
    INSERT INTO stock_diario (sku, fecha, cantidad, fuente, ts_carga)
    VALUES (%s, %s, %s, %s, NOW(6))
    ON DUPLICATE KEY UPDATE
      cantidad = VALUES(cantidad),
      fuente = VALUES(fuente),
      ts_carga = VALUES(ts_carga)
    """

# Cargar SKUs permitidos desde articulos (filtrar)
allowed_skus = None
try:
    art_cols = get_columns("articulos")

    # Preferido: sku
    sku_col = None
    for cand in ("sku", "SKU"):
        if cand.lower() in art_cols:
            sku_col = cand.lower()
            break

    # fallback razonable si no existe sku
    if not sku_col:
        for cand in ("id_articulo", "idarticulo", "codigo", "cod_articulo", "articulo"):
            if cand.lower() in art_cols:
                sku_col = cand.lower()
                print(f"[WARN] Tabla articulos no tiene 'sku'; uso '{sku_col}' como filtro.")
                break

    if not sku_col:
        print("[WARN] No encontré columna usable (sku/id_articulo/codigo/...) en articulos; no aplico filtro.")
    else:
        where = ""
        args = []
        id_emp = os.environ.get("ID_EMPRESA")

        # Si existe empresa_id o id_empresa, filtramos por empresa si viene
        emp_col = None
        if "id_empresa" in art_cols:
            emp_col = "id_empresa"
        elif "empresa_id" in art_cols:
            emp_col = "empresa_id"

        if id_emp and emp_col:
            where = f" WHERE {emp_col}=%s"
            args = [id_emp]

        sql = f"SELECT DISTINCT TRIM({sku_col}) FROM articulos{where}"
        with conn.cursor() as cur:
            cur.execute(sql, args)
            allowed_skus = {(r[0] or "").strip() for r in cur.fetchall() if r and r[0]}

        print(f"[INFO] Filtro articulos: {len(allowed_skus)} SKUs permitidos")
except Exception as e:
    print("[WARN] No pude cargar filtro desde articulos; continúo sin filtrar. Error:", e)
    allowed_skus = None

rows_ins = 0
rows_skip = 0
rows_failed = 0

with conn.cursor() as cur:
    for sku, stock, deposito in rows:
        if not sku:
            rows_skip += 1
            continue

        sku = parsers.normalize_sku(sku)
        if not sku:
            rows_skip += 1
            continue

        if allowed_skus is not None and sku not in allowed_skus:
            rows_skip += 1
            continue

        try:
            cantidad_val = parsers.parse_entero(stock, contexto=f"sku={sku}")
        except parsers.ParseError as e:
            print(f"[WARN] fila descartada, stock no interpretable sku={sku}: {e}")
            rows_skip += 1
            continue
        # Issue #122: stock_diario.deposito_id es NOT NULL DEFAULT '' desde la
        # migracion 20 -- trunc(None, 64) ya devuelve "" (ver definicion arriba),
        # asi que no hay que pasar None nunca. Antes esto se insertaba/actualizaba
        # como NULL, y post-migracion 20 hubiera tirado una excepcion de MySQL
        # absorbida en silencio por el except generico de abajo (fila "saltada"
        # sin distinguirse de un skip legitimo).
        deposito_val = trunc(deposito, 64)
        fuente = "ConsStockXml"

        try:
            if has_deposito:
                cur.execute(insert_sql, (sku, fecha, cantidad_val, deposito_val, fuente))
            else:
                cur.execute(insert_sql, (sku, fecha, cantidad_val, fuente))
            # Issue #141 (code-review post-implement): commit por fila, no
            # uno solo al final del loop. Un deadlock lo resuelve InnoDB
            # haciendo ROLLBACK de la transaccion ENTERA, no solo de la fila
            # que lo disparo -- con un commit unico al final, esa fila N
            # fallida se llevaba puestas las filas 1..N-1 ya insertadas (y
            # contadas en rows_ins) sin que el script se enterara. Comitear
            # apenas cada fila se escribe la deja durable de inmediato, asi
            # que una falla posterior solo puede perder su propia fila.
            conn.commit()
            rows_ins += 1
        except Exception as e:
            # Issue #141: un error real de escritura (deadlock, columna
            # invalida, conexion caida a mitad de loop) se contaba antes como
            # rows_skip, indistinguible de un skip legitimo (SKU no filtrado,
            # stock no interpretable) -- rows_failed lo separa para que al
            # final del script se pueda fallar fuerte en vez de reportar
            # "todo OK" con filas que en realidad nunca se escribieron.
            print(f"[ERROR] fila no escrita, excepcion de MySQL sku={sku} deposito={deposito_val}: {e}")
            conn.rollback()
            rows_failed += 1
            continue

conn.close()
print(f"[INFO] Inserted/Upserted {rows_ins} rows into stock_diario (skipped {rows_skip}, failed {rows_failed})")

if rows_failed:
    print(f"[ERROR] {rows_failed} fila(s) no se pudieron escribir por una excepcion de MySQL")
    raise SystemExit(1)