import datetime as dt
import os

import pytest

from run_calc_sugerencias import (
    MAX_MESES,
    MIN_MESES_CON_DATOS,
    UMBRAL_DIAS_STOCK_VIEJO,
    calcular_dias_hasta_quiebre,
    calcular_rotacion_y_fiabilidad,
    cargar_mes_referencia,
    calcular_sugerencias,
)


def _try_connect():
    """
    Conexion real a MySQL para el test de integracion -- se salta con
    pytest.skip si no hay DB disponible, mismo patron que
    test_run_calc_planilla.py (localhost:3307, docker-compose local).
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


# ── calcular_rotacion_y_fiabilidad() ────────────────────────────────────────

def test_menos_del_minimo_de_meses_da_none_none():
    assert calcular_rotacion_y_fiabilidad([5.0, 3.0]) == (None, None)  # 2 < MIN_MESES_CON_DATOS=3


def test_exactamente_el_minimo_de_meses_ya_calcula():
    rot, fiab = calcular_rotacion_y_fiabilidad([5.0, 5.0, 5.0])
    assert rot is not None and fiab is not None


def test_issue_116_meses_en_cero_cuentan_y_bajan_el_promedio():
    """
    Regresion del bug: antes del fix, un mes 'normal' con rotacion=0 se
    descartaba en el filtro SQL (nunca llegaba a esta lista) -- un SKU que
    vendio 10/10/10/0/0 promediaba sobre [10,10,10], no sobre los 5 meses
    reales. Esta funcion ya no filtra nada, solo agrega -- la prueba real
    del fix esta en el filtro SQL (test de integracion mas abajo), pero aca
    verificamos que la matematica no rompe con ceros y que efectivamente
    bajan el promedio ponderado.
    """
    rot_con_ceros, _ = calcular_rotacion_y_fiabilidad([0.0, 0.0, 10.0, 10.0, 10.0])
    rot_sin_ceros, _ = calcular_rotacion_y_fiabilidad([10.0, 10.0, 10.0])
    assert rot_con_ceros < rot_sin_ceros


def test_promedio_ponderado_favorece_meses_recientes():
    # valores[0] = mes mas reciente (mayor peso)
    rot, _ = calcular_rotacion_y_fiabilidad([10.0, 0.0, 0.0])
    assert rot > (10.0 / 3)  # mayor que el promedio simple, porque el reciente pesa mas


def test_fiabilidad_maxima_cuando_la_rotacion_es_estable():
    _, fiab = calcular_rotacion_y_fiabilidad([5.0, 5.0, 5.0, 5.0])
    assert fiab == 100.0


def test_fiabilidad_baja_con_alta_variabilidad():
    _, fiab_estable = calcular_rotacion_y_fiabilidad([5.0, 5.0, 5.0])
    _, fiab_erratico = calcular_rotacion_y_fiabilidad([0.0, 10.0, 0.0])
    assert fiab_erratico < fiab_estable


def test_issue_116_intermitencia_ya_no_desaparece_de_la_fiabilidad():
    """
    AC del issue: "un articulo que vende 3 meses de 12 no puede dar
    fiabilidad alta". Antes del fix esos 9 meses en cero se descartaban del
    calculo, dejando solo los 3 meses con venta (CV bajo, fiabilidad alta
    artificial). Con los ceros incluidos, el CV real de la intermitencia
    se refleja.
    """
    _, fiab_intermitente = calcular_rotacion_y_fiabilidad(
        [5.0, 5.0, 5.0] + [0.0] * 9
    )
    _, fiab_solo_meses_con_venta = calcular_rotacion_y_fiabilidad([5.0, 5.0, 5.0])
    assert fiab_intermitente < fiab_solo_meses_con_venta


def test_fiabilidad_no_negativa_con_variabilidad_extrema():
    _, fiab = calcular_rotacion_y_fiabilidad([0.0, 100.0, 0.0])
    assert fiab >= 0.0


def test_promedio_cero_da_fiabilidad_cero_sin_dividir_por_cero():
    rot, fiab = calcular_rotacion_y_fiabilidad([0.0, 0.0, 0.0])
    assert rot == 0.0
    assert fiab == 0.0


def test_hallazgo_code_review_rotacion_negativa_neta_se_recorta_a_cero():
    """
    Regresion de /code-review: ventas_cantidad es signed desde el #80 (notas
    de credito/devoluciones pueden dejar un mes con venta neta negativa).
    Sin recorte, un mes muy negativo puede arrastrar el promedio ponderado
    por debajo de 0, violando chk_sugerencias_rotacion CHECK (>= 0) al
    escribir en planilla_sugerencias y abortando todo el batch.
    """
    rot, _ = calcular_rotacion_y_fiabilidad([-100.0, 5.0, 5.0])
    assert rot is not None
    assert rot >= 0.0


# ── calcular_dias_hasta_quiebre() ───────────────────────────────────────────

REF = dt.date(2026, 8, 15)


def test_none_si_no_hay_rotacion_sugerida():
    assert calcular_dias_hasta_quiebre(100.0, None, REF, REF) is None


def test_none_si_rotacion_sugerida_es_cero():
    assert calcular_dias_hasta_quiebre(100.0, 0.0, REF, REF) is None


def test_none_si_rotacion_sugerida_es_negativa():
    assert calcular_dias_hasta_quiebre(100.0, -1.0, REF, REF) is None


def test_calcula_normal_con_stock_fresco():
    assert calcular_dias_hasta_quiebre(100.0, 5.0, REF, REF) == 20.0


def test_stock_negativo_se_trata_como_cero():
    assert calcular_dias_hasta_quiebre(-50.0, 5.0, REF, REF) == 0.0


def test_issue_116_none_si_el_stock_es_mas_viejo_que_el_umbral():
    fecha_stock = REF - dt.timedelta(days=UMBRAL_DIAS_STOCK_VIEJO + 1)
    assert calcular_dias_hasta_quiebre(100.0, 5.0, fecha_stock, REF) is None


def test_issue_116_umbral_es_inclusive():
    fecha_stock = REF - dt.timedelta(days=UMBRAL_DIAS_STOCK_VIEJO)
    assert calcular_dias_hasta_quiebre(100.0, 5.0, fecha_stock, REF) is not None


def test_none_si_no_hay_fecha_de_stock():
    assert calcular_dias_hasta_quiebre(100.0, 5.0, None, REF) is None


# ── calcular_sugerencias() — integracion contra MySQL real ────────────────

@pytest.fixture
def conn():
    c = _try_connect()
    yield c
    c.rollback()
    c.close()


def _sembrar_mes(cur, sku, year, month, estado_mes, rotacion_diaria_real, rotacion_ajustada=None):
    cur.execute(
        """
        INSERT INTO planilla_ventas_calculada
            (sku, year, month, ventas_cantidad, dias_con_stock, dias_naturales_mes,
             rotacion_diaria_real, rotacion_diaria_bruta, rotacion_diaria_desestacionalizada,
             estado_mes, frecuencia_nivel, rotacion_ajustada, tickets_mes,
             valor_historico, valor_ajustado, criterio_frecuencia)
        VALUES
            (%s, %s, %s, 0, 28, 28, %s, %s, NULL, %s, 'media', %s, 0, NULL, NULL, 'real_extrapolado')
        ON DUPLICATE KEY UPDATE
            rotacion_diaria_real = VALUES(rotacion_diaria_real),
            estado_mes = VALUES(estado_mes),
            rotacion_ajustada = VALUES(rotacion_ajustada)
        """,
        (sku, year, month, rotacion_diaria_real, rotacion_diaria_real or 0, estado_mes, rotacion_ajustada),
    )


def test_issue_116_mes_normal_en_cero_ya_no_se_descarta_del_calculo(conn):
    """
    Test de integracion (semilla real en planilla_ventas_calculada) que
    prueba el fix real: antes, el filtro SQL 'rotacion_diaria_real > 0'
    descartaba los meses normales sin ventas. Sembramos un SKU con 3 meses
    normales en cero y 2 meses normales con venta -- si el fix no esta
    aplicado, este SKU queda con < MIN_MESES_CON_DATOS (2 < 3) y
    rotacion_sugerida=NULL; con el fix, tiene 5 meses elegibles.
    """
    sku = "TEST-ISSUE-116"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            cur.execute("SELECT id FROM grupos LIMIT 1")
            grupo_id = cur.fetchone()[0]
            cur.execute(
                "INSERT IGNORE INTO articulos (sku, descripcion, grupo_id) VALUES (%s, 'test issue 116', %s)",
                (sku, grupo_id),
            )
            meses = [(2026, 1, 0.0), (2026, 2, 0.0), (2026, 3, 0.0), (2026, 4, 5.0), (2026, 5, 5.0)]
            for year, month, rot in meses:
                _sembrar_mes(cur, sku, year, month, "normal", rot)
        conn.commit()

        filas, _con, _sin, _quiebre = calcular_sugerencias(
            conn, stock_por_sku={}, mes_referencia=(2026, 6)
        )
        fila = next(f for f in filas if f["sku"] == sku)
        assert fila["rotacion_sugerida"] is not None
        assert fila["fiabilidad_porcentaje"] is not None
        # promedio ponderado sobre 5 valores (2 con venta, 3 en cero) = 3.0 exacto
        # ((5*5 + 4*5) / (5+4+3+2+1)); si el filtro viejo siguiera activo, los 3
        # meses en cero ni siquiera llegarian a esta lista (2 < MIN_MESES_CON_DATOS)
        # y rotacion_sugerida seria None, no 5.0 -- por eso comparamos contra el
        # valor exacto esperado, no solo "< 5.0".
        assert fila["rotacion_sugerida"] == 3.0
    finally:
        # Hallazgo de /code-review: el fixture `conn` solo hace rollback(), que
        # es un no-op sobre datos ya commiteados -- sin este cleanup explicito
        # el SKU de prueba queda para siempre en la DB local/dev.
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            # Issue #121: articulo_grupo tiene FK RESTRICT a articulos(sku).
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
