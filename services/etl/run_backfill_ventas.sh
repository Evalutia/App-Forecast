#!/usr/bin/env bash
set -uo pipefail
# run_backfill_ventas.sh - Backfill historico "hoy - 2 anios" de ConsStockVenta
# para los grupos nuevos (Issue #44). Corrida unica, manual, separada del cron
# diario de las 3 AM (run_ofelia.sh respeta el mismo lock file mas abajo).
#
# No dispara predict.py -- es estrictamente extraccion + merge a ventas_historicas
# (con el side-effect deseado de poblar tambien stock_diario, igual que el daily).
#
# Uso tipico (corrida completa):
#   docker compose exec etl /bin/bash /app/services/etl/run_backfill_ventas.sh
#
# Corrida piloto sobre un solo grupo chico (recomendado antes de la corrida
# completa, para validar tiempo/payload real del WS con BACKFILL_CHUNK_DAYS):
#   docker compose exec -e GROUPS=42 etl /bin/bash /app/services/etl/run_backfill_ventas.sh

: "${WS_URL:?missing}"
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"
: "${CERT_PATH:?missing}"    # Issue #51: mTLS obligatorio, sin fallback a HTTP
: "${CACERT_PATH:?missing}"
: "${CERT_PASSWORD:?missing}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsStockVenta}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockVenta}"

ID_EMPRESA="${ID_EMPRESA:-}"
S_DEPOSITOS="${S_DEPOSITOS:-}"

CURL_INSECURE="${CURL_INSECURE:-0}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-20}"
CURL_MAX_TIME="${CURL_MAX_TIME:-300}"   # ventanas de varios dias -> mas margen que el daily

# Rango fijo, calculado una sola vez al arrancar (no se recalcula por grupo).
# Override en ISO (YYYY-MM-DD) via BACKFILL_FROM/BACKFILL_TO para la corrida
# piloto o un reproceso puntual.
BACKFILL_TO="${BACKFILL_TO:-$(date +%F)}"
BACKFILL_FROM="${BACKFILL_FROM:-$(date -d "${BACKFILL_TO} -2 years" +%F)}"
BACKFILL_CHUNK_DAYS="${BACKFILL_CHUNK_DAYS:-30}"
BACKFILL_LOCK_FILE="${BACKFILL_LOCK_FILE:-/app/data/backfill.lock}"

# ── Lock: exclusion mutua con el cron diario (run_ofelia.sh) y con otra
#    corrida de este mismo script ────────────────────────────────────────────
mkdir -p "$(dirname "${BACKFILL_LOCK_FILE}")"
if [[ -e "${BACKFILL_LOCK_FILE}" ]]; then
  echo "[ERROR] Ya hay un backfill en curso (lock: ${BACKFILL_LOCK_FILE}). Abortando." >&2
  exit 1
fi
echo "$$" > "${BACKFILL_LOCK_FILE}"
trap 'rm -f "${BACKFILL_LOCK_FILE}"' EXIT

BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"

fmt_fecha() {
  # Convierte una fecha ISO (YYYY-MM-DD) al formato esperado por el WS.
  local iso="$1"
  if [[ "${DATE_FMT}" == "dmy" ]]; then
    date -d "${iso}" +'%d/%m/%Y'
  else
    echo "${iso}"
  fi
}

