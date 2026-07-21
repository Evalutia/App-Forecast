"""Self-check para el criterio de elegibilidad de #70 aplicado en #73.

Corre sin pytest (mismo patron que los demas tests de este directorio). Modo
modulo, no como script suelto:
    python3 -m tests.test_apply_elegibilidad

Issue #102: agrega tests para build_decisiones/compute_summary, la
extraccion del computo de resumen que antes solo vivia inline en main()
(imprimiendo directo). Ambas son puras (sin DB) -- build_decisiones toma un
DataFrame ya armado a mano (no una query real), compute_summary toma listas/
dicts fabricados. No se agrega una fixture de DB nueva: elegir_ganador_y_
elegibilidad (arriba) ya prueba que este archivo no necesita una para cubrir
la logica de decision, y build_decisiones/compute_summary heredan esa misma
propiedad.
"""
from __future__ import annotations

import pandas as pd

from ml.apply_elegibilidad import (
    elegir_ganador_y_elegibilidad,
    build_decisiones,
    compute_summary,
)


def _fila(modelo, r2_test, estable, n_folds=3):
    return {"modelo": modelo, "r2_test": r2_test, "estable": estable, "n_folds": n_folds}


def test_gana_el_modelo_con_mejor_r2_test():
    filas = [_fila("RF", 0.05, True), _fila("PROPHET", 0.32, False), _fila("XGB", 0.0, True)]
    r = elegir_ganador_y_elegibilidad(filas)
    assert r["modelo"] == "PROPHET", f"esperaba PROPHET (mayor r2_test), dio {r['modelo']}"
    assert r["r2_test"] == 0.32


def test_ignora_filas_con_r2_test_none_o_nan():
    filas = [_fila("RF", None, True), _fila("XGB", float("nan"), True), _fila("PROPHET", 0.02, True)]
    r = elegir_ganador_y_elegibilidad(filas)
    assert r["modelo"] == "PROPHET"


def test_devuelve_none_si_ninguna_fila_tiene_r2_test_valido():
    filas = [_fila("RF", None, True), _fila("XGB", float("nan"), None)]
    r = elegir_ganador_y_elegibilidad(filas)
    assert r is None


def test_elegible_cuando_r2_test_no_negativo_y_estable():
    r = elegir_ganador_y_elegibilidad([_fila("PROPHET", 0.32, True)])
    assert r["elegible"] is True


def test_elegible_cuando_r2_test_es_exactamente_cero_y_estable():
    # Issue #72: r2_test=0 es un resultado real y valido (peor caso de
    # generalizacion, no "sin dato") -- el umbral de #70 es >=0, no >0.
    r = elegir_ganador_y_elegibilidad([_fila("RF", 0.0, True)])
    assert r["elegible"] is True


def test_no_elegible_cuando_r2_test_es_negativo():
    r = elegir_ganador_y_elegibilidad([_fila("XGB", -0.1, True)])
    assert r["elegible"] is False


def test_no_elegible_cuando_es_volatil_aunque_r2_test_pase():
    # Issue #70: la volatilidad entre folds es un descalificador duro para
    # ELEGIBILIDAD (a diferencia de #88, donde es solo informativa para la
    # seleccion de predict.py -- son dos decisiones distintas).
    r = elegir_ganador_y_elegibilidad([_fila("PROPHET", 0.32, False)])
    assert r["elegible"] is False


def test_no_elegible_cuando_estable_es_none_un_solo_fold():
    # Issue #70: "SKUs con solo 1 fold evaluable... se tratan como no
    # elegibles por ahora" -- estable=None (no evaluable) no pasa el gate,
    # sin necesidad de un caso especial (None no es truthy).
    r = elegir_ganador_y_elegibilidad([_fila("RF", 0.5, None, n_folds=1)])
    assert r["elegible"] is False


def test_no_elegible_cuando_estable_es_nan_pandas():
    # Regresion: pandas lee un NULL de MySQL en una columna float64 como
    # NaN, no None -- y bool(float('nan')) es True en Python. Sin el
    # saneo, esto colaba SKUs de 1 solo fold como "elegibles" (bug real
    # encontrado comparando el dry-run contra el calculo manual: 1324 vs
    # 1219 elegibles).
    r = elegir_ganador_y_elegibilidad([_fila("RF", 0.5, float("nan"), n_folds=1)])
    assert r["elegible"] is False
    assert r["estable"] is None, "NaN debe normalizarse a None antes de persistir (pymysql rechaza NaN)"


def test_n_folds_nan_se_normaliza_a_none():
    # Mismo problema que estable: si n_folds llega como NaN (columna
    # nullable, upcasteada por pandas), pymysql lo rechaza al persistir.
    filas = [_fila("RF", 0.5, True, n_folds=float("nan"))]
    r = elegir_ganador_y_elegibilidad(filas)
    assert r["n_folds"] is None


# -------------------------------------------------------------------------
# build_decisiones -- groupby por sku sobre un DataFrame ya deduplicado
# (ver fetch_catalogo), sin DB
# -------------------------------------------------------------------------

