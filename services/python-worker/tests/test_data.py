import datetime as dt
import os

import pytest

from ioworker.data import build_only_skus_where, load_series_by_sku_mysql


# ── build_only_skus_where() -- helper puro compartido (issue #148) ─────────
# Extraido de load_series_by_sku_mysql para no duplicar esta logica en
# ml/eval_walkforward.py._load_meses_historia (encontrado por /code-review).

def test_build_only_skus_where_sin_skus_no_filtra():
    where_clause, params = build_only_skus_where(None)
    assert where_clause == ""
    assert params == {}


def test_build_only_skus_where_lista_vacia_no_filtra():
    where_clause, params = build_only_skus_where([])
    assert where_clause == ""
    assert params == {}


def test_build_only_skus_where_arma_placeholders_parametrizados():
    where_clause, params = build_only_skus_where(["B00002", "A00001"])
    assert where_clause == "WHERE sku IN (:sku0, :sku1)"
    assert set(params.values()) == {"A00001", "B00002"}


def test_build_only_skus_where_descarta_vacios_y_recorta_espacios():
    where_clause, params = build_only_skus_where([" A00001 ", "", None, "  "])
    assert where_clause == "WHERE sku IN (:sku0)"
    assert list(params.values()) == ["A00001"]


def _try_connect():
    """
    Conexion real a MySQL para el test de integracion -- se salta con
    pytest.skip si no hay DB disponible. Mismo patron ya usado en
    services/etl/tests/test_run_calc_planilla.py.
    """
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


def _get_engine():
    from sqlalchemy import create_engine

    port = os.environ.get("MYSQL_PORT", "3307")
    user = os.environ.get("MYSQL_USER", "evalutia")
    password = os.environ.get("MYSQL_PASSWORD", "evalutia")
    host = os.environ.get("MYSQL_HOST", "localhost")
    db = os.environ.get("MYSQL_DB", "evalutia")
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}", future=True)


# ── load_series_by_sku_mysql(only_skus=...) -- filtro empujado al SQL ──────
# Antes filtraba en pandas DESPUES de traer toda la tabla -- con el backfill
# de 10 anios de #104 (ventas_historicas paso a decenas de millones de filas)
# esto colgo la VM de produccion corriendo el dry-run de #105 sobre un
# catalogo entero, aunque el caller solo pidiera unos pocos SKUs.

def test_only_skus_devuelve_unicamente_los_skus_pedidos():
    conn = _try_connect()
    sku_incluido = "TESTDATA01"
    sku_excluido = "TESTDATA02"
    try:
        with conn.cursor() as cur:
            for sku in (sku_incluido, sku_excluido):
                cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
                cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
                cur.execute(
                    "INSERT INTO articulos (sku, descripcion, grupo_id) VALUES (%s, %s, %s)",
                    (sku, "SKU de prueba -- test_data.py", 201),
                )
                rows = [(sku, dt.date(2026, 1, d), 3, "test") for d in range(1, 6)]
                cur.executemany(
                    "INSERT INTO ventas_historicas (sku, fecha, cantidad, fuente) VALUES (%s, %s, %s, %s)",
                    rows,
                )
        conn.commit()

        engine = _get_engine()
        series_by_sku = load_series_by_sku_mysql(engine, freq="MS", only_skus=[sku_incluido])

        assert sku_incluido in series_by_sku
        assert sku_excluido not in series_by_sku
    finally:
        with conn.cursor() as cur:
            for sku in (sku_incluido, sku_excluido):
                cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
                cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()


def test_sin_only_skus_no_filtra_nada_nuevo():
    """Sin only_skus, el comportamiento (catalogo completo) no cambia."""
    conn = _try_connect()
    sku = "TESTDATA03"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
            cur.execute(
                "INSERT INTO articulos (sku, descripcion, grupo_id) VALUES (%s, %s, %s)",
                (sku, "SKU de prueba -- test_data.py", 201),
            )
            rows = [(sku, dt.date(2026, 1, d), 2, "test") for d in range(1, 6)]
            cur.executemany(
                "INSERT INTO ventas_historicas (sku, fecha, cantidad, fuente) VALUES (%s, %s, %s, %s)",
                rows,
            )
        conn.commit()

        engine = _get_engine()
        series_by_sku = load_series_by_sku_mysql(engine, freq="MS", only_skus=None)

        assert sku in series_by_sku
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()
