"""Self-check para la seleccion de modelo ganador en predict.py (issue #89).

Corre sin pytest (mismo patron que test_eval_walkforward.py). Modo modulo,
no como script suelto -- si no, 'predict'/'ml' no quedan en sys.path:
    python3 -m tests.test_predict
"""
from __future__ import annotations

from predict import elegir_ganador, ScoredModel


class _FakeWalkForwardResult:
    def __init__(self, r2_test_median, stable=True, rmse_test_median=1.0):
        self.r2_test_median = r2_test_median
        self.stable = stable
        self.rmse_test_median = rmse_test_median


def test_elegir_ganador_devuelve_mayor_r2_test():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(0.10)),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.32)),
        ScoredModel("XGB", _FakeWalkForwardResult(0.05)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET", f"esperaba PROPHET (mayor r2_test), dio {name}"
    assert wf.r2_test_median == 0.32


def test_elegir_ganador_ignora_r2_test_none_o_nan():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(None)),
        ScoredModel("XGB", _FakeWalkForwardResult(float("nan"))),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.02)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET", f"esperaba el unico r2_test valido (PROPHET), dio {name}"


def test_elegir_ganador_volatil_igual_puede_ganar():
    # Issue #88: la volatilidad entre folds es solo informativa, no
    # descalifica al ganador -- un modelo volatil con mejor r2_test sigue
    # ganando sobre uno estable con peor r2_test.
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(0.05, stable=True)),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.32, stable=False)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET"
    assert wf.stable is False


def test_elegir_ganador_cae_al_primero_si_ningun_r2_test_es_valido():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(None)),
        ScoredModel("XGB", _FakeWalkForwardResult(float("nan"))),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "RF", f"esperaba caer al primero (RF), dio {name}"


if __name__ == "__main__":
    test_elegir_ganador_devuelve_mayor_r2_test()
    test_elegir_ganador_ignora_r2_test_none_o_nan()
    test_elegir_ganador_volatil_igual_puede_ganar()
    test_elegir_ganador_cae_al_primero_si_ningun_r2_test_es_valido()
    print("OK - test_predict.py")
