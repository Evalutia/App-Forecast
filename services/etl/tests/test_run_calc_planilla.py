import datetime as dt
import os

import pytest

from run_calc_planilla import (
    TICKETS_ALTO_MIN,
    TICKETS_BAJO_MAX,
    _SQL_STOCK,
    _SQL_STOCK_DIARIO,
    cargar_configuracion,
    cargar_ingreso_durante_quiebre,
    cargar_tickets,
    calcular_historico,
    clasificar_estado,
    clasificar_estado_mes,
    detectar_ingreso_durante_mes,
    extrapolacion_mes,
    meses_disponibles_historico,
    valor_ajustado_y_criterio,
    venta_o_extrapolacion,
    ventana_meses,
)


def _try_connect():
    """
    Conexion real a MySQL para el test de integracion de cargar_tickets --
    se salta con pytest.skip si no hay DB disponible (CI no levanta MySQL
    para services/etl/tests, ver .github/workflows/ci.yml). Usa las mismas
    env vars que db_connect(), con defaults para correr local contra el
    docker-compose del repo (MySQL expuesto en localhost:3307).
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


# ── ventana_meses() ──────────────────────────────────────────────────────────

def test_ventana_meses_devuelve_n_meses_mas_reciente_primero():
    meses = ventana_meses(13, hoy=dt.date(2026, 2, 17))
    assert len(meses) == 13
    assert meses[0] == (2026, 2)
    assert meses[1] == (2026, 1)


def test_ventana_meses_rollover_de_anio():
    meses = ventana_meses(13, hoy=dt.date(2026, 1, 5))
    assert meses[0] == (2026, 1)
    assert meses[1] == (2025, 12)
    assert meses[-1] == (2025, 1)


def test_ventana_meses_sin_fecha_inyectada_usa_hoy():
    hoy = dt.date.today()
    meses = ventana_meses(1)
    assert meses[0] == (hoy.year, hoy.month)


# ── clasificar_estado() — umbral 100%, replica el criterio del cliente ──────
# Issue #36/#37: verificado contra su Excel de referencia (openpyxl) — colorea
# como quiebre el 100% de los meses con al menos 1 día sin stock, sin piso.

@pytest.mark.parametrize(
    "dias_stock,dias_naturales,esperado",
    [
        (0,  30, "sin_stock"),
        (30, 30, "normal"),           # 100% exacto, único caso "normal"
        (29, 30, "quiebre_parcial"),  # 96.7%, un solo día de quiebre — igual cuenta
        (1,  31, "quiebre_parcial"),  # caso real I01089 May/25: 1 día de quiebre sobre 31
        (31, 31, "normal"),
    ],
)
def test_clasificar_estado_mes_cerrado_umbral_100(dias_stock, dias_naturales, esperado):
    assert clasificar_estado(dias_stock, dias_naturales) == esperado


# ── clasificar_estado_mes() — el fix ──────────────────────────────────────────

def test_mes_referencia_dia_17_de_30_con_stock_perfecto_ya_no_es_quiebre():
    """Caso exacto reportado en el bug: día 17 de un mes de 30, stock todos los días."""
    assert clasificar_estado_mes(dias_stock=17, dias_naturales=30, es_mes_referencia=True) == "normal"


def test_mes_referencia_dia_1_con_un_solo_dia_de_stock_ya_es_normal():
    assert clasificar_estado_mes(dias_stock=1, dias_naturales=31, es_mes_referencia=True) == "normal"


def test_mes_referencia_sin_ningun_dia_de_stock_sigue_sin_stock():
    assert clasificar_estado_mes(dias_stock=0, dias_naturales=30, es_mes_referencia=True) == "sin_stock"


@pytest.mark.parametrize(
    "dias_stock,dias_naturales,esperado",
    [
        (0,  30, "sin_stock"),
        (30, 30, "normal"),
        (29, 30, "quiebre_parcial"),
    ],
)
def test_mes_cerrado_via_clasificar_estado_mes_delega_sin_cambios(dias_stock, dias_naturales, esperado):
    assert clasificar_estado_mes(dias_stock, dias_naturales, es_mes_referencia=False) == esperado


# ── valor_ajustado_y_criterio() — blending Historico/Promedio/Real (Issue #61/#63) ──
# Los 4 casos son el ejemplo numerico del mail de Rodrigo (2026-06-27), ver
# .claude/CONTEXTO.md sesion 2026-07-14. El Caso 4 usa dias_naturales_mes real
# (30 para junio) en vez del 30.5 que usa el mail en su ejemplo a mano -- da
# 62.5 en vez del 63.125 literal del mail (decision ya tomada, discrepancia
# minima documentada para QA en #64).

def test_caso1_mail_un_ticket_sin_quiebre_usa_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=10, extrapolacion=None, historico=45.0, es_quiebre=False
    )
    assert (valor, criterio) == (45.0, "historico")


def test_caso2_mail_dos_tickets_sin_quiebre_usa_historico_corte_inclusivo():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=2, ventas_real=20, extrapolacion=None, historico=45.0, es_quiebre=False
    )
    assert (valor, criterio) == (45.0, "historico")


def test_caso3_mail_tres_tickets_sin_quiebre_promedia_historico_y_venta_real():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=30, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert (valor, criterio) == (40.0, "promedio")


def test_caso4_mail_tres_tickets_con_quiebre_promedia_historico_y_extrapolacion():
    """
    Mail: Historico=50, Extrapolacion=(30/12)*30.5=76.25 -> (50+76.25)/2=63.125.
    Con dias_naturales_mes real de junio (30, no 30.5): (30/12)*30=75 ->
    (50+75)/2=62.5. Decision tomada en el grill: usar el dia real, no el
    redondeo casual del mail.
    """
    extrapolacion = round((30 / 12) * 30, 2)  # dias_con_stock=12, dias_naturales_mes=30 (junio real)
    assert extrapolacion == 75.0
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=30, extrapolacion=extrapolacion, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (62.5, "promedio")


def test_cuatro_tickets_sigue_en_banda_promedio_no_alto():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=4, ventas_real=40, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert criterio == "promedio"
    assert valor == 45.0


def test_cinco_tickets_sin_quiebre_usa_venta_real_ignora_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=5, ventas_real=99, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert (valor, criterio) == (99.0, "real_extrapolado")


def test_cinco_tickets_con_quiebre_usa_extrapolacion_ignora_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=5, ventas_real=10, extrapolacion=80.0, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (80.0, "real_extrapolado")


# ── extrapolacion_mes() — Issue #129 ────────────────────────────────────────
# Antes se extrapolaba (ventas / dias_con_stock) * dias_naturales, sin mirar en
# que momento del mes se corto el stock: un articulo que se agota el dia 6 de 30
# se multiplicaba x5. Ahora se proyecta en proporcion a cuanto del mes se pudo
# observar, que acotado da ventas * (2 - ds/dn).

def test_mes_completo_no_extrapola():
    # sin quiebre no hay nada que proyectar: la venta real es el valor
    assert extrapolacion_mes(ventas=30, dias_con_stock=30, dias_naturales=30) == 30.0


def test_issue_129_caso_del_cliente_agota_el_dia_6():
    # 6 unidades en 6 dias de 30. Antes: (6/6)*30 = 30 (x5). Ahora: 6*(2-0.2) = 10.8
    assert extrapolacion_mes(ventas=6, dias_con_stock=6, dias_naturales=30) == 10.8


def test_issue_129_caso_del_cliente_agota_el_dia_29_queda_casi_igual():
    """
    El cliente escribio que en este caso "iba a vender tan solo un 3% mas".
    La formula da x1.0333 sin haberse calibrado para eso -- es la validacion
    mas fuerte del criterio elegido.
    """
    valor = extrapolacion_mes(ventas=29, dias_con_stock=29, dias_naturales=30)
    assert valor == 29.97                                # el valor se guarda con 2 decimales
    assert valor / 29 == pytest.approx(1.0333, abs=0.0005)


def test_issue_129_importacion_que_entra_a_fin_de_mes():
    # 5 dias con stock de 30. Antes x6.00, ahora x1.83
    assert extrapolacion_mes(ventas=5, dias_con_stock=5, dias_naturales=30) == 9.17   # x1.83


@pytest.mark.parametrize("ds,dn", [(1, 30), (1, 31), (2, 28), (3, 31)])
def test_issue_129_el_multiplicador_nunca_supera_x2(ds, dn):
    """El tope emerge de la formula, no de un parametro: 2 - ds/dn < 2 siempre."""
    ventas = 10
    assert extrapolacion_mes(ventas, ds, dn) < 2 * ventas


def test_issue_129_es_continua_no_tiene_escalones():
    """
    A igual venta, cortar el stock el dia 15 o el 16 da practicamente lo mismo:
    no hay escalon arbitrario a mitad de mes. Un tope duro ("maximo x2") si lo
    tendria, y justo donde caen mas articulos.
    """
    a = extrapolacion_mes(ventas=100, dias_con_stock=15, dias_naturales=30)
    b = extrapolacion_mes(ventas=100, dias_con_stock=16, dias_naturales=30)
    assert abs(b - a) < 4.0            # ~3.3 sobre un valor de ~150
    assert b < a                       # y va en la direccion correcta


def test_issue_129_proyecta_mas_cuanto_menos_se_observo():
    """
    Misma venta, menos dias observados -> mas proyeccion. Es la direccion
    correcta: si vendiste 40 unidades en 1 dia, el mes completo daba mucho mas
    que si las vendiste en 30 dias. Lo que cambia respecto de la formula vieja
    no es el sentido sino cuanto: antes x30, ahora x1.97 como techo.
    """
    valores = [extrapolacion_mes(40, ds, 30) for ds in (30, 20, 10, 5, 1)]
    assert valores == sorted(valores)                    # estrictamente creciente
    assert valores[0] == 40.0                            # mes completo: sin proyectar
    assert valores[-1] < 80.0                            # el ultimo, aun asi, por debajo del doble


def test_issue_129_venta_negativa_no_se_extrapola():
    """
    Desde #80 un mes puede cerrar en negativo por notas de credito. Amplificar
    una devolucion por haber tenido poco stock no significa nada.
    """
    assert extrapolacion_mes(ventas=-5, dias_con_stock=6, dias_naturales=30) == -5.0


def test_issue_129_venta_cero_no_se_extrapola():
    assert extrapolacion_mes(ventas=0, dias_con_stock=6, dias_naturales=30) == 0.0


@pytest.mark.parametrize("ds,dn", [(0, 30), (-1, 30), (6, 0)])
def test_sin_base_para_proyectar_devuelve_none(ds, dn):
    """
    dias_con_stock=0 es el mes sin_stock: no hay ritmo observado del que partir.
    Devolver None mantiene el comportamiento previo -- valor_ajustado_y_criterio
    lo hace caer a Historico.
    """
    assert extrapolacion_mes(ventas=10, dias_con_stock=ds, dias_naturales=dn) is None


# ── extrapolacion_mes(p=...) — Issue #144 ────────────────────────────────────
# Rodrigo contrapropuso generalizar #129 con un exponente `p`: w = (d/D)**p,
# estimacion = ventas * (1 + w * (D/d - 1)). p=1 es la formula de #129 (la que
# sigue en produccion); p=0.5 es lo que el pidio. La medicion de que p predice
# mejor esta en #144 / CONTEXTO.md -- estos tests solo verifican que la formula
# generalizada es correcta, no deciden el valor de produccion.

@pytest.mark.parametrize(
    "ventas,ds,dn",
    [(30, 30, 30), (6, 6, 30), (29, 29, 30), (5, 5, 30), (40, 1, 30), (100, 16, 30)],
)
def test_p_default_es_1_y_reproduce_exactamente_la_formula_de_129(ventas, ds, dn):
    """
    Regresion: no pasar `p` (el caso de todos los call sites de produccion
    hoy) tiene que dar bit a bit el mismo resultado que antes de parametrizar
    -- produccion no cambia con este refactor.
    """
    sin_p = extrapolacion_mes(ventas, ds, dn)
    con_p_explicito = extrapolacion_mes(ventas, ds, dn, p=1.0)
    formula_129 = round(ventas * (2 - ds / dn), 2)
    assert sin_p == con_p_explicito == formula_129


@pytest.mark.parametrize(
    "ventas,ds,dn,multiplicador_p05",
    [
        (100, 6, 30, 2.79),    # issue #144: "se agota dia 6 (6/30)"
        (100, 15, 30, 1.71),   # issue #144: "mitad de mes (15/30)"
        (100, 29, 30, 1.03),   # issue #144: "se agota dia 29 (29/30)"
        (100, 5, 30, 3.04),    # issue #144: "importacion dia 25 (5/30)"
    ],
)
def test_p_0_5_reproduce_los_ejemplos_verificados_de_rodrigo(ventas, ds, dn, multiplicador_p05):
    valor = extrapolacion_mes(ventas, ds, dn, p=0.5)
    assert valor / ventas == pytest.approx(multiplicador_p05, abs=0.005)


def test_p_menor_a_1_proyecta_mas_que_p_1():
    """p=0.5 (lo que pidio Rodrigo) da un valor mayor que p=1 (produccion) --
    es justamente lo que el issue #144 describe: "proyecta mas"."""
    con_p1 = extrapolacion_mes(ventas=30, dias_con_stock=1, dias_naturales=31, p=1.0)
    con_p05 = extrapolacion_mes(ventas=30, dias_con_stock=1, dias_naturales=31, p=0.5)
    assert con_p05 > con_p1


