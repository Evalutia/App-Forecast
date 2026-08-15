#!/usr/bin/env bash
set -euo pipefail

# Issue #111: la corrida nocturna registra su propio estado en jobs_historial
# (tipo_job='etl', detalle.subtipo='cron_diario'). Antes solo dejaban rastro
# los pasos CALC finales, asi que cualquier falla anterior -- truncate del
# staging, extraccion SOAP, merges -- moria en silencio: la unica huella
# quedaba en `docker logs` de ofelia, que se pierde al recrear el contenedor
# (por eso las noches del 24-27/07/2026 quedaron sin diagnostico posible).
#
# El bookkeeping nunca puede voltear la corrida: cada llamada se aisla y su
# fallo solo se loguea. El ETL manda; el registro es observabilidad.

CRON_JOBS="${CRON_JOBS:-/app/services/etl/cron_jobs.py}"
# Overridable solo para poder testear la orquestacion sin Pentaho (ver
# tests/test_run_ofelia.py). En produccion siempre es el kitchen.sh real.
KITCHEN="${KITCHEN:-/opt/pentaho/data-integration/kitchen.sh}"
# Issue #102/#136: el mensual de elegibilidad econometrica vive aparte del
# .kjb (no pasa por Pentaho), pero se encadena al final de esta corrida --
# ver el bloque despues de KITCHEN mas abajo.
EVAL_MENSUAL_SH="${EVAL_MENSUAL_SH:-/app/services/etl/run_eval_elegibilidad_mensual.sh}"

# Issue #132: si este script aborta ANTES de poder registrar `start` (ej. el
# chequeo de LOCK_BACKFILL_SH de mas abajo, que fue justo lo que paso el
# 2026-08-11 con un cron que murio en 346ms sin dejar mas huella que el log
# efimero de Docker), la observabilidad que trajo #111 se pierde exactamente
# en la clase de fallo que #111 vino a resolver. Este trap es la red de
# seguridad: si el script termina con codigo != 0 y todavia no llegamos a
# intentar `start` (ETL_ARRANCADO sigue en 0), deja un registro con causa
# antes de morir. ETL_ARRANCADO se pone en 1 apenas se intenta `start` (haya
# salido bien o mal) -- de ahi en mas cualquier fallo es "durante" la
# corrida, no "antes de arrancarla", y ya tiene su propio manejo (`end`, o el
# exit code que preserva la ultima linea del script).
#
# Se registra ANTES de la validacion de #139 de mas abajo (WS_URL/
# ID_EMPRESA/S_DEPOSITOS) a proposito -- integrando ambos issues se detecto
# que, en el orden original, un WS_URL faltante disparaba el `:?missing` de
# bash y terminaba el script ANTES de que este trap existiera, asi que esa
# falla puntual quedaba otra vez sin registrar en jobs_historial pese a ser
# exactamente el tipo de abort temprano que #132 vino a resolver.
OFELIA_ABORT_MOTIVO=""
ETL_ARRANCADO=0
_registrar_abort_temprano() {
  local rc=$?
  [[ "${ETL_ARRANCADO}" == "1" ]] && return
  [[ "${rc}" -eq 0 ]] && return
  local motivo="${OFELIA_ABORT_MOTIVO:-fallo inesperado antes de arrancar el ETL (rc=${rc}, ultimo comando: ${BASH_COMMAND})}"
  echo "[OFELIA][ERROR] corrida abortada antes de arrancar el ETL: ${motivo}" >&2
  python3 "${CRON_JOBS}" abort "${motivo}" >/dev/null 2>&1 \
    || echo "[OFELIA][WARN] no se pudo registrar el abort temprano en jobs_historial." >&2
}
trap _registrar_abort_temprano EXIT

