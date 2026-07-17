#!/usr/bin/env bash
# prod_dump_to_s3.sh — Vuelca las tablas relevantes de produccion a un dump
# comprimido y lo sube a S3 (Issue #38). Corre EN LA VM, no en local.
#
# No incluye `usuarios` (credenciales reales de clientes) ni las tablas de
# staging (*_stage, transitorias, las trunca el ETL cada noche) -- ver
# .claude/CONTEXTO.md, sesion 2026-07-13, para el detalle de la decision.
#
# Requiere AWS CLI configurado en la VM con permisos de escritura al bucket
# (perfil o IAM role de la instancia con s3:PutObject/s3:ListBucket sobre
# BUCKET_NAME). No resuelve ese acceso -- ver el mismo registro de CONTEXTO.md.
#
# Uso (desde /opt/evalutia en la VM):
#   BUCKET_NAME=evalutia-prod-sync-xxxx MYSQL_PASSWORD=... ./scripts/prod_dump_to_s3.sh

set -euo pipefail

: "${BUCKET_NAME:?Falta BUCKET_NAME}"
: "${MYSQL_DB:=evalutia}"
: "${MYSQL_USER:=evalutia}"
: "${MYSQL_PASSWORD:?Falta MYSQL_PASSWORD}"

TABLAS=(articulos grupos ventas_historicas ventas_mensuales stock_diario
        stock_resumen_365 articulos_elegibilidad_econometrico predicciones
        jobs_historial planilla_ventas_calculada planilla_sugerencias)

TS="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="/tmp/evalutia_sync_${TS}.sql.gz"

echo "[SYNC] Tablas a volcar: ${TABLAS[*]}"

docker compose exec -T mysql sh -c "
  mysqldump --user='${MYSQL_USER}' --password='${MYSQL_PASSWORD}' \
    --single-transaction --quick --no-create-info --skip-triggers --no-tablespaces \
    '${MYSQL_DB}' ${TABLAS[*]}
" | gzip > "${DUMP_FILE}"

echo "[SYNC] Dump comprimido: $(du -h "${DUMP_FILE}" | cut -f1) en ${DUMP_FILE}"

echo "[SYNC] Subiendo a s3://${BUCKET_NAME}/latest.sql.gz"
aws s3 cp "${DUMP_FILE}" "s3://${BUCKET_NAME}/latest.sql.gz"

rm -f "${DUMP_FILE}"
echo "[SYNC] Listo."
