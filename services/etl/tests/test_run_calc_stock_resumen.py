import datetime as dt
import os

import pytest

from run_calc_stock_resumen import _SQL_RESUMEN_STOCK, VENTANA_DIAS, combinar, ventana_365


def _try_connect():
    """Conexion real a MySQL para tests de integracion -- se salta con pytest.skip
    si no hay DB disponible. Mismo patron que test_run_calc_planilla.py."""
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


# ── ventana_365() -- issue #180: BETWEEN inclusivo con days=365 daba 366 dias ───

def test_ventana_365_da_exactamente_365_dias_anio_no_bisiesto():
    """2026 no es bisiesto. Caso real: hoy=2026-08-20 (fecha de esta sesion)."""
    desde, hasta = ventana_365(hoy=dt.date(2026, 8, 20))
    assert desde == dt.date(2025, 8, 21)
    assert hasta == dt.date(2026, 8, 20)
    assert (hasta - desde).days + 1 == 365


def test_ventana_365_da_exactamente_365_dias_anio_bisiesto():
    """2028 es bisiesto (2028/4=507 exacto) y la ventana cruza el 29/feb/2028 --
    caso real donde un `days=365` sin ajustar rompia mas visiblemente (367 dias,
    no 366) si no se hubiera corregido el off-by-one."""
    desde, hasta = ventana_365(hoy=dt.date(2028, 8, 20))
    assert desde == dt.date(2027, 8, 22)
    assert hasta == dt.date(2028, 8, 20)
    assert dt.date(2028, 2, 29) > desde and dt.date(2028, 2, 29) < hasta
    assert (hasta - desde).days + 1 == 365


def test_ventana_365_sin_fecha_inyectada_usa_hoy():
    hoy = dt.date.today()
    desde, hasta = ventana_365()
    assert hasta == hoy
    assert (hasta - desde).days + 1 == 365


def test_ventana_dias_reportado_coincide_con_el_largo_real_de_la_ventana():
    """jobs_historial.detalle.ventana_dias usa la constante VENTANA_DIAS (365) --
    este test ata esa constante al largo real que ventana_365() produce, para que
    un futuro cambio en uno sin el otro falle acá en vez de en produccion."""
    assert VENTANA_DIAS == 365
    desde, hasta = ventana_365(hoy=dt.date(2026, 8, 20))
    assert (hasta - desde).days + 1 == VENTANA_DIAS


def test_combinar_sku_sin_ventas_queda_en_cero():
    stock_rows = [("A1", 100, 80)]
    ventas_rows = []
    filas = combinar(stock_rows, ventas_rows)
    assert filas == [{
        "sku": "A1",
        "dias_con_stock": 80,
        "dias_sin_stock": 20,
        "total_dias": 100,
        "ventas_365": 0,
    }]


def test_combinar_sku_sin_filas_de_stock_diario_queda_en_cero_dias():
    """LEFT JOIN desde articulos: un SKU sin ninguna fila en stock_diario dentro
    de la ventana llega acá con total_dias=0, dias_con_stock=0 — no se excluye."""
    stock_rows = [("A1", 0, 0)]
    ventas_rows = [("A1", 50)]
    filas = combinar(stock_rows, ventas_rows)
    assert filas[0]["total_dias"] == 0
    assert filas[0]["dias_sin_stock"] == 0
    assert filas[0]["ventas_365"] == 50


def test_combinar_dias_sin_stock_es_total_menos_con_stock():
    stock_rows = [("A1", 365, 200), ("A2", 30, 30)]
    ventas_rows = [("A1", 1000), ("A2", 500)]
    filas = combinar(stock_rows, ventas_rows)
    por_sku = {f["sku"]: f for f in filas}
    assert por_sku["A1"]["dias_sin_stock"] == 165
    assert por_sku["A2"]["dias_sin_stock"] == 0


def test_combinar_ventas_de_sku_no_presente_en_stock_se_ignoran():
    """Un SKU con ventas pero sin fila en articulos (huérfano) no puede aparecer
    en stock_rows (LEFT JOIN parte de articulos) — no se inventa una fila para él."""
    stock_rows = [("A1", 100, 50)]
    ventas_rows = [("A1", 10), ("HUERFANO", 999)]
    filas = combinar(stock_rows, ventas_rows)
    assert len(filas) == 1
    assert filas[0]["sku"] == "A1"


# ── _SQL_RESUMEN_STOCK -- FORCE INDEX, issue #153 (diagnostico #149) ────────────
# Mismo problema y mismo fix que _SQL_STOCK en run_calc_planilla.py -- ver ese
# archivo de test para el detalle del diagnostico.

def test_sql_resumen_stock_contiene_el_force_index():
    """Guardrail principal: no depende de una DB real ni de cuanto elija MySQL
    por su cuenta -- con el volumen chico de la replica local, MySQL puede
    elegir idx_stock_fecha igual SIN el hint."""
    assert "FORCE INDEX" in _SQL_RESUMEN_STOCK
    assert "idx_stock_fecha" in _SQL_RESUMEN_STOCK


def test_sql_resumen_stock_usa_force_index_idx_stock_fecha():
    """Falla si alguien saca el FORCE INDEX sin darse cuenta: sin el hint, MySQL
    puede volver a elegir idx_stock_sku_fecha (el plan lento de #149)."""
    conn = _try_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN " + _SQL_RESUMEN_STOCK,
                (dt.date(2026, 1, 1), dt.date(2026, 1, 31)),
            )
            filas = cur.fetchall()
            columnas = [d[0] for d in cur.description]

        idx_select_type = columnas.index("select_type")
        idx_key         = columnas.index("key")
        # DERIVED = el subquery interno sobre stock_diario.
        fila_stock = next(f for f in filas if f[idx_select_type] == "DERIVED")

        assert fila_stock[idx_key] == "idx_stock_fecha", (
            f"esperaba idx_stock_fecha, MySQL eligio {fila_stock[idx_key]!r} -- "
            "revisar que el FORCE INDEX siga en _SQL_RESUMEN_STOCK"
        )
    finally:
        conn.close()


def test_sql_resumen_stock_respeta_stock_minimo_como_umbral_estricto():
    """Verifica con datos reales que el FORCE INDEX no cambio el resultado:
    un dia con stock exactamente igual al minimo NO cuenta como "con stock"."""
    conn = _try_connect()
    sku = "TESTFORCEIDX02"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
            cur.execute(
                "INSERT INTO articulos (sku, descripcion, grupo_id, stock_minimo) "
                "VALUES (%s, %s, %s, %s)",
                (sku, "SKU de prueba -- regresion FORCE INDEX #153", 201, 5),
            )
            cur.executemany(
                "INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id) VALUES (%s, %s, %s, %s)",
                [
                    (sku, dt.date(2026, 1, 10), 10, "TEST"),  # 10 > 5 -> con stock
                    (sku, dt.date(2026, 1, 11), 5,  "TEST"),  # 5 == 5 -> NO cuenta
                    (sku, dt.date(2026, 1, 12), 3,  "TEST"),  # 3 < 5 -> NO cuenta
                ],
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(_SQL_RESUMEN_STOCK, (dt.date(2026, 1, 1), dt.date(2026, 1, 31)))
            por_sku = {row[0]: row for row in cur.fetchall()}

        assert sku in por_sku, "el SKU de prueba no aparecio -- LEFT JOIN desde articulos deberia cubrirlo"
        _, total_dias, dias_con_stock = por_sku[sku]
        assert total_dias == 3
        assert dias_con_stock == 1, f"esperaba 1 dia con stock, dio {dias_con_stock}"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()
