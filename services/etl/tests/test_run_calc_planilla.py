import datetime as dt
import os

import pytest

from run_calc_planilla import (
    TICKETS_ALTO_MIN,
    TICKETS_BAJO_MAX,
    cargar_configuracion,
    cargar_tickets,
    calcular_historico,
    clasificar_estado,
    clasificar_estado_mes,
    extrapolacion_mes,
    meses_disponibles_historico,
    valor_ajustado_y_criterio,
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


def test_calcular_historico_promedia_incluyendo_meses_sin_ventas_como_cero():
    meses_cerrados = [(2026, 3), (2026, 4), (2026, 5)]
    ventas = {("C001", 2026, 3): 30, ("C001", 2026, 5): 30}  # abril sin fila = 0
    historico = calcular_historico("C001", None, meses_cerrados, ventas)
    assert historico == 20.0  # (30 + 0 + 30) / 3


def test_calcular_historico_sin_meses_disponibles_devuelve_none():
    # SKU dado de alta despues del ultimo mes cerrado
    historico = calcular_historico("C002", dt.date(2026, 6, 1), [(2026, 5), (2026, 4)], {})
    assert historico is None


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
