"""
Tests de run_extract_stockxml.py (Issue #173) -- contract drift.

Mismo hueco que #159 cerro para run_extract_sales_chunk.py, nunca
replicado en este script hermano: si el WS renombra el campo de stock
(ej. Stock -> StockActual), todas las filas caian en el default "0"/0
(rama XML) o 0 (rama JSON) y se escribian igual via
ON DUPLICATE KEY UPDATE -- indistinguible de un dia real con stock en 0.
Ahora el script detecta la ausencia TOTAL del campo (ninguna fila lo
trae, ni en la rama XML ni en la JSON) y falla con SystemExit(1) ANTES de
conectar a la base, en vez de escribir ceros silenciosos.

Verificado en produccion (issue #173): 0 de 26.6M filas de stock_diario
tienen fuente='ConsStockXml' -- ConsStockVenta pisa el 100% de lo que
este script escribiria, por diseno desde #39. El riesgo de este bug es
real pero esta anestesiado por otro mecanismo, no por este codigo -- de
ahi que el hallazgo se haya priorizado medio (M4), no critico.

Los casos "debe fallar" no requieren MySQL real: el chequeo de contract
drift corre ANTES de conn = pymysql.connect(...), asi que el proceso
nunca llega a intentar la conexion. El caso "no debe fallar" si necesita
DB real (pytest.skip si no hay), porque tiene que atravesar el pipeline
completo hasta escribir en stock_diario.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_stockxml.py"

SKU_TEST = "__TEST_173__"
GRUPO_TEST = 90173


def _correr(tmp_path, content, **extra_env):
    payload_path = tmp_path / "stock_payload"
    payload_path.write_text(content, encoding="utf-8")

    env = {
        **os.environ,
        "TMP_JSON_PATH": str(payload_path),
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
    }
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30,
    )


# ── El caso central: campo ausente en TODAS las filas dispara el fallo ──────

def test_stock_ausente_en_todas_las_filas_json_dispara_contract_drift(tmp_path):
    """Ninguno de los nombres alternativos (Stock/StockDisp/Cantidad)
    aparece -- firma de un contrato roto, no de un dia sin datos. No
    necesita MySQL real: el chequeo corre antes de conectar, por eso el
    MYSQL_HOST invalido de abajo no importa."""
    payload = {
        "Rows": [
            {"IdArticulo": SKU_TEST, "IdDeposito": "5"},
            {"IdArticulo": SKU_TEST + "_2", "IdDeposito": "5"},
        ]
    }
    proc = _correr(tmp_path, json.dumps(payload), MYSQL_HOST="fake-host-no-existe")

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "[ERROR]" in proc.stdout
    assert "stock" in proc.stdout.lower()
    assert "Stock" in proc.stdout and "StockDisp" in proc.stdout and "Cantidad" in proc.stdout


def test_stock_ausente_en_todas_las_filas_xml_dispara_contract_drift(tmp_path):
    """Misma señal en la rama XML: mv.find(...) es None para las tres
    variantes (Stock, Existencia, Cantidad) en todas las filas."""
    xml = """<?xml version="1.0"?>
<Root>
  <MovStockTotal>
    <IdArticulo>__TEST_173__</IdArticulo>
    <IdDeposito>5</IdDeposito>
  </MovStockTotal>
  <MovStockTotal>
    <IdArticulo>__TEST_173__2</IdArticulo>
    <IdDeposito>5</IdDeposito>
  </MovStockTotal>
</Root>"""
    proc = _correr(tmp_path, xml, MYSQL_HOST="fake-host-no-existe")

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "[ERROR]" in proc.stdout
    assert "stock" in proc.stdout.lower()
    assert "Stock" in proc.stdout and "Existencia" in proc.stdout and "Cantidad" in proc.stdout


def test_payload_sin_filas_no_dispara_el_fallo(tmp_path):
    """Una respuesta valida pero sin filas no dice nada sobre el
    contrato -- no es la clase de fallo que este chequeo busca. El script
    puede seguir de largo (y fallar mas adelante por otro motivo, p. ej.
    MYSQL_HOST invalido, pero no por contract drift)."""
    proc = _correr(tmp_path, json.dumps({"Rows": []}), MYSQL_HOST="fake-host-no-existe")

    assert "cambio de contrato" not in proc.stdout.lower()


# ── El falso positivo que el issue pide evitar explicitamente ───────────────

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
        # sku = %s, no LIKE: SKU_TEST tiene guiones bajos, que LIKE trata
        # como wildcard de un solo caracter -- con el prefijo entero
        # comodin ("__..."), MySQL no puede usar el indice de sku para
        # acotar el rango y cae a full table scan sobre 26M+ filas.
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM articulos WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM grupos WHERE id = %s", (GRUPO_TEST,))

    with c.cursor() as cur:
        _limpiar(cur)
        cur.execute(
            "INSERT INTO grupos (id, descripcion) VALUES (%s, %s)",
            (GRUPO_TEST, "TEST GRUPO 173"),
        )
        cur.execute(
            "INSERT INTO articulos (sku, grupo_id) VALUES (%s, %s)",
            (SKU_TEST, GRUPO_TEST),
        )
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def test_stock_genuinamente_en_cero_no_dispara_el_fallo(tmp_path, conn):
    """Un dia real sin stock trae el campo Stock presente con valor 0 --
    eso es un dato legitimo, no la ausencia del campo. No debe disparar
    el fallo, y la fila se escribe igual en stock_diario con cantidad 0."""
    payload = {"Rows": [{"IdArticulo": SKU_TEST, "Stock": 0, "IdDeposito": "5"}]}
    proc = _correr(
        tmp_path, json.dumps(payload), CHUNK_START="2026-08-17", CHUNK_END="2026-08-17"
    )

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "cambio de contrato" not in proc.stdout.lower()

    with conn.cursor() as cur:
        cur.execute("SELECT cantidad FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        filas = cur.fetchall()
    assert filas == ((0,),), f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