def test_p_menor_a_1_pierde_el_tope_de_x2():
    """
    El caso real de I02552 citado en #144: 30 unidades en 1 solo dia de 31.
    Con p=1 el multiplicador esta acotado en [1,2) por construccion; con
    p=0.5 no hay tope y crece bastante mas alla del doble.
    """
    con_p1 = extrapolacion_mes(ventas=30, dias_con_stock=1, dias_naturales=31, p=1.0)
    con_p05 = extrapolacion_mes(ventas=30, dias_con_stock=1, dias_naturales=31, p=0.5)
    assert con_p1 < 2 * 30
    assert con_p05 > 2 * 30


def test_p_mayor_a_1_proyecta_menos_que_p_1():
    con_p1 = extrapolacion_mes(ventas=30, dias_con_stock=6, dias_naturales=30, p=1.0)
    con_p15 = extrapolacion_mes(ventas=30, dias_con_stock=6, dias_naturales=30, p=1.5)
    assert con_p15 < con_p1


def test_p_no_afecta_los_casos_borde_de_ventas_o_dias():
    """Los guard clauses (sin_stock -> None, venta<=0 -> sin extrapolar) son
    anteriores a aplicar `p` -- cualquier valor de p da el mismo resultado ahi."""
    for p in (0.25, 0.5, 1.0, 1.5, 2.0):
        assert extrapolacion_mes(ventas=10, dias_con_stock=0, dias_naturales=30, p=p) is None
        assert extrapolacion_mes(ventas=0, dias_con_stock=6, dias_naturales=30, p=p) == 0.0
        assert extrapolacion_mes(ventas=-5, dias_con_stock=6, dias_naturales=30, p=p) == -5.0


