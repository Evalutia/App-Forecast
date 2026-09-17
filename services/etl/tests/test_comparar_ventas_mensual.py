"""
Tests de las funciones puras de scripts/comparar_ventas_mensual.py (issue
#196). Mismo patrón que #195: el script vive en scripts/, se agrega ese
directorio al path -- no hay paquete que importar.

Las funciones de I/O (conexión a MySQL) no se testean acá: se verifican por
integración contra producción, vía túnel SSH, igual que #127/#187/#195. Estos
tests cubren la lógica de comparación y categorización, que es la que puede
tener un bug silencioso sin que la corrida contra la DB real lo note.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from cargador_archivos_cliente import ArticuloCliente  # noqa: E402
from comparar_ventas_mensual import (  # noqa: E402
    FECHA_CORTE_COHORTE,
    adjuntar_descomposicion_diaria,
    cohorte_de_mes,
    construir_dataset_discrepancias,
    generar_ventana,
    resumen_categorias,
    resumen_por_cohorte,
    totales_mensuales_cliente,
    totales_mensuales_nuestros,
    unidades_excluidas_por_restriccion,
    ventana_desde_ventas_cliente,
)


def _articulo(sku, ventas):
    return ArticuloCliente(sku=sku, descripcion=None, barcode=None, ventas=dict(ventas),
                           rotaciones={}, rot_desestac=None, rot_manual=None, estado="A")


# ── generar_ventana ──────────────────────────────────────────────────────────

def test_generar_ventana_13_meses_desde_ago_2025():
    ventana = generar_ventana((2025, 8), 13)
    assert len(ventana) == 13
    assert ventana[0] == (2025, 8)
    assert ventana[-1] == (2026, 8)
    assert ventana[11] == (2026, 7)  # cruza el año sin salto


# ── ventana_desde_ventas_cliente ─────────────────────────────────────────────
#
# La ventana se lee del archivo, no de una constante hardcodeada: el próximo
# que mande el cliente va a estar corrido un mes (o más), igual que #195 ya
# resolvió para `parse_mes` -- si la ventana quedara fija, el archivo nuevo se
# compararía en silencio contra los meses viejos.

def test_ventana_se_deriva_de_los_meses_presentes_en_el_archivo():
    cliente = {"C001": _articulo("C001", {(2025, 8): 1, (2025, 9): 2, (2025, 10): 3})}
    assert ventana_desde_ventas_cliente(cliente) == [(2025, 8), (2025, 9), (2025, 10)]


def test_ventana_junta_los_meses_de_todos_los_articulos():
    # No todos los artículos traen el mismo diccionario de meses poblado (un
    # SKU puede no tener venta en el primer mes, por ejemplo), así que la
    # ventana se arma con la unión, no con el primero que aparezca.
    cliente = {
        "C001": _articulo("C001", {(2025, 9): 1}),
        "C002": _articulo("C002", {(2025, 8): 1, (2025, 10): 1}),
    }
    assert ventana_desde_ventas_cliente(cliente) == [(2025, 8), (2025, 9), (2025, 10)]


def test_ventana_vacia_falla_fuerte():
    with pytest.raises(ValueError):
        ventana_desde_ventas_cliente({})


def test_ventana_no_contigua_falla_fuerte():
    # Un header roto que salte un mes no debería colarse como una ventana de
    # 2 meses discontinuos -- mejor un error claro que un resultado silencioso
    # y mal armado.
    cliente = {"C001": _articulo("C001", {(2025, 8): 1, (2025, 10): 1})}  # falta 09
    with pytest.raises(ValueError, match="contigua"):
        ventana_desde_ventas_cliente(cliente)


# ── cohorte_de_mes ───────────────────────────────────────────────────────────
#
# El corte real es 2026-07-24: todo lo cargado antes viene del extractor viejo,
# lo cargado desde ahí es de #192 (extractor nuevo). Julio/2026 queda partido
# por la mitad -- un mes que no se puede tagear con una sola cohorte sin mentir.

@pytest.mark.parametrize("year,month,esperado", [
    (2025, 8, "pre"),
    (2026, 6, "pre"),
    (2026, 8, "post"),
    (2026, 7, "mixto"),
])
def test_cohorte_de_mes(year, month, esperado):
    assert cohorte_de_mes(year, month) == esperado


def test_fecha_corte_es_la_documentada():
    assert (FECHA_CORTE_COHORTE.year, FECHA_CORTE_COHORTE.month, FECHA_CORTE_COHORTE.day) \
        == (2026, 7, 24)


# ── construir_dataset_discrepancias ──────────────────────────────────────────

VENTANA_CHICA = [(2025, 8), (2025, 9)]


def test_dataset_marca_coincide_cuando_no_vendio_y_nosotros_tampoco():
    cliente = {"C001": _articulo("C001", {(2025, 8): None, (2025, 9): None})}
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, VENTANA_CHICA)
    fila = next(f for f in filas if f.year == 2025 and f.month == 8)
    assert fila.cliente_original is None
    assert fila.cliente_numerico == 0
    assert fila.nuestro == 0
    assert fila.diff_abs == 0
    assert fila.categoria == "coincide"


def test_dataset_marca_deficit_cuando_tenemos_menos():
    cliente = {"C001": _articulo("C001", {(2025, 8): 10, (2025, 9): None})}
    agregados = {("C001", 2025, 8): 7}
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, VENTANA_CHICA)
    fila = next(f for f in filas if f.month == 8)
    assert fila.cliente_original == 10
    assert fila.nuestro == 7
    assert fila.diff_abs == -3
    assert fila.diff_rel == pytest.approx(-0.3)
    assert fila.categoria == "deficit"


def test_dataset_marca_superavit_cuando_tenemos_mas():
    cliente = {"C001": _articulo("C001", {(2025, 8): None, (2025, 9): None})}
    agregados = {("C001", 2025, 8): 5}
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, VENTANA_CHICA)
    fila = next(f for f in filas if f.month == 8)
    # cliente reporta None (nunca escribe 0 explícito) -- para la aritmética
    # eso vale 0, pero el original se preserva por separado.
    assert fila.cliente_original is None
    assert fila.cliente_numerico == 0
    assert fila.diff_abs == 5
    assert fila.diff_rel is None  # base 0: no hay porcentaje que calcular
    assert fila.categoria == "superavit"


def test_dataset_ignora_skus_fuera_del_conjunto_comun():
    cliente = {"C001": _articulo("C001", {(2025, 8): 10}),
               "C999": _articulo("C999", {(2025, 8): 99})}
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, VENTANA_CHICA)
    assert {f.sku for f in filas} == {"C001"}


def test_dataset_incluye_un_sku_comun_sin_datos_de_ningun_lado():
    # Un SKU del catálogo común que no vendió ni de un lado ni del otro en toda
    # la ventana tiene que aparecer igual como 'coincide' -- no desaparecer del
    # dataset. Es exactamente lo que promete el docstring de la función.
    filas = construir_dataset_discrepancias({}, {}, {"C003"}, VENTANA_CHICA)
    assert sorted((f.sku, f.month) for f in filas) == [("C003", 8), ("C003", 9)]
    assert all(f.categoria == "coincide" for f in filas)


def test_dataset_produce_una_fila_por_sku_y_mes_de_la_ventana():
    cliente = {"C001": _articulo("C001", {(2025, 8): 10})}
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, VENTANA_CHICA)
    assert sorted((f.year, f.month) for f in filas) == [(2025, 8), (2025, 9)]


def test_dataset_incluye_skus_que_solo_tienen_venta_nuestra():
    # Un SKU común que el cliente no vendió ese mes pero nosotros sí registramos
    # tiene que aparecer igual -- si no, el superávit queda invisible.
    agregados = {("C002", 2025, 8): 4}
    filas = construir_dataset_discrepancias({}, agregados, {"C002"}, VENTANA_CHICA)
    fila = next(f for f in filas if f.sku == "C002" and f.month == 8)
    assert fila.nuestro == 4 and fila.categoria == "superavit"


def test_dataset_etiqueta_la_cohorte_de_cada_fila():
    cliente = {"C001": _articulo("C001", {(2026, 6): 1, (2026, 7): 1, (2026, 8): 1})}
    filas = construir_dataset_discrepancias(
        cliente, {}, {"C001"}, [(2026, 6), (2026, 7), (2026, 8)])
    por_mes = {f.month: f.cohorte for f in filas}
    assert por_mes == {6: "pre", 7: "mixto", 8: "post"}


# ── adjuntar_descomposicion_diaria ───────────────────────────────────────────

def test_descomposicion_se_adjunta_solo_a_filas_con_diferencia():
    cliente = {"C001": _articulo("C001", {(2025, 8): 10, (2025, 9): None})}
    agregados = {("C001", 2025, 8): 7, ("C001", 2025, 9): 0}
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, VENTANA_CHICA)
    diario = {("C001", 2025, 8): ((1, 3), (2, 4))}
    con_dias = adjuntar_descomposicion_diaria(filas, diario)
    con_diff = next(f for f in con_dias if f.month == 8)
    sin_diff = next(f for f in con_dias if f.month == 9)
    assert con_diff.dias_nuestro == ((1, 3), (2, 4))
    assert con_diff.dias_con_venta_nuestra == 2
    assert con_diff.dias_naturales_mes == 31  # calendar.monthrange, no un dict threadeado
    assert sin_diff.dias_nuestro is None  # coincide: no hace falta bajar a día


def test_dias_naturales_mes_se_calcula_solo_para_cualquier_fila():
    # No depende de haber pasado por adjuntar_descomposicion_diaria -- es una
    # propiedad calculada de year/month, no un campo que haya que poblar.
    cliente = {"C001": _articulo("C001", {(2026, 2): 1})}  # febrero: caso no trivial
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, [(2026, 2)])
    assert filas[0].dias_naturales_mes == 28


def test_descomposicion_tolera_ausencia_en_el_diario():
    # Si el mes difiere pero no hay filas diarias (no debería pasar, pero un
    # dataset real puede tener sorpresas) no explota: día vacío, no crash.
    cliente = {"C001": _articulo("C001", {(2025, 8): 10})}
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, VENTANA_CHICA)
    con_dias = adjuntar_descomposicion_diaria(filas, {})
    fila = next(f for f in con_dias if f.month == 8)
    assert fila.dias_nuestro == ()
    assert fila.dias_con_venta_nuestra == 0


# ── resumen_categorias ───────────────────────────────────────────────────────

def test_resumen_categorias_cubre_el_100_por_ciento_de_las_unidades():
    cliente = {"C001": _articulo("C001", {(2025, 8): 10, (2025, 9): 4})}
    agregados = {("C001", 2025, 8): 7, ("C001", 2025, 9): 9}  # deficit, superavit
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, VENTANA_CHICA)
    resumen = resumen_categorias(filas)
    total_pct = sum(r["pct_unidades"] for r in resumen.values())
    assert total_pct == pytest.approx(100.0)
    assert resumen["deficit"]["unidades"] == 3
    assert resumen["superavit"]["unidades"] == 5
    assert resumen["deficit"]["pct_unidades"] == pytest.approx(3 / 8 * 100)
    assert resumen["superavit"]["pct_unidades"] == pytest.approx(5 / 8 * 100)


def test_resumen_categorias_sin_diferencias_no_rompe_por_division_cero():
    cliente = {"C001": _articulo("C001", {(2025, 8): None})}
    filas = construir_dataset_discrepancias(cliente, {}, {"C001"}, [(2025, 8)])
    resumen = resumen_categorias(filas)
    assert resumen["coincide"]["unidades"] == 0
    assert resumen["coincide"]["pct_unidades"] == 0.0


def test_resumen_categorias_falla_fuerte_ante_una_categoria_desconocida():
    # CATEGORIAS y _categoria() son dos fuentes separadas del mismo
    # vocabulario -- si alguna vez divergen, mejor este mensaje que un
    # KeyError críptico a mitad de una corrida contra producción.
    from comparar_ventas_mensual import FilaDiscrepancia
    fila_rara = FilaDiscrepancia(
        sku="C001", year=2025, month=8, cohorte="pre",
        cliente_original=1, cliente_numerico=1, nuestro=1, diff_abs=0,
        diff_rel=0.0, categoria="categoria_inventada")
    with pytest.raises(ValueError, match="categoria_inventada"):
        resumen_categorias([fila_rara])


def test_resumen_categorias_incluye_las_tres_siempre_aunque_esten_vacias():
    cliente = {"C001": _articulo("C001", {(2025, 8): 5})}
    agregados = {("C001", 2025, 8): 2}  # sólo déficit
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, [(2025, 8)])
    resumen = resumen_categorias(filas)
    assert set(resumen) == {"coincide", "deficit", "superavit"}
    assert resumen["superavit"]["unidades"] == 0


# ── resumen_por_cohorte ──────────────────────────────────────────────────────

def test_resumen_por_cohorte_separa_pre_post_y_mixto():
    cliente = {"C001": _articulo("C001", {(2026, 6): 10, (2026, 8): 20})}
    agregados = {("C001", 2026, 6): 8, ("C001", 2026, 8): 15}
    filas = construir_dataset_discrepancias(
        cliente, agregados, {"C001"}, [(2026, 6), (2026, 8)])
    resumen = resumen_por_cohorte(filas)
    assert resumen["pre"]["unidades_cliente"] == 10
    assert resumen["pre"]["unidades_nuestro"] == 8
    assert resumen["post"]["unidades_cliente"] == 20
    assert resumen["post"]["unidades_nuestro"] == 15


def test_resumen_por_cohorte_calcula_brecha_relativa():
    cliente = {"C001": _articulo("C001", {(2026, 6): 100})}
    agregados = {("C001", 2026, 6): 95}
    filas = construir_dataset_discrepancias(cliente, agregados, {"C001"}, [(2026, 6)])
    resumen = resumen_por_cohorte(filas)
    assert resumen["pre"]["brecha_relativa"] == pytest.approx(-0.05)


# ── unidades_excluidas_por_restriccion ───────────────────────────────────────

def test_unidades_excluidas_suma_solo_los_skus_fuera_del_conjunto_comun():
    from cargador_archivos_cliente import comparar_catalogo
    ventas_cliente_sin_restringir = {
        "C001": _articulo("C001", {(2025, 8): 10}),   # común
        "C777": _articulo("C777", {(2025, 8): 40}),   # sólo del cliente
    }
    agregados_sin_restringir = {("C001", 2025, 8): 10, ("C888", 2025, 8): 25}  # C888 sólo nuestro
    cobertura = comparar_catalogo(list(ventas_cliente_sin_restringir), ["C001", "C888"])
    excluidas = unidades_excluidas_por_restriccion(
        cobertura, ventas_cliente_sin_restringir, agregados_sin_restringir)
    assert excluidas.unidades_solo_cliente == 40
    assert excluidas.unidades_solo_nuestras == 25


def test_unidades_excluidas_falla_con_mensaje_claro_si_la_cobertura_no_matchea():
    # Si `cobertura` viniera de un snapshot distinto al `ventas_cliente` que se
    # le pasa acá, un SKU de `solo_cliente` podría faltar en el dict -- mejor
    # un error explícito que un KeyError críptico en medio de la corrida.
    from cargador_archivos_cliente import Cobertura
    cobertura_stale = Cobertura(comunes=(), solo_cliente=("C999",), solo_nuestros=())
    with pytest.raises(ValueError, match="C999"):
        unidades_excluidas_por_restriccion(cobertura_stale, {}, {})


# ── totales_mensuales_cliente ────────────────────────────────────────────────
#
# Chequeo de reproducibilidad (criterio de aceptación #5): estos totales tienen
# que dar exactamente lo que ya se verificó a mano contra el archivo real, SIN
# restringir al conjunto común -- es un chequeo de que el cargador y la
# agregación están bien enganchados, no la comparación real del ticket.

def test_totales_mensuales_nuestros_reduce_por_sku():
    # Reemplaza a una segunda query SQL que hacía el mismo scan que el
    # agregado por SKU -- se deriva en Python, sin ir dos veces a la DB.
    agregados = {("C001", 2025, 8): 10, ("C002", 2025, 8): 5, ("C001", 2025, 9): 3}
    assert totales_mensuales_nuestros(agregados) == {(2025, 8): 15, (2025, 9): 3}


def test_totales_mensuales_cliente_trata_none_como_cero():
    cliente = {
        "C001": _articulo("C001", {(2025, 8): 10, (2025, 9): None}),
        "C002": _articulo("C002", {(2025, 8): 5, (2025, 9): 3}),
    }
    totales = totales_mensuales_cliente(cliente)
    assert totales[(2025, 8)] == 15
    assert totales[(2025, 9)] == 3
