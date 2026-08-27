"""
Tests de run_extract_sales_chunk.py (Issue #186) -- nombres de tabla
configurables para poblar el almacen de comparacion aislado en vez de las
tablas de produccion.

Integracion contra MySQL real con pytest.skip si no hay DB, mismo patron
que test_run_extract_sales_chunk.py. Requiere infra/sql/26-tablas-
comparacion.sql ya aplicada (ver ese archivo) -- si las tablas *_comparacion
no existen, los tests de integracion fallan con un mensaje claro en vez de
saltearse en silencio (a diferencia de "sin conexion", "falta la migracion"
es un estado que vale la pena que el operador note).
"""

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


SKU_TEST = "__TEST_186__"


@pytest.fixture
def conn():
    c = _try_connect()
    with c.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ventas_historicas_stage_comparacion'"
        )
        if cur.fetchone()[0] == 0:
            pytest.fail(
                "Falta infra/sql/26-tablas-comparacion.sql -- aplicarla antes de "
                "correr estos tests (ver apply_migrations.sh)."
            )
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM ventas_historicas_stage_comparacion WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario_comparacion WHERE sku = %s", (SKU_TEST,))
    c.commit()
    yield c
    with c.cursor() as cur:
        cur.execute("DELETE FROM ventas_historicas_stage WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM ventas_historicas_stage_comparacion WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario_comparacion WHERE sku = %s", (SKU_TEST,))
    c.commit()


def _item(venta, stock=100, fecha="2026-08-01", sku=SKU_TEST):
    return {"Fecha": fecha, "IdArticulo": sku, "Venta": venta, "Stock": stock}


def _count(conn, tabla, sku=SKU_TEST):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE sku = %s", (sku,))
        return cur.fetchone()[0]


def test_tabla_stage_explicita_escribe_solo_en_la_de_comparacion(conn):
    rsc.procesar_payload(
        conn, [_item(venta=10)], deposito_forzado="5", grupo_id="30",
        tabla_stage="ventas_historicas_stage_comparacion",
        tabla_stock="stock_diario_comparacion",
    )

    assert _count(conn, "ventas_historicas_stage_comparacion") == 1
    assert _count(conn, "ventas_historicas_stage") == 0, "no debe tocar la tabla de produccion"
    assert _count(conn, "stock_diario_comparacion") == 1
    assert _count(conn, "stock_diario") == 0, "no debe tocar la tabla de produccion"


def test_sin_override_sigue_escribiendo_en_las_tablas_de_produccion(conn):
    """Default sin cambios de comportamiento -- lo que ya cubria
    test_run_extract_sales_chunk.py, repetido aca solo para dejar explicito
    que el nuevo parametro es opt-in, no una migracion silenciosa de default."""
    rsc.procesar_payload(conn, [_item(venta=7)], deposito_forzado="5", grupo_id="30")

    assert _count(conn, "ventas_historicas_stage") == 1
    assert _count(conn, "ventas_historicas_stage_comparacion") == 0
    assert _count(conn, "stock_diario") == 1
    assert _count(conn, "stock_diario_comparacion") == 0


def test_env_var_tambien_redirige_sin_pasar_el_parametro_explicito(conn, monkeypatch):
    """main() usa las env vars TABLA_VENTAS_STAGE/TABLA_STOCK_DIARIO -- este
    test cubre esa via (run_backfill_comparacion.sh las exporta antes de
    invocar el extractor), no solo el parametro explicito de la funcion."""
    monkeypatch.setenv("TABLA_VENTAS_STAGE", "ventas_historicas_stage_comparacion")
    monkeypatch.setenv("TABLA_STOCK_DIARIO", "stock_diario_comparacion")

    rsc.procesar_payload(
        conn, [_item(venta=4)], deposito_forzado="5", grupo_id="30",
        tabla_stage=None, tabla_stock=None,
    )

    assert _count(conn, "ventas_historicas_stage_comparacion") == 1
    assert _count(conn, "ventas_historicas_stage") == 0


def test_nombre_de_tabla_invalido_falla_fuerte_sin_tocar_la_db(conn):
    """Defensa en profundidad: el nombre de tabla se interpola en el SQL (no
    se puede pasar como bind parameter), asi que se valida antes de armar
    cualquier query -- un valor invalido no debe llegar nunca a un
    INSERT/SELECT con string interpolado."""
    with pytest.raises(ValueError):
        rsc.procesar_payload(
            conn, [_item(venta=1)], deposito_forzado="5", grupo_id="30",
            tabla_stage="ventas_historicas_stage; DROP TABLE articulos",
        )

    assert _count(conn, "ventas_historicas_stage") == 0