# ── venta_o_extrapolacion() -- Issue #137 ────────────────────────────────────
# "V/E" de la hoja de detalle, persistido para que ya no haga falta
# recalcularlo en el browser (la fuente de la desincronizacion real de #129).

def test_venta_o_extrapolacion_mes_normal_es_la_venta_real():
    assert venta_o_extrapolacion("normal", ventas_cantidad=42, extrapolacion=None) == 42.0


def test_venta_o_extrapolacion_sin_stock_es_none_sin_importar_la_extrapolacion():
    """
    Distinto de valor_no_historico (dentro de valor_ajustado_y_criterio):
    ese cae a ventas_cantidad cuando sin_stock+sin historico. V/E en cambio
    queda vacio siempre para sin_stock, igual que promete la hoja
    "Criterios" ("Vacia si el mes no tuvo stock").
    """
    assert venta_o_extrapolacion("sin_stock", ventas_cantidad=5, extrapolacion=None) is None
    assert venta_o_extrapolacion("sin_stock", ventas_cantidad=5, extrapolacion=9.17) is None


def test_venta_o_extrapolacion_quiebre_parcial_usa_la_extrapolacion():
    assert venta_o_extrapolacion("quiebre_parcial", ventas_cantidad=6, extrapolacion=10.8) == 10.8


