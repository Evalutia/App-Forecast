#!/usr/bin/env bash
# run_etl_daily.sh - Wrapper diario para extracción SOAP -> staging
# Requiere: run_extract_sales_chunk.sh en el mismo directorio
set -euo pipefail

# --- Parametría obligatoria (viene del job KJB) ---
WS_URL="${WS_URL:?WS_URL requerido (ej: http://200.125.29.194:81)}"
DATE_FMT="${DATE_FMT:-dmy}"                # dmy | ymd
ID_EMPRESA="${ID_EMPRESA:-1}"
S_DEPOSITOS="${S_DEPOSITOS:-}"
GROUPS="${GROUPS:?GROUPS requerido (ej: \"75\" or \"75 201\")} "

# MySQL
MYSQL_HOST="${MYSQL_HOST:?MYSQL_HOST requerido}"
MYSQL_DB="${MYSQL_DB:?MYSQL_DB requerido}"
MYSQL_USER="${MYSQL_USER:?MYSQL_USER requerido}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:?MYSQL_PASSWORD requerido}"
MYSQL_PORT="${MYSQL_PORT:-3306}"

# Opcionales (si los pasás desde el job, se usan tal cual)
FORCE_START="${FORCE_START:-}"   # formato según DATE_FMT (dmy => dd/mm/yyyy, ymd => yyyy-mm-dd)
FORCE_END="${FORCE_END:-}"

# --- Derivar rango si no viene forzado ---
fmt_date() {
  local iso="$1"
  if [[ "${DATE_FMT}" == "dmy" ]]; then
    date -d "${iso}" +'%d/%m/%Y'
  else
    date -d "${iso}" +'%Y-%m-%d'
  fi
}

if [[ -n "${FORCE_START}" && -n "${FORCE_END}" ]]; then
  CHUNK_START="${FORCE_START}"
  CHUNK_END="${FORCE_END}"
else
  # Últimos 7 días (ayer inclusive)
  ISO_END="$(date -d 'yesterday' +%F)"
  ISO_START="$(date -d "${ISO_END} -6 days" +%F)"
  CHUNK_START="$(fmt_date "${ISO_START}")"
  CHUNK_END="$(fmt_date "${ISO_END}")"
fi

# --- Echo de control ---
echo "[DAILY] WS_URL=${WS_URL}"
echo "[DAILY] DATE_FMT=${DATE_FMT}  Window: ${CHUNK_START} -> ${CHUNK_END}"
echo "[DAILY] ID_EMPRESA=${ID_EMPRESA}  S_DEPOSITOS=${S_DEPOSITOS}"
echo "[DAILY] GROUPS=${GROUPS}"
echo "[DAILY] MySQL=${MYSQL_USER}@${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DB}"

# --- Validaciones mínimas ---
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACT_SH="${SELF_DIR}/run_extract_sales_chunk.sh"
if [[ ! -x "${EXTRACT_SH}" ]]; then
  echo "[DAILY][ERROR] No encuentro ejecutable: ${EXTRACT_SH}" >&2
  exit 2
fi

# Asegura que pipefail afecte a pipelines con tee en este shell
set -o pipefail

rc=0
for G in ${GROUPS}; do
  LOG="/tmp/etl_group_${G}.log"
  echo "[DAILY] === Grupo ${G} === (log: ${LOG})"
  # Ejecutamos en subshell PERO chequeamos el exit code de ese subshell,
  # no el de 'tee'. Con 'pipefail' activo, si el subshell falla, el pipeline
  # devuelve código != 0 y entramos al branch 'if ! ...; then'.
  if ! (
    set -euo pipefail
    DATE_FMT="${DATE_FMT}" \
    WS_URL="${WS_URL}" \
    WS_METHOD="ConsStockVenta" \
    WS_SOAP_ACTION="http://tempuri.org/VSServicioWeb/SWNadWeb/ConsStockVenta" \
    CHUNK_START="${CHUNK_START}" \
    CHUNK_END="${CHUNK_END}" \
    ID_EMPRESA="${ID_EMPRESA}" \
    ID_GRUPO="${G}" \
    S_DEPOSITOS="${S_DEPOSITOS}" \
    MYSQL_HOST="${MYSQL_HOST}" \
    MYSQL_DB="${MYSQL_DB}" \
    MYSQL_USER="${MYSQL_USER}" \
    MYSQL_PASSWORD="${MYSQL_PASSWORD}" \
    MYSQL_PORT="${MYSQL_PORT}" \
    "${EXTRACT_SH}"
  ) 2>&1 | tee "${LOG}"; then
    echo "[DAILY][ERROR] Grupo ${G} FALLÓ (ver ${LOG})" | tee -a "${LOG}"
    rc=1
  else
    echo "[DAILY] Grupo ${G} OK" | tee -a "${LOG}"
  fi
done

if [[ ${rc} -ne 0 ]]; then
  echo "[DAILY][ERROR] Hubo fallas en uno o más grupos (ver /tmp/etl_group_*.log)" >&2
  exit ${rc}
fi

echo "[DAILY] Extracción completada OK para todos los grupos."
