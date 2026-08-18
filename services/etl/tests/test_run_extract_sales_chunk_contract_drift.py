"""
Tests de run_extract_sales_chunk.py (Issue #159) -- contract drift.

Si el WS deja de mandar un campo esperado (renombre de campo, ej. `Venta`
-> `VentaNeta`), `parse_entero(None)` devolvia 0 por default y esas filas
pisaban ventas buenas via ON DUPLICATE KEY UPDATE, sistematicamente, sin
ningun error -- el job quedaba 'exitoso'. `procesar_payload` ahora levanta
`ContractDriftError` ANTES de escribir nada si NINGUNA fila del payload
trae un campo de venta (o de stock, cuando corresponde) reconocible. La
señal es la ausencia TOTAL del campo, no el valor: un dia real sin ventas
(domingo) trae el campo presente con valor 0, y eso NO debe disparar el
fallo -- ese es el falso positivo que el propio issue pide evitar
explicitamente.

Integracion contra MySQL real con pytest.skip si no hay DB, mismo patron
que el resto de los tests de este script.
"""

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import run_extract_sales_chunk as rsc

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_sales_chunk.py"

SKU_TEST = "__TEST_159__"


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
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku = %s", (SKU_TEST,))

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def _filas_stage(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fecha, cantidad FROM ventas_historicas_stage WHERE sku = %s",
            (SKU_TEST,),
        )
        return cur.fetchall()


# ── El caso central: campo ausente en TODAS las filas dispara el fallo ──────

def test_venta_ausente_en_todas_las_filas_dispara_contract_drift(conn):
    """Ninguno de los 9 nombres alternativos de venta aparece -- firma de
    un contrato roto, no de un dia sin ventas."""
    payload = [
        {"Fecha": "2026-08-01", "IdArticulo": SKU_TEST, "Stock": "10"},
        {"Fecha": "2026-08-02", "IdArticulo": SKU_TEST, "Stock": "12"},
    ]
    with pytest.raises(rsc.ContractDriftError):
        rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")

    # Nada se escribio -- el chequeo corre antes de la primera escritura.
    assert _filas_stage(conn) == ()


def test_stock_ausente_en_todas_las_filas_con_deposito_forzado_dispara(conn):
    """Mismo mecanismo para stock, pero solo importa si deposito_forzado
    esta seteado -- sin eso, stock_diario nunca se escribe de todos modos."""
    payload = [
        {"Fecha": "2026-08-01", "IdArticulo": SKU_TEST, "Venta": "5"},
        {"Fecha": "2026-08-02", "IdArticulo": SKU_TEST, "Venta": "3"},
    ]
    with pytest.raises(rsc.ContractDriftError):
        rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")

    assert _filas_stage(conn) == ()


def test_stock_ausente_sin_deposito_forzado_no_dispara(conn):
    """Sin deposito_forzado, stock_diario nunca se escribe -- la ausencia
    del campo de stock no es relevante en ese caso, no debe fallar."""
    payload = [{"Fecha": "2026-08-01", "IdArticulo": SKU_TEST, "Venta": "5"}]

    ins, skip, stock_ins, failed, stock_failed = rsc.procesar_payload(
        conn, payload, deposito_forzado=None, grupo_id="30"
    )
    assert (ins, stock_ins) == (1, 0)


# ── El falso positivo que el issue pide evitar explicitamente ───────────────

def test_venta_presente_en_cero_no_dispara_el_fallo_domingo_real(conn):
    """Domingo real: el campo VIENE presente con valor 0 -- eso es un dato
    legitimo, no la ausencia del campo. No debe disparar ContractDriftError."""
    payload = [{"Fecha": "2026-08-02", "IdArticulo": SKU_TEST, "Venta": 0, "Stock": 50}]

    ins, skip, stock_ins, failed, stock_failed = rsc.procesar_payload(
        conn, payload, deposito_forzado="5", grupo_id="30"
    )
    assert ins == 1
    assert _filas_stage(conn) == ((dt.date(2026, 8, 2), 0),)


