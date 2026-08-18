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
#
# Issue #133: SALES_FORCE_START/SALES_FORCE_END (parametros propios de
# run_ofelia.sh/job_etl_diario.kjb, ventana de 7 dias) tienen prioridad
# sobre FORCE_START/FORCE_END -- esos siguen siendo de un solo dia,
# compartidos con RUN EXTRACT STOCKXML (ver run_extract_stockxml.sh), y
# forzar ventas a un solo dia todas las noches era justamente el bug de
# #133: una noche perdida no se reponia sola. FORCE_START/FORCE_END se deja
# como fallback para invocaciones manuales que no conozcan las variables
# nuevas -- mismo comportamiento de antes.
if [ -z "${CHUNK_START:-}" ] || [ -z "${CHUNK_END:-}" ]; then
  if [ -n "${SALES_FORCE_START:-}" ] && [ -n "${SALES_FORCE_END:-}" ]; then
    CHUNK_START="${SALES_FORCE_START}"
    CHUNK_END="${SALES_FORCE_END}"
  elif [ -n "${FORCE_START:-}" ] && [ -n "${FORCE_END:-}" ]; then
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

echo "[INFO] Sales window: ${CHUNK_START} -> ${CHUNK_END}"

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
    --cert-type P12 \
    --cert "${CERT_PATH}:${CERT_PASSWORD}" \
    --cacert "${CACERT_PATH}" \
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

  # Issue #124: una respuesta bien formada puede ser igual un error del WS (no
  # datos). Mismo chequeo que ya hace run_extract_articulos.py -- ventas/stock
  # nunca lo miraban, y ese silencio es lo que deja escribir cero sobre ventas
  # reales sin ningún rastro. Se chequea ANTES de buscar el resultado normal.
  local MENS_ERROR
  MENS_ERROR="$(perl -0777 -ne 'print $1 if m{<MensError>(.*?)</MensError>}is' "$TMP_XML" || true)"
  if [[ -n "$(printf '%s' "$MENS_ERROR" | tr -d '[:space:]')" ]]; then
    echo "[ERROR] MensError en ConsStockVenta (grupo ${grupo}, deposito ${dep}): ${MENS_ERROR}"
    rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
    return 13
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

  # Issue #125: el desescape de entities HTML se movio a Python
  # (run_extract_sales_chunk.py, via html.unescape) -- el sed de aca tenia
  # el orden quot/amp/lt/gt, que desescapaba de mas (&amp;lt; -> &lt; -> <
  # en vez de quedarse en &lt;). Se escribe el JSON tal cual vino del WS.
  printf '%s' "$JSON" > "$TMP_JSON"
  [[ -s "$TMP_JSON" ]] && cp -f "$TMP_JSON" /tmp/last_ws_json_sales.json 2>/dev/null || true

  export TMP_JSON_PATH="$TMP_JSON"
  export __FORCED_DEPOSITO="${dep}"
  # Issue #114: se propaga el grupo para que la fila quede trazable (de que
  # llamada vino) -- no participa de la clave unica, solo es diagnostico.
  export __FORCED_GRUPO="${grupo}"
  python3 /app/services/etl/run_extract_sales_chunk.py
  # Issue #124: capturar el rc ACA, ya. Esta funcion se invoca como
  # `call_for_grupo_deposito ... || ...` desde process_grupo, y con `set -e`
  # eso suspende errexit para TODA la funcion (no solo el ultimo comando) --
  # sin este capture explicito, el "rm -f" de abajo (que casi siempre da 0)
  # termina siendo el codigo de salida real de la funcion, y un crash de
  # run_extract_sales_chunk.py (ej. JSON ilegible) queda invisible. Confirmado
  # reproduciendo un JSONDecodeError real: sin este fix, el script terminaba
  # en exit 0 pese al traceback.
  local py_rc=$?
  unset __FORCED_DEPOSITO __FORCED_GRUPO

  rm -f "$TMP_REQ" "$TMP_HDR" "$TMP_XML" "$TMP_JSON"
  return "$py_rc"
}

# Issue #157: marca/desmarca en ventas_grupos_fallidos_run, para que el
# MERGE STAGING -> VENTAS del .kjb sepa que grupo excluir. Un WARN, no
# aborta -- mismo criterio que el resto de este script: un fallo puntual
# de bookkeeping no debe tumbar la extraccion real de los demas grupos.
# Un solo helper para las dos direcciones (mismo patron que
# truncar_stage_or_die() en run_backfill_ventas.sh, que colapso un guard
# duplicado equivalente) -- marcar/desmarcar solo difieren en el
# subcomando y en si el WARN aclara "podria incluirlo" o "podria
# excluirlo", lo demas es identico.
set_grupo_estado() {
  local subcomando="$1" verbo="$2" grupo="$3" consecuencia="$4"
  python3 /app/services/etl/grupos_fallidos_run.py "${subcomando}" "${grupo}" \
    || echo "[WARN] no se pudo ${verbo} grupo ${grupo} en ventas_grupos_fallidos_run -- ${consecuencia}." >&2
}

marcar_grupo_fallido() {
  set_grupo_estado marcar registrar "$1" "el merge de hoy podria incluirlo igual pese al fallo"
}

desmarcar_grupo_exitoso() {
  set_grupo_estado desmarcar desmarcar "$1" "el merge de hoy podria excluirlo pese a haber salido bien (se autocorrige la proxima corrida, que resetea la tabla)"
}

