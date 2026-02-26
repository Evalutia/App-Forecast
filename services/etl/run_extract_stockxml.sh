#!/usr/bin/env bash
set -euo pipefail

: "${WS_URL:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsStockXml}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockXml}"

ID_EMPRESA="${ID_EMPRESA:-}"
ID_GRUPO="${ID_GRUPO:-}"
S_DEPOSITOS="${S_DEPOSITOS:-}"
CANTREG="${CANTREG:-20000}"

# chunking: default diario
STEP_DAYS="${STEP_DAYS:-1}"

BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"

# ---------------------------
# Helpers de fecha
# ---------------------------
to_iso() {
  python3 - "$1" "$DATE_FMT" <<'PY'
import sys, datetime as dt
s = (sys.argv[1] or "").strip()
fmt = (sys.argv[2] or "dmy").lower()
if not s:
  print("")
  raise SystemExit(0)

# ya ISO
if len(s) >= 10 and s[4] == "-" and s[7] == "-":
  print(s[:10]); raise SystemExit(0)

if fmt == "dmy":
  d = dt.datetime.strptime(s[:10], "%d/%m/%Y").date()
else:
  d = dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
print(d.strftime("%Y-%m-%d"))
PY
}

fmt_out() {
  local iso="$1"
  if [[ "${DATE_FMT}" == "dmy" ]]; then
    date -d "${iso}" +'%d/%m/%Y'
  else
    date -d "${iso}" +'%Y-%m-%d'
  fi
}

# ---------------------------
# SOAP call por depósito
# ---------------------------
call_for_deposito() {
  local dep="$1"
  local TMP_REQ="/tmp/soap_request_stock.${dep}.$$.$RANDOM.xml"
  local TMP_HDR="/tmp/soap_headers_stock.${dep}.$$.$RANDOM.txt"
  local TMP_XML="/tmp/soap_response_stock.${dep}.$$.$RANDOM.xml"
  local TMP_JSON="/tmp/ws_json_stock.${dep}.$$.$RANDOM.json"

  # cleanup guard: copiar ultimo request/response si algo falla
  trap "cp -f '${TMP_REQ}' /tmp/last_soap_request_stock.xml 2>/dev/null || true; \
        cp -f '${TMP_HDR}' /tmp/soap_headers_stock.txt 2>/dev/null || true; \
        cp -f '${TMP_XML}' /tmp/soap_response_stock.xml 2>/dev/null || true; \
        [[ -s '${TMP_JSON}' ]] && cp -f '${TMP_JSON}' /tmp/last_ws_json_stock.json 2>/dev/null || true" RETURN

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
    echo "      <DesdeFec>${CHUNK_START}</DesdeFec>"
    echo "      <HastaFec>${CHUNK_END}</HastaFec>"
    echo "      <sDepositos>${dep}</sDepositos>"
    echo "      <CANTREG>${CANTREG}</CANTREG>"
    cat <<XML
    </${WS_METHOD}>
  </soap:Body>
</soap:Envelope>
XML
  } > "$TMP_REQ"

  curl -sS --http1.1 \
    -D "$TMP_HDR" \
    -H "Content-Type: text/xml; charset=utf-8" \
    -H "SOAPAction: \"${WS_SOAP_ACTION}\"" \
    --data-binary @"$TMP_REQ" \
    "${ENDPOINT}" \
    -o "$TMP_XML"

  if [[ ! -s "$TMP_XML" ]]; then
    echo "[ERROR] Respuesta vacía de ConsStockXml para deposito ${dep}"
    return 10
  fi

  JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i' "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is' "$TMP_XML" || true)"

  if [[ -z "$JSON" ]]; then
    echo "[WARN] No se detectó JSON en ConsStockXml para deposito ${dep}"
    echo "[DUMP] Inicio de body (1200 chars):"; head -c 1200 "$TMP_XML"; echo
    return 11
  fi

  JSON="$(printf "%s" "$JSON" | sed -e 's/&quot;/"/g' -e 's/&amp;/\&/g' -e 's/&lt;/</g' -e 's/&gt;/>/g')"

  printf '%s' "$JSON" > "$TMP_JSON"
  export TMP_JSON_PATH="$TMP_JSON"
  export __FORCED_DEPOSITO="${dep}"

  # importante: que python tenga fechas y empresa
  export CHUNK_START CHUNK_END ID_EMPRESA

  python3 /app/services/etl/run_extract_stockxml.py || true

  unset __FORCED_DEPOSITO
  trap - RETURN
  return 0
}

