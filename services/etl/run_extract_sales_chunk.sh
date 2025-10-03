#!/usr/bin/env bash
set -euo pipefail

# ===== Requeridos =====
: "${WS_URL:?missing}"
: "${CHUNK_START:?missing}"
: "${CHUNK_END:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

# ===== Opcionales =====
DATE_FMT="${DATE_FMT:-dmy}"  # dmy => dd/MM/yyyy
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsStockVenta}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockVenta}"

ID_EMPRESA="${ID_EMPRESA:-}"     # ej. 1
ID_GRUPO="${ID_GRUPO:-}"         # ej. 75 o 201
S_DEPOSITOS="${S_DEPOSITOS:-}"   # ej. 1,5 (opcional)

MYSQL_PORT="${MYSQL_PORT:-3306}"
CURL_INSECURE="${CURL_INSECURE:-}" # setear algo no vacío para usar -k en curl

# ===== Helpers =====
# fmt: toma cualquier cadena (puede venir con duplicaciones o saltos de línea),
#      extrae SOLO la primera fecha válida, y la normaliza al formato deseado.
fmt() {
  python3 - "$1" "$DATE_FMT" <<'PY'
import sys, re, datetime as dt
raw = (sys.argv[1] or "").replace("\r"," ").replace("\n"," ").strip()
target = sys.argv[2].lower()

m = re.search(r'(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})', raw)
if not m:
    print(raw); sys.exit(0)

s = m.group(1)
for fin, fout in (("%d/%m/%Y","%d/%m/%Y"), ("%Y-%m-%d","%Y-%m-%d")):
    try:
        d = dt.datetime.strptime(s, fin)
        print(d.strftime("%d/%m/%Y" if target=="dmy" else "%Y-%m-%d"))
        sys.exit(0)
    except Exception:
        pass

print(s)
PY
}

# ===== Normalización =====
CHUNK_START_FMT="$(fmt "$CHUNK_START")"
CHUNK_END_FMT="$(fmt "$CHUNK_END")"
# Quitar CR/LF/espacios extra en params
CHUNK_START_FMT="$(printf '%s' "$CHUNK_START_FMT" | tr -d '\r\n\t ')"
CHUNK_END_FMT="$(printf '%s' "$CHUNK_END_FMT" | tr -d '\r\n\t ')"
ID_EMPRESA="$(printf '%s' "$ID_EMPRESA" | tr -d '\r\n\t ')"
ID_GRUPO="$(printf '%s' "$ID_GRUPO" | tr -d '\r\n\t ')"
S_DEPOSITOS="$(printf '%s' "$S_DEPOSITOS" | tr -d '\r\n\t ')"

BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"

TMP_REQ="/tmp/soap_request.$$.$RANDOM.xml"
TMP_HDR="/tmp/soap_headers.$$.$RANDOM.txt"
TMP_XML="/tmp/soap_response.$$.$RANDOM.xml"
TMP_JSON="/tmp/ws_json.$$.$RANDOM.json"

# Dejo copias legibles para debug al terminar
trap 'cp -f "$TMP_REQ" /tmp/last_soap_request.xml 2>/dev/null || true;
      cp -f "$TMP_HDR" /tmp/soap_headers.txt 2>/dev/null || true;
      cp -f "$TMP_XML" /tmp/soap_response.xml 2>/dev/null || true;
      [[ -s "$TMP_JSON" ]] && cp -f "$TMP_JSON" /tmp/last_ws_json.json 2>/dev/null || true' EXIT

# ===== Envelope =====
{
  cat <<XML
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <${WS_METHOD} xmlns="${WS_NS}">
XML
  [[ -n "$ID_EMPRESA"  ]] && echo "      <IdEmpresa>${ID_EMPRESA}</IdEmpresa>"
  echo "      <DesdeFec>${CHUNK_START_FMT}</DesdeFec>"
  echo "      <HastaFec>${CHUNK_END_FMT}</HastaFec>"
  [[ -n "$ID_GRUPO"    ]] && echo "      <IdGrupo>${ID_GRUPO}</IdGrupo>"
  [[ -n "$S_DEPOSITOS" ]] && echo "      <sDepositos>${S_DEPOSITOS}</sDepositos>"
  cat <<XML
    </${WS_METHOD}>
  </soap:Body>
</soap:Envelope>
XML
} > "$TMP_REQ"