# Issue #139: WS_URL, ID_EMPRESA y S_DEPOSITOS salen de .env (env_file del
# servicio `etl` en docker-compose.yml), igual que el resto de la
# configuracion real (MYSQL_*, CERT_*) y que el patron ya establecido en
# run_backfill_ventas.sh / run_extract_sales_chunk.sh -- este era el unico
# script del cron automatico que los tenia hardcodeados en el `-param:` de
# kitchen.sh. Dos formas en que eso rompia en silencio: (a) un deposito nuevo
# que abre el cliente quedaba afuera de la extraccion sin que nada lo
# señalara, la planilla seguia calculando sobre datos incompletos; (b) si el
# proveedor del WS cambiaba la IP, habia que editar este script Y reconstruir
# la imagen para levantarlo de nuevo. Se valida ACA, antes de tomar el lock o
# tocar Pentaho, para fallar rapido con un mensaje claro en vez de que
# kitchen.sh reciba "-param:WS_URL=" vacio y falle mucho mas adelante con un
# error criptico de Pentaho.
: "${WS_URL:?missing}"
: "${ID_EMPRESA:?missing}"
: "${S_DEPOSITOS:?missing}"

# Issue #140: infra/sql/*.sql no se aplica solo contra un volumen de MySQL
# que ya existe -- migraciones de #86 y #102 quedaron meses sin aplicarse en
# produccion, descubiertas recien cuando un job fallaba a mitad de camino
# con "table doesn't exist". Se detecta ACA, mismo criterio que WS_URL de
# arriba (fallar rapido con causa clara antes de tocar Pentaho), en vez de
# dejar que un paso a mitad del .kjb reviente con un error criptico. Modo
# --check-only: nunca aplica DDL sola, solo lee schema_migrations -- aplicar
# una migracion pendiente sigue siendo, siempre, un paso manual
# (services/etl/apply_migrations.sh sin argumentos).
APPLY_MIGRATIONS_SH="${APPLY_MIGRATIONS_SH:-/app/services/etl/apply_migrations.sh}"
MIGRACIONES_PENDIENTES="$(bash "${APPLY_MIGRATIONS_SH}" --check-only 2>&1)" || {
  # Code review: no asumir que un exit != 0 es SIEMPRE "hay pendientes" -- el
  # mismo chequeo tambien falla si MySQL esta caido, las credenciales estan
  # mal, o el script no existe en esa ruta. Relaya la salida real (que ya
  # distingue el caso) en vez de una causa inventada que mandaria a
  # correr apply_migrations.sh a mano por un motivo que no es el real.
  OFELIA_ABORT_MOTIVO="chequeo de migraciones de infra/sql/ (apply_migrations.sh --check-only) fallo: $(echo "${MIGRACIONES_PENDIENTES}" | tr '\n' ' ')"
  echo "[OFELIA][ERROR] ${OFELIA_ABORT_MOTIVO}" >&2
  exit 1
}

# Issue #136: MySQL en reposo ya usa ~55% de los 3.7GB de la maquina, y
# Pentaho nunca tuvo su heap ajustado -- el default de fabrica de spoon.sh
# (de donde kitchen.sh delega) es "-Xms1024m -Xmx2048m". El diario SOLO, sin
# el mensual superpuesto, ya corria al limite. Los pasos pesados de este job
# (extraccion, calculo) corren como subprocesos python3 aparte, no dentro
# del heap de Kettle, asi que 768m es generoso para lo que la JVM en si
# necesita -- validado con una corrida real contra produccion antes de
# confiar en el valor. spoon.sh ya lee esta variable de entorno si esta
# seteada, no hace falta tocar el binario de Pentaho.
export PENTAHO_DI_JAVA_OPTIONS="${PENTAHO_DI_JAVA_OPTIONS:--Xms256m -Xmx768m}"