def test_venta_o_extrapolacion_quiebre_parcial_sin_extrapolacion_es_none():
    """No deberia pasar en la practica (quiebre_parcial siempre tiene
    dias_con_stock > 0), pero no debe inventar un valor si pasara."""
    assert venta_o_extrapolacion("quiebre_parcial", ventas_cantidad=6, extrapolacion=None) is None


# ── Fallbacks no cubiertos por el mail (decididos en la sesion de grill-me) ──

def test_sin_stock_extrapolacion_indefinida_cae_a_historico_sin_importar_tickets():
    """sin_stock (dias_con_stock=0) -> Extrapolacion=None. Cae a Historico
    incluso con tickets>=5, donde normalmente no se usaria Historico."""
    valor, criterio = valor_ajustado_y_criterio(
        tickets=10, ventas_real=5, extrapolacion=None, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (50.0, "historico")


def test_sin_stock_y_sin_historico_usa_venta_real_como_ultimo_recurso():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=7, extrapolacion=None, historico=None, es_quiebre=True
    )
    assert (valor, criterio) == (7.0, "real_extrapolado")


def test_sku_nuevo_sin_historico_tickets_bajo_usa_venta_real_sin_promediar():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=12, extrapolacion=None, historico=None, es_quiebre=False
    )
    assert (valor, criterio) == (12.0, "real_extrapolado")


def test_sku_nuevo_sin_historico_tickets_medio_usa_venta_real_sin_promediar():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=12, extrapolacion=None, historico=None, es_quiebre=False
    )
    assert (valor, criterio) == (12.0, "real_extrapolado")


# ── meses_disponibles_historico() / calcular_historico() — Issue #63 ────────────

def test_meses_disponibles_sin_fec_alta_devuelve_todos():
    meses = [(2026, 5), (2026, 4), (2026, 3)]
    assert meses_disponibles_historico(None, meses) == meses


def test_meses_disponibles_excluye_meses_antes_de_fec_alta():
    meses = [(2026, 5), (2026, 4), (2026, 3)]
    # SKU dado de alta el 15 de abril 2026 -> marzo queda excluido, abril y mayo quedan
    disponibles = meses_disponibles_historico(dt.date(2026, 4, 15), meses)
    assert set(disponibles) == {(2026, 5), (2026, 4)}


def test_calcular_historico_promedia_incluyendo_mes_sin_venta_real_como_cero():
    """Mes 'normal' (tuvo stock) sin fila en ventas_historicas SI cuenta como
    "vendio cero" -- es un dato real, no un mes sin_stock. Issue #163
    (code review de #63) separa explicitamente este caso del de abajo, que
    el test viejo confundia al no pasar estados en absoluto."""
    meses_cerrados = [(2026, 3), (2026, 4), (2026, 5)]
    ventas = {("C001", 2026, 3): 30, ("C001", 2026, 5): 30}  # abril sin fila = 0
    estados = {
        ("C001", 2026, 3): "normal",
        ("C001", 2026, 4): "normal",
        ("C001", 2026, 5): "normal",
    }
    historico = calcular_historico("C001", None, meses_cerrados, ventas, estados, {})
    assert historico == 20.0  # (30 + 0 + 30) / 3


