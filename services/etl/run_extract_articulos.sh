#!/usr/bin/env bash
set -euo pipefail

: "${WS_URL:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsArticulosWeb}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsArticulosWeb}"

ID_EMPRESA="${ID_EMPRESA:-1}"
ID_GRUPO="${ID_GRUPO:-}"
GRUPOS="${GRUPOS:-}"          # <-- usar ESTE (no GROUPS)
CANTREG="${CANTREG:-20000}"
ARTICULO_DESDE="${ARTICULO_DESDE:-}"

CURL_INSECURE="${CURL_INSECURE:-0}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-20}"
CURL_MAX_TIME="${CURL_MAX_TIME:-120}"

# -----------------------
# Args opcionales (para poder pasar grupos sin usar env GROUPS)
# Ej: run_extract_articulos.sh --grupos "201" --cuantos 100 --chunk-start 2016-10-03
# -----------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --grupos|--groups)
      GRUPOS="${2:-}"; shift 2;;
    --id-grupo|--id_grupo)
      ID_GRUPO="${2:-}"; shift 2;;
    --cuantos)
      CANTREG="${2:-}"; shift 2;;
    --articulo-desde|--articulo_desde)
      ARTICULO_DESDE="${2:-}"; shift 2;;
    --chunk-start|--fecha-desde|--fecha_desde)
      CHUNK_START="${2:-}"; shift 2;;
    *)
      echo "[ERROR] Arg desconocido: $1"
      exit 2;;
  esac
done

# Derivar CHUNK_START si no está provisto (compatibilidad con run_etl_daily.sh)
if [[ -z "${CHUNK_START:-}" ]]; then
  if [[ -n "${FORCE_START:-}" ]]; then
    CHUNK_START="${FORCE_START}"
  else
    ISO_END="$(date -d 'yesterday' +%F)"
    ISO_START="$(date -d "${ISO_END} -6 days" +%F)"
    if [[ "${DATE_FMT}" == "dmy" ]]; then
      CHUNK_START="$(date -d "${ISO_START}" +'%d/%m/%Y')"
    else
      CHUNK_START="${ISO_START}"
    fi
  fi
fi

# Normalizar FechaDesde a ISO dateTime (YYYY-MM-DDT00:00:00)
# Acepta: yyyy-mm-ddTHH:MM:SS, yyyy-mm-dd, dd/mm/yyyy
FechaDate="$(python3 - "$CHUNK_START" <<'PY'
import sys,re,datetime as dt
raw=sys.argv[1]
m=re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', raw or "")
if not m:
  print("")
  sys.exit(0)
s=m.group(1)
for fmt in ("%Y-%m-%d","%d/%m/%Y"):
  try:
    d=dt.datetime.strptime(s,fmt)
    print(d.strftime("%Y-%m-%d"))
    sys.exit(0)
  except Exception:
    pass
print("")
PY
)"
if [[ -z "$FechaDate" ]]; then
  FechaDate="$(date +%F)"
fi
FechaDesdeISO="${FechaDate}T00:00:00"

# Decidir Grupos: priorizar GRUPOS, sino ID_GRUPO
GRUPOS_VAL=""
if [[ -n "${GRUPOS}" && "${GRUPOS}" != "0" ]]; then
  GRUPOS_VAL="${GRUPOS}"
elif [[ -n "${ID_GRUPO}" && "${ID_GRUPO}" != "0" ]]; then
  GRUPOS_VAL="${ID_GRUPO}"
fi

# Endpoint robusto: si WS_URL ya trae el .asmx, no duplicar
BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
if [[ "$BASE" =~ /VsWebProduccion/SwNadWeb\.asmx$ ]]; then
  ENDPOINT="$BASE"
else
  ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"
fi

TMP_REQ="/tmp/soap_request_articulos.$$.$RANDOM.xml"
TMP_HDR="/tmp/soap_headers_articulos.$$.$RANDOM.txt"
TMP_XML="/tmp/soap_response_articulos.$$.$RANDOM.xml"
TMP_PAYLOAD="/tmp/ws_payload_articulos.$$.$RANDOM.txt"