# Issue #44/#119: si hay un backfill historico corriendo (run_backfill_ventas.sh),
# se saltea esta corrida del daily en vez de competir por ventas_historicas_stage
# y por conexiones al WS. Se recupera sola la noche siguiente.
#
# Issue #119: antes esto solo LEIA el lock (exclusion unidireccional) -- si el
# backfill arrancaba mientras el cron ya estaba corriendo, no habia nada que
# lo detuviera, y los dos terminaban pisandose el mismo staging. Ahora ofelia
# TOMA el mismo lock (flock, atomico, via lock_backfill.sh -- fuente
# compartida con run_backfill_ventas.sh, ver ese archivo para el porqué de
# no duplicarlo) para toda la corrida, no solo para chequear: el que llega
# primero gana, el otro se saltea/aborta.
BACKFILL_LOCK_FILE="${BACKFILL_LOCK_FILE:-/app/data/backfill.lock}"
# Ruta absoluta, NO relativa a la ubicacion de este script: el Dockerfile lo
# copia a /usr/local/bin/ pero lock_backfill.sh solo existe bajo /app, asi que
# resolverlo "junto a mi" no funciona en produccion y `set -e` aborta
# la corrida entera (paso el 2026-08-11: el cron nocturno no corrio). Misma
# convencion que CRON_JOBS de arriba, overridable para los tests.
LOCK_BACKFILL_SH="${LOCK_BACKFILL_SH:-/app/services/etl/lock_backfill.sh}"
if [[ ! -f "${LOCK_BACKFILL_SH}" ]]; then
  OFELIA_ABORT_MOTIVO="no encuentro ${LOCK_BACKFILL_SH} -- abortando sin tocar nada."
  echo "[OFELIA][ERROR] ${OFELIA_ABORT_MOTIVO}" >&2
  exit 1
fi
source "${LOCK_BACKFILL_SH}"
if ! tomar_lock_backfill "${BACKFILL_LOCK_FILE}"; then
  echo "[OFELIA] Backfill en curso (${BACKFILL_LOCK_FILE}) — se saltea la corrida diaria de esta noche."
  # Issue #132: antes esto se descartaba con >/dev/null -- `skip` imprime su
  # propio job_id (mismo patron que `start`), y sin capturarlo no habia forma
  # de despues adjuntarle el chequeo de atraso (`stale`) a ESA fila. Una
  # noche salteada quedaba con estado='exitoso' (ver cron_jobs.py) e
  # invisible para `stale`, indistinguible de una noche buena.
  SKIP_JOB_ID="$(python3 "${CRON_JOBS}" skip "backfill en curso (${BACKFILL_LOCK_FILE})" || true)"
  if [[ "${SKIP_JOB_ID}" =~ ^[0-9]+$ ]]; then
    python3 "${CRON_JOBS}" stale "${SKIP_JOB_ID}" || true
  else
    echo "[OFELIA][WARN] no se pudo registrar la noche salteada en jobs_historial." >&2
    python3 "${CRON_JOBS}" stale - || true
  fi
  exit 0
fi

# Solo stdout alimenta JOB_ID (la sustitucion de comandos no captura stderr),
# asi que los avisos del script -- ej. corridas zombi cerradas -- siguen
# llegando al log de ofelia en vez de perderse en /dev/null.
JOB_ID="$(python3 "${CRON_JOBS}" start || true)"
if [[ ! "${JOB_ID}" =~ ^[0-9]+$ ]]; then
  # Sin id valido no se intenta cerrar nada: un id adivinado de un mensaje de
  # error actualizaria la fila equivocada de jobs_historial.
  echo "[OFELIA][WARN] no se pudo registrar el inicio en jobs_historial; la corrida sigue igual." >&2
  JOB_ID=""
fi
# A partir de aca cualquier fallo es "durante" la corrida (tiene su propia
# fila y su propio manejo), no un abort temprano sin explicacion -- se
# desarma la red de seguridad del trap de arriba.
ETL_ARRANCADO=1
T0=${SECONDS}

Y=$(date -d "yesterday" +%d/%m/%Y)
# Mismo "ayer" que arriba, en ISO -- se lo pasamos explicito a `coherencia`
# en vez de dejar que lo recalcule sola despues de KITCHEN. Si una corrida
# alguna vez cruzara la medianoche, dos "yesterday" calculados en momentos
# distintos podrian discrepar y el chequeo mediria el dia equivocado.
Y_ISO=$(date -d "yesterday" +%Y-%m-%d)

