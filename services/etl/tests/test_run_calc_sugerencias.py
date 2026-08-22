import datetime as dt
import os

import pytest

from run_calc_sugerencias import (
    MAX_DIAS_HASTA_QUIEBRE,
    MAX_MESES,
    MIN_MESES_CON_DATOS,
    MODELO,
    UMBRAL_DIAS_STOCK_VIEJO,
    _pesos_por_distancia_calendario,
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


def test_todos_los_meses_en_cero_da_fiabilidad_100_sin_dividir_por_cero():
    """
    Issue #142: la hoja "Criterios" promete "100% = rotación idéntica todos
    los meses" -- un SKU que vendio 0 en TODOS sus meses elegibles cumple
    eso exacto (desvio cero). Antes daba 0% porque el CV (std/mean) no se
    puede calcular con mean=0 -- el caso real de 272 SKUs en produccion.
    """
    rot, fiab = calcular_rotacion_y_fiabilidad([0.0, 0.0, 0.0])
    assert rot == 0.0
    assert fiab == 100.0


def test_mean_cero_por_cancelacion_no_es_estable_en_cero():
    """
    Distinto de "todos iguales": [-5, 5, 0] promedia a 0 pero es MUY
    inestable (oscila entre valores bien distintos, std != 0) -- no
    corresponde el 100%, que solo aplica cuando el desvio es realmente cero.
    """
    _, fiab = calcular_rotacion_y_fiabilidad([-5.0, 5.0, 0.0])
    assert fiab == 0.0


def test_constante_negativa_da_fiabilidad_100_igual_que_constante_en_cero():
    """
    Hallazgo de /code-review: la primera version de este fix solo daba 100%
    para "todos exactamente cero", dejando una rotacion constante en -10
    (misma estabilidad, std=0) con 0% solo por el signo -- inconsistente
    con la propia regla que el fix intenta cumplir ("100% = rotación
    idéntica"). std==0 generaliza correcto sin importar el signo.
    """
    _, fiab = calcular_rotacion_y_fiabilidad([-10.0, -10.0, -10.0])
    assert fiab == 100.0


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


# ── _pesos_por_distancia_calendario() / Issue #181 ──────────────────────────

def test_pesos_por_distancia_calendario_mutuamente_consecutivos_da_lo_mismo_que_range():
    """
    (2026,3),(2026,2),(2026,1) son mutuamente consecutivos ENTRE SI aunque
    haya un hueco de 6 meses hasta mes_referencia (2026,9) -- lo que importa
    para reproducir el peso viejo es que los meses ELEGIBLES esten pegados
    entre si, no que esten pegados al mes de referencia. Debe dar
    exactamente [3, 2, 1], igual que el viejo range(n, 0, -1).
    """
    meses = [(2026, 3), (2026, 2), (2026, 1)]
    assert _pesos_por_distancia_calendario(meses, (2026, 9)) == [3, 2, 1]


def test_pesos_por_distancia_calendario_pegados_al_mes_referencia_tambien_da_range():
    meses = [(2026, 9), (2026, 8), (2026, 7)]
    assert _pesos_por_distancia_calendario(meses, (2026, 10)) == [3, 2, 1]


def test_pesos_por_distancia_calendario_no_consecutivos_diverge_del_viejo():
    """
    Issue #181, caso del propio issue: ago-2026, mar-2026, sep-2025 con
    mes_referencia=sep-2026. Distancias reales: ago-2026 a 1 mes, mar-2026
    a 6 meses, sep-2025 a 12 meses. max_distancia=12 (no 3=len(meses), como
    asumiria el peso por posicion) -> pesos = [12-1+1, 12-6+1, 12-12+1] =
    [12, 7, 1]. Bien distinto de [3, 2, 1] (el peso viejo por posicion) --
    el viejo trataba a sep-2025 como "un mes antes" de mar-2026, exagerando
    su peso relativo (1/6 del total viejo vs 1/20 del total nuevo).
    """
    meses = [(2026, 8), (2026, 3), (2025, 9)]
    assert _pesos_por_distancia_calendario(meses, (2026, 9)) == [12, 7, 1]


def test_issue_181_pesos_calendario_dan_rotacion_distinta_de_pesos_por_posicion():
    """
    Mismos 3 valores, dos formas de pesar: por posicion (viejo, pesos=None)
    vs por distancia calendario real (nuevo, Issue #181) sobre el caso no
    consecutivo de arriba -- ago-2026 vendio 10, mar-2026 y sep-2025
    vendieron 0. El pesado viejo (posicion [3,2,1]) da (3*10+2*0+1*0)/6 =
    5.0; el nuevo (calendario [12,7,1]) da (12*10+7*0+1*0)/20 = 6.0 -- el
    mes mas reciente pesa proporcionalmente MAS porque los otros dos estan
    mas lejos en el calendario de lo que su posicion en la lista sugeria.
    """
    valores = [10.0, 0.0, 0.0]
    meses = [(2026, 8), (2026, 3), (2025, 9)]
    pesos_calendario = _pesos_por_distancia_calendario(meses, (2026, 9))

    rot_viejo, _ = calcular_rotacion_y_fiabilidad(valores)  # pesos=None -> range(n,0,-1)
    rot_nuevo, _ = calcular_rotacion_y_fiabilidad(valores, pesos_calendario)

    assert rot_viejo == 5.0
    assert rot_nuevo == 6.0
    assert rot_nuevo != rot_viejo


def test_pesos_explicitos_consecutivos_reproduce_el_default():
    """
    Pasar pesos=None (default posicional) y pasar el equivalente explicito
    [n,...,1] para un caso consecutivo da resultados identicos -- confirma
    que el default no es un camino de codigo aparte, es literalmente el
    mismo calculo con pesos=[3,2,1] construido a mano.
    """
    valores = [10.0, 0.0, 0.0]
    rot_default, fiab_default = calcular_rotacion_y_fiabilidad(valores)
    rot_explicito, fiab_explicito = calcular_rotacion_y_fiabilidad(valores, [3, 2, 1])
    assert rot_default == rot_explicito
    assert fiab_default == fiab_explicito


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


def test_issue_183_rotacion_minima_con_stock_alto_no_desborda_decimal_10_2():
    """dias_hasta_quiebre es DECIMAL(10,2) (max 99.999.999,99). rotacion_sugerida
    viene redondeada a 4 decimales, asi que su menor valor no nulo es 0,0001 --
    con stock alto, stock/rotacion desborda el tipo y aborta el executemany
    completo de escribir_sugerencias (mismo modo de fallo que el code-review
    de #116 encontro para chk_sugerencias_rotacion, en otra columna). Se
    acota a MAX_DIAS_HASTA_QUIEBRE en vez de dejar que MySQL lo rechace."""
    resultado = calcular_dias_hasta_quiebre(20000.0, 0.0001, REF, REF)
    assert resultado == MAX_DIAS_HASTA_QUIEBRE
    assert resultado <= 99_999_999.99


def test_issue_183_valor_normal_dentro_del_cap_no_se_toca():
    """El cap no debe interferir con valores normales, muy por debajo del
    limite -- solo el caso extremo que realmente desbordaria la columna."""
    assert calcular_dias_hasta_quiebre(100.0, 5.0, REF, REF) == 20.0


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

        filas, _con, _sin, _quiebre, _huerfanos = calcular_sugerencias(
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


def test_issue_142_sku_que_pierde_toda_elegibilidad_se_limpia_no_queda_huerfano(conn):
    """
    Regresion real de #142: un SKU con una fila vieja en planilla_sugerencias
    (modelo retirado, valores no-nulos) que este ciclo no tiene NI UN mes
    elegible en planilla_ventas_calculada -- nunca entra a por_sku, asi que
    sin el fix su fila vieja jamas se toca. Con el fix, aparece como huerfano
    y se limpia a NULL con el modelo actual (mismo caso real que los 7 SKUs
    encontrados en produccion con weighted_avg_13m).
    """
    sku = "TEST-ISSUE-142-HUERFANO"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM planilla_sugerencias WHERE sku = %s", (sku,))
            cur.execute("SELECT id FROM grupos LIMIT 1")
            grupo_id = cur.fetchone()[0]
            cur.execute(
                "INSERT IGNORE INTO articulos (sku, descripcion, grupo_id) VALUES (%s, 'test issue 142', %s)",
                (sku, grupo_id),
            )
            # Fila vieja simulando un modelo retirado -- sin ningun mes en
            # planilla_ventas_calculada, este SKU no puede entrar a por_sku.
            cur.execute(
                """
                INSERT INTO planilla_sugerencias
                    (sku, rotacion_sugerida, fiabilidad_porcentaje, dias_hasta_quiebre, modelo, ts_generacion)
                VALUES (%s, 12.3456, 80.00, 5.00, 'weighted_avg_13m', NOW(6))
                """,
                (sku,),
            )
        conn.commit()

        filas, _con, _sin, _quiebre, huerfanos = calcular_sugerencias(
            conn, stock_por_sku={}, mes_referencia=(2026, 6)
        )

        assert huerfanos >= 1
        fila = next(f for f in filas if f["sku"] == sku)
        assert fila["rotacion_sugerida"] is None
        assert fila["fiabilidad_porcentaje"] is None
        assert fila["dias_hasta_quiebre"] is None
        assert fila["modelo"] == MODELO  # ya no queda con el modelo retirado
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM planilla_sugerencias WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()


def test_issue_181_calcular_sugerencias_usa_distancia_calendario_no_posicion(conn):
    """
    Test de integracion: sembramos un SKU con 3 meses elegibles NO
    consecutivos (ago-2026, mar-2026, sep-2025) con mes_referencia fijo en
    2026-09 -- mismo caso que los tests unitarios de
    _pesos_por_distancia_calendario de mas arriba -- y confirmamos que
    calcular_sugerencias() efectivamente pasa los pesos calendario reales a
    calcular_rotacion_y_fiabilidad, no los pesos por posicion. Con pesos
    calendario [12, 7, 1] sobre [10, 0, 0] (ago-2026 vendio 10, los otros
    dos 0) da 6.0; el viejo peso por posicion [3, 2, 1] hubiera dado 5.0 --
    si este test da 5.0 en vez de 6.0, calcular_sugerencias() no esta
    pasando `pesos` al llamar a calcular_rotacion_y_fiabilidad.
    """
    sku = "TEST-ISSUE-181"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            cur.execute("SELECT id FROM grupos LIMIT 1")
            grupo_id = cur.fetchone()[0]
            cur.execute(
                "INSERT IGNORE INTO articulos (sku, descripcion, grupo_id) VALUES (%s, 'test issue 181', %s)",
                (sku, grupo_id),
            )
            meses = [(2026, 8, 10.0), (2026, 3, 0.0), (2025, 9, 0.0)]
            for year, month, rot in meses:
                _sembrar_mes(cur, sku, year, month, "normal", rot)
        conn.commit()

        filas, _con, _sin, _quiebre, _huerfanos = calcular_sugerencias(
            conn, stock_por_sku={}, mes_referencia=(2026, 9)
        )
        fila = next(f for f in filas if f["sku"] == sku)
        assert fila["rotacion_sugerida"] == 6.0
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planilla_ventas_calculada WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
