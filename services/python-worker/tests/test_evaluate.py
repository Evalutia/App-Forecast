"""Self-check para r2_score y el piso de PREDICT_EVAL_HORIZON (issue #95).

Corre sin pytest (mismo patron que los demas tests de este directorio). Modo
modulo, no como script suelto:
    python3 -m tests.test_evaluate
"""
from __future__ import annotations

from ml.evaluate import r2_score


def test_r2_score_con_2_puntos_es_degenerado_siempre_1():
    # Issue #95: con exactamente 2 puntos no-constantes, la correlacion de
    # Pearson es matematicamente siempre +-1 -- el cuadrado da siempre 1.0,
    # sea buena o mala la prediccion. Esto NO es un bug de r2_score en si
    # (la formula es correcta) -- es que 2 puntos nunca alcanzan para medir
    # nada. El fix real esta en predict.py (issue #95): no evaluar
    # walk-forward con un horizonte tan chico.
    assert abs(r2_score([10.0, 20.0], [11.0, 19.0]) - 1.0) < 1e-9, "prediccion 'buena' -> 1.0"
    assert abs(r2_score([10.0, 20.0], [100.0, 50.0]) - 1.0) < 1e-9, (
        "prediccion en tendencia opuesta y con magnitud totalmente distinta -> "
        "sigue dando 1.0 (correlacion negativa al cuadrado tambien es 1.0)"
    )


def test_r2_score_con_4_puntos_no_es_degenerado():
    # Con >=3-4 puntos, una prediccion sin relacion real con y_true SI puede
    # dar un r2 lejos de 1.0 -- a diferencia del caso de 2 puntos (siempre
    # 1.0 sin importar los valores), la metrica vuelve a ser informativa.
    y_true = [10.0, 12.0, 8.0, 15.0]
    y_pred_mala = [3.0, 9.0, 14.0, 2.0]  # sin relacion real con y_true
    r2 = r2_score(y_true, y_pred_mala)
    assert r2 < 0.9, f"con 4 puntos y una prediccion sin relacion real, esperaba r2 lejos de 1.0, dio {r2}"


def test_r2_score_con_4_puntos_prediccion_perfecta_da_1():
    y_true = [10.0, 12.0, 8.0, 15.0]
    assert r2_score(y_true, y_true) == 1.0


def test_predict_eval_horizon_default_no_es_degenerado():
    # Regresion directa del bug de #95: el horizonte de evaluacion de
    # predict.py tiene que ser >=3 para que r2_score sea informativo.
    from predict import PREDICT_EVAL_HORIZON

    assert PREDICT_EVAL_HORIZON >= 3, (
        f"PREDICT_EVAL_HORIZON={PREDICT_EVAL_HORIZON} es degenerado para r2_score (issue #95)"
    )


if __name__ == "__main__":
    test_r2_score_con_2_puntos_es_degenerado_siempre_1()
    test_r2_score_con_4_puntos_no_es_degenerado()
    test_r2_score_con_4_puntos_prediccion_perfecta_da_1()
    test_predict_eval_horizon_default_no_es_degenerado()
    print("OK - test_evaluate.py")
