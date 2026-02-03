#!/usr/bin/env python3
# Inserta/Upserta articulos en tabla `articulos`
import json, os, pymysql, datetime as dt
from decimal import Decimal, InvalidOperation

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

def to_int(x, default=None):
    try:
        if x is None or str(x).strip()=="":
            return default
        return int(Decimal(str(x)))
    except Exception:
        return default

def to_nonneg_int(x, default=0):
    n = to_int(x, None)
    if n is None:
        return default
    return max(0, n)

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

insert_sql = """
INSERT INTO articulos
  (sku, barcode, descripcion, familia_id, familia_nombre, genero_id, genero_descripcion,
   stock_minimo, frecuencia_mensual, fuente, ts_carga)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6))
ON DUPLICATE KEY UPDATE
  barcode = VALUES(barcode),
  descripcion = VALUES(descripcion),
  familia_id = VALUES(familia_id),
  familia_nombre = VALUES(familia_nombre),
  genero_id = VALUES(genero_id),
  genero_descripcion = VALUES(genero_descripcion),
  stock_minimo = VALUES(stock_minimo),
  frecuencia_mensual = VALUES(frecuencia_mensual),
  fuente = VALUES(fuente),
  actualizado_en = NOW(6),
  ts_carga = NOW(6)
"""

rows_ins = 0
rows_skip = 0
with conn.cursor() as cur:
    for it in payload:
        if not isinstance(it, dict):
            rows_skip += 1
            continue

        # Mapeo flexible de campos comunes
        sku = (it.get('SKU') or it.get('Sku') or it.get('IdArticulo') or it.get('Articulo') or it.get('sku') or it.get('id') or it.get('Codigo')).strip() if any(it.get(k) for k in ['SKU','IdArticulo','Articulo','sku','id','Codigo']) else None
        barcode = it.get('Barcode') or it.get('CodigoBarra') or it.get('barcode') or None
        descripcion = it.get('Descripcion') or it.get('DescripcionArticulo') or it.get('descripcion') or it.get('nombre') or None

        familia_id = to_int(it.get('FamiliaId') or it.get('IdFamilia') or it.get('family_id') or None, None)
        familia_nombre = it.get('Familia') or it.get('FamiliaNombre') or it.get('family_name') or None

        genero_id = to_int(it.get('GeneroId') or it.get('IdGenero') or it.get('genre_id') or None, None)
        genero_descripcion = it.get('Genero') or it.get('GeneroDescripcion') or it.get('genre_description') or None

        stock_minimo = to_nonneg_int(it.get('StockMinimo') or it.get('stock_minimo') or it.get('MinimumStock') or it.get('Minimum_Stock') or 0, 0)
        frecuencia_mensual = to_int(it.get('FrecuenciaMensual') or it.get('frecuencia_mensual') or it.get('PurchaseFrequencyMonths') or None, None)

        if not sku:
            rows_skip += 1
            continue

        sku = trunc(sku, 120)
        barcode = trunc(barcode, 64)
        descripcion = trunc(descripcion, 512)
        familia_nombre = trunc(familia_nombre, 255)
        genero_descripcion = trunc(genero_descripcion, 255)
        fuente = "ConsArticulosWeb"

        try:
            cur.execute(insert_sql, (
                sku, barcode, descripcion,
                familia_id, familia_nombre,
                genero_id, genero_descripcion,
                stock_minimo, frecuencia_mensual,
                fuente
            ))
            rows_ins += 1
        except Exception as e:
            rows_skip += 1
            continue
    conn.commit()

print(f"[INFO] Inserted/Upserted {rows_ins} articulos (skipped {rows_skip})")
