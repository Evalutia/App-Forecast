#!/usr/bin/env python3
# Inserta/Upserta en stock_diario
import json, os, pymysql
from decimal import Decimal, InvalidOperation
import datetime as dt

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

json_path = os.environ.get("TMP_JSON_PATH")
if not json_path or not os.path.exists(json_path):
    print("[ERROR] TMP_JSON_PATH no existe")
    raise SystemExit(2)

with open(json_path, "r", encoding="utf-8") as f:
    payload = json.load(f)

if isinstance(payload, dict):
    # algunos WS devuelven {'Rows': {...}} o {'Data': [...]}
    if 'Rows' in payload and isinstance(payload['Rows'], list):
        payload = payload['Rows']
    elif 'Data' in payload and isinstance(payload['Data'], list):
        payload = payload['Data']
    else:
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
    for it in payload:
        if not isinstance(it, dict):
            rows_skip += 1
            continue

        # Campos posibles
        sku = (it.get('SKU') or it.get('IdArticulo') or it.get('Articulo') or it.get('sku') or it.get('Codigo') or it.get('CodArticulo'))
        fecha = (it.get('Fecha') or it.get('fecha') or it.get('FechaStock') or it.get('FechaExistencia'))
        deposito = (it.get('Deposito') or it.get('deposito') or it.get('deposito_id') or it.get('IdDeposito') or it.get('idDeposito'))
        cantidad = it.get('Stock') or it.get('StockDisp') or it.get('Cantidad') or it.get('Existencia') or it.get('Existencias') or 0

        if not sku or not fecha:
            rows_skip += 1
            continue

        sku = trunc(str(sku).strip(), 120)
        deposito = trunc(str(deposito).strip(), 64) if deposito is not None else None

        # Normalizar fecha -> YYYY-MM-DD
        fecha_str = str(fecha).strip()
        # soportar formatos  dd/mm/YYYY o YYYY-mm-dd o ISO
        parsed_date = None
        for fmt in ("%d/%m/%Y","%Y-%m-%dT%H:%M:%S","%Y-%m-%d"):
            try:
                parsed_date = dt.datetime.strptime(fecha_str[:19], fmt).date()
                break
            except Exception:
                continue
        if parsed_date is None:
            rows_skip += 1
            continue

        cantidad_val = to_nonneg_int(cantidad, 0)
        fuente = "ConsStockXml"

        try:
            cur.execute(insert_sql, (sku, parsed_date.strftime("%Y-%m-%d"), cantidad_val, deposito, fuente))
            rows_ins += 1
        except Exception:
            rows_skip += 1
            continue
    conn.commit()

print(f"[INFO] Inserted/Upserted {rows_ins} rows into stock_diario (skipped {rows_skip})")