trap 'cp -f "$TMP_REQ" /tmp/last_soap_request_articulos.xml 2>/dev/null || true;
      cp -f "$TMP_HDR" /tmp/soap_headers_articulos.txt 2>/dev/null || true;
      cp -f "$TMP_XML" /tmp/soap_response_articulos.xml 2>/dev/null || true;
      [[ -s "$TMP_PAYLOAD" ]] && cp -f "$TMP_PAYLOAD" /tmp/last_ws_payload_articulos.txt 2>/dev/null || true' EXIT

# Build SOAP request
{
  cat <<XML
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <${WS_METHOD} xmlns="${WS_NS}">
      <Cuantos>${CANTREG}</Cuantos>
XML

  if [[ -n "${ARTICULO_DESDE}" ]]; then
    echo "      <ArticuloDesde>${ARTICULO_DESDE}</ArticuloDesde>"
  fi

  echo "      <FechaDesde>${FechaDesdeISO}</FechaDesde>"

  if [[ -n "${GRUPOS_VAL}" ]]; then
    echo "      <Grupos>${GRUPOS_VAL}</Grupos>"
  fi

  cat <<XML
      <IdEmpresa>${ID_EMPRESA}</IdEmpresa>
    </${WS_METHOD}>
  </soap:Body>
</soap:Envelope>
XML
} > "$TMP_REQ"

echo "[INFO] Endpoint   : ${ENDPOINT}"
echo "[INFO] SOAPAction : ${WS_SOAP_ACTION}"
echo "[INFO] FechaDesde : ${FechaDesdeISO}"
echo "[INFO] Cuantos    : ${CANTREG}"
echo "[INFO] Grupos     : ${GRUPOS_VAL:-<vacio>}"

CURL_ARGS=(
  -sS --http1.1
  --connect-timeout "${CURL_CONNECT_TIMEOUT}"
  --max-time "${CURL_MAX_TIME}"
  -D "$TMP_HDR"
  -H "Content-Type: text/xml; charset=utf-8"
  -H "SOAPAction: \"${WS_SOAP_ACTION}\""
  --data-binary @"$TMP_REQ"
  "${ENDPOINT}"
  -o "$TMP_XML"
)
if [[ "${CURL_INSECURE}" == "1" ]]; then
  CURL_ARGS=(-k "${CURL_ARGS[@]}")
fi

if ! curl "${CURL_ARGS[@]}"; then
  echo "[ERROR] curl falló contra ${ENDPOINT}"
  echo "[DUMP] Headers:"
  sed -n '1,120p' "$TMP_HDR" || true
  exit 12
fi

if [[ ! -s "$TMP_XML" ]]; then
  echo "[ERROR] Respuesta vacía de ${WS_METHOD}"
  echo "[DUMP] Headers:"
  sed -n '1,120p' "$TMP_HDR" || true
  exit 10
fi

# Si viene MensError, mostrarlo y salir OK (para no romper el job), pero deja evidencia clara
MENSERR="$(perl -0777 -ne 'print $1 if m{<MensError>([\s\S]*?)</MensError>}i' "$TMP_XML" || true)"
if [[ -n "${MENSERR//[[:space:]]/}" ]]; then
  echo "[WARN] MensError en ${WS_METHOD}: ${MENSERR}"
  echo "[WARN] No se insertan artículos por MensError. Salida OK."
  exit 0
fi

# Extraer contenido del Result (SIN desescape acá; lo hace Python de forma segura)
PAYLOAD="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
[[ -z "$PAYLOAD" ]] && PAYLOAD="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i' "$TMP_XML" || true)"
[[ -z "$PAYLOAD" ]] && PAYLOAD="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is' "$TMP_XML" || true)"

if [[ -z "$PAYLOAD" ]]; then
  echo "[WARN] No se detectó payload en ${WS_METHOD}Result"
  echo "[DUMP] Inicio de body (1200 chars):"
  head -c 1200 "$TMP_XML"; echo
  exit 11
fi

printf '%s' "$PAYLOAD" > "$TMP_PAYLOAD"
export TMP_PAYLOAD_PATH="$TMP_PAYLOAD"

python3 /app/services/etl/run_extract_articulos.py