def _catalogo_df(rows):
    """rows: lista de dicts con sku/modelo/r2_test/estable/n_folds/fecha_estimacion."""
    return pd.DataFrame(rows)


def test_build_decisiones_un_ganador_por_sku():
    rows = [
        {"sku": "A", "modelo": "RF", "r2_test": 0.2, "estable": True, "n_folds": 3, "fecha_estimacion": "2026-07-01"},
        {"sku": "A", "modelo": "XGB", "r2_test": 0.5, "estable": True, "n_folds": 3, "fecha_estimacion": "2026-07-01"},
        {"sku": "B", "modelo": "PROPHET", "r2_test": -0.1, "estable": True, "n_folds": 3, "fecha_estimacion": "2026-07-01"},
    ]
    decisiones = build_decisiones(_catalogo_df(rows))
    por_sku = {d["sku"]: d for d in decisiones}
    assert len(decisiones) == 2
    assert por_sku["A"]["modelo"] == "XGB"
    assert por_sku["A"]["elegible"] is True
    assert por_sku["B"]["elegible"] is False


def test_build_decisiones_descarta_sku_sin_r2_test_valido():
    rows = [
        {"sku": "A", "modelo": "RF", "r2_test": None, "estable": True, "n_folds": 3, "fecha_estimacion": "2026-07-01"},
    ]
    decisiones = build_decisiones(_catalogo_df(rows))
    assert decisiones == []


# -------------------------------------------------------------------------
# compute_summary -- el resumen que main() imprimia inline, ahora extraido
# como dict puro (issue #102, reusado por la automatizacion mensual)
# -------------------------------------------------------------------------

def _decision(sku, elegible, modelo="RF"):
    return {"sku": sku, "modelo": modelo, "r2_test": 0.5, "estable": True, "n_folds": 3, "elegible": elegible}


def test_compute_summary_cuenta_evaluados_y_elegibles():
    decisiones = [_decision("A", True), _decision("B", False), _decision("C", True)]
    r = compute_summary(decisiones, actual_map={}, skus_medidos={"A", "B", "C"})
    assert r["skus_evaluados"] == 3
    assert r["elegibles"] == 2


def test_compute_summary_ganan_pierden_sin_cambio():
    decisiones = [_decision("A", True), _decision("B", False), _decision("C", True)]
    actual_map = {"A": False, "B": True, "C": True}  # A gana, B pierde, C sin cambio
    r = compute_summary(decisiones, actual_map, skus_medidos={"A", "B", "C"})
    assert r["ganan"] == 1
    assert r["pierden"] == 1
    assert r["sin_cambio"] == 1


def test_compute_summary_sin_decisiones_devuelve_ceros():
    r = compute_summary([], actual_map={"A": True}, skus_medidos=set())
    assert r["skus_evaluados"] == 0
    assert r["elegibles"] == 0
    assert r["ganan"] == 0
    assert r["pierden"] == 0
    assert r["sin_cambio"] == 0
    assert r["revocados_sin_medicion"] == []


def test_compute_summary_revocados_sin_medicion():
    # D es elegible en produccion pero no aparece medido en esta version --
    # mismo concepto que "huerfanos" en main()/revocar_elegibilidad_sin_medicion.
    decisiones = [_decision("A", True)]
    actual_map = {"A": True, "D": True}
    r = compute_summary(decisiones, actual_map, skus_medidos={"A"})
    assert r["revocados_sin_medicion"] == ["D"]


def test_compute_summary_revocados_ordenados():
    decisiones = [_decision("A", True)]
    actual_map = {"A": True, "Z": True, "B": True}
    r = compute_summary(decisiones, actual_map, skus_medidos={"A"})
    assert r["revocados_sin_medicion"] == ["B", "Z"]


if __name__ == "__main__":
    test_gana_el_modelo_con_mejor_r2_test()
    test_ignora_filas_con_r2_test_none_o_nan()
    test_devuelve_none_si_ninguna_fila_tiene_r2_test_valido()
    test_elegible_cuando_r2_test_no_negativo_y_estable()
    test_elegible_cuando_r2_test_es_exactamente_cero_y_estable()
    test_no_elegible_cuando_r2_test_es_negativo()
    test_no_elegible_cuando_es_volatil_aunque_r2_test_pase()
    test_no_elegible_cuando_estable_es_none_un_solo_fold()
    test_no_elegible_cuando_estable_es_nan_pandas()
    test_n_folds_nan_se_normaliza_a_none()
    test_build_decisiones_un_ganador_por_sku()
    test_build_decisiones_descarta_sku_sin_r2_test_valido()
    test_compute_summary_cuenta_evaluados_y_elegibles()
    test_compute_summary_ganan_pierden_sin_cambio()
    test_compute_summary_sin_decisiones_devuelve_ceros()
    test_compute_summary_revocados_sin_medicion()
    test_compute_summary_revocados_ordenados()
    print("OK - test_apply_elegibilidad.py")
