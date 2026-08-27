"""
Tests de las funciones puras de scripts/comparar_extraccion_vs_produccion.py
(issue #187). El script vive en scripts/ junto a los demás de QA, así que se
agrega ese directorio al path -- mismo patrón que
test_diagnostico_planillas_cliente.py (no hay paquete que importar).

Hallazgo de /code-review, séptima ronda: esta suite había quedado primero en
scripts/test_comparar_extraccion_vs_produccion.py -- CI corre `pytest tests/`
con working-directory services/etl (.github/workflows/ci.yml), así que nunca
la iba a descubrir. Se movió acá siguiendo el precedente real que ya existía
(este mismo patrón, para diagnostico_planillas_cliente.py) en vez del que se
había asumido al principio (que no había tests para scripts/ -- incorrecto,
solo no se había buscado bien).

clasificar()/detectar_magnitud_fija_recurrente() son funciones puras (sin
DB), y son las que deciden qué diferencia se reporta como "cerrada, sin
acción" vs "necesita revisión" -- un bug ahí hace que el reporte mienta en
silencio. Sin fixture de MySQL -- la comparación contra datos reales
(comparar_ventas/comparar_stock/main) se verifica corriendo el script contra
el dataset chico de #186 (ver criterio de aceptación de #187), no acá.
"""

import os
import sys

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from comparar_extraccion_vs_produccion import clasificar, detectar_magnitud_fija_recurrente  # noqa: E402


def _diff(sku="C00204", anio=2026, mes=7, produccion=10, comparacion=8, tipo="ventas", **extra):
    d = {"tipo": tipo, "sku": sku, "anio": anio, "mes": mes,
         "produccion": produccion, "comparacion": comparacion,
         "delta": (comparacion or 0) - (produccion or 0)}
    d.update(extra)
    return d


# ── clasificar(): #174 (clamp de negativos pre-#80) -- ventas, no cierra sola ──

def test_negativo_antes_del_backfill_80_se_clasifica_como_174_pero_requiere_revision():
    """A nivel mes no se puede confirmar que la baja sea EL clamp y no otra
    causa (#126 documentó meses con ventas positivas y una devolución grande
    mezcladas) -- la categoría queda etiquetada pero abierta, ninguna
    categoría de este script cierra sola hoy."""
    d = _diff(anio=2024, mes=3, produccion=0, comparacion=-5)
    categoria, explicacion, requiere_revision = clasificar(d)
    assert categoria == "clamp_negativos_pre_80_posible"
    assert "#174" in explicacion
    assert requiere_revision is True


def test_negativo_despues_del_backfill_80_no_se_clasifica():
    """El backfill de #80 ya cubrió 12/08/2024 en adelante -- una fecha
    posterior con delta negativo no tiene esta explicación, es candidata
    real."""
    d = _diff(anio=2025, mes=3, produccion=0, comparacion=-5)
    categoria, _, requiere_revision = clasificar(d)
    assert categoria is None
    assert requiere_revision is True


def test_delta_positivo_antes_del_backfill_80_no_es_clamp():
    """El clamp de #80 solo pierde negativos -- un delta positivo antes de
    la ventana no tiene esta causa (producción no puede tener MENOS que un
    valor ya clampeado a 0 salvo que el nuevo sea negativo)."""
    d = _diff(anio=2024, mes=3, produccion=5, comparacion=8)
    categoria, _, _ = clasificar(d)
    assert categoria is None


def test_fecha_limite_exacta_2024_08_12_no_esta_cubierta():
    """La fecha límite es exclusiva -- el propio 12/08/2024 ya está dentro
    del backfill de #80 (que cubrió desde ese día), no antes."""
    d = _diff(anio=2024, mes=8, produccion=0, comparacion=-3)
    categoria, _, _ = clasificar(d)
    assert categoria is None


def test_stock_nunca_se_clasifica_como_clamp_de_ventas():
    """Hallazgo de /code-review: #174 es específico de ventas_historicas.cantidad
    (era UNSIGNED hasta #80). stock_diario.cantidad es UNSIGNED con
    CHECK(cantidad>=0) desde siempre -- un stock negativo ni existe, así que
    esta categoría no puede aplicarle a un diff de stock aunque la fecha sea
    anterior al backfill. (El valor comparacion=-2 de este test es en sí
    mismo un estado que la DB real nunca permitiría -- se usa igual para
    confirmar que el código no lo clasificaría ni por accidente si algún día
    llegara así desde una fuente que no sea la DB real.)"""
    import datetime as dt
    d = _diff(tipo="stock", anio=2024, mes=8, fecha=dt.date(2024, 8, 1), produccion=0, comparacion=-2)
    categoria, _, _ = clasificar(d)
    assert categoria is None


def test_produccion_positiva_antes_del_backfill_no_es_necesariamente_clamp():
    """Hallazgo de /code-review: producción=50, comparación=45 antes del
    backfill NO es evidencia de que la baja sea el clamp -- el clamp
    zeroea un día negativo dentro del mes, no reduce un total positivo a
    otro positivo menor por sí solo. Sigue siendo CONSISTENTE con el patrón
    (por eso clasifica, no queda en None) pero por eso mismo no cierra sola."""
    d = _diff(anio=2024, mes=3, produccion=50, comparacion=45)
    categoria, _, requiere_revision = clasificar(d)
    assert categoria == "clamp_negativos_pre_80_posible"
    assert requiere_revision is True


# ── clasificar(): filas que solo existen de un lado -- tienen nombre PERO ──
# siguen necesitando revisión (no son "seguras para ignorar" como #174)

