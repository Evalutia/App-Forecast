"""
Tests de apply_migrations.sh (Issue #140).

infra/sql/*.sql no se aplicaba solo contra un volumen de MySQL que ya
existia -- docker-entrypoint-initdb.d solo corre en un volumen vacio, y no
habia ningun registro de que migraciones estaban aplicadas en cada entorno.
Migraciones de #86 y #102 quedaron meses sin aplicarse en produccion,
descubiertas recien cuando un job fallaba a mitad de camino con "table
doesn't exist".

No usa infra/sql/ real (que ya esta todo aplicado en cualquier entorno de
test) -- arma un directorio sintetico de archivos .sql y apunta el script
ahi via MIGRATIONS_SQL_DIR, contra una tabla schema_migrations REAL (mismo
patron de integracion que el resto de services/etl/tests/, con
pytest.skip si no hay MySQL disponible).
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "apply_migrations.sh"
BASH = shutil.which("bash")
MYSQL_CLIENT = shutil.which("mysql")

pytestmark = [
    pytest.mark.skipif(BASH is None, reason="bash no disponible"),
    pytest.mark.skipif(MYSQL_CLIENT is None, reason="cliente mysql no disponible en este entorno"),
]

REQUIRED_ENV = {
    "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
    "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
    "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
    "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
    "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
}


def _try_connect():
    import pymysql

    try:
        return pymysql.connect(
            host=REQUIRED_ENV["MYSQL_HOST"],
            port=int(REQUIRED_ENV["MYSQL_PORT"]),
            user=REQUIRED_ENV["MYSQL_USER"],
            password=REQUIRED_ENV["MYSQL_PASSWORD"],
            database=REQUIRED_ENV["MYSQL_DB"],
            autocommit=False,
            charset="utf8mb4",
        )
    except pymysql.err.OperationalError:
        pytest.skip("Sin conexion a MySQL disponible -- test de integracion se salta.")


def _escribir(path: Path, contenido: str) -> Path:
    path.write_text(textwrap.dedent(contenido).lstrip(), encoding="utf-8")
    return path


@pytest.fixture
def sql_dir(tmp_path):
    """
    Dos migraciones sinteticas: la primera crea una tabla de prueba, la
    segunda solo se auto-registra (simula una migracion "de datos" sin DDL).
    Nombres prefijados __TEST140__ para poder limpiarlos de schema_migrations
    sin arriesgar tocar filas reales.
    """
    d = tmp_path / "sql"
    d.mkdir()
    _escribir(d / "01-__TEST140__crea_tabla.sql", """
        CREATE TABLE IF NOT EXISTS __test140_dummy__ (id INT PRIMARY KEY);
        INSERT IGNORE INTO schema_migrations (filename) VALUES ('01-__TEST140__crea_tabla.sql');
        """)
    _escribir(d / "02-__TEST140__solo_registro.sql", """
        SELECT 1;
        INSERT IGNORE INTO schema_migrations (filename) VALUES ('02-__TEST140__solo_registro.sql');
        """)
    return d


def _limpiar(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS __test140_dummy__")
        cur.execute("DELETE FROM schema_migrations WHERE filename LIKE '%__TEST140__%'")
    conn.commit()


def _correr(sql_dir, *args):
    env = {**os.environ, **REQUIRED_ENV, "MIGRATIONS_SQL_DIR": str(sql_dir)}
    return subprocess.run(
        [BASH, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30,
    )


def test_check_only_detecta_pendientes_y_no_ejecuta_nada(sql_dir):
    conn = _try_connect()
    try:
        _limpiar(conn)

        proc = _correr(sql_dir, "--check-only")

        assert proc.returncode != 0
        assert "01-__TEST140__crea_tabla.sql" in proc.stderr
        assert "02-__TEST140__solo_registro.sql" in proc.stderr

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = '__test140_dummy__'"
            )
            assert cur.fetchone()[0] == 0, "--check-only no debe ejecutar ningun archivo"
    finally:
        _limpiar(conn)
        conn.close()


def test_apply_aplica_pendientes_y_las_registra(sql_dir):
    conn = _try_connect()
    try:
        _limpiar(conn)

        proc = _correr(sql_dir)
        assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = '__test140_dummy__'"
            )
            assert cur.fetchone()[0] == 1

            cur.execute(
                "SELECT filename FROM schema_migrations WHERE filename LIKE '%__TEST140__%' ORDER BY filename"
            )
            registrados = [r[0] for r in cur.fetchall()]
            assert registrados == [
                "01-__TEST140__crea_tabla.sql",
                "02-__TEST140__solo_registro.sql",
            ]
    finally:
        _limpiar(conn)
        conn.close()


def test_re_correr_apply_es_no_op_una_vez_todo_aplicado(sql_dir):
    """AC de #140: aplicable sin re-ejecutar lo ya aplicado."""
    conn = _try_connect()
    try:
        _limpiar(conn)
        _correr(sql_dir)  # primera corrida real

        proc = _correr(sql_dir)  # segunda: no deberia re-ejecutar nada

        assert proc.returncode == 0
        assert "no hay migraciones pendientes" in proc.stdout.lower()
    finally:
        _limpiar(conn)
        conn.close()


def test_argumento_no_reconocido_no_cae_en_modo_aplicar(sql_dir):
    """
    Code review de #140: un typo (--check-onyl, --dry-run) no debe caer en
    silencio al modo de aplicar -- este script promete nunca correr DDL sola
    fuera de una invocacion explicita sin argumentos.
    """
    conn = _try_connect()
    try:
        _limpiar(conn)

        proc = _correr(sql_dir, "--check-onyl")

        assert proc.returncode != 0
        assert "no reconocido" in proc.stderr.lower()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = '__test140_dummy__'"
            )
            assert cur.fetchone()[0] == 0, "un argumento invalido no debe ejecutar nada"
    finally:
        _limpiar(conn)
        conn.close()


def test_check_only_ok_cuando_no_hay_pendientes(sql_dir):
    conn = _try_connect()
    try:
        _limpiar(conn)
        _correr(sql_dir)

        proc = _correr(sql_dir, "--check-only")

        assert proc.returncode == 0
        assert "no hay migraciones pendientes" in proc.stdout.lower()
    finally:
        _limpiar(conn)
        conn.close()
