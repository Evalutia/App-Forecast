"""Tests de services/etl/parsers.py (Issue #125).

Unit tests puros -- sin DB, a diferencia de test_run_extract_sales_chunk.py.
Cubren el acceptance criteria: miles con punto, decimales con coma, nulos,
cero, negativos, cada formato de fecha observado, y codigos con espacios de
borde/internos. El caso central es el bug original: un valor no
interpretable nunca se traduce a 0 en silencio (ParseError), y el bypass de
normalizacion que tenia clamp_signed_int (Issue original: 'venta' con coma
caia a 0 porque no pasaba por el reemplazo de coma) queda cerrado porque
ahora todos los caminos numericos pasan por la misma parse_decimal.
"""

import pytest

import parsers
import fixtures_ws_payloads as fx


# ── Numeros: miles con punto ──────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", [
    ("25.000", 25),       # un solo punto: se interpreta como decimal (25.000 == 25),
                           # igual que el extractor de stock ya en produccion -- no se
                           # "corrige" esa ambiguedad aca, queda fuera de este issue.
    ("3.800.000", 3800000),  # mas de un punto: separador de miles, se remueven todos.
    ("1.200", 1),
])
def test_parse_entero_miles_con_punto(valor, esperado):
    assert parsers.parse_entero(valor) == esperado


# ── Numeros: decimales con coma ───────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", [
    ("1,5", 2),   # ROUND_HALF_UP
    ("0,5", 1),
])
def test_parse_entero_decimal_con_coma_redondea(valor, esperado):
    assert parsers.parse_entero(valor, signed=True) == esperado


def test_parse_decimal_decimal_con_coma_preserva_precision():
    assert parsers.parse_decimal("1,5") == parsers.parse_decimal("1.5")


# ── Numeros: nulos, vacios, cero ──────────────────────────────────────────

@pytest.mark.parametrize("valor", fx.NUMEROS_NULOS)
def test_parse_decimal_nulo_o_vacio_es_none_no_cero(valor):
    assert parsers.parse_decimal(valor) is None


@pytest.mark.parametrize("valor", fx.NUMEROS_NULOS)
def test_parse_entero_nulo_o_vacio_usa_default(valor):
    assert parsers.parse_entero(valor, default=0) == 0
    assert parsers.parse_entero(valor, default=None) is None


@pytest.mark.parametrize("valor", fx.NUMEROS_CERO)
def test_parse_entero_cero_explicito(valor):
    assert parsers.parse_entero(valor) == 0


# ── Numeros: negativos ─────────────────────────────────────────────────────

@pytest.mark.parametrize("valor", fx.NUMEROS_NEGATIVOS)
def test_parse_entero_signed_preserva_negativo(valor):
    assert parsers.parse_entero(valor, signed=True) < 0


@pytest.mark.parametrize("valor", fx.NUMEROS_NEGATIVOS)
def test_parse_entero_nonneg_clampea_a_cero(valor):
    """Regla de negocio deliberada (stock nunca negativo), no un fallo de
    parseo -- se preserva el comportamiento original de clamp_nonneg_int."""
    assert parsers.parse_entero(valor, signed=False) == 0


# ── Numeros: el clamp real deja rastro (Issue #156) ───────────────────────

@pytest.mark.parametrize("valor", fx.NUMEROS_NEGATIVOS)
def test_parse_entero_clamp_real_deja_rastro_en_log(valor, capsys):
    """El recorte sigue funcionando igual (valor persistido = 0), pero ahora
    queda visible en el log -- antes era indistinguible de un 0 real del WS."""
    resultado = parsers.parse_entero(valor, signed=False)
    assert resultado == 0
    salida = capsys.readouterr().out
    assert "[WARN]" in salida
    assert repr(valor) in salida


def test_parse_entero_clamp_real_contexto_aparece_en_log(capsys):
    """Los extractores conocen sku/fecha al momento de parsear -- si lo
    pasan, el WARN de clamp queda tan identificable como los demas WARN de
    fila descartada (que ya incluyen sku=... fecha=...)."""
    parsers.parse_entero(-5, signed=False, contexto="sku=ABC123 fecha=2026-08-01")
    salida = capsys.readouterr().out
    assert "[WARN]" in salida
    assert "sku=ABC123 fecha=2026-08-01" in salida


def test_parse_entero_clamp_sin_contexto_no_rompe(capsys):
    """contexto es opcional -- sin el, el log sigue funcionando (compat con
    callers que todavia no lo pasan)."""
    parsers.parse_entero(-5, signed=False)
    salida = capsys.readouterr().out
    assert "[WARN]" in salida


@pytest.mark.parametrize("valor", fx.NUMEROS_CERO)
def test_parse_entero_cero_real_no_genera_ruido_en_log(valor, capsys):
    """Un 0 (o positivo) que no pasó por el clamp no debe generar log --
    solo se avisa cuando el recorte realmente ocurre."""
    parsers.parse_entero(valor, signed=False)
    assert capsys.readouterr().out == ""


