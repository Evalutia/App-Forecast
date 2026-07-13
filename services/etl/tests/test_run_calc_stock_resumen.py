from run_calc_stock_resumen import combinar


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
