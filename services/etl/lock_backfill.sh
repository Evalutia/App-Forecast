# lock_backfill.sh -- fuente compartida para run_ofelia.sh y
# run_backfill_ventas.sh (Issue #119).
#
# Antes cada script tenia su propia copia del mecanismo de lock, y la
# exclusion termino siendo unidireccional (run_ofelia.sh solo LEIA el lock,
# nunca lo creaba) sin que nadie lo notara -- exactamente el tipo de bug que
# una segunda copia divergente puede reintroducir en el futuro si alguien
# edita una sin tocar la otra. Se sourcea, no se ejecuta aparte: exec/flock
# corridos dentro de una funcion de bash afectan al shell que la llama (no
# corren en una subshell), asi que el fd 200 queda abierto en el script que
# invoca tomar_lock_backfill, no se pierde al volver de la funcion.
#
# Uso:
#   source "${SELF_DIR}/lock_backfill.sh"
#   if ! tomar_lock_backfill "${BACKFILL_LOCK_FILE}"; then
#     ... rama de "ya hay otro proceso corriendo" ...
#   fi
#
# Limitacion conocida (code-review post-implement): el fd 200 lo heredan los
# procesos hijos (kitchen.sh, y lo que kitchen.sh a su vez ejecute) salvo que
# se cierre a mano -- bash no tiene forma nativa de marcarlo close-on-exec. Si
# algún día un hijo de kitchen.sh sobrevive a la muerte de run_ofelia.sh (un
# proceso colgado, un demonio que algún paso deje vivo sin querer), ese hijo
# se queda con el lock tomado. Diagnóstico si pasa: `fuser
# "${BACKFILL_LOCK_FILE}"` o `lsof "${BACKFILL_LOCK_FILE}"` para encontrar y
# matar el proceso que lo sigue reteniendo.
#
# Issue #141: esto YA NO es "para siempre" para el paso mas propenso a
# colgarse (RUN EXTRACT STOCKXML, un curl SOAP sin timeout hasta ese issue) --
# job_etl_diario.kjb envuelve ese paso puntual con
# `timeout --kill-after=30s 1200s`, asi que un hijo colgado ahi se mata solo
# dentro de una ventana acotada y el fd se libera. La limitacion de fondo
# (bash no puede marcar el fd close-on-exec) sigue existiendo tal cual -- solo
# está acotada para ese paso, no eliminada. Otro paso que llegara a colgarse
# sin su propio timeout volvería a retener el lock indefinidamente.
tomar_lock_backfill() {
  local lock_file="$1"
  mkdir -p "$(dirname "${lock_file}")"
  exec 200>"${lock_file}"
  if ! flock -n 200; then
    return 1
  fi
  # Diagnostico manual (`cat "${lock_file}"`) -- flock en si no deja rastro
  # de quien lo tiene.
  echo "$$" >&200
  return 0
}