def test_calcular_historico_excluye_meses_sin_stock():
    """Issue #163: un mes sin_stock no es "vendio cero", es "no sabemos" --
    se excluye del promedio (ni suma ni denominador), mismo criterio que
    #116 ya aplico a rotacion_ajustada en run_calc_sugerencias.py."""
    meses_cerrados = [(2026, 3), (2026, 4), (2026, 5)]
    ventas = {("C001", 2026, 3): 30, ("C001", 2026, 5): 30}
    estados = {
        ("C001", 2026, 3): "normal",
        ("C001", 2026, 4): "sin_stock",  # se excluye, aunque no tenga fila en ventas
        ("C001", 2026, 5): "normal",
    }
    historico = calcular_historico("C001", None, meses_cerrados, ventas, estados, {})
    assert historico == 30.0  # (30 + 30) / 2, abril no cuenta


def test_calcular_historico_todos_los_meses_sin_stock_devuelve_none():
    meses_cerrados = [(2026, 4), (2026, 5)]
    estados = {("C001", 2026, 4): "sin_stock", ("C001", 2026, 5): "sin_stock"}
    historico = calcular_historico("C001", None, meses_cerrados, {}, estados, {})
    assert historico is None


def test_calcular_historico_usa_extrapolacion_no_venta_cruda_en_quiebre_parcial():
    """Issue #163: un mes quiebre_parcial aporta al historico su venta
    extrapolada (proyectada al mes completo), no la venta cruda deprimida
    por el propio quiebre -- mismo ajuste que #116 aplico a
    rotacion_ajustada."""
    meses_cerrados = [(2026, 4), (2026, 5)]
    ventas = {("C001", 2026, 4): 10, ("C001", 2026, 5): 30}
    estados = {("C001", 2026, 4): "quiebre_parcial", ("C001", 2026, 5): "normal"}
    extrapolaciones = {("C001", 2026, 4): 22.0}  # ej: 10 vendidas con medio mes de stock
    historico = calcular_historico("C001", None, meses_cerrados, ventas, estados, extrapolaciones)
    assert historico == 26.0  # (22 + 30) / 2, no (10 + 30) / 2


def test_calcular_historico_quiebre_parcial_sin_extrapolacion_usa_venta_cruda():
    """Fallback defensivo: si por algun motivo no hay extrapolacion
    calculada para un mes quiebre_parcial (no deberia pasar en el flujo
    real, extrapolacion_mes() siempre devuelve algo con dias_con_stock>0),
    no se pierde el mes -- cae a la venta cruda en vez de romper."""
    meses_cerrados = [(2026, 4)]
    ventas = {("C001", 2026, 4): 10}
    estados = {("C001", 2026, 4): "quiebre_parcial"}
    historico = calcular_historico("C001", None, meses_cerrados, ventas, estados, {})
    assert historico == 10.0


def test_calcular_historico_sin_meses_disponibles_devuelve_none():
    # SKU dado de alta despues del ultimo mes cerrado
    historico = calcular_historico(
        "C002", dt.date(2026, 6, 1), [(2026, 5), (2026, 4)], {}, {}, {},
    )
    assert historico is None


def test_calcular_historico_mes_sin_fila_en_ningun_lado_usa_default_normal():
    """Un mes ausente de `estados` (ni fila en ventas_historicas ni en
    stock_diario -- no llega a entrar a `filas` en calcular_filas()) cae al
    default 'normal'/0 de estados.get(), no a un KeyError ni a 'sin_stock'.
    Mismo comportamiento heredado que el docstring ya documentaba para "mes
    sin fila en ventas" -- este test fija ese contrato explicitamente en vez
    de dejarlo cubierto solo por casualidad (hallazgo de /code-review)."""
    meses_cerrados = [(2026, 3), (2026, 4)]
    ventas = {("C001", 2026, 3): 30}  # abril: ausente de ventas Y de estados
    estados = {("C001", 2026, 3): "normal"}  # abril deliberadamente sin clave
    historico = calcular_historico("C001", None, meses_cerrados, ventas, estados, {})
    assert historico == 15.0  # (30 + 0) / 2 -- abril cuenta como "vendio cero"


# ── cargar_tickets() -- regresion del bug de #64 (dias con cantidad=0 inflaban tickets) ──