def test_stock_presente_en_cero_no_dispara_el_fallo(conn):
    payload = [{"Fecha": "2026-08-02", "IdArticulo": SKU_TEST, "Venta": 5, "Stock": 0}]

    ins, skip, stock_ins, failed, stock_failed = rsc.procesar_payload(
        conn, payload, deposito_forzado="5", grupo_id="30"
    )
    assert (ins, stock_ins) == (1, 1)


def test_payload_vacio_no_dispara_el_fallo(conn):
    """Una respuesta valida pero sin filas (semana sin ventas para ese
    grupo/deposito puntual) no dice nada sobre el contrato -- no es la
    clase de fallo que este chequeo busca."""
    ins, skip, stock_ins, failed, stock_failed = rsc.procesar_payload(
        conn, [], deposito_forzado="5", grupo_id="30"
    )
    assert (ins, skip, stock_ins, failed, stock_failed) == (0, 0, 0, 0, 0)


def test_algunas_filas_con_el_campo_no_dispara_el_fallo(conn):
    """Ausencia parcial (algunas filas si traen el campo, otras no) no es
    la firma de contract drift -- esas filas sin el campo ya se manejan
    fila por fila (parse_entero(None) -> 0, comportamiento intencional
    para una fila puntual sin dato)."""
    payload = [
        {"Fecha": "2026-08-01", "IdArticulo": SKU_TEST, "Venta": 5, "Stock": 10},
        {"Fecha": "2026-08-02", "IdArticulo": SKU_TEST, "Stock": 12},  # sin campo de venta
    ]
    ins, skip, stock_ins, failed, stock_failed = rsc.procesar_payload(
        conn, payload, deposito_forzado="5", grupo_id="30"
    )
    assert ins == 2


# ── El mensaje debe ser diagnosticable sin leer el codigo ───────────────────

def test_mensaje_de_error_lista_los_campos_de_venta_probados(conn):
    payload = [{"Fecha": "2026-08-01", "IdArticulo": SKU_TEST}]
    with pytest.raises(rsc.ContractDriftError) as exc:
        rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")

    msg = str(exc.value)
    for campo in rsc.CAMPOS_VENTA:
        assert campo in msg, f"{campo!r} no aparece en el mensaje de error"


def test_mensaje_de_error_lista_los_campos_de_stock_probados(conn):
    payload = [{"Fecha": "2026-08-01", "IdArticulo": SKU_TEST, "Venta": 5}]
    with pytest.raises(rsc.ContractDriftError) as exc:
        rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")

    msg = str(exc.value)
    for campo in rsc.CAMPOS_STOCK:
        assert campo in msg, f"{campo!r} no aparece en el mensaje de error"


# ── main(): el proceso completo termina con exit != 0 ───────────────────────

def _correr_main(tmp_path, payload, forced_deposito="5"):
    json_path = tmp_path / "ventas.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    env = {
        **os.environ,
        "TMP_JSON_PATH": str(json_path),
        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3307"),
        "MYSQL_USER": os.environ.get("MYSQL_USER", "evalutia"),
        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "evalutia"),
        "MYSQL_DB": os.environ.get("MYSQL_DB", "evalutia"),
    }
    if forced_deposito:
        env["__FORCED_DEPOSITO"] = forced_deposito
    else:
        env.pop("__FORCED_DEPOSITO", None)
    env.pop("__FORCED_GRUPO", None)

    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30,
    )


def test_main_termina_con_exit_distinto_de_cero_si_falta_el_campo_de_venta(tmp_path, conn):
    proc = _correr_main(tmp_path, [{"Fecha": "01/08/2026", "IdArticulo": SKU_TEST, "Stock": "10"}])

    assert proc.returncode != 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "cambio de contrato" in proc.stdout.lower()
    assert _filas_stage(conn) == ()


def test_main_no_falla_un_domingo_real_con_venta_en_cero(tmp_path, conn):
    proc = _correr_main(tmp_path, [{"Fecha": "02/08/2026", "IdArticulo": SKU_TEST, "Venta": 0, "Stock": 20}])

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert len(_filas_stage(conn)) == 1
