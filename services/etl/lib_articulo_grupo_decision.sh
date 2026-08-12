# lib_articulo_grupo_decision.sh -- Issue #121: decide si una corrida de
# run_extract_articulos.sh debe reconstruir articulo_grupo (delete-and-reinsert
# de TODAS las membresias reales + recalculo de grupo_id "principal").
#
# Aislada en su propia funcion pura (sin curl ni MySQL de por medio) para
# poder testear la regla sin tener que levantar el resto del script -- mismo
# motivo por el que lock_backfill.sh vive aparte (Issue #119).
#
# Solo debe reconstruir si la corrida barrio TODOS los grupos (sin override
# GROUPS/GRUPOS puntual, que es un crawl parcial por diseno) Y ningun grupo
# fallo -- reconstruir con datos parciales borraria membresias reales de
# grupos que no llegaron a correr esta vez.
debe_reconstruir_articulo_grupo() {
  local crawl_completo="$1"
  local grupos_fallidos="$2"
  [[ "${crawl_completo}" == "1" && "${grupos_fallidos}" -eq 0 ]]
}