# ── Una llamada SOAP por grupo + deposito + chunk de fecha ───────────────────
call_chunk() {
  local grupo="$1" dep="$2" desde_fmt="$3" hasta_fmt="$4"

  local TMP_REQ="/tmp/soap_request_backfill.$$.${grupo}.${dep}.xml"
  local TMP_HDR="/tmp/soap_headers_backfill.$$.${grupo}.${dep}.txt"
  local TMP_XML="/tmp/soap_response_backfill.$$.${grupo}.${dep}.xml"
  local TMP_JSON="/tmp/ws_json_backfill.$$.${grupo}.${dep}.json"

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
    echo "      <DesdeFec>${desde_fmt}</DesdeFec>"
    echo "      <HastaFec>${hasta_fmt}</HastaFec>"
    echo "      <IdGrupo>${grupo}</IdGrupo>"
    [[ -n "$dep" ]] && echo "      <sDepositos>${dep}</sDepositos>"
    cat <<XML
    </${WS_METHOD}>
  </soap:Body>
</soap:Envelope>
XML
  } > "$TMP_REQ"

  local CURL_ARGS=(
    -sS --http1.1
    --connect-timeout "${CURL_CONNECT_TIMEOUT}" --max-time "${CURL_MAX_TIME}"
    --cert-type P12
    --cert "${CERT_PATH}:${CERT_PASSWORD}"
    --cacert "${CACERT_PATH}"
    -D "$TMP_HDR"
    -H "Content-Type: text/xml; charset=utf-8"
    -H "SOAPAction: \"${WS_SOAP_ACTION}\""
    --data-binary @"$TMP_REQ"
    "${ENDPOINT}"
    -o "$TMP_XML"
  )
  [[ "${CURL_INSECURE}" == "1" ]] && CURL_ARGS=(-k "${CURL_ARGS[@]}")

  if ! curl "${CURL_ARGS[@]}"; then
    echo "[ERROR] curl falló (grupo ${grupo}, deposito ${dep}, ${desde_fmt}-${hasta_fmt})"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 12
  fi

  if [[ ! -s "$TMP_XML" ]]; then
    echo "[ERROR] Respuesta vacía (grupo ${grupo}, deposito ${dep}, ${desde_fmt}-${hasta_fmt})"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 10
  fi

  # Issue #124: mismo chequeo que run_extract_sales_chunk.sh -- una respuesta
  # bien formada puede ser igual un error del WS (no datos). Sin esto, ese
  # chunk se trata como "0 ventas genuinas" y backfill_jobs.py puede marcar
  # el grupo como exitoso sin haber cargado nada.
  local MENS_ERROR
  MENS_ERROR="$(perl -0777 -ne 'print $1 if m{<MensError>(.*?)</MensError>}is' "$TMP_XML" || true)"
  if [[ -n "$(printf '%s' "$MENS_ERROR" | tr -d '[:space:]')" ]]; then
    echo "[ERROR] MensError (grupo ${grupo}, deposito ${dep}, ${desde_fmt}-${hasta_fmt}): ${MENS_ERROR}"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 13
  fi

  local JSON
  JSON="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i'      "$TMP_XML" || true)"
  [[ -z "$JSON" ]] && JSON="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is'                 "$TMP_XML" || true)"

  if [[ -z "$JSON" ]]; then
    echo "[WARN] No se detectó JSON en la respuesta (grupo ${grupo}, deposito ${dep}, ${desde_fmt}-${hasta_fmt})"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 11
  fi

  JSON="$(printf "%s" "$JSON" | sed -e 's/&quot;/"/g' -e 's/&amp;/\&/g' -e 's/&lt;/</g' -e 's/&gt;/>/g')"
  printf '%s' "$JSON" > "$TMP_JSON"

  TMP_JSON_PATH="$TMP_JSON" __FORCED_DEPOSITO="${dep}" python3 "${SELF_DIR}/run_extract_sales_chunk.py"
  local rc=$?

  rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
  return $rc
}

process_chunk_depositos() {
  local grupo="$1" desde_fmt="$2" hasta_fmt="$3"
  local -n _failed_ref=$4   # nameref al array de fallas del grupo

  if [[ "${S_DEPOSITOS}" == *","* ]]; then
    local OLD_IFS="$IFS"; IFS=","
    for dep in ${S_DEPOSITOS}; do
      dep="$(echo "$dep" | tr -d '[:space:]')"
      [[ -z "$dep" ]] && continue
      if ! call_chunk "${grupo}" "${dep}" "${desde_fmt}" "${hasta_fmt}"; then
        _failed_ref+=("grupo=${grupo} dep=${dep} rango=${desde_fmt}..${hasta_fmt}")
      fi
    done
    IFS="$OLD_IFS"
  else
    if ! call_chunk "${grupo}" "${S_DEPOSITOS:-}" "${desde_fmt}" "${hasta_fmt}"; then
      _failed_ref+=("grupo=${grupo} dep=${S_DEPOSITOS:-(ninguno)} rango=${desde_fmt}..${hasta_fmt}")
    fi
  fi
}

