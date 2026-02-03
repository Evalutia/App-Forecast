#!/usr/bin/env bash
set -euo pipefail

: "${WS_URL:?missing}"
: "${CHUNK_START:?missing}"
: "${CHUNK_END:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsArticulosWeb}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsArticulosWeb}"

ID_EMPRESA="${ID_EMPRESA:-}"
ID_GRUPO="${ID_GRUPO:-}"
CANTREG="${CANTREG:-20000}"

BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"

TMP_REQ="/tmp/soap_request.$$.$RANDOM.xml"
TMP_HDR="/tmp/soap_headers.$$.$RANDOM.txt"
TMP_XML="/tmp/soap_response.$$.$RANDOM.xml"
TMP_JSON="/tmp/ws_json.$$.$RANDOM.json"

trap 'cp -f "$TMP_REQ" /tmp/last_soap_request_articulos.xml 2>/dev/null || true;
      cp -f "$TMP_HDR" /tmp/soap_headers_articulos.txt 2>/dev/null || true;
      cp -f "$TMP_XML" /tmp/soap_response_articulos.xml 2>/dev/null || true;
      [[ -s "$TMP_JSON" ]] && cp -f "$TMP_JSON" /tmp/last_ws_json_articulos.json 2>/dev/null || true' EXIT

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
  [[ -n "$ID_GRUPO"    ]] && echo "      <IdGrupo>${ID_GRUPO}</IdGrupo>"
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
  echo "[ERROR] Respuesta vacía de ConsArticulosWeb"
  exit 10
fi

JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
[[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i' "$TMP_XML" || true)"
[[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is' "$TMP_XML" || true)"

if [[ -z "$JSON" ]]; then
  echo "[WARN] No se detectó JSON en ConsArticulosWeb"
  echo "[DUMP] Inicio de body (1200 chars):"; head -c 1200 "$TMP_XML"; echo
  exit 11
fi

JSON="$(printf "%s" "$JSON" | sed -e 's/&quot;/"/g' -e 's/&amp;/\&/g' -e 's/&lt;/</g' -e 's/&gt;/>/g')"
printf '%s' "$JSON" > "$TMP_JSON"
export TMP_JSON_PATH="$TMP_JSON"

python3 /app/services/etl/run_extract_articulos.py