echo "[INFO] Endpoint     : ${ENDPOINT}"
echo "[INFO] SOAPAction   : ${WS_SOAP_ACTION}"
echo "[INFO] Fechas       : ${CHUNK_START_FMT} -> ${CHUNK_END_FMT}"
echo "[INFO] Params extra : IdEmpresa='${ID_EMPRESA:-}' IdGrupo='${ID_GRUPO:-}' sDepositos='${S_DEPOSITOS:-}'"

# ===== Llamada =====
curl ${CURL_INSECURE:+-k} -sS --http1.1 \
  -D "$TMP_HDR" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H "SOAPAction: \"${WS_SOAP_ACTION}\"" \
  --data-binary @"$TMP_REQ" \
  "$ENDPOINT" \
  -o "$TMP_XML"

STATUS="$(head -n1 "$TMP_HDR" | awk '{print $2}')"
echo "[INFO] HTTP status  : ${STATUS:-N/A}"
echo "[INFO] Files        : req=$(wc -c < "$TMP_REQ"  2>/dev/null || echo 0)B, hdr=$(wc -c < "$TMP_HDR" 2>/dev/null || echo 0)B, body=$(wc -c < "$TMP_XML" 2>/dev/null || echo 0)B"

[[ -s "$TMP_XML" ]] || { echo "[ERROR] Respuesta vacía"; exit 10; }

# MensError explícito
if grep -qi '<MensError>' "$TMP_XML"; then
  ERR=$(sed -n 's/.*<MensError>\(.*\)<\/MensError>.*/\1/ip' "$TMP_XML" | head -n1)
  echo "[WS ERROR] $ERR"
  echo "[DUMP] Inicio de body (600 chars):"; head -c 600 "$TMP_XML"; echo
  exit 11
fi

