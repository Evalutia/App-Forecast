#!/usr/bin/env bash
set -euo pipefail

: "${WS_URL:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsStockVenta}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockVenta}"

ID_EMPRESA="${ID_EMPRESA:-}"
ID_GRUPO="${ID_GRUPO:-}"
S_DEPOSITOS="${S_DEPOSITOS:-}"

GROUPS="${GROUPS:-${ID_GRUPO:-}}"
if [ -z "${GROUPS}" ]; then
  GROUPS="201"
fi

# Derivar CHUNK_START / CHUNK_END si no están provistos
if [ -z "${CHUNK_START:-}" ] || [ -z "${CHUNK_END:-}" ]; then
  if [ -n "${FORCE_START:-}" ] && [ -n "${FORCE_END:-}" ]; then
    CHUNK_START="${FORCE_START}"
    CHUNK_END="${FORCE_END}"
  else
    ISO_END="$(date -d 'yesterday' +%F)"
    ISO_START="$(date -d "${ISO_END} -6 days" +%F)"
    if [ "${DATE_FMT}" = "dmy" ]; then
      CHUNK_START="$(date -d "${ISO_START}" +'%d/%m/%Y')"
      CHUNK_END="$(date -d "${ISO_END}" +'%d/%m/%Y')"
    else
      CHUNK_START="$(date -d "${ISO_START}" +'%Y-%m-%d')"
      CHUNK_END="$(date -d "${ISO_END}" +'%Y-%m-%d')"
    fi
  fi
fi

BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"

# ── Una llamada SOAP por depósito + ingest Python ────────────────────────────
# El WS no acepta lista de depósitos — se itera igual que run_extract_stockxml.sh
call_for_deposito() {
  local dep="$1"

  local TMP_REQ="/tmp/soap_request_sales.$$.${dep}.xml"
  local TMP_HDR="/tmp/soap_headers_sales.$$.${dep}.txt"
  local TMP_XML="/tmp/soap_response_sales.$$.${dep}.xml"
  local TMP_JSON="/tmp/ws_json_sales.$$.${dep}.json"

  {
    cat <<XML
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <${WS_METHOD} xmlns="${WS_NS}">
XML
    [[ -n "$ID_EMPRESA" ]] && echo "      <IdEmpresa>${ID_EMPRESA}</IdEmpresa>"
    echo "      <DesdeFec>${CHUNK_START}</DesdeFec>"
    echo "      <HastaFec>${CHUNK_END}</HastaFec>"
    if [[ "${GROUPS}" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
      echo "      <IdGrupo>${GROUPS}</IdGrupo>"
    else
      [[ -n "$ID_GRUPO" ]] && echo "      <IdGrupo>${ID_GRUPO}</IdGrupo>"
    fi
    [[ -n "$dep" ]] && echo "      <sDepositos>${dep}</sDepositos>"
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

  # Conservar últimos archivos para debug
  cp -f "$TMP_REQ" /tmp/last_soap_request_sales.xml   2>/dev/null || true
  cp -f "$TMP_HDR" /tmp/soap_headers_sales.txt         2>/dev/null || true
  cp -f "$TMP_XML" /tmp/soap_response_sales.xml        2>/dev/null || true

  if [[ ! -s "$TMP_XML" ]]; then
    echo "[ERROR] Respuesta vacía de ConsStockVenta (deposito ${dep})"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 10
  fi

  local JSON
  JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i'           "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is'                      "$TMP_XML" || true)"

  if [[ -z "$JSON" ]]; then
    echo "[WARN] No se detectó JSON en ConsStockVenta (deposito ${dep})"
    echo "[DUMP] Inicio de body (1200 chars):"; head -c 1200 "$TMP_XML"; echo
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 11
  fi

  JSON="$(printf "%s" "$JSON" | sed -e 's/&quot;/"/g' -e 's/&amp;/\&/g' -e 's/&lt;/</g' -e 's/&gt;/>/g')"
  printf '%s' "$JSON" > "$TMP_JSON"
  [[ -s "$TMP_JSON" ]] && cp -f "$TMP_JSON" /tmp/last_ws_json_sales.json 2>/dev/null || true

  export TMP_JSON_PATH="$TMP_JSON"
  export __FORCED_DEPOSITO="${dep}"
  python3 /app/services/etl/run_extract_sales_chunk.py
  unset __FORCED_DEPOSITO

  rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
}

# ── Main: iterar por depósito si viene lista separada por comas ──────────────
if [[ "${S_DEPOSITOS}" == *","* ]]; then
  OLD_IFS="$IFS"
  IFS=","
  for dep in ${S_DEPOSITOS}; do
    dep="$(echo "$dep" | tr -d '[:space:]')"
    [[ -z "$dep" ]] && continue
    echo "[INFO] Ejecutando ConsStockVenta para deposito: ${dep}"
    call_for_deposito "${dep}" || echo "[WARN] Fallo en deposito ${dep}, continuando con el siguiente..."
  done
  IFS="$OLD_IFS"
else
  call_for_deposito "${S_DEPOSITOS:-}"
fi
