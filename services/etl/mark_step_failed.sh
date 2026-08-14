#!/usr/bin/env bash
# mark_step_failed.sh - paso comun de las ramas "fallo pero sigo" del job
# ETL diario (job_etl_diario.kjb, Issue #131).
#
# Antes de #131, el unico paso del .kjb con una rama de fallo real era
# "RUN EXTRACT VENTAS" (Issue #124), y su rama insertaba un SQL crudo
# directo en jobs_historial. Con #131 replicando el mismo criterio al resto
# de los pasos, repetir ese SQL/CDATA en cada entrada hubiera significado
# 9 copias casi identicas dentro del .kjb -- este script las centraliza.
#
# Cada llamada deja DOS rastros:
#   1) Toca ETL_FAIL_MARKER -- un archivo de "algo fallo esta corrida" que
#      vive solo mientras dura la corrida (lo crea/borra "RESET FAIL
#      MARKER", el segundo entry del job, justo despues de START). El
#      ultimo paso del .kjb ("CHECK RUN RESULT") lo revisa antes de decidir
#      si termina en SUCCESS o en FAILURE -- ESO es lo que de verdad cambia
#      el exit code de kitchen.sh (y por lo tanto el estado que
#      run_ofelia.sh graba en la fila OFICIAL de jobs_historial). Sin este
#      marker, un paso podia fallar y la cadena igual desembocaba en
#      SUCCESS, que resetea el resultado interno de Kettle -- la causa raiz
#      de #131.
#   2) Inserta una fila de auditoria propia en jobs_historial (via
#      `cron_jobs.py mark_step_failed`) con el nombre del paso y el motivo.
#      Es una fila desconectada del job_id de la corrida oficial a
#      proposito -- este script corre DENTRO de Kettle, que no conoce ese
#      job_id (vive en run_ofelia.sh, afuera del .kjb).
#
# Uso (desde una entrada SHELL del .kjb):
#   /bin/bash /app/services/etl/mark_step_failed.sh "<paso>" "<motivo>" "<ruta del marker>"
#
# El 3er argumento (hallazgo de /code-review, no acortar a 2): Kettle NO
# exporta sus parametros de job como variables de entorno del shell hijo --
# "${ETL_FAIL_MARKER}" en RESET FAIL MARKER/CHECK RUN RESULT es sustitucion
# de TEXTO que hace el propio motor de Kettle antes de correr el script
# (insertScript=Y), un mecanismo completamente distinto del $ETL_FAIL_MARKER
# que este script leeria de su propio entorno si no se lo pasaran. Sin
# pasarlo explicito, los dos caminos solo coinciden hoy porque comparten el
# mismo valor default por casualidad -- si alguna vez se cambia el parametro
# del job (para aislar una corrida de test, por ejemplo), CHECK RUN RESULT
# miraria una ruta y este script tocaria otra, rompiendo el gate en silencio.
set -uo pipefail

PASO="${1:?uso: mark_step_failed.sh <paso> <motivo> [marker]}"
MOTIVO="${2:-sin detalle}"
ETL_FAIL_MARKER="${3:-${ETL_FAIL_MARKER:-/tmp/etl_diario_run_failed.flag}}"

echo "[MARK_FAILED] ${PASO}: ${MOTIVO}" >&2

touch "${ETL_FAIL_MARKER}" \
  || echo "[MARK_FAILED][WARN] no se pudo tocar el marker '${ETL_FAIL_MARKER}' -- la corrida podria terminar en SUCCESS pese a este fallo." >&2

python3 /app/services/etl/cron_jobs.py mark_step_failed "${PASO}" "${MOTIVO}" >/dev/null \
  || echo "[MARK_FAILED][WARN] no se pudo dejar auditoria en jobs_historial para '${PASO}'." >&2

# Siempre exit 0: esta es la rama "fallo pero sigo" -- el propio hecho de
# haber llegado aca YA significa que un paso anterior fallo. Que este script
# tambien fallara no debe impedir que la cadena reconverja al siguiente paso.
exit 0