# Issue #132: atraso del dato "al entrar a la noche", ANTES de que kitchen
# tenga chance de arreglarlo -- por eso corre aca y no despues. Sale con
# codigo 1 cuando hay atraso (no es un fallo del chequeo), asi que se ignora
# el codigo a proposito: es informativo y no debe abortar la corrida que
# justamente viene a arreglarlo. Si JOB_ID es valido, el resultado tambien
# queda escrito en detalle.atraso de esa fila (antes solo se imprimia a
# stdout, invisible fuera del log efimero de Docker) -- sobrevive al `end`
# de mas abajo porque `end` ahora hace merge del detalle, no reemplazo.
if [[ -n "${JOB_ID}" ]]; then
  python3 "${CRON_JOBS}" stale "${JOB_ID}" || true
else
  python3 "${CRON_JOBS}" stale - || true
fi

set +e
"${KITCHEN}" \
  "-file=/app/services/etl/job_etl_diario.kjb" -level=Basic \
  "-param:WS_URL=${WS_URL}" "-param:DATE_FMT=dmy" \
  "-param:ID_EMPRESA=${ID_EMPRESA}" "-param:S_DEPOSITOS=${S_DEPOSITOS}" \
  "-param:MYSQL_HOST=mysql" "-param:MYSQL_DB=evalutia" \
  "-param:MYSQL_USER=evalutia" "-param:MYSQL_PASSWORD=evalutia" "-param:MYSQL_PORT=3306" \
  "-param:PREDICT_PERIODS=2" "-param:PREDICT_MODEL_SET=classic" "-param:PREDICT_RESAMPLE_RULE=QS" "-param:PREDICT_VERSION=mvp-001" \
  "-param:FORCE_START=$Y" "-param:FORCE_END=$Y" \
  "-param:CERT_PATH=${CERT_PATH:-}" "-param:CACERT_PATH=${CACERT_PATH:-}" "-param:CERT_PASSWORD=${CERT_PASSWORD:-}"
RC=$?
set -e

if [[ -n "${JOB_ID}" ]]; then
  python3 "${CRON_JOBS}" end "${JOB_ID}" "${RC}" "$((SECONDS - T0))" >/dev/null \
    || echo "[OFELIA][WARN] no se pudo cerrar el registro ${JOB_ID} en jobs_historial." >&2

  # Issue #115: coherencia venta-vs-stock del dia que se acaba de cargar.
  # Va DESPUES de `end` a proposito -- `end` hace merge del detalle (Issue
  # #132), pero igual conviene mantener el orden: si `end` no llegara a
  # correr (ETL murio de una forma que ni siquiera deja `RC` utilizable)
  # esto tampoco deberia. Igual que `stale`, es informativo: si el chequeo
  # mismo esta roto (DB abajo, consulta rota) no debe frenar una corrida que
  # ya termino.
  python3 "${CRON_JOBS}" coherencia "${JOB_ID}" "${Y_ISO}" || true
fi

# Issue #136: el mensual de elegibilidad econometrica se encadena ACA, al
# final del diario, en vez de por un horario fijo en ofelia.ini -- el diario
# viene creciendo (2h09->2h44 en dos semanas) y un horario fijo vuelve a
# quedar corto tarde o temprano. Solo corre el dia 1 de cada mes, y SOLO si
# el diario de esa noche termino bien: es una medicion de tendencia (walk-
# forward sobre historico ya cargado, no depende del dato de hoy en
# particular) -- perderse un mes no cambia el resultado de forma material, y
# encadenar un job pesado justo despues de una corrida que ya fallo (por
# memoria o cualquier otro motivo) es la peor combinacion posible para la
# maquina. Bookkeeping propio (jobs_historial, tipo_job='eval_elegibilidad')
# via ml/run_eval_elegibilidad_dry_run.py -- no hace falta duplicarlo aca, y
# su resultado no debe alterar el exit code de esta corrida diaria.
if [[ "${RC}" -eq 0 && "$(date +%d)" == "01" ]]; then
  echo "[OFELIA] Dia 1 del mes, diario OK -> corriendo mensual de elegibilidad econometrica."
  "${EVAL_MENSUAL_SH}" || echo "[OFELIA][WARN] el mensual de elegibilidad fallo -- ver jobs_historial (tipo_job='eval_elegibilidad')." >&2
fi

exit "${RC}"
