#!/usr/bin/env bash
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SELF_DIR}/lib_articulo_grupo_decision.sh"

: "${WS_URL:?missing}"    # sigue siendo obligatorio
: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"
: "${CERT_PATH:?missing}"    # Issue #51: mTLS obligatorio, sin fallback a HTTP
: "${CACERT_PATH:?missing}"
: "${CERT_PASSWORD:?missing}"

DATE_FMT="${DATE_FMT:-dmy}"
WS_NS="${WS_NS:-http://tempuri.org/VSServicioWeb/SWNadWeb}"
WS_METHOD="${WS_METHOD:-ConsArticulosWeb}"
WS_SOAP_ACTION="${WS_SOAP_ACTION:-http://tempuri.org/VSServicioWeb/SWNadWeb/ConsArticulosWeb}"

ID_EMPRESA="${ID_EMPRESA:-1}"
ID_GRUPO="${ID_GRUPO:-}"
GRUPOS="${GRUPOS:-${GROUPS:-}}"  # acepta GRUPOS o GROUPS (compatibilidad)
CANTREG="${CANTREG:-20000}"
ARTICULO_DESDE="${ARTICULO_DESDE:-}"
# Issue #121: escape hatch operativo para forzar un pull COMPLETO (sin
# filtro de fecha) de todos los grupos aunque es_grupo_nuevo diga que no
# hace falta -- necesario una vez despues de este deploy, porque la
# migracion sembro articulo_grupo desde el grupo_id que cada articulo ya
# tenia (para no dejar el filtro en cero mientras tanto), y eso hace que
# es_grupo_nuevo devuelva "no" para casi todos los grupos ya conocidos.
# Sin este flag, la membresia MULTIPLE real (el motivo de este issue) nunca
# se terminaria de descubrir para el catalogo existente -- solo para grupos
# genuinamente nuevos de aca en mas.
FORCE_FULL_PULL="${FORCE_FULL_PULL:-0}"

CURL_INSECURE="${CURL_INSECURE:-0}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-20}"
CURL_MAX_TIME="${CURL_MAX_TIME:-120}"

# Leer args opcionales
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

# Si vino --grupos/--id-grupo (o GRUPOS/ID_GRUPO por env) explicito, se empuja a
# GROUPS para que get_grupos.py lo tome como override puntual (Issue #42) en vez
# de consultar la tabla grupos.
#
# OVERRIDE_GRUPOS_ACTIVO, no inspeccionar "${GROUPS}" mas abajo (issue #121,
# bug real encontrado corriendo esto en produccion): $GROUPS es una variable
# ESPECIAL de bash (la lista de group-ids del proceso, ver `help groups` /
# POSIX), no una env var libre -- como root vale literalmente "0", asi que
# `[[ -n "${GROUPS:-}" ]]` da verdadero SIEMPRE, override o no. No se filtra
# a subprocesos (no es una env var real, `printenv GROUPS` no la ve), asi
# que get_grupos.py nunca sufrio esto -- el problema era solo este chequeo.
OVERRIDE_GRUPOS_ACTIVO=0
if [[ -n "${GRUPOS}" && "${GRUPOS}" != "0" ]]; then
  export GROUPS="${GRUPOS}"
  OVERRIDE_GRUPOS_ACTIVO=1
elif [[ -n "${ID_GRUPO}" && "${ID_GRUPO}" != "0" ]]; then
  export GROUPS="${ID_GRUPO}"
  OVERRIDE_GRUPOS_ACTIVO=1
fi

# Derivar CHUNK_START si no está provisto (compatibilidad, ventana incremental)
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

# Normalizar FechaDesde incremental a ISO dateTime (YYYY-MM-DDT00:00:00)
FechaDate="$(python3 - "$CHUNK_START" <<'PY'
import sys,re,datetime as dt
raw=sys.argv[1] if len(sys.argv)>1 else ""
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
FECHA_DESDE_INCREMENTAL="${FechaDate}T00:00:00"

# Grupos nunca extraidos (sin articulos cargados todavia): pull completo, sin
# filtro de fecha, en vez de la ventana incremental de 7 dias -- si no, sus SKUs
# nunca entrarian a `articulos` y el backfill de ventas (#44) fallaria por FK.
# (Issue #42)
FECHA_DESDE_FULL_PULL="2000-01-01T00:00:00"

# Endpoint robusto: si WS_URL ya trae el .asmx, no duplicar
BASE="$(printf '%s' "${WS_URL}" | sed -E 's,/+$,,')"
if [[ "$BASE" =~ /VsWebProduccion/SwNadWeb\.asmx$ ]]; then
  ENDPOINT="$BASE"
else
  ENDPOINT="${BASE}/VsWebProduccion/SwNadWeb.asmx"
fi

