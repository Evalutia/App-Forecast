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

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

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

# Detect if staging table has 'stock' column
with conn.cursor() as cur:
    cur.execute("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
    """, (os.environ['MYSQL_DB'], "ventas_historicas_stage"))
    meta = {row[0].lower(): row[1].lower() for row in cur.fetchall()}

has_stock = "stock" in meta
cantidad_is_decimal = ("cantidad" in meta and meta["cantidad"] in ("decimal","numeric","fixed"))
stock_is_decimal = (has_stock and meta["stock"] in ("decimal","numeric","fixed"))

if has_stock:
    insert_cols = ["fecha","sku","cantidad","stock","fuente"]
else:
    insert_cols = ["fecha","sku","cantidad","fuente"]
placeholders = ",".join(["%s"]*len(insert_cols))
sql = f"INSERT INTO ventas_historicas_stage({','.join(insert_cols)}) VALUES({placeholders})"

# Stock real por fecha (viene en la misma respuesta de ConsStockVenta) -> stock_diario.
# Reemplaza la dependencia de ConsStockXml (snapshot sin fecha real) como fuente de
# dias_con_stock. Ver Issue stock-historico, sesion 2026-06-18.
deposito_forzado = os.environ.get("__FORCED_DEPOSITO") or None
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
            cant_val = clamp_nonneg_int(venta)
        if has_stock:
            if stock_is_decimal:
                stk_val = str(to_decimal(stock, "0"))
            else:
                stk_val = clamp_nonneg_int(stock)
        try:
            if has_stock:
                cur.execute(sql, (fecha, sku, cant_val, stk_val, fuente))
            else:
                cur.execute(sql, (fecha, sku, cant_val, fuente))
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

print(f"[INFO] Inserted {rows_ins} rows into ventas_historicas_stage (skipped {rows_skip})")
print(f"[INFO] Upserted {rows_stock_ins} rows into stock_diario (fuente={('ws_consstockventa' if rows_stock_ins else '-')})")