process_current_window() {
  if [[ "${S_DEPOSITOS}" == *","* ]]; then
    local OLD_IFS="$IFS"
    IFS=","
    for dep in ${S_DEPOSITOS}; do
      dep="$(echo "$dep" | tr -d '[:space:]')"
      [[ -z "$dep" ]] && continue
      echo "[INFO] Ejecutando ConsStockXml para deposito: ${dep}"
      call_for_deposito "${dep}" || true
    done
    IFS="$OLD_IFS"
  else
    local dep="${S_DEPOSITOS:-}"
    echo "[INFO] Ejecutando ConsStockXml para deposito: ${dep:-<vacio>}"
    call_for_deposito "${dep:-}" || true
  fi
}

# ---------------------------
# Modo 1: si CHUNK_START/CHUNK_END vienen seteadas externamente => 1 ejecución
# ---------------------------
if [[ -n "${CHUNK_START:-}" && -n "${CHUNK_END:-}" ]]; then
  export CHUNK_START CHUNK_END ID_EMPRESA
  echo "[INFO] Stock window (externo): ${CHUNK_START} -> ${CHUNK_END}"
  process_current_window
  exit 0
fi

# ---------------------------
# Modo 2: rango automático
# - Si FORCE_START: desde FORCE_START hasta HOY (o hasta FORCE_END si viene, capado a HOY)
# - Si no FORCE_START: comportamiento default (últimos 7 días terminando AYER)
# ---------------------------
ISO_TODAY="$(date +%F)"

if [[ -n "${FORCE_START:-}" ]]; then
  ISO_START="$(to_iso "${FORCE_START}")"
  if [[ -z "${ISO_START}" ]]; then
    echo "[ERROR] FORCE_START inválida: '${FORCE_START}'"
    exit 2
  fi

  if [[ -n "${FORCE_END:-}" ]]; then
    ISO_END="$(to_iso "${FORCE_END}")"
    if [[ -z "${ISO_END}" ]]; then
      echo "[ERROR] FORCE_END inválida: '${FORCE_END}'"
      exit 2
    fi
    [[ "${ISO_END}" > "${ISO_TODAY}" ]] && ISO_END="${ISO_TODAY}"
  else
    ISO_END="${ISO_TODAY}"
  fi
else
  ISO_END="$(date -d 'yesterday' +%F)"
  ISO_START="$(date -d "${ISO_END} -6 days" +%F)"
fi

# sanity
if [[ "${ISO_START}" > "${ISO_END}" ]]; then
  echo "[ERROR] Rango inválido: ISO_START=${ISO_START} > ISO_END=${ISO_END}"
  exit 2
fi

CUR="${ISO_START}"
while [[ "${CUR}" < "${ISO_END}" || "${CUR}" == "${ISO_END}" ]]; do
  CHUNK_START="$(fmt_out "${CUR}")"

  ISO_CHUNK_END="$(date -d "${CUR} +$((STEP_DAYS-1)) days" +%F)"
  [[ "${ISO_CHUNK_END}" > "${ISO_END}" ]] && ISO_CHUNK_END="${ISO_END}"
  CHUNK_END="$(fmt_out "${ISO_CHUNK_END}")"

  export CHUNK_START CHUNK_END ID_EMPRESA

  echo "[INFO] Stock window: ${CHUNK_START} -> ${CHUNK_END}"
  process_current_window

  CUR="$(date -d "${ISO_CHUNK_END} +1 day" +%F)"
done