# Un grupo es "nuevo" si nunca produjo ninguna membresia (articulo_grupo), no
# si nunca fue elegido como grupo PRINCIPAL de ningun articulo (issue #121):
# un grupo real pero siempre secundario tendria articulos.grupo_id=otro_grupo
# para siempre, y con el chequeo viejo (contra articulos.grupo_id) haria pull
# completo sin filtro de fecha en cada corrida, para siempre.
es_grupo_nuevo() {
  local g="$1"
  python3 - "$g" <<'PY'
import os, sys, pymysql
g = sys.argv[1]
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DB"],
    charset="utf8mb4",
)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM articulo_grupo WHERE grupo_id=%s", (g,))
        n = cur.fetchone()[0]
    print("1" if n == 0 else "0")
finally:
    conn.close()
PY
}

# Una llamada SOAP por grupo (no por lista combinada): es la unica forma de
# saber a que grupo pertenece cada articulo devuelto, ya que no se confirmo que
# el SOAP incluya el grupo en la respuesta (Issue #41/#42).
call_for_grupo() {
  local grupo="$1"
  local fecha_desde_iso="$2"

  local TMP_REQ="/tmp/soap_request_articulos.${grupo}.$$.$RANDOM.xml"
  local TMP_HDR="/tmp/soap_headers_articulos.${grupo}.$$.$RANDOM.txt"
  local TMP_XML="/tmp/soap_response_articulos.${grupo}.$$.$RANDOM.xml"
  local TMP_PAYLOAD="/tmp/ws_payload_articulos.${grupo}.$$.$RANDOM.txt"

  trap "cp -f '${TMP_REQ}' /tmp/last_soap_request_articulos.xml 2>/dev/null || true; \
        cp -f '${TMP_HDR}' /tmp/soap_headers_articulos.txt 2>/dev/null || true; \
        cp -f '${TMP_XML}' /tmp/soap_response_articulos.xml 2>/dev/null || true; \
        [[ -s '${TMP_PAYLOAD}' ]] && cp -f '${TMP_PAYLOAD}' /tmp/last_ws_payload_articulos.txt 2>/dev/null || true; \
        rm -f '${TMP_REQ}' '${TMP_HDR}' '${TMP_XML}' '${TMP_PAYLOAD}'" RETURN

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

    echo "      <FechaDesde>${fecha_desde_iso}</FechaDesde>"
    echo "      <Grupos>${grupo}</Grupos>"

    cat <<XML
      <IdEmpresa>${ID_EMPRESA}</IdEmpresa>
    </${WS_METHOD}>
  </soap:Body>
</soap:Envelope>
XML
  } > "$TMP_REQ"

  echo "[INFO] Grupo ${grupo} | FechaDesde: ${fecha_desde_iso} | Cuantos: ${CANTREG}"

  CURL_ARGS=(
    -sS --http1.1
    --connect-timeout "${CURL_CONNECT_TIMEOUT}"
    --max-time "${CURL_MAX_TIME}"
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
  if [[ "${CURL_INSECURE}" == "1" ]]; then
    CURL_ARGS=(-k "${CURL_ARGS[@]}")
  fi

  if ! curl "${CURL_ARGS[@]}"; then
    echo "[ERROR] curl falló contra ${ENDPOINT} (grupo ${grupo})"
    return 12
  fi

  if [[ ! -s "$TMP_XML" ]]; then
    echo "[ERROR] Respuesta vacía de ${WS_METHOD} (grupo ${grupo})"
    return 10
  fi

  local MENSERR
  MENSERR="$(perl -0777 -ne 'print $1 if m{<MensError>([\s\S]*?)</MensError>}i' "$TMP_XML" || true)"
  if [[ -n "${MENSERR//[[:space:]]/}" ]]; then
    echo "[WARN] MensError en ${WS_METHOD} (grupo ${grupo}): ${MENSERR}"
    echo "[WARN] No se insertan artículos por MensError. Salida OK."
    return 0
  fi

  local PAYLOAD
  PAYLOAD="$(perl -0777 -ne "print \$1 if m{<${WS_METHOD}Result>([\\s\\S]*?)</${WS_METHOD}Result>}i" "$TMP_XML" || true)"
  [[ -z "$PAYLOAD" ]] && PAYLOAD="$(perl -0777 -ne 'print $1 if m{<string[^>]*>([\s\S]*?)</string>}i' "$TMP_XML" || true)"
  [[ -z "$PAYLOAD" ]] && PAYLOAD="$(perl -0777 -ne 'print $1 if m{<!\[CDATA\[(.*?)\]\]>}is' "$TMP_XML" || true)"

  if [[ -z "$PAYLOAD" ]]; then
    echo "[WARN] No se detectó payload en ${WS_METHOD}Result (grupo ${grupo})"
    echo "[DUMP] Inicio de body (1200 chars):"
    head -c 1200 "$TMP_XML"; echo
    return 11
  fi

  printf '%s' "$PAYLOAD" > "$TMP_PAYLOAD"

  TMP_PAYLOAD_PATH="$TMP_PAYLOAD" __FORCED_GRUPO="${grupo}" python3 /app/services/etl/run_extract_articulos.py
}

