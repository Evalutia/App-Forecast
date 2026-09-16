"""
Tests de las funciones puras de scripts/cargador_archivos_cliente.py (issue
#195). Mismo patrón que test_diagnostico_planillas_cliente.py (#127): el script
vive en scripts/, así que se agrega ese directorio al path.

openpyxl se importa de forma diferida dentro de las funciones de lectura, así
que todo lo de acá corre aunque la librería no esté instalada. Los tests de
integración contra los archivos reales se saltean solos si los fixtures no
están.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from cargador_archivos_cliente import (  # noqa: E402
    ARCHIVO_MOVIMIENTOS,
    ARCHIVO_VENTAS,
    ENTRADA_MERCADERIA,
    DIR_POR_DEFECTO,
    ajustar_cobertura_por_recodificacion,
    comparar_catalogo,
    emparejar_recodificaciones,
    normalizar_rotacion,
    normalizar_venta,
    parse_mes,
    parsear_filtros,
    parsear_movimientos,
    parsear_ventas,
)


# ── parse_mes ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etiqueta,esperado", [
    ("Vta.Ago/25", (2025, 8)),
    ("Ago/25", (2025, 8)),
    ("Vta.Ene/26", (2026, 1)),
    ("Dic/25", (2025, 12)),
    ("  Vta.Jul/26  ", (2026, 7)),
])
def test_parse_mes_reconoce_ambas_convenciones(etiqueta, esperado):
    assert parse_mes(etiqueta) == esperado


@pytest.mark.parametrize("etiqueta", [
    "Rotacion DesEstac.", "Rot. Manual", "Estado Art.", "Articulo",
    "Descripcion", "Codigos Barras", None, 42, "", "Vta.", "Xyz/25", "Jul-25",
])
def test_parse_mes_ignora_lo_que_no_es_mes(etiqueta):
    assert parse_mes(etiqueta) is None


# ── la regla nulo/cero, que es asimétrica entre venta y rotación ─────────────
#
# El cliente usa celda vacía para "no vendió" y nunca 0 explícito en las
# columnas de venta (0 ceros explícitos en 70.564 celdas), pero las columnas de
# rotación mensual sí están densas y usan cero real. Aplicar una sola regla a
# las dos familias genera miles de falsos positivos.

@pytest.mark.parametrize("crudo", [None, "", "   "])
def test_venta_vacia_es_none_no_cero(crudo):
    assert normalizar_venta(crudo) is None


def test_venta_cero_explicito_se_respeta_si_alguna_vez_aparece():
    # Hoy no aparece ninguno, pero si el cliente cambia de convención
    # queremos distinguirlo de un nulo, no colapsarlo.
    assert normalizar_venta(0) == 0


def test_venta_negativa_se_conserva():
    assert normalizar_venta(-7) == -7


def test_venta_devuelve_entero():
    assert normalizar_venta(5.0) == 5
    assert isinstance(normalizar_venta(5.0), int)


@pytest.mark.parametrize("crudo", [None, "", "   "])
def test_rotacion_vacia_es_none(crudo):
    assert normalizar_rotacion(crudo) is None


def test_rotacion_cero_es_un_cero_real_no_un_nulo():
    assert normalizar_rotacion(0) == 0.0
    assert normalizar_rotacion(0.0) == 0.0


def test_rotacion_devuelve_float():
    assert normalizar_rotacion(3) == 3.0
    assert isinstance(normalizar_rotacion(3), float)


# ── parsear_ventas ───────────────────────────────────────────────────────────

HDR_VENTAS = ("Articulo", "Descripcion", "Codigos Barras",
              "Vta.Ago/25", "Vta.Sep/25",
              "Ago/25", "Sep/25",
              "Rotacion DesEstac.", "Rot. Manual", "Estado Art.")

FILAS_VENTAS = (
    HDR_VENTAS,
    ("C001", "CARTUCHO EPSON", "7790000000001", 5, None, 0.5, 0.0, 0.25, 0.25, "A"),
    ("C002", "TONER SAMSUNG", None, None, -3, 0.0, 0.0, None, None, "D"),
)


def test_parsear_ventas_indexa_por_sku():
    art = parsear_ventas(FILAS_VENTAS)
    assert sorted(art) == ["C001", "C002"]


def test_parsear_ventas_lee_la_ventana_del_header_no_hardcodeada():
    art = parsear_ventas(FILAS_VENTAS)
    assert art["C001"].ventas == {(2025, 8): 5, (2025, 9): None}


def test_parsear_ventas_distingue_nulo_de_cero_entre_venta_y_rotacion():
    art = parsear_ventas(FILAS_VENTAS)["C002"]
    # venta vacía -> None (no vendió, no cero)
    assert art.ventas[(2025, 8)] is None
    # rotación cero -> cero real, no None
    assert art.rotaciones[(2025, 8)] == 0.0


def test_parsear_ventas_conserva_negativos():
    assert parsear_ventas(FILAS_VENTAS)["C002"].ventas[(2025, 9)] == -3


def test_parsear_ventas_lee_las_columnas_sueltas():
    c1 = parsear_ventas(FILAS_VENTAS)["C001"]
    assert (c1.rot_desestac, c1.rot_manual, c1.estado) == (0.25, 0.25, "A")
    assert c1.barcode == "7790000000001"
    c2 = parsear_ventas(FILAS_VENTAS)["C002"]
    assert c2.rot_desestac is None and c2.barcode is None and c2.estado == "D"


def test_parsear_ventas_ignora_filas_sin_sku():
    art = parsear_ventas(FILAS_VENTAS + ((None, None, None, 1, 1, 1, 1, 1, 1, "A"),))
    assert sorted(art) == ["C001", "C002"]


def test_parsear_ventas_falla_fuerte_ante_un_sku_duplicado():
    # Pisar en silencio perdería la venta de la primera fila y el diagnóstico
    # lo leería como "ese artículo vendió menos".
    filas = FILAS_VENTAS + (
        ("C001", "CARTUCHO EPSON", None, 99, None, 0.0, 0.0, None, None, "A"),)
    with pytest.raises(ValueError, match="C001"):
        parsear_ventas(filas)


def test_parsear_ventas_normaliza_el_sku():
    art = parsear_ventas(
        (HDR_VENTAS, ("  c001  ", "X", None, 1, None, 0.0, 0.0, None, None, "A")))
    assert "C001" in art


# ── parsear_movimientos ──────────────────────────────────────────────────────
#
# El archivo de movimientos NO es una tabla plana: es un reporte bandeado con
# filas de sección, 35 filas de subtotal, una fila `Total General` con las
# columnas corridas y un pie de página. Un parser que no las filtre triplica
# los totales -- pasó durante la verificación del plan (dio +1209/-2457/+1399
# en vez de +403/-819/+466).

FILAS_MOV = (
    ("Articulo", "Descripción", " Unidades", None),
    ("Tipo de Documento: Ajuste de Entrada", None, None, None),
    ("Genero: TONER CPT", None, None, None),
    ("C001", "TONER X", 3, None),
    ("C002", "TONER Y", 2, None),
    ("Total", "Genero: TONER CPT", 5, None),
    ("Total", "Tipo de Documento: Ajuste de Entrada", 5, None),
    ("Tipo de Documento: Ajuste de Salida", None, None, None),
    ("Genero: {Sin Definir}", None, None, None),
    ("HX030", "MOCHILA\xa0PROMO", -150, None),
    ("Total", "Genero: {Sin Definir}", -150, None),
    ("Total", "Tipo de Documento: Ajuste de Salida", -150, None),
    ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
    ("Genero: {Sin Definir}", None, None, None),
    ("I01874", "MOCHILA", 150, None),
    ("Total", "Genero: {Sin Definir}", 150, None),
    ("Total", "Tipo de Documento: Entrada de Mercaderia", 150, None),
    ("Total General", 5, "Doc.: AJE,AJS,EMR,SMR,_x000d__x000a_", "Coleccion: Todos_x000d__x000a_"),
    ("New Age Data", "Pág.", 1, None),
)


def test_parsear_movimientos_devuelve_solo_las_filas_de_detalle():
    movs, _ = parsear_movimientos(FILAS_MOV)
    assert [m.sku for m in movs] == ["C001", "C002", "HX030", "I01874"]


def test_parsear_movimientos_descarta_los_subtotales():
    movs, _ = parsear_movimientos(FILAS_MOV)
    assert "Total" not in {m.sku for m in movs}


def test_parsear_movimientos_descarta_total_general_pese_a_las_columnas_corridas():
    # En esa fila el total cae en la 2da columna y la 3ra trae texto: un
    # float() sobre la 3ra columna revienta si no se filtra antes.
    movs, _ = parsear_movimientos(FILAS_MOV)
    assert "Total General" not in {m.sku for m in movs}


def test_parsear_movimientos_descarta_el_pie_de_pagina():
    # 'New Age Data' trae un número de página en la columna de unidades: se
    # ingiere como SKU fantasma con 1 unidad si no se filtra.
    movs, _ = parsear_movimientos(FILAS_MOV)
    assert "New Age Data" not in {m.sku for m in movs}


def test_parsear_movimientos_no_pierde_una_banda_que_arranca_en_la_primera_fila():
    # Un export sin fila de header: si se saltea la primera a ciegas, esa banda
    # queda sin tipo de documento y sus filas desaparecen del emparejamiento.
    movs, _ = parsear_movimientos((
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: G", None, None, None),
        ("C001", "X", -5, None),
    ))
    assert [(m.sku, m.tipo_documento) for m in movs] == [("C001", "Ajuste de Salida")]


def test_parsear_movimientos_acepta_un_generador():
    # openpyxl.iter_rows devuelve un generador, no una lista.
    movs, _ = parsear_movimientos(iter(FILAS_MOV))
    assert [m.sku for m in movs] == ["C001", "C002", "HX030", "I01874"]


def test_parsear_movimientos_tolera_unidades_como_decimal():
    # Una celda que llega como '12.0' pasa un chequeo con float() y después
    # revienta en int() si la conversión no pasa por float primero.
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Entrada", None, None, None),
        ("Genero: G", None, None, None),
        ("C001", "X", "12.0", None),
    ))
    assert [m.unidades for m in movs] == [12]


def test_parsear_movimientos_arrastra_tipo_y_genero_como_estado():
    movs, _ = parsear_movimientos(FILAS_MOV)
    por_sku = {m.sku: m for m in movs}
    assert por_sku["C001"].tipo_documento == "Ajuste de Entrada"
    assert por_sku["C001"].genero == "TONER CPT"
    assert por_sku["HX030"].tipo_documento == "Ajuste de Salida"
    assert por_sku["HX030"].genero == "{Sin Definir}"
    assert por_sku["I01874"].tipo_documento == ENTRADA_MERCADERIA


def test_parsear_movimientos_limpia_el_espacio_de_no_quiebre():
    movs, _ = parsear_movimientos(FILAS_MOV)
    desc = {m.sku: m.descripcion for m in movs}["HX030"]
    assert "\xa0" not in desc and desc == "MOCHILA PROMO"


def test_parsear_movimientos_conserva_el_signo():
    movs, _ = parsear_movimientos(FILAS_MOV)
    assert {m.sku: m.unidades for m in movs}["HX030"] == -150


# ── filtros del reporte ──────────────────────────────────────────────────────
#
# La fila `Total General` expone con qué filtros se generó el reporte. El
# importante es `Doc.`, una whitelist de tipos de documento: acota lo que se
# puede concluir sobre #193, porque una transferencia con otro código habría
# quedado excluida por el filtro y no por ausencia real.

def test_parsear_filtros_extrae_la_whitelist_de_documentos():
    _, filtros = parsear_movimientos(FILAS_MOV)
    assert filtros.doc == ("AJE", "AJS", "EMR", "SMR")


def test_parsear_filtros_conserva_todas_las_lineas():
    _, filtros = parsear_movimientos(FILAS_MOV)
    assert "Coleccion: Todos" in filtros.lineas


def test_parsear_filtros_parte_por_el_escape_literal_de_openpyxl():
    filtros = parsear_filtros(["Seccion: 0 a 99_x000d__x000a_Marca: 0 a 99_x000d__x000a_"])
    assert filtros.lineas == ("Seccion: 0 a 99", "Marca: 0 a 99")


def test_parsear_filtros_tambien_parte_por_saltos_reales():
    filtros = parsear_filtros(["Seccion: 0 a 99\r\nMarca: 0 a 99"])
    assert filtros.lineas == ("Seccion: 0 a 99", "Marca: 0 a 99")


def test_parsear_filtros_sin_doc_no_inventa_whitelist():
    assert parsear_filtros(["Coleccion: Todos"]).doc == ()


# ── emparejar recodificaciones ───────────────────────────────────────────────
#
# El 100% de las Entradas de Mercadería del archivo real es la contrapartida
# exacta de salidas del mismo mes: es renumeración de códigos, no stock
# perdido. Se empareja por monto, no por una lista hardcodeada.

def test_emparejar_reconoce_el_par_uno_a_uno():
    movs, _ = parsear_movimientos(FILAS_MOV)
    pares = emparejar_recodificaciones(movs)
    assert len(pares) == 1
    assert pares[0].destino == "I01874"
    assert pares[0].origenes == ("HX030",)


def test_emparejar_resuelve_una_entrada_contra_varias_salidas():
    # El caso real: I01874 +176 <- HX030 -150 + I01874 -26.
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: G", None, None, None),
        ("HX030", "MOCHILA PROMO", -150, None),
        ("I01874", "MOCHILA", -26, None),
        ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
        ("Genero: G", None, None, None),
        ("I01874", "MOCHILA", 176, None),
    ))
    pares = emparejar_recodificaciones(movs)
    assert len(pares) == 1
    assert pares[0].destino == "I01874"
    assert sorted(pares[0].origenes) == ["HX030", "I01874"]


def test_emparejar_no_inventa_pares_cuando_no_cierra():
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: G", None, None, None),
        ("C001", "X", -7, None),
        ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
        ("Genero: G", None, None, None),
        ("C002", "Y", 99, None),
    ))
    assert emparejar_recodificaciones(movs) == ()


def test_emparejar_desempata_por_descripcion_cuando_el_monto_es_ambiguo():
    # Caso real: K00012 (+14) tiene dos salidas de magnitud 14 disponibles.
    # Por monto solo, el emparejamiento es ambiguo y elige cualquiera; la
    # contrapartida verdadera es la que comparte identidad de producto.
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: CARG p CEL", None, None, None),
        ("I01393", "CARGADOR TIPO-C EU46 3A 18W USB 3.0 FONENG", -14, None),
        ("Genero: REPUESTOS", None, None, None),
        ("I01878", "(NO USAR) Carcasa A CHUWI Corebook X I5 repuesto", -14, None),
        ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
        ("Genero: REPUESTOS", None, None, None),
        ("K00012", "Carcasa A Bisagra Corebook X repuesto CHUWI", 14, None),
    ))
    pares = emparejar_recodificaciones(movs)
    assert len(pares) == 1
    assert pares[0].origenes == ("I01878",)


def test_emparejar_empareja_igual_sin_parecido_de_descripcion():
    # Si no hay ninguna candidata parecida pero el monto cierra sin ambigüedad,
    # el par se arma igual: la descripción desempata, no es un requisito.
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: G", None, None, None),
        ("C001", "ALGO COMPLETAMENTE DISTINTO", -14, None),
        ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
        ("Genero: G", None, None, None),
        ("K00012", "Carcasa A Bisagra Corebook X repuesto CHUWI", 14, None),
    ))
    pares = emparejar_recodificaciones(movs)
    assert len(pares) == 1 and pares[0].origenes == ("C001",)


def test_emparejar_no_reutiliza_una_salida_en_dos_entradas():
    movs, _ = parsear_movimientos((
        ("Articulo", "Descripción", " Unidades", None),
        ("Tipo de Documento: Ajuste de Salida", None, None, None),
        ("Genero: G", None, None, None),
        ("C001", "X", -10, None),
        ("Tipo de Documento: Entrada de Mercaderia", None, None, None),
        ("Genero: G", None, None, None),
        ("C002", "Y", 10, None),
        ("C003", "Z", 10, None),
    ))
    pares = emparejar_recodificaciones(movs)
    assert len(pares) == 1


# ── cobertura de catálogo ────────────────────────────────────────────────────

def test_comparar_catalogo_parte_en_tres_conjuntos():
    cob = comparar_catalogo(["A", "B", "C"], ["B", "C", "D"])
    assert cob.comunes == ("B", "C")
    assert cob.solo_cliente == ("A",)
    assert cob.solo_nuestros == ("D",)


def test_comparar_catalogo_normaliza_antes_de_cruzar():
    cob = comparar_catalogo([" a ", "b"], ["A", "B"])
    assert cob.solo_cliente == () and cob.solo_nuestros == ()


def test_ausencia_por_recodificacion_no_cuenta_como_hueco():
    # HX030 no está en articulos, pero sus unidades volvieron bajo I01874, que
    # sí está: no es un hueco nuestro, es un código retirado por el cliente.
    movs, _ = parsear_movimientos(FILAS_MOV)
    cob = comparar_catalogo({m.sku for m in movs}, ["C001", "C002", "I01874"])
    assert cob.solo_cliente == ("HX030",)

    ajuste = ajustar_cobertura_por_recodificacion(cob, movs)
    assert ajuste.recodificados == ("HX030",)
    assert ajuste.ausencias_reales == ()


def test_ausencia_sin_contrapartida_sigue_siendo_hueco():
    movs, _ = parsear_movimientos(FILAS_MOV + (
        ("Tipo de Documento: Ajuste de Entrada", None, None, None),
        ("Genero: G", None, None, None),
        ("I02045", "CONTROL TV BOX", 4, None),
    ))
    cob = comparar_catalogo({m.sku for m in movs}, ["C001", "C002", "I01874"])
    ajuste = ajustar_cobertura_por_recodificacion(cob, movs)
    assert ajuste.ausencias_reales == ("I02045",)
    assert "I02045" not in ajuste.recodificados


# ── integración contra los archivos reales ───────────────────────────────────
#
# Los números de acá son los criterios de aceptación del issue #195. Se saltean
# si los fixtures no están (el repo es privado pero los xlsx pueden no haberse
# copiado todavía).

ARCH_VENTAS = os.path.join(DIR_POR_DEFECTO, ARCHIVO_VENTAS)
ARCH_MOV = os.path.join(DIR_POR_DEFECTO, ARCHIVO_MOVIMIENTOS)


def _falta_openpyxl():
    try:
        import openpyxl  # noqa: F401
        return False
    except ImportError:
        return True


# El skip va por test, NO a nivel de módulo: un `importorskip` arriba saltearía
# también los 57 tests de funciones puras, que son justamente los que tienen que
# correr donde no hay openpyxl -- que es el escenario para el que el módulo
# difiere el import.
sin_fixtures = pytest.mark.skipif(
    _falta_openpyxl() or not (os.path.exists(ARCH_VENTAS) and os.path.exists(ARCH_MOV)),
    reason="fixtures de #195 u openpyxl no presentes",
)


@sin_fixtures
def test_real_ventas_dimensiones():
    from cargador_archivos_cliente import leer_ventas
    art = leer_ventas(ARCH_VENTAS)
    assert len(art) == 5428
    meses = sorted({m for a in art.values() for m in a.ventas})
    assert len(meses) == 13
    assert meses[0] == (2025, 8) and meses[-1] == (2026, 8)


@sin_fixtures
def test_real_ventas_regla_nulo_cero():
    from cargador_archivos_cliente import leer_ventas
    art = leer_ventas(ARCH_VENTAS)
    celdas = [v for a in art.values() for v in a.ventas.values()]
    assert len(celdas) == 70564
    assert sum(1 for v in celdas if v is None) == 57272
    assert sum(1 for v in celdas if v == 0) == 0, "el cliente nunca usa cero explícito en venta"
    assert sum(1 for v in celdas if v is not None and v < 0) == 331
    assert sum(1 for v in celdas if v is not None and v > 0) == 12961
    # las de rotación, en cambio, están densas y sí usan cero real
    rot = [v for a in art.values() for v in a.rotaciones.values()]
    assert sum(1 for v in rot if v is None) == 0
    assert sum(1 for v in rot if v == 0.0) > 0


@sin_fixtures
def test_real_ventas_columnas_sueltas():
    from cargador_archivos_cliente import leer_ventas
    art = leer_ventas(ARCH_VENTAS)
    assert sum(1 for a in art.values() if a.estado == "A") == 4719
    assert sum(1 for a in art.values() if a.estado == "D") == 709
    con_rot = [a for a in art.values() if a.rot_desestac is not None]
    assert len(con_rot) == 1419
    assert sum(1 for a in con_rot if a.rot_manual == a.rot_desestac) == 1419
    assert sum(1 for a in art.values() if a.barcode) == 1679
    assert sum(1 for a in art.values() if any(v is not None for v in a.ventas.values())) == 1855


@sin_fixtures
def test_real_movimientos_totales():
    from cargador_archivos_cliente import leer_movimientos
    movs, _ = leer_movimientos(ARCH_MOV)
    assert len(movs) == 127
    assert len({m.sku for m in movs}) == 124
    por_tipo = {}
    for m in movs:
        por_tipo[m.tipo_documento] = por_tipo.get(m.tipo_documento, 0) + m.unidades
    assert por_tipo["Ajuste de Entrada"] == 403
    assert por_tipo["Ajuste de Salida"] == -819
    assert por_tipo[ENTRADA_MERCADERIA] == 466
    assert sum(m.unidades for m in movs) == 50


@sin_fixtures
def test_real_movimientos_sin_artefactos():
    from cargador_archivos_cliente import leer_movimientos
    movs, _ = leer_movimientos(ARCH_MOV)
    skus = {m.sku for m in movs}
    for artefacto in ("Total", "Total General", "New Age Data"):
        assert artefacto not in skus
    assert not any(s.startswith("Tipo de Documento:") or s.startswith("Genero:") for s in skus)


@sin_fixtures
def test_real_movimientos_filtros_del_reporte():
    from cargador_archivos_cliente import leer_movimientos
    _, filtros = leer_movimientos(ARCH_MOV)
    assert filtros.doc == ("AJE", "AJS", "EMR", "SMR")
    assert "Art.: Activos - Inactivos - Disc." in filtros.lineas
    assert "NO Inc.Stk. Pendiente" in filtros.lineas


@sin_fixtures
def test_real_recodificacion_cubre_todas_las_entradas():
    from cargador_archivos_cliente import leer_movimientos
    movs, _ = leer_movimientos(ARCH_MOV)
    pares = emparejar_recodificaciones(movs)
    emparejado = sum(p.unidades for p in pares)
    total_emr = sum(m.unidades for m in movs if m.tipo_documento == ENTRADA_MERCADERIA)
    assert emparejado == total_emr == 466
    assert {p.destino for p in pares} == {
        "I01874", "I02210", "I02772", "K00010", "K00012", "K00027", "K00035", "C00482"}
    # los pares concretos, verificados a mano contra el archivo: son los que
    # #199 va a usar para chequear continuidad de stock, así que un par mal
    # armado ahí da un veredicto mal armado
    por_destino = {p.destino: tuple(sorted(p.origenes)) for p in pares}
    assert por_destino["I01874"] == ("HX030", "I01874")
    assert por_destino["I02210"] == ("HX031",)
    assert por_destino["I02772"] == ("I01396",)
    assert por_destino["C00482"] == ("C00482",)
    assert por_destino["K00010"] == ("I01875",)
    assert por_destino["K00012"] == ("I01878",)
    assert por_destino["K00027"] == ("I01951",)
    assert por_destino["K00035"] == ("I02320",)