# Issue #157 (hallazgo de /code-review): marcar solo DESPUES de un fallo
# dejaba un hueco real -- si el contenedor moria a mitad de este grupo
# (OOM, timeout) entre un deposito que ya habia escrito filas en stage y
# el siguiente, el grupo nunca llegaba a marcarse, y el merge lo hubiera
# tratado como exitoso pese a tener datos parciales. Ahora se marca
# PESIMISTA al entrar (antes de intentar nada) y se desmarca al final SOLO
# si TODOS sus depositos salieron bien -- una muerte a mitad de camino deja
# la marca puesta, que es exactamente lo que se quiere. El timing es
# seguro: el MERGE corre recien despues de que este script termina del
# todo, nunca en paralelo con el, asi que un desmarque tardio no puede
# pisarse con una lectura en curso. Efecto lateral bueno: marcar_grupo_fallido
# ahora se llama una sola vez por grupo (antes, una vez por CADA deposito
# fallido del mismo grupo -- llamadas redundantes bajo una falla amplia).
process_grupo() {
  local grupo="$1"
  marcar_grupo_fallido "${grupo}"
  local grupo_ok=1

  if [[ "${S_DEPOSITOS}" == *","* ]]; then
    local OLD_IFS="$IFS"
    IFS=","
    for dep in ${S_DEPOSITOS}; do
      dep="$(echo "$dep" | tr -d '[:space:]')"
      [[ -z "$dep" ]] && continue
      echo "[INFO] Ejecutando ConsStockVenta para grupo ${grupo}, deposito: ${dep}"
      if ! call_for_grupo_deposito "${grupo}" "${dep}"; then
        echo "[WARN] Fallo en grupo ${grupo} deposito ${dep}, continuando con el siguiente..."
        FAILED_GRUPO_DEPOSITO+=("grupo=${grupo} dep=${dep}")
        grupo_ok=0
      fi
    done
    IFS="$OLD_IFS"
  else
    if ! call_for_grupo_deposito "${grupo}" "${S_DEPOSITOS:-}"; then
      echo "[WARN] Fallo en grupo ${grupo}, continuando con el siguiente..."
      FAILED_GRUPO_DEPOSITO+=("grupo=${grupo} dep=${S_DEPOSITOS:-(ninguno)}")
      grupo_ok=0
    fi
  fi

  # Bug real encontrado corriendo los tests (no solo teorico): con
  # `set -e` activo, el ultimo comando ejecutado dentro de una funcion se
  # convierte en su codigo de retorno -- `[[ "${grupo_ok}" == "1" ]]` sola
  # (sin && desmarcar) devuelve 1 cuando el grupo fallo, y ese 1 se filtra
  # como resultado de `process_grupo "${G}"` en el loop de mas abajo, que
  # no esta protegido por if/&&/||. Eso cortaba el script ahi mismo, antes
  # de llegar al resumen final de "grupo(s)/deposito(s) fallaron" -- el
  # `return 0` explicito evita que un grupo fallido (estado ya manejado,
  # no un error del script) se confunda con un error real.
  if [[ "${grupo_ok}" == "1" ]]; then
    desmarcar_grupo_exitoso "${grupo}"
  fi
  return 0
}

# Issue #157 (hallazgo de /code-review): se vacia ANTES de CUALQUIER otra
# cosa -- incluso antes de resolver GROUPS_LIST. Si esto quedara despues
# del chequeo de GROUPS_LIST y esa lista viniera vacia, el script
# terminaria (exit 2) sin haber tocado la tabla, dejando entradas de la
# noche anterior -- exactamente el estado stale que este reset existe para
# evitar. ventas_grupos_fallidos_run es el estado de "esta corrida", una
# entrada vieja no debe sobrevivir. A diferencia de marcar/desmarcar (WARN,
# per-grupo, un fallo puntual no debe tumbar a los demas), este SI es
# fatal -- mismo criterio que TRUNCATE VENTAS_STAGE al principio del .kjb
# ("riesgo real de corrupcion silenciosa"): si el reset falla y la corrida
# sigue igual, un grupo que fallo ANOCHE queda marcado para siempre, y el
# merge de HOY excluiria de mas -- datos genuinamente buenos de un grupo
# que esta noche si funciono, descartados en silencio. Abortar aca es
# seguro: staging arranca vacio (lo trunca el .kjb) y el merge de mas
# abajo no encuentra filas nuevas, asi que ventas_historicas simplemente
# conserva el valor de ayer, degradado pero util -- mismo principio que el
# resto de este archivo.
if ! python3 /app/services/etl/grupos_fallidos_run.py reset; then
  echo "[ERROR] no se pudo vaciar ventas_grupos_fallidos_run -- abortando antes de extraer nada, para no arriesgar que el merge excluya de mas por una entrada vieja." >&2
  exit 3
fi

GROUPS_LIST="$(python3 /app/services/etl/get_grupos.py)"
if [[ -z "${GROUPS_LIST}" ]]; then
  echo "[ERROR] No se obtuvo lista de grupos (ni override ni tabla grupos)" >&2
  exit 2
fi

echo "[INFO] Grupos a procesar: ${GROUPS_LIST}"

# Issue #124: antes, un fallo de cualquier grupo/deposito quedaba en un
# "[WARN] ... continuando" y el script SIEMPRE terminaba en exit 0 -- el
# caller (Pentaho, o un humano) no tenia forma de saber que faltaron datos.
FAILED_GRUPO_DEPOSITO=()

for G in ${GROUPS_LIST}; do
  echo "[INFO] === Grupo ${G} ==="
  process_grupo "${G}"
done

if [[ ${#FAILED_GRUPO_DEPOSITO[@]} -gt 0 ]]; then
  echo "[ERROR] ${#FAILED_GRUPO_DEPOSITO[@]} grupo(s)/deposito(s) fallaron esta corrida:"
  printf '  %s\n' "${FAILED_GRUPO_DEPOSITO[@]}"
  exit 1
fi