def test_cargar_tickets_excluye_filas_con_cantidad_cero():
    conn = _try_connect()
    sku = "TESTTICKETS01"
    try:
        with conn.cursor() as cur:
            # Idempotente: limpia un fixture residual de una corrida anterior
            # cortada a mitad de camino (kill/timeout entre el commit y el
            # finally) antes de insertar, en vez de fallar con PK duplicada.
            cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
            # Issue #121: articulo_grupo tiene FK RESTRICT a articulos(sku).
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
            cur.execute(
                "INSERT INTO articulos (sku, descripcion, grupo_id) VALUES (%s, %s, %s)",
                (sku, "SKU de prueba -- regresion tickets #64", 201),
            )
            # 5 dias con venta real (cantidad != 0), 3 dias "sin venta" que
            # igual tienen fila con cantidad=0 -- mismo patron que produccion.
            rows = [(sku, dt.date(2026, 6, d), 3, "test") for d in range(1, 6)]
            rows += [(sku, dt.date(2026, 6, d), 0, "test") for d in range(6, 9)]
            cur.executemany(
                "INSERT INTO ventas_historicas (sku, fecha, cantidad, fuente) VALUES (%s, %s, %s, %s)",
                rows,
            )
        conn.commit()

        tickets = cargar_tickets(
            conn,
            fecha_desde=dt.date(2026, 6, 1),
            fecha_hasta=dt.date(2026, 6, 30),
            meses_set={(2026, 6)},
        )

        assert tickets.get((sku, 2026, 6)) == 5, (
            f"esperaba 5 tickets (dias con venta real), dio {tickets.get((sku, 2026, 6))} "
            "-- si da 30, volvio el bug de contar dias con cantidad=0"
        )
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (sku,))
            # Issue #121: articulo_grupo tiene FK RESTRICT a articulos(sku).
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()


# ── cargar_configuracion() -- Issue #67 (umbrales editables por el admin) ──

def test_cargar_configuracion_lee_valores_reales_de_la_tabla():
    # No hardcodea 2/5 -- son las claves reales que un admin puede editar
    # desde la UI (#67), asumir un valor fijo haria este test fragil ante
    # cualquier cambio legitimo. Compara contra lo que la tabla dice AHORA.
    conn = _try_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT clave, valor FROM configuracion_sistema "
                "WHERE clave IN ('tickets_bajo_max', 'tickets_alto_min')"
            )
            esperado = {clave: int(valor) for clave, valor in cur.fetchall()}

        config = cargar_configuracion(conn)

        assert config["tickets_bajo_max"] == esperado["tickets_bajo_max"]
        assert config["tickets_alto_min"] == esperado["tickets_alto_min"]
    finally:
        conn.close()


def test_cargar_configuracion_usa_default_si_falta_la_clave():
    conn = _try_connect()
    try:
        with conn.cursor() as cur:
            # Guarda la fila completa (no solo valor) para restaurarla igual
            # a como estaba -- una restauracion parcial deja la tabla real
            # distinta a como la encontro (ej. perdiendo la descripcion).
            cur.execute(
                "SELECT valor, descripcion, actualizado_por FROM configuracion_sistema "
                "WHERE clave = 'tickets_alto_min'"
            )
            fila_original = cur.fetchone()
            assert fila_original is not None, (
                "falta seed de tickets_alto_min -- aplicar infra/sql/17-configuracion-sistema.sql"
            )
            valor_original, descripcion_original, actualizado_por_original = fila_original
            cur.execute("DELETE FROM configuracion_sistema WHERE clave = 'tickets_alto_min'")
        conn.commit()

        config = cargar_configuracion(conn)

        assert config["tickets_alto_min"] == TICKETS_ALTO_MIN, (
            "sin la clave en la tabla, tiene que caer al default del modulo"
        )
        assert config["tickets_bajo_max"] == TICKETS_BAJO_MAX
    finally:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO configuracion_sistema (clave, valor, descripcion, actualizado_por) "
                "VALUES ('tickets_alto_min', %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE valor = VALUES(valor), descripcion = VALUES(descripcion), "
                "actualizado_por = VALUES(actualizado_por)",
                (valor_original, descripcion_original, actualizado_por_original),
            )
        conn.commit()
        conn.close()


# ── _SQL_STOCK -- FORCE INDEX, issue #153 (diagnostico #149) ────────────────────
# Sin el hint, MySQL elige idx_stock_sku_fecha (sku primero) y escanea la tabla
# entera antes de filtrar por fecha -- 120,5M de 121M filas medido en produccion.
# idx_stock_fecha (fecha primero) evita eso. Ver CONTEXTO.md para el detalle.

def test_sql_stock_contiene_el_force_index():
    """Guardrail principal: no depende de una DB real ni de cuanto elija MySQL
    por su cuenta (con el volumen chico de la replica local, MySQL puede elegir
    idx_stock_fecha igual SIN el hint -- ver test_sql_stock_usa_force_index_idx_stock_fecha
    de abajo, que por eso solo no alcanza como regresion)."""
    assert "FORCE INDEX" in _SQL_STOCK
    assert "idx_stock_fecha" in _SQL_STOCK


