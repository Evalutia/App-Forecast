"""
Tests de grupos_fallidos_run.py (Issue #157) -- registro efimero de que
grupos de ConsStockVenta fallaron en la extraccion de ventas de la corrida
de esta noche. `run_extract_sales_chunk.sh` llama `reset` al arrancar y
`marcar <grupo>` en cada fallo; el paso "MERGE STAGING -> VENTAS" del .kjb
llama `listar` para armar el motivo dinamico, y su propio INSERT excluye
via NOT EXISTS los grupos que esta tabla registra (ver
test_job_etl_diario_merge_ventas.py para ese lado).

Integracion contra MySQL real con pytest.skip si no hay DB, mismo patron
que el resto de los tests de este directorio.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "grupos_fallidos_run.py"


def _try_connect():
    import pymysql

    try:
        port = int(os.environ.get("MYSQL_PORT", "3307"))
    except ValueError as e:
        pytest.fail(f"MYSQL_PORT invalido: {e}")

    try:
        return pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            port=port,
            user=os.environ.get("MYSQL_USER", "evalutia"),
            password=os.environ.get("MYSQL_PASSWORD", "evalutia"),
            database=os.environ.get("MYSQL_DB", "evalutia"),
            autocommit=False,
            charset="utf8mb4",
        )
    except pymysql.err.OperationalError:
        pytest.skip("Sin conexion a MySQL disponible -- test de integracion se salta.")


@pytest.fixture
def conn():
    c = _try_connect()
    with c.cursor() as cur:
        cur.execute("DELETE FROM ventas_grupos_fallidos_run")
    c.commit()

    yield c

    with c.cursor() as cur:
        cur.execute("DELETE FROM ventas_grupos_fallidos_run")
    c.commit()
    c.close()


def _correr(*args):
    env = {
        **os.environ,
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=15,
    )


def _grupos_en_tabla(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT grupo_id FROM ventas_grupos_fallidos_run ORDER BY grupo_id")
        return [row[0] for row in cur.fetchall()]


def test_listar_vacio_sin_fallos(conn):
    proc = _correr("listar")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_marcar_registra_el_grupo(conn):
    proc = _correr("marcar", "15")
    assert proc.returncode == 0
    assert _grupos_en_tabla(conn) == [15]


def test_marcar_el_mismo_grupo_dos_veces_no_duplica(conn):
    """marcar() en si es idempotente -- importa incluso con la marca
    pesimista de process_grupo() (una sola vez por grupo, al entrar), no
    solo para el caso viejo de un fallo por cada deposito."""
    _correr("marcar", "15")
    _correr("marcar", "15")

    assert _grupos_en_tabla(conn) == [15]


def test_marcar_varios_grupos_y_listar_ordenado(conn):
    _correr("marcar", "200")
    _correr("marcar", "15")
    _correr("marcar", "65")

    assert _grupos_en_tabla(conn) == [15, 65, 200]

    proc = _correr("listar")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "15,65,200"


def test_reset_vacia_la_tabla(conn):
    _correr("marcar", "15")
    _correr("marcar", "200")

    proc = _correr("reset")
    assert proc.returncode == 0
    assert _grupos_en_tabla(conn) == []


def test_reset_no_afecta_corridas_futuras_si_no_fallan(conn):
    """Simulacro del ciclo completo de una corrida sin fallos: reset al
    arrancar, nada se marca, listar queda vacio -- el merge no excluye
    ningun grupo."""
    _correr("marcar", "15")  # resto de una corrida anterior, con fallo
    _correr("reset")  # arranque de la corrida de esta noche

    proc = _correr("listar")
    assert proc.stdout.strip() == ""


def test_desmarcar_quita_solo_ese_grupo(conn):
    _correr("marcar", "15")
    _correr("marcar", "200")

    proc = _correr("desmarcar", "15")
    assert proc.returncode == 0
    assert _grupos_en_tabla(conn) == [200]


def test_desmarcar_un_grupo_no_marcado_no_falla(conn):
    """process_grupo() llama desmarcar() para TODO grupo que termina bien,
    incluidos los que nunca fallaron y por lo tanto nunca se marcaron --
    debe ser un no-op silencioso, no un error."""
    proc = _correr("desmarcar", "15")

    assert proc.returncode == 0
    assert _grupos_en_tabla(conn) == []


def test_marcar_grupo_no_numerico_falla_con_mensaje_claro(conn):
    """Entrada invalida (typo, copy-paste) no debe volcar un traceback
    crudo -- mismo criterio que el resto de los subcomandos."""
    proc = _correr("marcar", "abc")

    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert _grupos_en_tabla(conn) == []