# ===== Extraer JSON =====
JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
[[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i' "$TMP_XML" || true)"
[[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is' "$TMP_XML" || true)"

if [[ -z "$JSON" ]]; then
  echo "[WARN] No se detectó JSON en <${WS_METHOD}Result>/<string>/CDATA."
  echo "[DUMP] Inicio de body (1200 chars):"; head -c 1200 "$TMP_XML"; echo
  exit 12
fi

# Desescapar entidades y guardar en archivo
JSON="$(printf "%s" "$JSON" | sed -e 's/&quot;/"/g' -e 's/&amp;/\&/g' -e 's/&lt;/</g' -e 's/&gt;/>/g')"
printf '%s' "$JSON" > "$TMP_JSON"
echo "[INFO] JSON length  : $(wc -c < "$TMP_JSON") bytes"
export TMP_JSON_PATH="$TMP_JSON"

# ===== Insert en MySQL =====
python3 - <<'PY'
import json, os, pymysql, datetime as dt
from decimal import Decimal, InvalidOperation

# -------- helpers ----------
def norm_fecha(s):
    if not s: return None
    s = str(s).strip()[:19]
    for f in ("%Y-%m-%dT%H:%M:%S","%d/%m/%Y","%Y-%m-%d"):
        try:
            d = dt.datetime.strptime(s, f)
            # filtrar fechas fuera de rango razonable para evitar CHECKs tipo 1900..2100
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
    # para columnas con CHECK cantidad>=0 o stock>=0
    try:
        n = int(Decimal(str(x)).to_integral_value(rounding="ROUND_HALF_UP"))
    except Exception:
        n = 0
    return max(0, n)

def clamp_nonneg_dec3(x: Decimal):
    # si tu cantidad es DECIMAL(18,3) con CHECK >=0
    if x is None:
        x = Decimal("0")
    if x < 0:
        x = Decimal("0")
    # redondear a 3 decimales
    q = Decimal("0.001")
    return x.quantize(q)

def trunc(s, maxlen):
    s = "" if s is None else str(s)
    return s[:maxlen]

# -------- cargar JSON ----------
json_path = os.environ["TMP_JSON_PATH"]
with open(json_path, "r", encoding="utf-8") as f:
    payload = json.load(f)

# normalizar a lista
if isinstance(payload, dict):
    payload = [payload]
elif not isinstance(payload, list):
    payload = []

# -------- conectar MySQL ----------
conn = pymysql.connect(
    host=os.environ['MYSQL_HOST'],
    port=int(os.environ.get('MYSQL_PORT','3306')),
    user=os.environ['MYSQL_USER'],
    password=os.environ['MYSQL_PASSWORD'],
    database=os.environ['MYSQL_DB'],
    autocommit=False,
    charset='utf8mb4'
)

# -------- descubrir columnas disponibles ----------
with conn.cursor() as cur:
    cur.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
    """, (os.environ['MYSQL_DB'], "ventas_historicas_stage"))
    meta = {row[0].lower(): (row[1].lower(), row[2]) for row in cur.fetchall()}

has_stock = "stock" in meta
# detectar si cantidad es decimal
cantidad_is_decimal = ("cantidad" in meta and meta["cantidad"][0] in ("decimal","numeric","fixed"))
stock_is_decimal = (has_stock and meta["stock"][0] in ("decimal","numeric","fixed"))

# construir INSERT según columnas
if has_stock:
    insert_cols = ["fecha","sku","cantidad","stock","fuente"]
else:
    insert_cols = ["fecha","sku","cantidad","fuente"]
placeholders = ",".join(["%s"]*len(insert_cols))
sql = f"INSERT INTO ventas_historicas_stage({','.join(insert_cols)}) VALUES({placeholders})"

# -------- mapeo WS -> tabla con validaciones ----------
rows_ins = 0
rows_skip = 0
with conn.cursor() as cur:
    cur.execute("SET time_zone = '+00:00'")
    for it in payload:
        if not isinstance(it, dict):
            rows_skip += 1
            continue

        fecha = norm_fecha(it.get('Fecha') or it.get('fecha'))
        sku   = it.get('IdArticulo') or it.get('Articulo') or it.get('SKU') or it.get('sku')
        # ventas: probar varias variantes comunes del WS
        venta = None
        for k in ['Venta','Cantidad','CantVenta','CantidadVta','CantVta','Cant_Vta','CantidadVenta','CANTIDAD','CANT_VENTA']:
            if it.get(k) is not None:
                venta = it.get(k)
                break

        # stock: también probamos alias (por si en algún cliente cambia)
        stock = None
        for k in ['Stock','StockDisp','StockDisponible','Existencia','Existencias','CantidadStock']:
            if it.get(k) is not None:
                stock = it.get(k)
                break

        if not fecha or not sku:
            # no pasa CHECKs de NOT NULL/validez
            rows_skip += 1
            continue

        # longitudes seguras
        sku = trunc(sku, 128)
        fuente = trunc("ws_consstockventa", 64)

        # cantidad
        if cantidad_is_decimal:
            cant_dec = clamp_nonneg_dec3(to_decimal(venta, "0"))
            cant_val = str(cant_dec)  # PyMySQL maneja bien strings para DECIMAL
        else:
            cant_val = clamp_nonneg_int(venta)

        # stock
        if has_stock:
            if stock_is_decimal:
                stk_dec = clamp_nonneg_dec3(to_decimal(stock, "0"))
                stk_val = str(stk_dec)
            else:
                stk_val = clamp_nonneg_int(stock)

        try:
            if has_stock:
                cur.execute(sql, (fecha, sku, cant_val, stk_val, fuente))
            else:
                cur.execute(sql, (fecha, sku, cant_val, fuente))
            rows_ins += 1
        except Exception:
            # si alguna fila aún viola otra regla, la salteamos
            rows_skip += 1
            continue

    conn.commit()

print(f"[INFO] Inserted {rows_ins} rows into ventas_historicas_stage (skipped {rows_skip})")
PY


