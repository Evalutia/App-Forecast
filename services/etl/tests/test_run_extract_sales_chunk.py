"""
Tests de run_extract_sales_chunk.py (Issue #114) -- idempotencia del
staging de ventas por deposito.

Integracion contra MySQL real con pytest.skip si no hay DB (CI no levanta
MySQL para services/etl/tests), mismo patron que test_cron_jobs.py.

Bug original: ventas_historicas_stage no tenia clave unica, asi que un
articulo devuelto por N grupos del loop de #42 insertaba N filas, y el
merge (SUM GROUP BY fecha,sku) multiplicaba la venta por N. El fix agrega
UNIQUE(fecha,sku,deposito_id) + ON DUPLICATE KEY UPDATE: la segunda vez
que el mismo grupo/deposito devuelve el mismo articulo/fecha, la fila se
pisa, no se duplica.
"""

import json
import os

import pytest

import run_extract_sales_chunk as rsc


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
    """
    Limpieza por rango de id (todo lo insertado durante el test), sin
    marcadores especiales en el codigo de produccion -- mismo patron que
    test_cron_jobs.py. ventas_historicas_stage se trunca cada noche en
    produccion real, asi que ademas se hace un DELETE del SKU de prueba al
    terminar, por si el test corre contra una DB con datos reales cargados.
    """
    c = _try_connect()
    SKU_TEST = "__TEST_114__"
    with c.cursor() as cur:
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku = %s", (SKU_TEST,))
    c.commit()
    yield c
    with c.cursor() as cur:
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku = %s", (SKU_TEST,))
    c.commit()


def _filas(conn, sku="__TEST_114__"):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT fecha, sku, cantidad, stock, deposito_id, grupo_id, fuente "
            "FROM ventas_historicas_stage WHERE sku = %s ORDER BY fecha, deposito_id",
            (sku,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _item(venta, stock=100, fecha="2026-08-01", sku="__TEST_114__"):
    return {"Fecha": fecha, "IdArticulo": sku, "Venta": venta, "Stock": stock}


# ── El caso central del bug: mismo articulo, mismo deposito, dos grupos ──────

def test_mismo_articulo_devuelto_por_dos_grupos_no_se_duplica(conn):
    """
    Escenario real de #114: un articulo pertenece a dos grupos del catalogo
    del cliente. El WS lo devuelve en la respuesta de cada uno. Antes del
    fix, esto insertaba 2 filas y el merge sumaba 2x la venta real.
    """
    payload = [_item(venta=10)]

    rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")
    rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="76")

    filas = _filas(conn)
    assert len(filas) == 1, "el mismo articulo/fecha/deposito debe pisar, no duplicar"
    assert filas[0]["cantidad"] == 10
    # grupo_id es trazabilidad, no clave: se queda con el ultimo que escribio
    assert filas[0]["grupo_id"] == 76


def test_mismo_articulo_en_depositos_distintos_SI_genera_dos_filas(conn):
    """
    El caso que #39 necesita seguir funcionando: el mismo articulo vendido
    en DOS depositos reales el mismo dia son dos filas legitimas, que el
    merge debe sumar. La clave unica no puede aplastar esto.
    """
    payload = [_item(venta=7)]

    rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")
    rsc.procesar_payload(conn, payload, deposito_forzado="8", grupo_id="30")

    filas = _filas(conn)
    assert len(filas) == 2
    assert {f["deposito_id"] for f in filas} == {"5", "8"}
    assert sum(f["cantidad"] for f in filas) == 14


def test_reprocesar_el_mismo_dia_actualiza_el_valor_no_lo_suma(conn):
    """Reintento/re-corrida de la misma noche: el valor nuevo reemplaza,
    no se acumula sobre el viejo."""
    rsc.procesar_payload(conn, [_item(venta=10)], deposito_forzado="5", grupo_id="30")
    rsc.procesar_payload(conn, [_item(venta=15)], deposito_forzado="5", grupo_id="30")

    filas = _filas(conn)
    assert len(filas) == 1
    assert filas[0]["cantidad"] == 15


# ── Deposito vacio: el sentinel, no NULL ──────────────────────────────────────

