"""
Tests de las funciones puras de scripts/reconciliar_deposito5.py (issue #199).
Mismo patrón que #195/#196/#197: el script vive en scripts/, se agrega ese
directorio al path.

Las funciones de I/O (conexión a MySQL) no se testean acá -- se verifican por
integración contra producción, vía túnel SSH, igual que las anteriores.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from cargador_archivos_cliente import (  # noqa: E402
    AJUSTE_ENTRADA,
    AJUSTE_SALIDA,
    ENTRADA_MERCADERIA,
    Movimiento,
    emparejar_recodificaciones,
)
from reconciliar_deposito5 import (  # noqa: E402
    desglose_salida,
    evaluar_continuidad,
    identificar_autocancelantes,
    skus_salida_genuina,
    valor_a_fecha,
)


def _mov(sku, unidades, tipo, genero="G"):
    return Movimiento(sku=sku, descripcion=None, unidades=unidades, tipo_documento=tipo, genero=genero)


# ── identificar_autocancelantes ──────────────────────────────────────────────
#
# El caso real: C00477 aparece con +50 de Ajuste de Entrada y -50 de Ajuste de
# Salida en el mismo archivo -- una corrección de error, neto cero. Es distinto
# de una recodificación (que empareja Ajuste de Salida contra Entrada de
# Mercadería, no contra Ajuste de Entrada).

def test_identifica_el_par_que_cierra_en_cero():
    movs = [_mov("C00477", 50, AJUSTE_ENTRADA), _mov("C00477", -50, AJUSTE_SALIDA)]
    autocancelantes = identificar_autocancelantes(movs)
    assert len(autocancelantes) == 1
    assert autocancelantes[0].sku == "C00477"
    assert autocancelantes[0].entrada == 50
    assert autocancelantes[0].salida == -50


def test_no_confunde_una_recodificacion_con_un_autocancelante():
    # C00482 aparece en Ajuste de Salida y Entrada de Mercadería -- es una
    # recodificación (#195), no un autocancelante de Ajuste de Entrada/Salida.
    movs = [_mov("C00482", -10, AJUSTE_SALIDA), _mov("C00482", 10, ENTRADA_MERCADERIA)]
    assert identificar_autocancelantes(movs) == ()


def test_no_marca_un_sku_que_no_cierra_en_cero():
    # Mismo SKU en Entrada y Salida pero que no neta exactamente 0 no es un
    # "error de tipeo corregido" -- es otra cosa, no se debe descartar en
    # silencio como si fuera ruido explicado.
    movs = [_mov("C001", 50, AJUSTE_ENTRADA), _mov("C001", -30, AJUSTE_SALIDA)]
    assert identificar_autocancelantes(movs) == ()


def test_ignora_skus_en_un_solo_tipo_de_documento():
    movs = [_mov("C001", -10, AJUSTE_SALIDA)]
    assert identificar_autocancelantes(movs) == ()


# ── desglose_salida ──────────────────────────────────────────────────────────

def _pares(movs):
    return emparejar_recodificaciones(movs)


def test_desglose_reproduce_los_numeros_esperados_de_un_caso_chico():
    # Caso chico armado a mano, con las tres categorías presentes: una
    # recodificación (HX030+I01874 -> I01874, -176 del lado salida), un
    # autocancelante (C00477, -50) y una salida genuina (C00216, -303).
    # Total: 176+50+303 = 529.
    movs = [
        _mov("HX030", -150, AJUSTE_SALIDA),
        _mov("I01874", -26, AJUSTE_SALIDA),
        _mov("I01874", 176, ENTRADA_MERCADERIA),
        _mov("C00477", 50, AJUSTE_ENTRADA),
        _mov("C00477", -50, AJUSTE_SALIDA),
        _mov("C00216", -303, AJUSTE_SALIDA),
    ]
    pares = _pares(movs)
    autocancelantes = identificar_autocancelantes(movs)
    desglose = desglose_salida(movs, pares, autocancelantes)
    assert desglose == {
        "total": 529,
        "recodificacion": 176,
        "autocancelante": 50,
        "genuina": 303,
    }


def test_desglose_las_cuatro_partes_suman_el_total():
    movs = [
        _mov("HX030", -150, AJUSTE_SALIDA),
        _mov("I01874", -26, AJUSTE_SALIDA),
        _mov("I01874", 176, ENTRADA_MERCADERIA),
        _mov("C00477", 50, AJUSTE_ENTRADA),
        _mov("C00477", -50, AJUSTE_SALIDA),
        _mov("C00216", -303, AJUSTE_SALIDA),
    ]
    pares = _pares(movs)
    autocancelantes = identificar_autocancelantes(movs)
    desglose = desglose_salida(movs, pares, autocancelantes)
    assert desglose["recodificacion"] + desglose["autocancelante"] + desglose["genuina"] \
        == desglose["total"]


def test_desglose_falla_fuerte_si_un_sku_es_recodificado_y_autocancelante():
    # Construido a mano: C001 aparece en Ajuste de Entrada (+10), Ajuste de
    # Salida (-10, neta con la entrada -> autocancelante) Y en Entrada de
    # Mercadería con un monto que emparejar_recodificaciones también podría
    # matchear contra esa misma salida -- caso ambiguo, no debe clasificarse
    # en silencio bajo una sola categoría.
    from reconciliar_deposito5 import Autocancelante
    from cargador_archivos_cliente import Recodificacion
    movs = [_mov("C001", -10, AJUSTE_SALIDA)]
    pares_forzados = (Recodificacion(destino="C002", origenes=("C001",), unidades=10),)
    autocancel_forzado = (Autocancelante(sku="C001", entrada=10, salida=-10),)
    with pytest.raises(ValueError, match="C001"):
        desglose_salida(movs, pares_forzados, autocancel_forzado)


def test_desglose_contra_el_archivo_real_completo():
    from cargador_archivos_cliente import leer_movimientos
    movs, _ = leer_movimientos()
    pares = _pares(movs)
    autocancelantes = identificar_autocancelantes(movs)
    desglose = desglose_salida(movs, pares, autocancelantes)
    assert desglose["total"] == 819
    assert desglose["recodificacion"] == 466
    assert desglose["autocancelante"] == 50
    assert desglose["genuina"] == 303
    assert desglose["recodificacion"] + desglose["autocancelante"] + desglose["genuina"] == 819


# ── skus_salida_genuina ───────────────────────────────────────────────────────

def test_skus_genuina_excluye_recodificados_y_autocancelantes():
    movs = [
        _mov("HX030", -150, AJUSTE_SALIDA),
        _mov("I01874", -26, AJUSTE_SALIDA),
        _mov("I01874", 176, ENTRADA_MERCADERIA),
        _mov("C00477", 50, AJUSTE_ENTRADA),
        _mov("C00477", -50, AJUSTE_SALIDA),
        _mov("C00216", -303, AJUSTE_SALIDA),
    ]
    pares = _pares(movs)
    autocancelantes = identificar_autocancelantes(movs)
    genuinas = skus_salida_genuina(movs, pares, autocancelantes)
    assert {m.sku for m in genuinas} == {"C00216"}


def test_skus_genuina_contra_el_archivo_real():
    from cargador_archivos_cliente import leer_movimientos
    movs, _ = leer_movimientos()
    pares = _pares(movs)
    autocancelantes = identificar_autocancelantes(movs)
    genuinas = skus_salida_genuina(movs, pares, autocancelantes)
    assert sum(m.unidades for m in genuinas) == -303
    assert "HX030" not in {m.sku for m in genuinas}
    assert "C00477" not in {m.sku for m in genuinas}


# ── valor_a_fecha ─────────────────────────────────────────────────────────────
#
# stock_diario no necesariamente tiene una fila para cada día -- valor_a_fecha
# hace forward-fill desde la última fila disponible en o antes de la fecha
# pedida, y devuelve None (no 0) si no hay ninguna fila anterior: ausencia de
# dato no es lo mismo que stock cero.

def test_valor_a_fecha_toma_la_ultima_fila_en_o_antes():
    serie = {"2026-06-28": 10, "2026-06-30": 15, "2026-07-05": 8}
    assert valor_a_fecha(serie, "2026-07-01") == 15
    assert valor_a_fecha(serie, "2026-06-30") == 15
    assert valor_a_fecha(serie, "2026-06-29") == 10


def test_valor_a_fecha_none_si_no_hay_dato_anterior():
    serie = {"2026-07-05": 8}
    assert valor_a_fecha(serie, "2026-06-30") is None


def test_valor_a_fecha_serie_vacia():
    assert valor_a_fecha({}, "2026-07-01") is None


# ── evaluar_continuidad ───────────────────────────────────────────────────────
#
# La firma de una renumeración limpia: el stock COMBINADO (todos los orígenes
# + el destino) se mantiene igual entre fin de junio y fin de julio, aunque
# cada SKU individual salte -- uno cae a 0, el otro sube en la misma magnitud.

def _par(origenes, destino):
    (pares,) = emparejar_recodificaciones([
        *[_mov(o, -1, AJUSTE_SALIDA) for o in origenes],  # unidades no importan acá
        _mov(destino, len(origenes), ENTRADA_MERCADERIA),
    ])
    return pares


def test_continuidad_combinado_estable_es_una_renumeracion_limpia():
    par = _par(("HX030",), "I01874")
    series = {
        "HX030": {"2026-06-30": 150, "2026-07-31": 0},
        "I01874": {"2026-06-30": 20, "2026-07-31": 170},
    }
    c = evaluar_continuidad(par, series)
    assert c.combinado_fin_junio == 170
    assert c.combinado_fin_julio == 170
    assert c.salto_combinado == 0


def test_continuidad_detecta_un_salto_real():
    par = _par(("HX030",), "I01874")
    series = {
        "HX030": {"2026-06-30": 150, "2026-07-31": 0},
        "I01874": {"2026-06-30": 20, "2026-07-31": 100},  # falta stock: no llegaron los 150
    }
    c = evaluar_continuidad(par, series)
    assert c.salto_combinado == -70


def test_continuidad_suma_varios_origenes():
    par = _par(("HX030", "I01874"), "I01874")
    series = {
        "HX030": {"2026-06-30": 150, "2026-07-31": 0},
        "I01874": {"2026-06-30": 30, "2026-07-31": 176},
    }
    c = evaluar_continuidad(par, series)
    assert c.origen_fin_junio == 180  # HX030 + I01874, ambos "origen" antes del cambio


def test_continuidad_no_duplica_un_sku_que_es_origen_y_destino_a_la_vez():
    # Caso real del archivo: HX030+I01874 -> I01874 (I01874 es origen Y
    # destino). El combinado tiene que contar I01874 UNA vez, no sumarlo
    # dentro de "origen" y de nuevo dentro de "destino".
    par = _par(("HX030", "I01874"), "I01874")
    series = {
        "HX030": {"2026-06-30": 150, "2026-07-31": 0},
        "I01874": {"2026-06-30": 30, "2026-07-31": 176},
    }
    c = evaluar_continuidad(par, series)
    assert c.combinado_fin_junio == 180  # HX030(150) + I01874(30), no 180+30=210
    assert c.combinado_fin_julio == 176  # sólo I01874, ya que HX030 quedó en 0
    assert c.salto_combinado == -4  # 176-180, chico: consistente con una migración limpia


def test_continuidad_no_duplica_cuando_destino_es_el_mismo_sku_que_el_unico_origen():
    # Caso real: C00482 -> C00482 (mismo SKU de los dos lados). El combinado
    # tiene que ser el stock real de C00482, no el doble.
    par = _par(("C00482",), "C00482")
    series = {"C00482": {"2026-06-30": 40, "2026-07-31": 45}}
    c = evaluar_continuidad(par, series)
    assert c.combinado_fin_junio == 40  # no 40+40=80
    assert c.combinado_fin_julio == 45
    assert c.salto_combinado == 5


def test_continuidad_none_si_falta_todo_el_dato_de_un_lado():
    par = _par(("HX030",), "I01874")
    series = {"I01874": {"2026-06-30": 20, "2026-07-31": 170}}  # sin serie de HX030
    c = evaluar_continuidad(par, series)
    assert c.origen_fin_junio is None
    # el combinado no se puede calcular sin el origen
    assert c.combinado_fin_junio is None
    assert c.salto_combinado is None
