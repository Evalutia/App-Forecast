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

# Si vino ID_GRUPO explicito (compatibilidad), se empuja a GROUPS para que
# get_grupos.py lo tome como override puntual (Issue #42) en vez de consultar
# la tabla grupos.
if [[ -n "${ID_GRUPO}" && -z "${GROUPS:-}" && -z "${GRUPOS:-}" ]]; then
  export GROUPS="${ID_GRUPO}"
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

# ── Una llamada SOAP por grupo + depósito + ingest Python ───────────────────
# El WS no acepta lista de depósitos — se itera igual que run_extract_stockxml.sh.
# Tampoco se manda una lista combinada de grupos: una llamada por grupo es la
# unica forma de saber a que grupo pertenece cada fila devuelta (Issue #42).
call_for_grupo_deposito() {
  local grupo="$1"
  local dep="$2"

  local TMP_REQ="/tmp/soap_request_sales.$$.${grupo}.${dep}.xml"
  local TMP_HDR="/tmp/soap_headers_sales.$$.${grupo}.${dep}.txt"
  local TMP_XML="/tmp/soap_response_sales.$$.${grupo}.${dep}.xml"
  local TMP_JSON="/tmp/ws_json_sales.$$.${grupo}.${dep}.json"

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
    echo "      <IdGrupo>${grupo}</IdGrupo>"
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
    echo "[ERROR] Respuesta vacía de ConsStockVenta (grupo ${grupo}, deposito ${dep})"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 10
  fi

  local JSON
  JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i'           "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is'                      "$TMP_XML" || true)"

  if [[ -z "$JSON" ]]; then
    echo "[WARN] No se detectó JSON en ConsStockVenta (grupo ${grupo}, deposito ${dep})"
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

process_grupo() {
  local grupo="$1"
  if [[ "${S_DEPOSITOS}" == *","* ]]; then
    local OLD_IFS="$IFS"
    IFS=","
    for dep in ${S_DEPOSITOS}; do
      dep="$(echo "$dep" | tr -d '[:space:]')"
      [[ -z "$dep" ]] && continue
      echo "[INFO] Ejecutando ConsStockVenta para grupo ${grupo}, deposito: ${dep}"
      call_for_grupo_deposito "${grupo}" "${dep}" || echo "[WARN] Fallo en grupo ${grupo} deposito ${dep}, continuando con el siguiente..."
    done
    IFS="$OLD_IFS"
  else
    call_for_grupo_deposito "${grupo}" "${S_DEPOSITOS:-}" || echo "[WARN] Fallo en grupo ${grupo}, continuando con el siguiente..."
  fi
}

GROUPS_LIST="$(python3 /app/services/etl/get_grupos.py)"
if [[ -z "${GROUPS_LIST}" ]]; then
  echo "[ERROR] No se obtuvo lista de grupos (ni override ni tabla grupos)" >&2
  exit 2
fi

echo "[INFO] Grupos a procesar: ${GROUPS_LIST}"

for G in ${GROUPS_LIST}; do
  echo "[INFO] === Grupo ${G} ==="
  process_grupo "${G}"
done