def test_deposito_forzado_vacio_usa_sentinel_no_nulo(conn):
    """
    Si S_DEPOSITOS viene vacio (rama del .sh sin coma), __FORCED_DEPOSITO
    puede llegar como cadena vacia. Debe normalizarse al mismo sentinel ''
    de la columna NOT NULL DEFAULT '' -- nunca NULL, porque MySQL no
    colisiona NULL contra NULL en la UNIQUE y reabriria el bug.
    """
    rsc.procesar_payload(conn, [_item(venta=5)], deposito_forzado="", grupo_id="30")
    rsc.procesar_payload(conn, [_item(venta=9)], deposito_forzado="", grupo_id="76")

    filas = _filas(conn)
    assert len(filas) == 1, "deposito vacio en dos grupos distintos debe pisar igual, no duplicar"
    assert filas[0]["deposito_id"] == ""
    assert filas[0]["cantidad"] == 9


def test_deposito_forzado_none_tambien_usa_el_sentinel(conn):
    rsc.procesar_payload(conn, [_item(venta=3)], deposito_forzado=None, grupo_id="30")

    filas = _filas(conn)
    assert len(filas) == 1
    assert filas[0]["deposito_id"] == ""


def test_deposito_forzado_entero_cero_no_colapsa_al_sentinel(conn):
    """
    Chequeo explicito, no truthy: un deposito real llamado 0 (entero) no
    deberia normalizarse al sentinel de 'sin deposito' solo porque 0 es
    falsy en Python. Los depositos reales nunca son 0 en produccion, pero
    la clave unica no deberia depender de esa suposicion.
    """
    rsc.procesar_payload(conn, [_item(venta=4)], deposito_forzado=0, grupo_id="30")

    filas = _filas(conn)
    assert len(filas) == 1
    assert filas[0]["deposito_id"] == "0"


# ── grupo_id: trazabilidad, no participa en la clave ──────────────────────────

def test_grupo_id_null_cuando_no_se_provee(conn):
    rsc.procesar_payload(conn, [_item(venta=1)], deposito_forzado="5", grupo_id=None)

    filas = _filas(conn)
    assert filas[0]["grupo_id"] is None


# ── Comportamiento ya existente que el refactor no puede romper ──────────────

def test_filas_sin_fecha_o_sku_se_saltean(conn):
    payload = [
        {"IdArticulo": "__TEST_114__", "Venta": 5},  # sin fecha
        {"Fecha": "2026-08-01", "Venta": 5},          # sin sku
        _item(venta=8),
    ]
    ins, skip, _ = rsc.procesar_payload(conn, payload, deposito_forzado="5", grupo_id="30")

    assert ins == 1
    assert skip == 2
    assert len(_filas(conn)) == 1


def test_venta_negativa_preserva_el_signo(conn):
    """Issue #80: nota de credito, no se aplasta a 0."""
    rsc.procesar_payload(conn, [_item(venta=-3)], deposito_forzado="5", grupo_id="30")

    filas = _filas(conn)
    assert filas[0]["cantidad"] == -3


def test_stock_diario_se_upsertea_con_grupo_pisando_igual(conn):
    """El camino de stock_diario ya era idempotente antes de #114 (upsert
    por sku,fecha,deposito_id) -- el refactor no debe cambiar eso."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM stock_diario WHERE sku = '__TEST_114__'")
    conn.commit()
    try:
        rsc.procesar_payload(conn, [_item(venta=1, stock=50)], deposito_forzado="5", grupo_id="30")
        rsc.procesar_payload(conn, [_item(venta=1, stock=60)], deposito_forzado="5", grupo_id="76")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT cantidad FROM stock_diario WHERE sku = '__TEST_114__' "
                "AND fecha = '2026-08-01' AND deposito_id = '5'"
            )
            rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 60
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = '__TEST_114__'")
        conn.commit()


def test_conteos_de_retorno(conn):
    ins, skip, stock_ins = rsc.procesar_payload(conn, [_item(venta=1)], deposito_forzado="5", grupo_id="30")
    assert (ins, skip, stock_ins) == (1, 0, 1)
