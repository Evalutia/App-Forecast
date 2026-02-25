#!/usr/bin/env python3
import os
import json
import datetime as dt
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
import pymysql

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

def parse_stock_value(s):
    """
    Normaliza valores como '25.000', '3.800.000', '25,000' etc.
    - Si hay >1 punto, asumimos separadores de miles y los removemos.
    - Reemplazamos coma por punto para soportar decimales con coma.
    Devuelve int (no-negativo).
    """
    if s is None:
        return 0
    s = str(s).strip()
    if s == "":
        return 0
    s = s.replace(",", ".")
    if s.count(".") > 1:
        s = s.replace(".", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        digits = "".join(ch for ch in s if ch.isdigit())
        try:
            d = Decimal(digits or "0")
        except Exception:
            d = Decimal(0)
    try:
        n = int(d.to_integral_value(rounding="ROUND_HALF_UP"))
    except Exception:
        n = int(d)
    return max(0, n)

def parse_date_any(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = dt.datetime.strptime(s[:19], fmt)
            return d.date().strftime("%Y-%m-%d")
        except Exception:
            continue
    return None

json_path = os.environ.get("TMP_JSON_PATH")
if not json_path or not os.path.exists(json_path):
    print("[ERROR] TMP_JSON_PATH no existe")
    raise SystemExit(2)

with open(json_path, "r", encoding="utf-8") as f:
    content = f.read().strip()

# Desescape mínimo si quedan entities HTML
content = content.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')

rows = []
forced_dep = os.environ.get("__FORCED_DEPOSITO")

# Parse XML o JSON
if content.startswith("<"):
    try:
        root = ET.fromstring(content)
    except Exception as e:
        print("[ERROR] parseando XML:", e)
        raise

    for mv in root.findall(".//MovStockTotal"):
        sku = (mv.findtext("IdArticulo") or mv.findtext("Id_Articulo") or
               mv.findtext("Articulo") or mv.findtext("Id") or mv.findtext("SKU"))
        stock = mv.findtext("Stock") or mv.findtext("Existencia") or mv.findtext("Cantidad") or "0"
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
        deposito = it.get("IdDeposito") or it.get("Deposito") or it.get("Id_Deposito")
        if (not deposito or str(deposito).strip() == "") and forced_dep:
            deposito = forced_dep
        rows.append((sku, stock, deposito))

# Fecha de carga: preferir CHUNK_END (o CHUNK_START), sino hoy
chunk_end = os.environ.get("CHUNK_END") or os.environ.get("CHUNK_START") or None
fecha = parse_date_any(chunk_end) or dt.date.today().strftime("%Y-%m-%d")

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

with conn.cursor() as cur:
    for sku, stock, deposito in rows:
        if not sku:
            rows_skip += 1
            continue

        sku = trunc(sku, 128).strip()
        if not sku:
            rows_skip += 1
            continue

        if allowed_skus is not None and sku not in allowed_skus:
            rows_skip += 1
            continue

        cantidad_val = parse_stock_value(stock)
        deposito_val = trunc(deposito, 64) if deposito else None
        fuente = "ConsStockXml"

        try:
            if has_deposito:
                cur.execute(insert_sql, (sku, fecha, cantidad_val, deposito_val, fuente))
            else:
                cur.execute(insert_sql, (sku, fecha, cantidad_val, fuente))
            rows_ins += 1
        except Exception:
            rows_skip += 1
            continue

    conn.commit()

conn.close()
print(f"[INFO] Inserted/Upserted {rows_ins} rows into stock_diario (skipped {rows_skip})")