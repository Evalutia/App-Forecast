"""
Tests de las funciones puras de scripts/validaciones_transversales.py (issue
#198). Mismo patrón que #195/#196/#197/#199/#200: el script vive en scripts/,
se agrega ese directorio al path.

Las funciones de I/O (conexión a MySQL) no se testean acá -- se verifican por
integración contra producción, igual que las anteriores.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from cargador_archivos_cliente import ArticuloCliente, Movimiento  # noqa: E402
from comparar_ventas_mensual import FilaDiscrepancia  # noqa: E402
from validaciones_transversales import (  # noqa: E402
    CeldaNegativa,
    clasificar_grupos,
    comparar_clasificacion_genero,
    construir_negativos_cliente,
    resumen_negativos_cliente,
    resumen_negativos_nuestro,
    resumen_por_genero,
    resumen_por_poblacion_grupo,
)


def _fila(sku, year, month, diff_abs, categoria=None, cohorte="pre"):
    if categoria is None:
        categoria = "coincide" if diff_abs == 0 else ("deficit" if diff_abs < 0 else "superavit")
    return FilaDiscrepancia(
        sku=sku, year=year, month=month, cohorte=cohorte,
        cliente_original=None, cliente_numerico=abs(diff_abs), nuestro=0,
        diff_abs=diff_abs, diff_rel=None, categoria=categoria)


def _articulo(sku, ventas):
    return ArticuloCliente(sku=sku, descripcion=None, barcode=None, ventas=dict(ventas),
                           rotaciones={}, rot_desestac=None, rot_manual=None, estado="A")


# ── construir_negativos_cliente ──────────────────────────────────────────────

def test_construir_negativos_solo_toma_celdas_negativas():
    cliente = {
        "C001": _articulo("C001", {(2025, 8): -3, (2025, 9): 5}),
        "C002": _articulo("C002", {(2025, 8): None}),
    }
    negs = construir_negativos_cliente(cliente, {"C001", "C002"})
    assert len(negs) == 1
    assert negs[0].sku == "C001" and negs[0].valor_cliente == -3


def test_construir_negativos_respeta_conjunto_comun():
    cliente = {"C001": _articulo("C001", {(2025, 8): -3}),
               "C999": _articulo("C999", {(2025, 8): -5})}
    negs = construir_negativos_cliente(cliente, {"C001"})
    assert {n.sku for n in negs} == {"C001"}


def test_construir_negativos_etiqueta_cohorte():
    cliente = {"C001": _articulo("C001", {(2026, 6): -1, (2026, 8): -1})}
    negs = construir_negativos_cliente(cliente, {"C001"})
    por_mes = {n.month: n.cohorte for n in negs}
    assert por_mes[6] == "pre" and por_mes[8] == "post"


# ── CeldaNegativa.tiene_contraparte ──────────────────────────────────────────

def test_celda_negativa_tiene_contraparte_si_hay_dias_negativos():
    c = CeldaNegativa(sku="C001", year=2025, month=8, cohorte="pre",
                      valor_cliente=-3, dias_negativos_nuestro=1, unidades_negativas_nuestro=-3)
    assert c.tiene_contraparte is True


def test_celda_negativa_sin_contraparte():
    c = CeldaNegativa(sku="C001", year=2025, month=8, cohorte="pre",
                      valor_cliente=-3, dias_negativos_nuestro=0, unidades_negativas_nuestro=0)
    assert c.tiene_contraparte is False


# ── resumen_negativos_cliente ────────────────────────────────────────────────

def test_resumen_negativos_cliente_cuenta_con_y_sin_contraparte():
    celdas = (
        CeldaNegativa("C001", 2025, 8, "pre", -3, 1, -3),   # con contraparte
        CeldaNegativa("C002", 2025, 9, "pre", -5, 0, 0),    # sin contraparte
        CeldaNegativa("C003", 2026, 8, "post", -1, 2, -4),  # con contraparte
    )
    r = resumen_negativos_cliente(celdas)
    assert r["total"] == 3
    assert r["con_contraparte"] == 2
    assert r["sin_contraparte"] == 1


def test_resumen_negativos_cliente_particiona_por_cohorte():
    celdas = (
        CeldaNegativa("C001", 2025, 8, "pre", -3, 1, -3),
        CeldaNegativa("C002", 2026, 8, "post", -1, 0, 0),
    )
    r = resumen_negativos_cliente(celdas)
    assert r["por_cohorte"]["pre"]["total"] == 1
    assert r["por_cohorte"]["pre"]["con_contraparte"] == 1
    assert r["por_cohorte"]["post"]["total"] == 1
    assert r["por_cohorte"]["post"]["con_contraparte"] == 0


def test_resumen_negativos_cliente_vacio():
    r = resumen_negativos_cliente(())
    assert r["total"] == 0 and r["con_contraparte"] == 0 and r["sin_contraparte"] == 0


# ── resumen_negativos_nuestro (dirección inversa) ────────────────────────────
#
# De nuestras filas-día con cantidad negativa, ¿cuántas caen en un mes donde el
# cliente TAMBIÉN reportó negativo, y cuántas en un mes que para el cliente
# neteó a positivo o no aparece? Ilustra el efecto de escala mes-vs-día.

def test_resumen_negativos_nuestro_distingue_coincide_de_neteado():
    # (sku,y,m) -> dias_negativos
    nuestro = {("C001", 2025, 8): 1, ("C002", 2025, 9): 3}
    negativos_cliente_set = {("C001", 2025, 8)}  # sólo C001 reportó negativo
    r = resumen_negativos_nuestro(nuestro, negativos_cliente_set)
    assert r["total_meses_con_negativo_nuestro"] == 2
    assert r["coincide_con_cliente"] == 1
    assert r["neteado_o_ausente_del_lado_cliente"] == 1


# ── clasificar_grupos ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,esperado", [(0, "sin_grupo"), (1, "unico"), (2, "multi"), (5, "multi")])
def test_clasificar_grupos(n, esperado):
    assert clasificar_grupos(n) == esperado


# ── resumen_por_poblacion_grupo ───────────────────────────────────────────────

def test_resumen_por_poblacion_separa_unico_de_multi():
    filas = (
        _fila("C001", 2025, 8, -10),  # deficit, unico
        _fila("C002", 2025, 8, -20),  # deficit, multi
        _fila("C003", 2025, 8, 5),    # superavit, unico -- no cuenta para deficit
    )
    grupos = {"C001": 1, "C002": 2, "C003": 1}
    r = resumen_por_poblacion_grupo(filas, grupos)
    assert r["unico"]["skus"] == 2  # C001 y C003 son SKUs únicos en el dataset
    assert r["unico"]["unidades_deficit"] == 10
    assert r["multi"]["skus"] == 1
    assert r["multi"]["unidades_deficit"] == 20


def test_resumen_por_poblacion_grupo_sku_sin_grupo():
    filas = (_fila("C999", 2025, 8, -5),)
    grupos = {}  # C999 no aparece en articulo_grupo
    r = resumen_por_poblacion_grupo(filas, grupos)
    assert r["sin_grupo"]["skus"] == 1
    assert r["sin_grupo"]["unidades_deficit"] == 5


def test_resumen_por_poblacion_grupo_cuenta_skus_no_filas():
    # Un mismo SKU aparece en varios meses -- el tamaño de población es SKUs
    # distintos, no cantidad de filas.
    filas = (_fila("C001", 2025, 8, -10), _fila("C001", 2025, 9, -5))
    grupos = {"C001": 1}
    r = resumen_por_poblacion_grupo(filas, grupos)
    assert r["unico"]["skus"] == 1
    assert r["unico"]["unidades_deficit"] == 15


# ── resumen_por_genero ────────────────────────────────────────────────────────

def test_resumen_por_genero_agrupa_y_rankea():
    filas = (
        _fila("C001", 2025, 8, -100),
        _fila("C002", 2025, 8, -10),
        _fila("C003", 2025, 8, -5),
    )
    generos = {"C001": "TONER CPT", "C002": "TONER CPT", "C003": "PAPEL FOTO"}
    r = resumen_por_genero(filas, generos)
    ordenado = sorted(r.items(), key=lambda kv: -kv[1]["unidades_deficit"])
    assert ordenado[0][0] == "TONER CPT"
    assert ordenado[0][1]["unidades_deficit"] == 110
    assert ordenado[1][0] == "PAPEL FOTO"


def test_resumen_por_genero_pct_del_total():
    filas = (_fila("C001", 2025, 8, -75), _fila("C002", 2025, 8, -25))
    generos = {"C001": "A", "C002": "B"}
    r = resumen_por_genero(filas, generos)
    assert r["A"]["pct_del_total"] == pytest.approx(75.0)
    assert r["B"]["pct_del_total"] == pytest.approx(25.0)


def test_resumen_por_genero_sku_sin_genero_va_a_desconocido():
    filas = (_fila("C999", 2025, 8, -10),)
    r = resumen_por_genero(filas, {})
    assert "(sin género)" in r
    assert r["(sin género)"]["unidades_deficit"] == 10


# ── comparar_clasificacion_genero ────────────────────────────────────────────

def _mov(sku, genero):
    return Movimiento(sku=sku, descripcion=None, unidades=1,
                      tipo_documento="Ajuste de Entrada", genero=genero)


def test_comparar_clasificacion_genero_coincide():
    movimientos = (_mov("C001", "TONER CPT"),)
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["coincide"] == 1 and r["difiere"] == 0


def test_comparar_clasificacion_genero_normaliza_antes_de_comparar():
    # Mayúsculas/espacios no deberían contar como una diferencia real.
    movimientos = (_mov("C001", "  toner cpt "),)
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["coincide"] == 1


def test_comparar_clasificacion_genero_detecta_diferencia_real():
    movimientos = (_mov("C001", "{Sin Definir}"),)
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["difiere"] == 1
    assert r["ejemplos"][0] == ("C001", "{Sin Definir}", "TONER CPT")


def test_comparar_clasificacion_genero_ignora_artefactos_sin_sku_nuestro():
    movimientos = (_mov("HX030", "{Sin Definir}"),)  # HX030 no está en articulos
    generos_nuestro = {}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["sin_dato_nuestro"] == 1
    assert r["coincide"] == 0 and r["difiere"] == 0


def test_comparar_clasificacion_genero_none_no_se_compara_como_string_literal():
    # parsear_movimientos (#195) inicializa genero=None y sólo lo llena al ver
    # una banda "Genero:" -- una fila de detalle antes de la primera banda
    # (no pasa en el archivo de hoy, pero un archivo futuro podría traerlo)
    # no debe compararse como si "None" fuera un género real.
    movimientos = (_mov("C001", None),)
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["sin_dato_archivo"] == 1
    assert r["coincide"] == 0 and r["difiere"] == 0


def test_comparar_clasificacion_genero_prefiere_el_primer_valor_no_nulo():
    # La primera ocurrencia de C001 trae genero=None (banda no vista todavía),
    # una ocurrencia posterior sí trae el dato real -- no debe perderse.
    movimientos = (_mov("C001", None), _mov("C001", "TONER CPT"))
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["coincide"] == 1
    assert r["sin_dato_archivo"] == 0


def test_comparar_clasificacion_genero_un_sku_por_sku_no_por_fila():
    # El mismo SKU puede repetirse en varias filas del archivo de movimientos
    # (distintos tipos de documento) -- no debe contarse dos veces.
    movimientos = (_mov("C001", "TONER CPT"), _mov("C001", "TONER CPT"))
    generos_nuestro = {"C001": "TONER CPT"}
    r = comparar_clasificacion_genero(movimientos, generos_nuestro)
    assert r["coincide"] == 1