# Issue #124 (hardening post-review): merge_y_truncar_stage() es atómico a
# propósito (una sola transacción, igual que el original) -- ver ".claude/
# CONTEXTO.md" (sección #124) para el porqué. truncar_stage() (DELETE solo)
# se usa nada más en el camino donde YA se decidió no mergear, para dejar el
# stage limpio antes del próximo grupo (que no tiene columna de grupo propia).
merge_y_truncar_stage() {
  # Issue #104: excluye SKUs sin fila en articulos (productos dados de baja del
  # catalogo actual, pero con ventas historicas reales que el WS sigue
  # devolviendo) -- sin el filtro, el INSERT completo revienta por la FK
  # fk_ventas_articulo y ninguna fila del grupo se mergea, aunque sean pocos
  # SKUs huerfanos entre millones de filas validas.
  python3 - <<PY
import os, pymysql
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"], port=int(os.environ.get("MYSQL_PORT","3306")),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DB"], autocommit=False, charset="utf8mb4",
)
try:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ventas_historicas (fecha, sku, cantidad, ts_carga, fuente)
            SELECT DATE(s.fecha), TRIM(s.sku),
                   SUM(CAST(s.cantidad AS DECIMAL(12,3))),
                   NOW(6), COALESCE(MIN(s.fuente),'ws_consstockventa')
            FROM ventas_historicas_stage s
            WHERE s.sku IS NOT NULL
              AND s.sku IN (SELECT sku FROM articulos)
            GROUP BY DATE(s.fecha), TRIM(s.sku)
            ON DUPLICATE KEY UPDATE
              cantidad = VALUES(cantidad), ts_carga = VALUES(ts_carga), fuente = VALUES(fuente)
        """)
        cur.execute("DELETE FROM ventas_historicas_stage")
    conn.commit()
finally:
    # Un close() que falla DESPUES de un commit exitoso no debe reportarse
    # como si el merge hubiera fallado (el dato ya quedó escrito en MySQL).
    try:
        conn.close()
    except Exception:
        pass
PY
}

truncar_stage() {
  python3 - <<PY
import os, pymysql
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"], port=int(os.environ.get("MYSQL_PORT","3306")),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DB"], autocommit=False, charset="utf8mb4",
)
try:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ventas_historicas_stage")
    conn.commit()
finally:
    try:
        conn.close()
    except Exception:
        pass
PY
}

# Si truncar_stage() falla (nada garantiza ya que el stage esté limpio para
# el próximo grupo -- no tiene columna de grupo propia, así que sus filas
# se sumarían sin distinguir de dónde vinieron), aborta todo el backfill en
# vez de seguir. Un grupo colgado en "ejecutando" es preferible a un merge
# corrupto en el próximo grupo -- pero por eso el mensaje le dice al
# operador exactamente qué revisar antes de reintentar, no solo "la conexión".
truncar_stage_or_die() {
  local grupo="$1"
  if ! truncar_stage; then
    echo "[ERROR CRÍTICO] Grupo ${grupo}: truncar_stage falló -- no se puede garantizar que ventas_historicas_stage quede limpio para el próximo grupo. Antes de volver a correr el backfill: 1) confirmar que MySQL está accesible, 2) inspeccionar 'SELECT COUNT(*) FROM ventas_historicas_stage' y vaciarla a mano si tiene filas de este grupo."
    exit 1
  fi
}

# ── Loop principal ────────────────────────────────────────────────────────────

GROUPS_LIST="$(python3 "${SELF_DIR}/get_grupos_backfill.py")"
if [[ -z "${GROUPS_LIST}" ]]; then
  echo "[ERROR] No se obtuvo lista de grupos para backfill" >&2
  exit 2
fi

echo "[INFO] Backfill ${BACKFILL_FROM} -> ${BACKFILL_TO} (chunks de ${BACKFILL_CHUNK_DAYS} dias)"
echo "[INFO] Grupos a procesar: ${GROUPS_LIST}"

for G in ${GROUPS_LIST}; do
  echo "[INFO] === Grupo ${G} ==="

  if [[ "$(python3 "${SELF_DIR}/backfill_jobs.py" check "${G}" "${BACKFILL_FROM}" "${BACKFILL_TO}")" == "1" ]]; then
    echo "[INFO] Grupo ${G} ya completado en una corrida anterior para este mismo rango — se saltea."
    continue
  fi

  T0=$(date +%s)
  JOB_ID="$(python3 "${SELF_DIR}/backfill_jobs.py" start "${G}" "${BACKFILL_FROM}" "${BACKFILL_TO}")"
  echo "[INFO] jobs_historial id=${JOB_ID}"

  FAILED_CHUNKS=()
  cur_start_iso="${BACKFILL_FROM}"
  while [[ "${cur_start_iso}" < "${BACKFILL_TO}" || "${cur_start_iso}" == "${BACKFILL_TO}" ]]; do
    cur_end_iso="$(date -d "${cur_start_iso} +$((BACKFILL_CHUNK_DAYS - 1)) days" +%F)"
    [[ "${cur_end_iso}" > "${BACKFILL_TO}" ]] && cur_end_iso="${BACKFILL_TO}"

    desde_fmt="$(fmt_fecha "${cur_start_iso}")"
    hasta_fmt="$(fmt_fecha "${cur_end_iso}")"
    echo "[INFO] Grupo ${G} | chunk ${desde_fmt} -> ${hasta_fmt}"
    process_chunk_depositos "${G}" "${desde_fmt}" "${hasta_fmt}" FAILED_CHUNKS

    cur_start_iso="$(date -d "${cur_end_iso} +1 day" +%F)"
  done

  # Un fallo de merge/truncate se suma a FAILED_CHUNKS -- mismo mecanismo que
  # ya usan los chunks fallidos del WS -- en vez de un exit propio. exit
  # frenaría los 65 grupos por un problema transitorio de UNO solo (el resto
  # ni se intenta), y dejaría la fila de jobs_historial de este grupo colgada
  # en "ejecutando" para siempre (el "end" de abajo nunca se alcanzaría).
  # Sumarlo a FAILED_CHUNKS reusa el "end ... fallido" que ya existe: este
  # grupo se reintenta completo la próxima corrida, los demás siguen.
  #
  # Superset del fix de #104 (que solo chequeaba que merge_y_truncar_stage
  # no explotara): esto ADEMÁS saltea el merge directamente cuando el grupo
  # ya tuvo chunks fallidos del WS -- #104 igual llamaba al merge en ese
  # caso, mezclando datos parciales con completos (la Capa 2 que #124 vino
  # a cerrar).
  if [[ ${#FAILED_CHUNKS[@]} -eq 0 ]]; then
    if ! merge_y_truncar_stage; then
      # Atómico: si esto falló, ni el INSERT ni el DELETE se aplicaron (misma
      # transacción) -- las filas de stage siguen intactas. Igual se trunca
      # después (best-effort) para no contaminar el próximo grupo -- perder
      # la copia local extraída es recuperable re-corriendo el backfill; que
      # el próximo grupo se contamine con estas filas no lo es tan fácil.
      echo "[ERROR] Grupo ${G}: merge_y_truncar_stage falló (ver traceback arriba)."
      FAILED_CHUNKS+=("grupo=${G} merge_y_truncar_stage_error")
      truncar_stage_or_die "${G}"
    fi
  else
    echo "[WARN] Grupo ${G} tuvo ${#FAILED_CHUNKS[@]} chunk(s) fallido(s) -- NO se mergea a ventas_historicas esta corrida (datos parciales pisarían datos completos; se reintenta el grupo completo la próxima vez)."
    truncar_stage_or_die "${G}"
  fi

  DURACION=$(( $(date +%s) - T0 ))
  if [[ ${#FAILED_CHUNKS[@]} -eq 0 ]]; then
    ESTADO="exitoso"
  else
    ESTADO="fallido"
    echo "[WARN] Grupo ${G} terminó con ${#FAILED_CHUNKS[@]} chunk(s) fallido(s) — se reintenta completo en la próxima corrida."
  fi

  printf '%s\n' "${FAILED_CHUNKS[@]}" | python3 "${SELF_DIR}/backfill_jobs.py" end "${JOB_ID}" "${ESTADO}" "${G}" "${BACKFILL_FROM}" "${BACKFILL_TO}" "${DURACION}"

  echo "[INFO] Grupo ${G} -> ${ESTADO} (${DURACION}s)"
done

echo "[INFO] Backfill finalizado."