def test_parse_entero_signed_negativo_no_generar_log():
    """El camino signed=True (ventas, negativo legitimo desde #80) no debe
    verse afectado por este log -- ahi no hay clamp."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        resultado = parsers.parse_entero(-3, signed=True)
    assert resultado == -3
    assert buf.getvalue() == ""


# ── Numeros: el bug original -- no interpretable nunca es 0 silencioso ───

@pytest.mark.parametrize("valor", fx.NUMEROS_NO_INTERPRETABLES)
def test_parse_decimal_no_interpretable_levanta_parseerror(valor):
    with pytest.raises(parsers.ParseError):
        parsers.parse_decimal(valor)


@pytest.mark.parametrize("valor", fx.NUMEROS_NO_INTERPRETABLES)
def test_parse_entero_no_interpretable_levanta_parseerror_no_cero(valor):
    with pytest.raises(parsers.ParseError):
        parsers.parse_entero(valor, signed=True)


def test_parse_decimal_booleano_no_es_numero_valido():
    with pytest.raises(parsers.ParseError):
        parsers.parse_decimal(True)


# ── Fechas: cada formato observado ────────────────────────────────────────

@pytest.mark.parametrize("valor", fx.FECHAS_POR_FORMATO.values())
def test_parse_fecha_formatos_observados(valor):
    assert parsers.parse_fecha(valor) == "2026-08-01"


def test_parse_fecha_separador_espacio_ya_no_se_pierde():
    """El hallazgo puntual del issue: antes ningun extractor aceptaba
    'YYYY-MM-DD HH:MM:SS' (espacio en vez de 'T')."""
    assert parsers.parse_fecha("2026-08-01 14:30:00") == "2026-08-01"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_parse_fecha_nula_o_vacia_es_none(valor):
    assert parsers.parse_fecha(valor) is None


@pytest.mark.parametrize("valor", fx.FECHAS_NO_INTERPRETABLES)
def test_parse_fecha_no_interpretable_levanta_parseerror(valor):
    with pytest.raises(parsers.ParseError):
        parsers.parse_fecha(valor)


def test_parse_fecha_fuera_de_rango_levanta_parseerror():
    with pytest.raises(parsers.ParseError):
        parsers.parse_fecha("1899-12-31")


# ── Codigos de articulo ───────────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", fx.CODIGOS_ARTICULO.items())
def test_normalize_sku(valor, esperado):
    assert parsers.normalize_sku(valor) == esperado


def test_normalize_sku_none_es_none():
    assert parsers.normalize_sku(None) is None


def test_normalize_sku_vacio_tras_normalizar_es_none():
    assert parsers.normalize_sku("   \x00\x01  ") is None


def test_normalize_sku_trunca_a_128():
    assert len(parsers.normalize_sku("A" * 200)) == 128


# ── Los tres extractores comparten exactamente la misma normalizacion ─────

def test_normalizacion_de_sku_identica_via_modulos_extractores():
    """Acceptance criteria: 'la normalizacion del codigo de articulo es
    identica en los tres caminos'. Los tres modulos delegan a
    parsers.normalize_sku -- se verifica importando los dos que son
    seguros de importar (articulos, sales_chunk exponen funciones sin
    ejecutar nada al importar). run_extract_stockxml.py es un script de
    top a top -- importarlo dispara conexion a DB -- asi que su uso de
    parsers.normalize_sku se verifica leyendo el codigo, no importandolo."""
    import run_extract_articulos as art
    import run_extract_sales_chunk as ssc

    valor = "  abc 123  "
    assert art.normalize_sku_from_value(valor) == parsers.normalize_sku(valor)
    assert ssc.parsers.normalize_sku(valor) == parsers.normalize_sku(valor)


# ── Regresion del bug central del issue ────────────────────────────────────

def test_venta_con_coma_ya_no_es_cero_silencioso():
    """Antes: clamp_signed_int hacia Decimal(str(x)) directo, sin pasar por
    el reemplazo de coma -- 'Decimal('1,5')' tira InvalidOperation y el
    except devolvia 0. Con la normalizacion unificada, '1,5' se interpreta
    (redondeado) y nunca cae a 0 por una coma sin manejar."""
    resultado = parsers.parse_entero(fx.ITEM_VENTA_DECIMAL_COMA["Venta"], signed=True)
    assert resultado != 0
    assert resultado == 2


# ── redondear() -- Issue #182 ───────────────────────────────────────────────
# round() nativo de Python redondea al par mas cercano ("banker's rounding"):
# round(2.675, 2) == 2.67, no 2.68. parse_entero ya usa ROUND_HALF_UP a
# proposito (ver arriba) -- redondear() expone el mismo criterio para
# columnas con decimales (run_calc_planilla.py/run_calc_sugerencias.py),
# no solo para enteros.

@pytest.mark.parametrize("valor,decimales,esperado", [
    (2.675, 2, 2.68),   # round() nativo da 2.67 -- este es el caso del issue
    (0.125, 2, 0.13),   # round() nativo da 0.12
    (19.395, 2, 19.4),  # round() nativo da 19.39
    (1.00005, 4, 1.0001),
    (2.5, 0, 3.0),
])
def test_redondear_usa_round_half_up_no_banker(valor, decimales, esperado):
    assert parsers.redondear(valor, decimales) == esperado


def test_redondear_valor_no_ambiguo_coincide_con_round_nativo():
    assert parsers.redondear(3.14159, 2) == round(3.14159, 2) == 3.14


def test_redondear_negativo_redondea_lejos_de_cero_en_el_medio():
    """ROUND_HALF_UP de Decimal redondea .5 lejos de cero en negativos
    (-2.675 -> -2.68), no hacia el par -- comportamiento distinto de
    round() nativo (-2.67) y de "half up" en el sentido aritmetico
    ingenuo (que seria -2.67). Documentado para que no sorprenda: es el
    mismo ROUND_HALF_UP que ya usa parse_entero, sin casos especiales
    para negativos."""
    assert parsers.redondear(-2.675, 2) == -2.68
