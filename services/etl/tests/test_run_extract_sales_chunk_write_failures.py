"""
Tests de run_extract_sales_chunk.py (Issue #154) -- antes de este fix,
`procesar_payload` tenia `except Exception: pass` en la escritura de
stock_diario y un solo `commit()` al final del lote. Una excepcion real de
MySQL (deadlock, valor fuera de rango) se perdia en silencio y el script
siempre terminaba en exit 0, aunque la fila nunca hubiera llegado a la
tabla que run_extract_sales_chunk.py pisa por diseno (#39, fuente
autoritativa de stock_diario). Ahora una excepcion real se cuenta aparte
(rows_stock_failed), se loguea con contexto, y el script termina con
exit != 0 -- mismo criterio que el fix analogo de #141 en
run_extract_stockxml.py (ver test_run_extract_stockxml_write.py).

Integracion contra MySQL real con pytest.skip si no hay DB (mismo patron
que el resto de los tests de este script).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_sales_chunk.py"

SKU_OK = "__TEST_154_OK__"
SKU_BAD = "__TEST_154_BAD__"
DEPOSITO_TEST = "154"


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
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def _correr(tmp_path):
    json_path = tmp_path / "ventas.json"
    json_path.write_text(
        json.dumps(
            [
                {"Fecha": "01/08/2026", "IdArticulo": SKU_OK, "Venta": "5", "Stock": "10"},
                # cantidad de stock_diario es INT UNSIGNED (max ~4.29e9) --
                # este valor tiene 14 digitos, entra sin problema en el
                # DECIMAL(18,4) de ventas_historicas_stage.stock (14 enteros
                # + 4 decimales = 18 digitos totales, justo en el limite) pero
                # desborda el entero de stock_diario. Es una excepcion real
                # de escritura ("Out of range value"), no un dato descartable
                # por parseo -- parse_entero solo clampea el piso, nunca el
                # techo (mismo razonamiento que el valor analogo de #141).
                {"Fecha": "01/08/2026", "IdArticulo": SKU_BAD, "Venta": "3", "Stock": "99999999999999"},
            ]
        ),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "TMP_JSON_PATH": str(json_path),
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
        "__FORCED_DEPOSITO": DEPOSITO_TEST,
    }
    env.pop("__FORCED_GRUPO", None)

    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30,
    )


def test_fila_con_error_real_de_escritura_en_stock_diario_no_pasa_inadvertida(tmp_path, conn):
    proc = _correr(tmp_path)

    assert proc.returncode != 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "failed 1" in proc.stdout.lower()

    with conn.cursor() as cur:
        cur.execute("SELECT sku FROM stock_diario WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        skus_en_stock_diario = {row[0] for row in cur.fetchall()}

    # La fila mala nunca llega a stock_diario -- la buena si, porque el
    # commit por fila (Issue #154) impide que el fallo de la segunda se
    # lleve puesta la primera, ya durable antes de que ocurra el error.
    assert skus_en_stock_diario == {SKU_OK}

    with conn.cursor() as cur:
        cur.execute("SELECT sku FROM ventas_historicas_stage WHERE sku IN (%s, %s)", (SKU_OK, SKU_BAD))
        skus_en_stage = {row[0] for row in cur.fetchall()}

    # El fallo es especifico de stock_diario -- el mismo valor entra sin
    # problema en la columna DECIMAL(18,4) de stage, asi que las dos filas
    # de ventas quedan escritas igual (perder el stock de un dia no debe
    # perder tambien la venta, son escrituras independientes).
    assert skus_en_stage == {SKU_OK, SKU_BAD}
