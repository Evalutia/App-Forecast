#!/usr/bin/env python3
import os, pymysql, datetime as dt
from decimal import Decimal
import xml.etree.ElementTree as ET
import json

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

def to_nonneg_int(x, default=0):
    try:
        if x is None or str(x).strip()=="":
            return default
        n = int(Decimal(str(x)))
        return max(0, n)
    except Exception:
        return default

def parse_date_any(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
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

# Desescape if HTML entities still present (minimal)
content = content.replace("&lt;","<").replace("&gt;",">").replace("&amp;","&").replace("&quot;",'"')

rows = []
# If it starts with '<' consider XML
if content.startswith("<"):
    try:
        root = ET.fromstring(content)
    except Exception as e:
        print("[ERROR] parseando XML:", e)
        raise

    # Buscar MovStockTotal en cualquier nivel
    for mv in root.findall(".//MovStockTotal"):
        sku = mv.findtext("IdArticulo") or mv.findtext("Id_Articulo") or mv.findtext("Articulo") or mv.findtext("Id")
        stock = mv.findtext("Stock") or mv.findtext("Existencia") or mv.findtext("Cantidad") or "0"
        rows.append((sku, stock))
else:
    # Try parse JSON array/object
    try:
        payload = json.loads(content)
    except Exception as e:
        print("[ERROR] JSONDecodeError:", e)
        raise SystemExit(3)
    # normalize to list
    if isinstance(payload, dict):
        # if container like {'Rows':[...]} or {'NewDataSet': {...}}
        if 'Rows' in payload and isinstance(payload['Rows'], list):
            payload = payload['Rows']
        elif 'Data' in payload and isinstance(payload['Data'], list):
            payload = payload['Data']
        else:
            payload = [payload]
    elif not isinstance(payload, list):
        payload = []
    for it in payload:
        if not isinstance(it, dict):
            continue
        sku = it.get('IdArticulo') or it.get('Articulo') or it.get('SKU') or it.get('Codigo')
        stock = it.get('Stock') or it.get('StockDisp') or it.get('Cantidad') or 0
        rows.append((sku, stock))

# Fecha para stock: preferir CHUNK_END, sino today
chunk_end = os.environ.get('CHUNK_END') or os.environ.get('CHUNK_START') or None
fecha = parse_date_any(chunk_end) or dt.date.today().strftime("%Y-%m-%d")

# DB connect
conn = pymysql.connect(
    host=os.environ['MYSQL_HOST'],
    port=int(os.environ.get('MYSQL_PORT','3306')),
    user=os.environ['MYSQL_USER'],
    password=os.environ['MYSQL_PASSWORD'],
    database=os.environ['MYSQL_DB'],
    autocommit=False,
    charset='utf8mb4'
)

insert_sql = """
INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente, ts_carga)
VALUES (%s, %s, %s, %s, %s, NOW(6))
ON DUPLICATE KEY UPDATE
  cantidad = VALUES(cantidad),
  fuente = VALUES(fuente),
  ts_carga = VALUES(ts_carga)
"""

rows_ins = 0
rows_skip = 0
with conn.cursor() as cur:
    for sku, stock in rows:
        if not sku:
            rows_skip += 1
            continue
        sku = trunc(sku, 120)
        cantidad_val = to_nonneg_int(stock, 0)
        deposito = None
        fuente = "ConsStockXml"
        try:
            cur.execute(insert_sql, (sku, fecha, cantidad_val, deposito, fuente))
            rows_ins += 1
        except Exception as e:
            rows_skip += 1
            continue
    conn.commit()

print(f"[INFO] Inserted/Upserted {rows_ins} rows into stock_diario (skipped {rows_skip})")
