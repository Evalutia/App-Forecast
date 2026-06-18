#!/usr/bin/env bash
# sync_local_from_prod.sh — Sincroniza datos de producción a MySQL local (Issue #38).
#
# Solo sincroniza las 6 tablas relevantes a la Planilla de Reposición, no la base
# completa (evita traer `usuarios` con hashes reales, `jobs_historial`, `predicciones`
# que no hacen falta para este caso de uso).
#
# Requiere que tu IP esté habilitada para conectarse a MySQL de producción
# (pedido aparte al admin del hosting — no lo resuelve este script).
#
# Corre el dump y el restore DENTRO del contenedor `mysql` local (que ya tiene
# mysqldump/mysql cliente), así no depende de tener esas herramientas instaladas
# en el host. El contenedor sale a internet con la IP pública de tu máquina,
# igual que si corrieras mysqldump directo desde la terminal.
#
# Uso:
#   PROD_MYSQL_HOST=... PROD_MYSQL_USER=... PROD_MYSQL_PASSWORD=... PROD_MYSQL_DB=... \
#     ./scripts/sync_local_from_prod.sh
#
# Variables opcionales: PROD_MYSQL_PORT (default 3306)

set -euo pipefail

# Evita que Git Bash / MSYS2 traduzca rutas estilo /tmp/... a rutas de Windows
# antes de pasarlas al contenedor (rompe el path dentro del container Linux).
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

TABLAS=(articulos ventas_historicas stock_diario ventas_mensuales planilla_ventas_calculada planilla_sugerencias)

: "${PROD_MYSQL_HOST:?Falta PROD_MYSQL_HOST}"
: "${PROD_MYSQL_PORT:=3306}"
: "${PROD_MYSQL_USER:?Falta PROD_MYSQL_USER}"
: "${PROD_MYSQL_PASSWORD:?Falta PROD_MYSQL_PASSWORD}"
: "${PROD_MYSQL_DB:?Falta PROD_MYSQL_DB}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SELF_DIR}"

echo "[SYNC] Tablas a sincronizar: ${TABLAS[*]}"
echo "[SYNC] Origen: ${PROD_MYSQL_HOST}:${PROD_MYSQL_PORT}/${PROD_MYSQL_DB}"

DUMP_PATH_IN_CONTAINER="/tmp/prod_sync_$(date +%s).sql"

echo "[SYNC] Dumpeando desde producción..."
docker compose exec -T \
  -e PROD_MYSQL_HOST="${PROD_MYSQL_HOST}" \
  -e PROD_MYSQL_PORT="${PROD_MYSQL_PORT}" \
  -e PROD_MYSQL_USER="${PROD_MYSQL_USER}" \
  -e PROD_MYSQL_PASSWORD="${PROD_MYSQL_PASSWORD}" \
  -e PROD_MYSQL_DB="${PROD_MYSQL_DB}" \
  -e DUMP_PATH="${DUMP_PATH_IN_CONTAINER}" \
  -e TABLAS_STR="${TABLAS[*]}" \
  mysql sh -c '
    set -e
    mysqldump \
      --host="$PROD_MYSQL_HOST" --port="$PROD_MYSQL_PORT" \
      --user="$PROD_MYSQL_USER" --password="$PROD_MYSQL_PASSWORD" \
      --single-transaction --quick --no-create-info --skip-triggers --no-tablespaces \
      "$PROD_MYSQL_DB" $TABLAS_STR > "$DUMP_PATH"
    echo "[SYNC] Dump OK: $(wc -l < "$DUMP_PATH") lineas"
  '

echo "[SYNC] Vaciando tablas locales y restaurando..."
docker compose exec -T \
  -e DUMP_PATH="${DUMP_PATH_IN_CONTAINER}" \
  -e TABLAS_STR="${TABLAS[*]}" \
  -e MYSQL_DB="${MYSQL_DB:-evalutia}" \
  -e MYSQL_USER="${MYSQL_USER:-evalutia}" \
  -e MYSQL_PASSWORD="${MYSQL_PASSWORD:-evalutia}" \
  mysql sh -c '
    set -e
    TRUNCATE_SQL="SET FOREIGN_KEY_CHECKS=0;"
    for t in $TABLAS_STR; do
      TRUNCATE_SQL="$TRUNCATE_SQL TRUNCATE TABLE $t;"
    done
    TRUNCATE_SQL="$TRUNCATE_SQL SET FOREIGN_KEY_CHECKS=1;"
    mysql --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" "$MYSQL_DB" -e "$TRUNCATE_SQL"

    {
      echo "SET FOREIGN_KEY_CHECKS=0;"
      cat "$DUMP_PATH"
      echo "SET FOREIGN_KEY_CHECKS=1;"
    } | mysql --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" "$MYSQL_DB"

    rm -f "$DUMP_PATH"
    echo "[SYNC] Restore OK"
  '

echo "[SYNC] Listo. Datos locales sincronizados con producción para: ${TABLAS[*]}"
