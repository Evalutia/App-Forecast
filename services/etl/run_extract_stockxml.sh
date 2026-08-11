#!/usr/bin/env bash
set -euo pipefail

: "${WS_URL:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"
: "${CERT_PATH:?missing}"    # Issue #51: mTLS obligatorio, sin fallback a HTTP
: "${CACERT_PATH:?missing}"
: "${CERT_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsStockXml}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockXml}"

ID_EMPRESA="${ID_EMPRESA:-}"
ID_GRUPO="${ID_GRUPO:-}"
S_DEPOSITOS="${S_DEPOSITOS:-}"
CANTREG="${CANTREG:-20000}"

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

# Issue #119 (code-review post-implement): antes esto dejaba que strptime
# tirara ValueError sin atrapar en fechas no vacias pero invalidas -- el
# caller (assert_ventana_no_peligrosa) esperaba "" como unico contrato de
# "no se pudo interpretar", no un crash. Ahora CUALQUIER fecha no
# interpretable -- vacia, con espacios, o con formato invalido -- da "" de
# la misma forma, para que haya un solo camino que el bash de afuera tenga
# que chequear.
try:
  if fmt == "dmy":
    d = dt.datetime.strptime(s[:10], "%d/%m/%Y").date()
  else:
    d = dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
  print(d.strftime("%Y-%m-%d"))
except ValueError:
  print("")
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

# Issue #119: ConsStockXml devuelve siempre la foto de HOY, sin importar el
# rango pedido (DesdeFec/HastaFec) -- no es un bug de este script, es como
# responde el web service. Pedir una ventana de mas de un dia significa que
# CADA fecha del rango termina con el MISMO contenido (el de hoy) escrito
# bajo una fecha distinta -- exactamente lo que corrompe stock_diario cuando
# se invoca a mano sin FORCE_START (ventana default de 7 dias): pisa valores
# reales por fecha que ya habia cargado el otro extractor (ConsStockVenta,
# que si respeta el rango pedido). Un solo dia (el uso real del cron
# nocturno, FORCE_START=FORCE_END=ayer) es una foto de hoy mal-etiquetada
# por a lo sumo un dia -- tolerado, no es lo que este chequeo previene.
assert_ventana_no_peligrosa() {
  local desde="$1" hasta="$2"
  if [[ "${desde}" != "${hasta}" ]]; then
    echo "[ERROR] Ventana de mas de un dia (${desde} -> ${hasta}): ConsStockXml devuelve siempre la foto de HOY sin importar el rango pedido -- pedir varios dias escribiria el mismo contenido bajo fechas distintas, pisando stock_diario real. Invocar con un solo dia por vez (CHUNK_START == CHUNK_END, o FORCE_START == FORCE_END)." >&2
    exit 3
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
    --cert-type P12 \
    --cert "${CERT_PATH}:${CERT_PASSWORD}" \
    --cacert "${CACERT_PATH}" \
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

  # Issue #125: mismo bug que tenia run_extract_sales_chunk.sh -- este sed
  # (orden quot/amp/lt/gt) desescapaba de mas (&amp;lt; -> &lt; -> < en vez
  # de quedarse en &lt;). El desescape se centraliza en Python
  # (run_extract_stockxml.py, via html.unescape); aca se escribe el
  # contenido tal cual vino del WS.
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
  # Issue #119 (code-review post-implement): to_iso() de una fecha invalida
  # imprime "" -- sin este chequeo, DOS fechas invalidas distintas resolvian
  # a la misma cadena vacia, assert_ventana_no_peligrosa las veia "iguales"
  # y dejaba pasar la ventana (con las fechas originales, invalidas, intactas)
  # en vez de abortar. Reproducido antes de este fix: pasaba sin abortar.
  ISO_CHUNK_START_EXT="$(to_iso "${CHUNK_START}")"
  ISO_CHUNK_END_EXT="$(to_iso "${CHUNK_END}")"
  if [[ -z "${ISO_CHUNK_START_EXT}" || -z "${ISO_CHUNK_END_EXT}" ]]; then
    echo "[ERROR] CHUNK_START/CHUNK_END inválidas: '${CHUNK_START}' / '${CHUNK_END}'" >&2
    exit 2
  fi
  assert_ventana_no_peligrosa "${ISO_CHUNK_START_EXT}" "${ISO_CHUNK_END_EXT}"
  export CHUNK_START CHUNK_END ID_EMPRESA
  echo "[INFO] Stock window (externo): ${CHUNK_START} -> ${CHUNK_END}"
  process_current_window
  exit 0
fi

# ---------------------------
# Modo 2: rango automático
# - Si FORCE_START: exige FORCE_END tambien (Issue #119, ver mas abajo), un
#   solo dia (FORCE_START == FORCE_END) es el uso real del cron nocturno.
# - Si no FORCE_START: default de 7 dias terminando AYER -- Issue #119: esta
#   ventana multi-dia siempre choca contra assert_ventana_no_peligrosa()
#   mas abajo y aborta. ConsStockXml no soporta rangos historicos (ver el
#   comentario de esa funcion), asi que este "default" nunca fue seguro para
#   una invocacion manual sin FORCE_START explicito de un solo dia.
# ---------------------------
ISO_TODAY="$(date +%F)"

if [[ -n "${FORCE_START:-}" ]]; then
  ISO_START="$(to_iso "${FORCE_START}")"
  if [[ -z "${ISO_START}" ]]; then
    echo "[ERROR] FORCE_START inválida: '${FORCE_START}'"
    exit 2
  fi

  if [[ -z "${FORCE_END:-}" ]]; then
    # Issue #119: antes esto defaulteaba en silencio a HOY (ISO_END="${ISO_TODAY}"),
    # una ventana de rango incompleto usando "otra" ventana sin avisar. Un
    # FORCE_START sin FORCE_END ahora es un error explicito, no una adivinanza.
    echo "[ERROR] FORCE_START='${FORCE_START}' sin FORCE_END -- rango incompleto. Si el rango es de un solo dia, pasar FORCE_END igual a FORCE_START." >&2
    exit 2
  fi
  ISO_END="$(to_iso "${FORCE_END}")"
  if [[ -z "${ISO_END}" ]]; then
    echo "[ERROR] FORCE_END inválida: '${FORCE_END}'"
    exit 2
  fi
  [[ "${ISO_END}" > "${ISO_TODAY}" ]] && ISO_END="${ISO_TODAY}"
else
  ISO_END="$(date -d 'yesterday' +%F)"
  ISO_START="$(date -d "${ISO_END} -6 days" +%F)"
fi

# sanity
if [[ "${ISO_START}" > "${ISO_END}" ]]; then
  echo "[ERROR] Rango inválido: ISO_START=${ISO_START} > ISO_END=${ISO_END}"
  exit 2
fi

assert_ventana_no_peligrosa "${ISO_START}" "${ISO_END}"

# Issue #119 (code-review post-implement): antes esto era un loop de
# chunking por STEP_DAYS sobre [ISO_START, ISO_END]. La guarda de arriba ya
# garantiza ISO_START == ISO_END en todo camino que llegue hasta acá (Modo 2
# aborta si difieren) -- el loop nunca podía dar más de una vuelta, STEP_DAYS
# ya no cambiaba nada. Se saca el loop y la variable en vez de dejar código
# que aparenta soportar sub-chunking y no lo hace.
CHUNK_START="$(fmt_out "${ISO_START}")"
CHUNK_END="$(fmt_out "${ISO_END}")"
export CHUNK_START CHUNK_END ID_EMPRESA

echo "[INFO] Stock window: ${CHUNK_START} -> ${CHUNK_END}"
process_current_window