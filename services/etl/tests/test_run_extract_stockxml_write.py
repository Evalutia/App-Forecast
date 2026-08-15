"""
Tests de run_extract_stockxml.py (Issue #141) -- antes de este fix, una
excepcion real de MySQL al escribir una fila (fuera de rango, tipo invalido,
etc.) se contaba igual que un skip legitimo de datos (SKU filtrado, stock no
interpretable): rows_skip++ sin distincion, y el script siempre terminaba con
exit 0 aunque TODAS las filas hubieran fallado al escribirse. Ahora una
excepcion real de escritura se cuenta aparte (rows_failed) y el script
termina con exit != 0 si hubo al menos una.

Integracion contra MySQL real con pytest.skip si no hay DB (mismo patron que
test_finalize_articulo_grupos.py / test_run_extract_sales_chunk.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_stockxml.py"

SKU_OK = "__TEST_141_OK__"
SKU_BAD = "__TEST_141_BAD__"
GRUPO_TEST = 90141  # id alto, no deberia chocar con grupos reales


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
        cur.execute("DELETE FROM stock_diario WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        cur.execute("DELETE FROM articulos WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        cur.execute("DELETE FROM grupos WHERE id = %s", (GRUPO_TEST,))

    with c.cursor() as cur:
        _limpiar(cur)
        cur.execute(
            "INSERT INTO grupos (id, descripcion) VALUES (%s, %s)",
            (GRUPO_TEST, "TEST GRUPO 141"),
        )
        # Sin esto el filtro de allowed_skus del script (que solo deja pasar
        # SKUs que ya existen en articulos) descartaria las dos filas de
        # prueba como si fueran datos ajenos al catalogo, y nunca llegarian
        # al INSERT que este test quiere ejercitar.
        cur.executemany(
            "INSERT INTO articulos (sku, grupo_id) VALUES (%s, %s)",
            [(SKU_OK, GRUPO_TEST), (SKU_BAD, GRUPO_TEST)],
        )
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def _correr(tmp_path):
    json_path = tmp_path / "stock.json"
    json_path.write_text(
        json.dumps(
            {
                "Rows": [
                    {"IdArticulo": SKU_OK, "Stock": "10", "IdDeposito": "5"},
                    # cantidad es INT UNSIGNED -- este valor desborda la
                    # columna y MySQL levanta "Out of range value" al
                    # INSERT. Es una excepcion real de escritura, no un dato
                    # descartable por parseo: parse_entero solo clampea el
                    # piso (nunca negativo), no tiene techo.
                    {"IdArticulo": SKU_BAD, "Stock": "99999999999999", "IdDeposito": "5"},
                ]
            }
        ),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "TMP_JSON_PATH": str(json_path),
        "CHUNK_START": "2026-08-01",
        "CHUNK_END": "2026-08-01",
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
    }
    env.pop("__FORCED_DEPOSITO", None)
    env.pop("ID_EMPRESA", None)

    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30,
    )


def test_fila_con_error_real_de_escritura_no_pasa_inadvertida(tmp_path, conn):
    proc = _correr(tmp_path)

    assert proc.returncode != 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "failed 1" in proc.stdout.lower()

    with conn.cursor() as cur:
        cur.execute("SELECT sku FROM stock_diario WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        skus_insertados = {row[0] for row in cur.fetchall()}

    # la fila buena se escribe igual -- una fila con error real no debe
    # frenar ni revertir las que si funcionan (Issue #141: "continuar,
    # trackear, fallar al final", mismo criterio que el resto del script).
    assert skus_insertados == {SKU_OK}
