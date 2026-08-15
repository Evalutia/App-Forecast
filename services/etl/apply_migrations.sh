#!/usr/bin/env bash
set -euo pipefail
# apply_migrations.sh - Issue #140: infra/sql/*.sql no se aplica solo contra
# un volumen de MySQL que ya existe (docker-entrypoint-initdb.d solo corre en
# un volumen vacio) y no habia ningun registro de que migraciones estaban
# aplicadas en cada entorno -- migraciones de #86 y #102 quedaron meses sin
# aplicarse en produccion, descubiertas recien cuando un job fallaba a mitad
# de camino con "table doesn't exist".
#
# Dos modos:
#   apply_migrations.sh              -> aplica las pendientes, en orden
#   apply_migrations.sh --check-only -> NUNCA ejecuta SQL de infra/sql/, solo
#                                        detecta pendientes (exit 1 si hay)
#
# Uso manual (agregar una migracion nueva):
#   1. Crear infra/sql/NN-descripcion.sql (numero siguiente al mas alto que
#      exista), terminando con la linea de auto-registro (ver el resto de
#      infra/sql/ como plantilla):
#        INSERT IGNORE INTO schema_migrations (filename) VALUES ('NN-descripcion.sql');
#   2. docker compose exec etl bash /app/services/etl/apply_migrations.sh
#      (local y produccion, cada entorno por separado -- no hay sync automatico)
#
# No hace falta correrlo en un volumen recien creado: docker-entrypoint-initdb.d
# ya corrio todos los archivos, y cada uno se auto-registro al final (ver la
# linea de arriba en cada archivo de infra/sql/) -- schema_migrations queda
# poblada igual, sin este script de por medio.

: "${MYSQL_HOST:=mysql}"
: "${MYSQL_PORT:=3306}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Overridable solo para poder testear contra un directorio sintetico de
# archivos .sql sin tocar infra/sql/ real (ver tests/test_apply_migrations.py).
SQL_DIR="${MIGRATIONS_SQL_DIR:-$(cd "${SELF_DIR}/../../infra/sql" && pwd)}"

# Code review: match estricto -- un typo (--check-onyl, --dry-run) no debe
# caer en silencio al modo de aplicar. Este script promete no correr DDL
# sola fuera de una invocacion explicita; un argumento no reconocido rompe
# esa garantia si se interpreta como "aplicar" por default.
CHECK_ONLY=0
case "${1:-}" in
  "") ;;
  --check-only) CHECK_ONLY=1 ;;
  *)
    echo "[apply_migrations][ERROR] argumento no reconocido: '${1}' (uso: apply_migrations.sh [--check-only])" >&2
    exit 2
    ;;
esac

# Code review: MYSQL_PWD en vez de -p<password> -- el argumento -p queda
# visible en texto plano para cualquiera con acceso a `ps aux`/`docker top`
# mientras el proceso corre (el chequeo --check-only se invoca ~diario desde
# run_ofelia.sh).
export MYSQL_PWD="${MYSQL_PASSWORD}"
_mysql() {
  mysql --protocol=TCP -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_USER}" "$@"
}

# Bootstrap defensivo: la tabla de tracking tiene que existir para poder
# consultarla, incluso contra un entorno donde 01-init.sql corrio hace tiempo
# (antes de #140) y nunca la creo. Idempotente, no pisa filas existentes.
_mysql "${MYSQL_DB}" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   VARCHAR(255) NOT NULL,
  applied_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SQL

APPLIED="$(_mysql -N -B "${MYSQL_DB}" -e "SELECT filename FROM schema_migrations")"

PENDING=()
for f in "${SQL_DIR}"/*.sql; do
  base="$(basename "${f}")"
  if ! grep -qxF "${base}" <<< "${APPLIED}"; then
    PENDING+=("${f}")
  fi
done
# Orden lexicografico por nombre de archivo -- mismo orden que usa
# docker-entrypoint-initdb.d en un volumen nuevo.
IFS=$'\n' PENDING=($(sort <<< "${PENDING[*]}")); unset IFS

if [[ ${#PENDING[@]} -eq 0 ]]; then
  echo "[apply_migrations] OK: no hay migraciones pendientes."
  exit 0
fi

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  echo "[apply_migrations] ATENCION: hay ${#PENDING[@]} migracion(es) pendiente(s):" >&2
  for f in "${PENDING[@]}"; do
    echo "  - $(basename "${f}")" >&2
  done
  exit 1
fi

for f in "${PENDING[@]}"; do
  base="$(basename "${f}")"
  echo "[apply_migrations] aplicando ${base}..."
  if ! _mysql "${MYSQL_DB}" < "${f}"; then
    echo "[apply_migrations][ERROR] fallo aplicando ${base} -- corte, no se sigue con las siguientes." >&2
    exit 1
  fi
  # Backstop de defensa en profundidad: si el archivo se auto-registro (la
  # convencion desde #140), esto es un no-op (INSERT IGNORE). Si algun autor
  # futuro se olvida la linea de auto-registro, esto igual deja el registro
  # correcto -- no depende ciegamente de que cada archivo cumpla la convencion.
  _mysql "${MYSQL_DB}" -e "INSERT IGNORE INTO schema_migrations (filename) VALUES ('${base}')"
  echo "[apply_migrations] ${base} aplicado y registrado."
done

echo "[apply_migrations] listo: ${#PENDING[@]} migracion(es) aplicada(s)."