def test_sql_stock_usa_force_index_idx_stock_fecha():
    """Falla si alguien saca el FORCE INDEX sin darse cuenta: sin el hint, MySQL
    puede volver a elegir idx_stock_sku_fecha (el plan lento de #149)."""
    conn = _try_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN " + _SQL_STOCK,
                (dt.date(2026, 1, 1), dt.date(2026, 1, 31)),
            )
            filas = cur.fetchall()
            columnas = [d[0] for d in cur.description]

        idx_select_type = columnas.index("select_type")
        idx_key         = columnas.index("key")
        # DERIVED = el subquery interno sobre stock_diario -- se busca por
        # select_type en vez de por nombre de tabla porque el subquery usa
        # alias ("sd"), y EXPLAIN muestra el alias, no "stock_diario".
        fila_stock = next(f for f in filas if f[idx_select_type] == "DERIVED")

        assert fila_stock[idx_key] == "idx_stock_fecha", (
            f"esperaba idx_stock_fecha, MySQL eligio {fila_stock[idx_key]!r} -- "
            "revisar que el FORCE INDEX siga en _SQL_STOCK"
        )
    finally:
        conn.close()


def test_sql_stock_respeta_stock_minimo_como_umbral_estricto():
    """Verifica con datos reales que el FORCE INDEX no cambio el resultado:
    un dia con stock exactamente igual al minimo NO cuenta como "con stock"
    (la query usa `>`, no `>=` -- ver issue #135 sobre este criterio)."""
    conn = _try_connect()
    sku = "TESTFORCEIDX01"
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
            cur.execute(_SQL_STOCK, (dt.date(2026, 1, 1), dt.date(2026, 1, 31)))
            resultado = {(r[0], r[1], r[2]): r[3] for r in cur.fetchall()}

        assert resultado.get((sku, 2026, 1)) == 1, (
            f"esperaba 1 dia con stock (solo el de cantidad=10), dio {resultado.get((sku, 2026, 1))}"
        )
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()


# ── detectar_ingreso_durante_mes() -- issue #145 ─────────────────────────────

def test_ingreso_stock_llega_a_mitad_de_mes():
    assert detectar_ingreso_durante_mes([0, 0, 0, 5, 5, 5]) is True


def test_quiebre_comun_se_agota_y_no_repone():
    assert detectar_ingreso_durante_mes([5, 5, 5, 0, 0, 0]) is False


def test_sin_stock_en_absoluto_no_es_ingreso():
    assert detectar_ingreso_durante_mes([0, 0, 0]) is False


def test_stock_completo_todo_el_mes_no_es_ingreso():
    assert detectar_ingreso_durante_mes([5, 5, 5]) is False


def test_un_solo_dia_de_dato_nunca_es_ingreso():
    assert detectar_ingreso_durante_mes([5]) is False
    assert detectar_ingreso_durante_mes([0]) is False


def test_sin_dias_de_dato_no_es_ingreso():
    assert detectar_ingreso_durante_mes([]) is False


def test_ingreso_seguido_de_otro_quiebre_sigue_contando_como_ingreso():
    """Entró y volvió a agotarse en el mismo mes -- igual hubo una importación
    real que el cliente quiere ver marcada, no hace falta que dure hasta fin de mes."""
    assert detectar_ingreso_durante_mes([0, 5, 0, 5]) is True


def test_stock_negativo_por_devolucion_cuenta_como_cero_no_como_positivo():
    """cantidad puede dar neto negativo por una devolucion grande (#80) --
    no debe interpretarse como \"tenia stock\"."""
    assert detectar_ingreso_durante_mes([-3, -3, 5]) is True
    assert detectar_ingreso_durante_mes([5, 5, -3]) is False


# ── detectar_ingreso_durante_mes(stock_minimo=...) -- issue #164 ────────────
# El bug: el umbral de "tiene stock" usaba `stock <= 0` en vez del que ya usa
# dias_con_stock/_SQL_STOCK (`stock > stock_minimo`). El 88% del catalogo
# tiene stock_minimo > 0 (ver CONTEXTO.md, auditoria 2026-08-19, hallazgo
# C2) -- para esos SKUs el flag era estructuralmente inalcanzable: 61% de
# los meses quiebre_parcial nunca tocan stock=0 literal, solo caen por
# debajo de stock_minimo.

def test_con_stock_minimo_detecta_ingreso_sin_tocar_cero_literal():
    """El caso mayoritario que el bug dejaba sin poder dispararse: el stock
    cae a 3 (bajo el minimo de 5) y sube a 8 -- nunca toca 0, pero es
    exactamente la transicion sin-stock -> con-stock que #145 pidio marcar."""
    assert detectar_ingreso_durante_mes([3, 3, 3, 8, 8], stock_minimo=5) is True


def test_con_stock_minimo_quiebre_que_nunca_se_recupera_no_es_ingreso():
    """Quiebre parcial que se queda todo el mes por debajo del minimo -- no
    hubo ingreso real, tiene que seguir dando False."""
    assert detectar_ingreso_durante_mes([3, 3, 3, 3], stock_minimo=5) is False