# Issue #121: articulo_grupo se reconstruye por completo (delete-and-reinsert)
# al terminar el loop -- pero eso solo tiene sentido si esta corrida barrio
# TODOS los grupos. Un override puntual (GROUPS/GRUPOS/--grupos, pensado para
# reprocesar un grupo suelto en debug, ver comentario de get_grupos.py) es un
# crawl parcial por diseno: reconstruir ahi borraria membresias reales de los
# grupos que quedaron afuera de este run.
CRAWL_COMPLETO=1
if [[ "${OVERRIDE_GRUPOS_ACTIVO}" == "1" ]]; then
  CRAWL_COMPLETO=0
fi

GROUPS_LIST="$(python3 /app/services/etl/get_grupos.py)"
if [[ -z "${GROUPS_LIST}" ]]; then
  echo "[ERROR] No se obtuvo lista de grupos (ni override ni tabla grupos)" >&2
  exit 2
fi

echo "[INFO] Endpoint   : ${ENDPOINT}"
echo "[INFO] SOAPAction : ${WS_SOAP_ACTION}"
echo "[INFO] Grupos a procesar: ${GROUPS_LIST}"

if [[ "${CRAWL_COMPLETO}" == "1" ]]; then
  # Limpio el residuo de una corrida anterior fallida antes de arrancar esta,
  # para que el finalize de mas abajo (si esta corrida sale entera bien) nunca
  # mezcle membresias de dos noches distintas.
  python3 - <<'PY'
import os, pymysql
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DB"],
    charset="utf8mb4",
)
try:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE articulo_grupo_stage")
    conn.commit()
finally:
    conn.close()
PY
else
  echo "[INFO] Override de grupos activo (${GROUPS}) -> crawl parcial, no se toca articulo_grupo_stage/articulo_grupo"
fi

GRUPOS_FALLIDOS=0
# Grupos cuyo pull COMPLETO (sin filtro de fecha) de esta corrida tuvo exito
# -- son los unicos para los que finalize_articulo_grupos.py puede reemplazar
# la membresia entera (issue #121). Un grupo ya conocido usa la ventana
# incremental de 7 dias, asi que su stage de esta noche es solo un delta, NO
# la foto completa -- pasarlo igual haria que el finalize borre membresias
# reales que simplemente no cambiaron esta semana.
GRUPOS_FULL_PULL_CSV=""
for G in ${GROUPS_LIST}; do
  echo "[INFO] === Grupo ${G} ==="
  NUEVO="$(es_grupo_nuevo "${G}")"
  if [[ "${NUEVO}" == "1" || "${FORCE_FULL_PULL}" == "1" ]]; then
    echo "[INFO] Grupo ${G}: pull completo (sin filtro de fecha)$([[ "${NUEVO}" != "1" ]] && echo " -- forzado por FORCE_FULL_PULL")"
    FECHA_DESDE_EFECTIVA="${FECHA_DESDE_FULL_PULL}"
  else
    FECHA_DESDE_EFECTIVA="${FECHA_DESDE_INCREMENTAL}"
  fi
  if call_for_grupo "${G}" "${FECHA_DESDE_EFECTIVA}"; then
    if [[ "${NUEVO}" == "1" || "${FORCE_FULL_PULL}" == "1" ]]; then
      GRUPOS_FULL_PULL_CSV="${GRUPOS_FULL_PULL_CSV:+${GRUPOS_FULL_PULL_CSV},}${G}"
    fi
  else
    echo "[WARN] Grupo ${G} FALLÓ, continuando con el siguiente..."
    GRUPOS_FALLIDOS=$((GRUPOS_FALLIDOS + 1))
  fi
done

if debe_reconstruir_articulo_grupo "${CRAWL_COMPLETO}" "${GRUPOS_FALLIDOS}"; then
  echo "[INFO] Actualizando articulo_grupo (pull completo esta corrida: ${GRUPOS_FULL_PULL_CSV:-ninguno})"
  python3 /app/services/etl/finalize_articulo_grupos.py "${GRUPOS_FULL_PULL_CSV}"
elif [[ "${CRAWL_COMPLETO}" == "1" ]]; then
  echo "[WARN] ${GRUPOS_FALLIDOS} grupo(s) fallaron esta corrida -- articulo_grupo NO se toca (queda con los datos de la ultima corrida completa)"
fi