def test_solo_en_comparacion_no_en_produccion_tiene_nombre_pero_requiere_revision():
    d = _diff(anio=2026, mes=6, produccion=None, comparacion=7)
    categoria, explicacion, requiere_revision = clasificar(d)
    assert categoria == "solo_en_comparacion"
    assert "fallo silencioso" in explicacion
    assert requiere_revision is True, "tiene categoría, pero no es lo mismo que 'seguro ignorar'"


def test_solo_en_produccion_no_en_comparacion_tiene_nombre_pero_requiere_revision():
    d = _diff(anio=2026, mes=6, produccion=7, comparacion=None)
    categoria, explicacion, requiere_revision = clasificar(d)
    assert categoria == "solo_en_produccion"
    assert "regresión" in explicacion
    assert requiere_revision is True


def test_fila_ausente_antes_del_backfill_80_no_se_confunde_con_el_clamp():
    """Hallazgo de /code-review: una fila enteramente ausente de un lado
    (posible regresión real) fechada antes de #80 se evaluaba primero contra
    el clamp y quedaba mal etiquetada -- el orden importa, #174 es una
    explicación de VALOR, no de fila faltante."""
    d = _diff(anio=2024, mes=3, produccion=50, comparacion=None)
    categoria, _, requiere_revision = clasificar(d)
    assert categoria == "solo_en_produccion"
    assert requiere_revision is True


def test_diferencia_de_valor_reciente_sin_explicar_queda_como_candidata():
    """El caso central: ambos lados tienen dato, la fecha es reciente -- no
    hay categoría conocida, y por supuesto requiere revisión."""
    d = _diff(anio=2026, mes=7, produccion=100, comparacion=84)
    categoria, explicacion, requiere_revision = clasificar(d)
    assert categoria is None
    assert explicacion is None
    assert requiere_revision is True


# ── detectar_magnitud_fija_recurrente(): mismo método que destapó #161 ─────

def test_mismo_delta_repetido_en_un_sku_se_detecta():
    diffs = [_diff(sku="C00204", mes=m, produccion=20, comparacion=5) for m in (2, 3, 5, 6, 7)]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert any("C00204" in h and "5 veces" in h for h in hallazgos)


def test_delta_disperso_sin_repeticion_no_se_detecta():
    diffs = [_diff(sku="C00204", mes=m, produccion=20, comparacion=20 - m) for m in (2, 3, 5)]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert hallazgos == []


def test_mismo_delta_mismo_dia_en_varios_skus_se_detecta():
    import datetime as dt
    fecha = dt.date(2026, 6, 1)
    diffs = [
        _diff(sku="C00160", tipo="stock", fecha=fecha, produccion=20, comparacion=10),
        _diff(sku="C00184", tipo="stock", fecha=fecha, produccion=15, comparacion=5),
    ]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert any("2 SKUs distintos" in h and "C00160" in h and "C00184" in h for h in hallazgos)


def test_no_mezcla_ventas_y_stock_con_el_mismo_delta_por_casualidad():
    """Hallazgo de /code-review: ventas y stock miden cosas distintas (unidades
    vendidas por mes vs. unidades en depósito por día) -- que coincidan en
    magnitud por casualidad no es un patrón sistemático real."""
    diffs = [
        _diff(sku="C00204", tipo="ventas", mes=2, produccion=20, comparacion=15),
        _diff(sku="C00204", tipo="ventas", mes=3, produccion=20, comparacion=15),
        _diff(sku="C00204", tipo="stock", mes=4, produccion=20, comparacion=15),
    ]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert hallazgos == [], "2 ventas + 1 stock con el mismo delta no son 3 ocurrencias del mismo patrón"


def test_umbral_minimo_ocurrencias_respetado():
    """2 repeticiones no alcanzan si el umbral pide 3 -- el default no debe
    disparar sobre coincidencias chicas que bien pueden ser casualidad."""
    diffs = [_diff(sku="C00204", mes=m, produccion=20, comparacion=5) for m in (2, 3)]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert hallazgos == []


def test_mismo_delta_mismo_mes_en_varios_skus_ventas_dice_mes_no_dia():
    """Hallazgo de /code-review: para ventas la clave de agrupación es
    (año, mes), no una fecha -- el mensaje tiene que decir 'mismo mes', no
    'mismo día' (que sería directamente falso), y mostrar el mes legible en
    vez de una tupla Python cruda."""
    diffs = [
        _diff(sku="C00160", tipo="ventas", anio=2026, mes=6, produccion=20, comparacion=10),
        _diff(sku="C00184", tipo="ventas", anio=2026, mes=6, produccion=15, comparacion=5),
    ]
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=3)
    assert any("2026-06" in h and "mismo mes" in h and "C00160" in h and "C00184" in h for h in hallazgos)
    assert not any("mismo día" in h for h in hallazgos)


def test_umbral_minimo_skus_mismo_dia_configurable():
    """Hallazgo de /code-review: el segundo chequeo (mismo día, varios SKUs)
    tenía el umbral de 2 hardcodeado, sin que un caller pudiera subirlo."""
    import datetime as dt
    fecha = dt.date(2026, 6, 1)
    diffs = [
        _diff(sku="C00160", tipo="stock", fecha=fecha, produccion=20, comparacion=10),
        _diff(sku="C00184", tipo="stock", fecha=fecha, produccion=15, comparacion=5),
    ]
    # Con el umbral default (2) se detecta.
    assert detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=99) != []
    # Pidiendo 3 SKUs mínimo, 2 no alcanzan.
    hallazgos = detectar_magnitud_fija_recurrente(diffs, minimo_ocurrencias=99, minimo_skus_mismo_dia=3)
    assert hallazgos == []