def test_con_stock_minimo_umbral_estricto_igual_al_minimo_cuenta_como_sin_stock():
    """Mismo criterio estricto que _SQL_STOCK (`>`, no `>=`) -- stock ==
    stock_minimo NO es "con stock" (ver test_sql_stock_respeta_stock_minimo_
    como_umbral_estricto, issue #153)."""
    assert detectar_ingreso_durante_mes([5, 5, 8], stock_minimo=5) is True
    assert detectar_ingreso_durante_mes([8, 8, 5], stock_minimo=5) is False


def test_sin_pasar_stock_minimo_el_default_reproduce_el_comportamiento_previo():
    """Regresion: sin pasar stock_minimo (default 0, el caso del 12% del
    catalogo con stock_minimo=0) el resultado tiene que ser bit a bit el
    mismo que antes del fix de #164."""
    assert detectar_ingreso_durante_mes([0, 0, 0, 5, 5, 5]) is True
    assert detectar_ingreso_durante_mes([5, 5, 5, 0, 0, 0]) is False


# ── cargar_ingreso_durante_quiebre() -- integracion, issue #145 ─────────────

def test_cargar_ingreso_durante_quiebre_detecta_transicion_real():
    conn = _try_connect()
    sku = "TESTINGRESO01"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
            cur.execute(
                "INSERT INTO articulos (sku, descripcion, grupo_id, stock_minimo) "
                "VALUES (%s, %s, %s, %s)",
                (sku, "SKU de prueba -- ingreso durante quiebre #145", 201, 0),
            )
            cur.executemany(
                "INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id) VALUES (%s, %s, %s, %s)",
                [
                    (sku, dt.date(2026, 2, 1), 0, "TEST"),
                    (sku, dt.date(2026, 2, 2), 0, "TEST"),
                    (sku, dt.date(2026, 2, 15), 8, "TEST"),  # llegó la importación acá
                    (sku, dt.date(2026, 2, 20), 6, "TEST"),
                ],
            )
        conn.commit()

        resultado = cargar_ingreso_durante_quiebre(
            conn, dt.date(2026, 2, 1), dt.date(2026, 2, 28), {(2026, 2)}
        )

        assert resultado.get((sku, 2026, 2)) is True
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()


def test_cargar_ingreso_durante_quiebre_con_stock_minimo_mayor_a_cero():
    """Issue #164: caso mayoritario (88% del catalogo) que el test original
    de #145 no cubria -- ese test usaba stock_minimo=0, el 12% minoritario
    donde el umbral viejo (`stock<=0`) coincidia con el correcto por
    casualidad. Aca stock_minimo=5 y el stock nunca toca 0 literal, solo cae
    por debajo del minimo y despues sube -- antes del fix esto daba False
    por construccion."""
    conn = _try_connect()
    sku = "TESTINGRESO02"
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
            cur.execute(
                "INSERT INTO articulos (sku, descripcion, grupo_id, stock_minimo) "
                "VALUES (%s, %s, %s, %s)",
                (sku, "SKU de prueba -- ingreso durante quiebre con stock_minimo>0 #164", 201, 5),
            )
            cur.executemany(
                "INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id) VALUES (%s, %s, %s, %s)",
                [
                    (sku, dt.date(2026, 3, 1), 3, "TEST"),   # bajo el minimo, nunca 0
                    (sku, dt.date(2026, 3, 2), 3, "TEST"),
                    (sku, dt.date(2026, 3, 15), 8, "TEST"),  # llegó la importación acá
                    (sku, dt.date(2026, 3, 20), 6, "TEST"),
                ],
            )
        conn.commit()

        resultado = cargar_ingreso_durante_quiebre(
            conn, dt.date(2026, 3, 1), dt.date(2026, 3, 31), {(2026, 3)}
        )

        assert resultado.get((sku, 2026, 3)) is True, (
            "con stock_minimo=5 y stock que nunca toca 0 pero cruza el minimo, "
            "tiene que detectar el ingreso -- si da False/None volvio el bug de #164"
        )
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_diario WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (sku,))
            cur.execute("DELETE FROM articulos WHERE sku = %s", (sku,))
        conn.commit()
        conn.close()


def test_sql_stock_diario_usa_force_index_idx_stock_fecha():
    """Mismo guardrail que _SQL_STOCK/_SQL_RESUMEN_STOCK (#153): sin el hint,
    MySQL puede volver a elegir idx_stock_sku_fecha (el plan lento de #149)."""
    assert "FORCE INDEX" in _SQL_STOCK_DIARIO
    assert "idx_stock_fecha" in _SQL_STOCK_DIARIO

    conn = _try_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN " + _SQL_STOCK_DIARIO, (dt.date(2026, 1, 1), dt.date(2026, 1, 31)))
            filas = cur.fetchall()
            columnas = [d[0] for d in cur.description]

        idx_key = columnas.index("key")
        # Consulta simple sin subquery derivada -- una sola fila de plan.
        assert filas[0][idx_key] == "idx_stock_fecha"
    finally:
        conn.close()
