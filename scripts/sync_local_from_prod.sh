#!/usr/bin/env bash
# sync_local_from_prod.sh — Sincroniza datos de producción a MySQL local (Issue #38).
#
# Transporte vía S3 (no conexión directa a producción -- versión anterior de
# este script asumía eso, reemplazada en la sesión 2026-07-13, ver
# .claude/CONTEXTO.md): el dump se genera y sube a S3 en la VM
# (scripts/prod_dump_to_s3.sh), este script solo baja el último dump y lo
# restaura en el MySQL local. No incluye `usuarios` (credenciales reales de
# clientes) ni tablas de staging.
#
# Requiere AWS CLI configurado localmente con un perfil de acceso acotado al
# bucket (s3:GetObject/s3:ListBucket sobre BUCKET_NAME).
#
# Uso:
#   BUCKET_NAME=evalutia-prod-sync-xxxx AWS_PROFILE=evalutia-sync \
#     ./scripts/sync_local_from_prod.sh

set -euo pipefail

# Evita que Git Bash / MSYS2 traduzca rutas estilo /tmp/... a rutas de Windows
# antes de pasarlas al contenedor (rompe el path dentro del container Linux).
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

: "${BUCKET_NAME:?Falta BUCKET_NAME}"
: "${AWS_PROFILE:?Falta AWS_PROFILE}"
: "${MYSQL_DB:=evalutia}"
: "${MYSQL_USER:=evalutia}"
: "${MYSQL_PASSWORD:=evalutia}"

TABLAS=(articulos grupos ventas_historicas ventas_mensuales stock_diario
        stock_resumen_365 articulos_elegibilidad_econometrico predicciones
        jobs_historial planilla_ventas_calculada planilla_sugerencias)

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SELF_DIR}"


# Ojo: NO usar mktemp -t (genera rutas estilo /tmp/...) ni una ruta absoluta
# construida a mano -- aws.exe en Windows es un binario nativo, no MSYS, y no
# resuelve bien un path con "/" (termina buscando "..\..\..\..\c\Users\...").
# Un nombre de archivo relativo (ya estamos parados en SELF_DIR) no tiene
# ninguna barra que traducir, evita el problema por completo.
TMP_DUMP=".sync_tmp_dump.sql.gz"

echo "[SYNC] Bajando dump desde s3://${BUCKET_NAME}/latest.sql.gz"
aws s3 cp "s3://${BUCKET_NAME}/latest.sql.gz" "${TMP_DUMP}" --profile "${AWS_PROFILE}" --no-progress
echo "[SYNC] Dump bajado: $(du -h "${TMP_DUMP}" | cut -f1)"

echo "[SYNC] Vaciando tablas locales: ${TABLAS[*]}"
docker compose exec -T \
  -e MYSQL_DB="${MYSQL_DB}" \
  -e MYSQL_USER="${MYSQL_USER}" \
  -e MYSQL_PASSWORD="${MYSQL_PASSWORD}" \
  -e TABLAS_STR="${TABLAS[*]}" \
  mysql sh -c '
    set -e
    TRUNCATE_SQL="SET FOREIGN_KEY_CHECKS=0;"
    for t in $TABLAS_STR; do
      TRUNCATE_SQL="$TRUNCATE_SQL TRUNCATE TABLE $t;"
    done
    TRUNCATE_SQL="$TRUNCATE_SQL SET FOREIGN_KEY_CHECKS=1;"
    mysql --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" "$MYSQL_DB" -e "$TRUNCATE_SQL"
  '

echo "[SYNC] Restaurando dump..."
gunzip -c "${TMP_DUMP}" | {
  echo "SET FOREIGN_KEY_CHECKS=0;"
  cat
  echo "SET FOREIGN_KEY_CHECKS=1;"
} | docker compose exec -T \
  -e MYSQL_DB="${MYSQL_DB}" \
  -e MYSQL_USER="${MYSQL_USER}" \
  -e MYSQL_PASSWORD="${MYSQL_PASSWORD}" \
  mysql sh -c 'mysql --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" "$MYSQL_DB"'

rm -f "${TMP_DUMP}"
echo "[SYNC] Listo. Datos locales sincronizados con producción para: ${TABLAS[*]}"
