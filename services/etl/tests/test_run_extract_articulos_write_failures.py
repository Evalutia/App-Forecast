"""
Tests de run_extract_articulos.py (Issue #167) -- antes de este fix, el
script tenia UN SOLO commit() al final del loop completo, un contador
rows_skip que mezclaba descartes legitimos (sku vacio) con excepciones
reales de MySQL al escribir, y `return 0` incondicional sin importar si
hubo errores de insercion. Mismo defecto que #141 (run_extract_stockxml.py)
y #154 (run_extract_sales_chunk.py) ya resolvieron dos veces en este repo
-- ver test_run_extract_stockxml_write.py y
test_run_extract_sales_chunk_write_failures.py para el mismo patron de
test.

Integracion contra MySQL real con pytest.skip si no hay DB, mismo patron
que el resto de los tests de este directorio.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_articulos.py"

SKU_OK = "__TEST_167_OK__"
SKU_BAD = "__TEST_167_BAD__"
# articulos.grupo_id tiene FK real contra grupos(id) (fk_articulos_grupo) --
# a diferencia de ventas_historicas_stage, donde grupo_id es solo
# trazabilidad sin constraint (#114). Los grupos reales van hasta 201 (PDF
# del cliente, ver 10-grupos.sql) -- 90167 esta deliberadamente fuera de
# ese rango para no poder colisionar nunca con un grupo real.
GRUPO_TEST = "90167"


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

    def _limpiar(cur):
        cur.execute("DELETE FROM articulo_grupo_stage WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        cur.execute("DELETE FROM articulos WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))

    with c.cursor() as cur:
        _limpiar(cur)
        # grupo de prueba, requerido por fk_articulos_grupo -- INSERT IGNORE
        # porque es un seed estable entre corridas, no residuo a limpiar.
        cur.execute(
            "INSERT IGNORE INTO grupos (id, descripcion, visible_planilla) "
            "VALUES (%s, 'TEST issue 167', 0)",
            (GRUPO_TEST,),
        )
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def _correr(tmp_path, items):
    payload_path = tmp_path / "articulos.json"
    payload_path.write_text(json.dumps(items), encoding="utf-8")

    env = {
        **os.environ,
        "TMP_JSON_PATH": str(payload_path),
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
        "__FORCED_GRUPO": GRUPO_TEST,
    }

    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30,
    )


def test_fila_con_error_real_de_escritura_no_pasa_inadvertida(tmp_path, conn):
    items = [
        {"IdArticulo": SKU_OK, "DescripcionArt": "OK", "StockMinimo": "5"},
        # articulos.stock_minimo es INT UNSIGNED (max ~4.29e9) -- este valor
        # desborda el tipo en el INSERT real. to_nonneg_int() solo clampea el
        # piso en 0, nunca topea el techo -- es una excepcion real de MySQL
        # ("Out of range value"), no un dato descartable por parseo. Misma
        # tecnica que #154 uso con stock_diario.cantidad.
        {"IdArticulo": SKU_BAD, "DescripcionArt": "BAD", "StockMinimo": "99999999999"},
    ]

    proc = _correr(tmp_path, items)

    assert proc.returncode != 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "failed 1" in proc.stdout.lower() or "failed: 1" in proc.stdout.lower()

    with conn.cursor() as cur:
        cur.execute("SELECT sku FROM articulos WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        skus_en_articulos = {row[0] for row in cur.fetchall()}

    # La fila mala nunca llega a articulos -- la buena si, porque el commit
    # por fila (Issue #167) impide que el fallo de la segunda se lleve
    # puesta la primera, ya durable antes de que ocurra el error.
    assert skus_en_articulos == {SKU_OK}


def test_solo_descartes_legitimos_sin_sku_no_cuenta_como_fallo(tmp_path, conn):
    """Un item sin ningun campo de sku reconocible es un descarte legitimo
    (dato ausente del WS), no un error de escritura -- debe seguir dando
    exit 0, distinguido de rows_failed."""
    items = [
        {"IdArticulo": SKU_OK, "DescripcionArt": "OK", "StockMinimo": "5"},
        {"DescripcionArt": "sin sku reconocible"},
    ]

    proc = _correr(tmp_path, items)

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "skipped 1" in proc.stdout.lower()

    with conn.cursor() as cur:
        cur.execute("SELECT sku FROM articulos WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        skus_en_articulos = {row[0] for row in cur.fetchall()}

    assert skus_en_articulos == {SKU_OK}


def test_membresia_de_grupo_se_escribe_junto_con_el_articulo(tmp_path, conn):
    """insert_sql (articulos) y membership_sql (articulo_grupo_stage) son un
    solo hecho atomico -- "este SKU existe y pertenece al grupo X" -- y
    deben commitear juntos por fila, a diferencia de sales_chunk donde
    stage/stock_diario son hechos independientes con commits separados."""
    items = [{"IdArticulo": SKU_OK, "DescripcionArt": "OK", "StockMinimo": "5"}]

    proc = _correr(tmp_path, items)

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku, grupo_id FROM articulo_grupo_stage WHERE sku = %s", (SKU_OK,)
        )
        rows = cur.fetchall()

    assert list(rows) == [(SKU_OK, int(GRUPO_TEST))]
