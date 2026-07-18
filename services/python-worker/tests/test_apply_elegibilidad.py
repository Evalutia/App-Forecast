"""Self-check para el criterio de elegibilidad de #70 aplicado en #73.

Corre sin pytest (mismo patron que los demas tests de este directorio). Modo
modulo, no como script suelto:
    python3 -m tests.test_apply_elegibilidad
"""
from __future__ import annotations

from ml.apply_elegibilidad import elegir_ganador_y_elegibilidad


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
    print("OK - test_apply_elegibilidad.py")
