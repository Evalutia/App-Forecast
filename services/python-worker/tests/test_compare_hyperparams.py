"""Self-check para la herramienta de comparacion de hiperparametros (#101).

No mockea el subproceso de eval_walkforward.py ni la conexion a DB (awkward
y de bajo valor, ver docstring del issue) -- se enfoca en las partes puras:
parseo de CLI, merge de env vars, y sobre todo el computo del reporte a
partir de un set de filas de catalogo_modelos fabricadas a mano (normal,
r2_test=0.0 exacto, r2_test=1.0 exacto, estable NULL, cobertura incompleta).

Corre sin pytest (mismo patron que el resto de tests/). Modo modulo:
    python3 -m tests.test_compare_hyperparams
"""
from __future__ import annotations

from ml.compare_hyperparams import (
    parse_args,
    parse_explicit_skus,
    generate_version,
    build_env,
    compute_report,
    format_report,
    DEGENERACY_FLAG_THRESHOLD_PCT,
)
from datetime import datetime


def _fila(sku, modelo, r2_train=None, r2_test=None, estable=None):
    return {"sku": sku, "modelo": modelo, "r2_train": r2_train, "r2_test": r2_test, "estable": estable}


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def test_parse_args_skus_explicitos():
    args = parse_args(["--skus", "E00204,E00428", "--lags", "4"])
    assert args.skus == "E00204,E00428"
    assert args.random_n is None
    assert args.lags == 4


def test_parse_args_random_n():
    args = parse_args(["--random-n", "5"])
    assert args.random_n == 5
    assert args.skus is None


def test_parse_args_env_repetible():
    args = parse_args(["--random-n", "5", "--env", "RF_MAX_DEPTH=3", "--env", "XGB_LEARNING_RATE=0.05"])
    assert args.env == ["RF_MAX_DEPTH=3", "XGB_LEARNING_RATE=0.05"]


def test_parse_args_requiere_skus_o_random_n():
    try:
        parse_args([])
        assert False, "esperaba SystemExit (argparse) sin --skus ni --random-n"
    except SystemExit:
        pass


def test_parse_args_skus_y_random_n_son_mutuamente_excluyentes():
    try:
        parse_args(["--skus", "E00204", "--random-n", "5"])
        assert False, "esperaba SystemExit (argparse) con ambos flags a la vez"
    except SystemExit:
        pass


def test_parse_explicit_skus_recorta_espacios_y_descarta_vacios():
    assert parse_explicit_skus(" E00204 , E00428,, E00678 ") == ["E00204", "E00428", "E00678"]


# -------------------------------------------------------------------------
# Version autogenerada
# -------------------------------------------------------------------------

def test_generate_version_usa_explicito_si_se_paso():
    assert generate_version("mi-version-custom") == "mi-version-custom"


def test_generate_version_autogenera_con_timestamp_si_no_se_paso():
    v = generate_version(None, now=datetime(2026, 7, 21, 15, 30, 0))
    assert v == "compare-20260721-153000"


def test_generate_version_ignora_string_vacio():
    v = generate_version("   ", now=datetime(2026, 7, 21, 15, 30, 0))
    assert v == "compare-20260721-153000"


# -------------------------------------------------------------------------
# Merge de env vars
# -------------------------------------------------------------------------

def test_build_env_fija_persist_catalog_only_skus_version():
    env = build_env({"PATH": "/usr/bin"}, skus=["E00204", "E00428"], version="v-test")
    assert env["EVAL_PERSIST_CATALOG"] == "1"
    assert env["EVAL_ONLY_SKUS"] == "E00204,E00428"
    assert env["EVAL_VERSION"] == "v-test"
    assert env["PATH"] == "/usr/bin", "no debe pisar el resto del os.environ base"


def test_build_env_atajos_dedicados():
    env = build_env({}, skus=["E00204"], version="v-test", lags=4, horizon=6, max_folds=3)
    assert env["EVAL_LAGS"] == "4"
    assert env["EVAL_HORIZON"] == "6"
    assert env["EVAL_MAX_FOLDS"] == "3"


def test_build_env_atajos_ausentes_no_agregan_keys():
    env = build_env({}, skus=["E00204"], version="v-test")
    assert "EVAL_LAGS" not in env
    assert "EVAL_HORIZON" not in env
    assert "EVAL_MAX_FOLDS" not in env


def test_build_env_escape_hatch_generico():
    env = build_env({}, skus=["E00204"], version="v-test", extra_env=["RF_MAX_DEPTH=3", "XGB_LEARNING_RATE=0.05"])
    assert env["RF_MAX_DEPTH"] == "3"
    assert env["XGB_LEARNING_RATE"] == "0.05"


def test_build_env_extra_env_tiene_la_ultima_palabra_sobre_atajo():
    env = build_env({}, skus=["E00204"], version="v-test", lags=8, extra_env=["EVAL_LAGS=4"])
    assert env["EVAL_LAGS"] == "4"


def test_build_env_extra_env_sin_signo_igual_lanza_valueerror():
    try:
        build_env({}, skus=["E00204"], version="v-test", extra_env=["RF_MAX_DEPTH"])
        assert False, "esperaba ValueError con un --env sin '='"
    except ValueError:
        pass


# -------------------------------------------------------------------------
# compute_report -- el corazon testeable de la herramienta
# -------------------------------------------------------------------------

def test_compute_report_mediana_r2_test_real_no_solo_booleano():
    rows = [
        _fila("A", "RF", r2_train=0.5, r2_test=0.30, estable=True),
        _fila("B", "RF", r2_train=0.6, r2_test=0.50, estable=True),
        _fila("C", "RF", r2_train=0.4, r2_test=0.70, estable=True),
    ]
    r = compute_report(rows, requested_skus=["A", "B", "C"])
    assert r["median_r2_test"] == 0.50


def test_compute_report_brecha_train_test_informativa_separada():
    rows = [
        _fila("A", "RF", r2_train=0.6, r2_test=0.4, estable=True),
        _fila("B", "RF", r2_train=0.8, r2_test=0.6, estable=True),
    ]
    r = compute_report(rows, requested_skus=["A", "B"])
    assert abs(r["mean_train_test_gap"] - 0.2) < 1e-9
    # la brecha y la mediana de r2_test son numeros DISTINTOS y separados,
    # nunca colapsados en un solo score
    assert r["mean_train_test_gap"] != r["median_r2_test"]


def test_compute_report_pct_estable_ignora_nulos():
    rows = [
        _fila("A", "RF", r2_test=0.3, estable=True),
        _fila("B", "RF", r2_test=0.3, estable=False),
        _fila("C", "RF", r2_test=0.3, estable=None),  # 1 solo fold, no evaluable -- no debe contar ni en numerador ni denominador
    ]
    r = compute_report(rows, requested_skus=["A", "B", "C"])
    assert r["n_estable_rows"] == 2, "estable=None no debe entrar al denominador"
    assert r["pct_estable"] == 50.0


def test_compute_report_cobertura_detecta_muestra_incompleta():
    # Simula exactamente el escenario de #97: la muestra pedida tiene 5
    # SKUs, pero el hiperparametro probado solo produjo resultado valido
    # para 1 de ellos -- la cobertura tiene que reflejar eso, no quedar
    # oculta detras de un r2_test que se ve bien sobre ese unico SKU.
    rows = [_fila("A", "RF", r2_test=0.9, estable=True)]
    requested = ["A", "B", "C", "D", "E"]
    r = compute_report(rows, requested_skus=requested)
    assert r["coverage_pct"] == 20.0
    assert r["n_skus_covered"] == 1
    assert r["n_skus_requested"] == 5
    # y el r2_test alto no dice nada sobre esa cobertura baja -- son 2
    # numeros separados
    assert r["median_r2_test"] == 0.9


def test_compute_report_cobertura_ignora_skus_con_solo_filas_sin_r2_test():
    # Un SKU con fila en catalogo_modelos pero r2_test NULL (ej. todos los
    # folds degenerados y filtrados) no debe contar como "cubierto".
    rows = [_fila("A", "RF", r2_test=None, estable=None)]
    r = compute_report(rows, requested_skus=["A", "B"])
    assert r["coverage_pct"] == 0.0
    assert r["n_skus_covered"] == 0


def test_compute_report_degeneracion_cero_exacto():
    rows = [_fila("A", "RF", r2_test=0.0), _fila("B", "RF", r2_test=0.35)]
    r = compute_report(rows, requested_skus=["A", "B"])
    assert r["pct_degenerate"] == 50.0
    assert r["n_degenerate"] == 1


def test_compute_report_degeneracion_uno_exacto():
    rows = [_fila("A", "RF", r2_test=1.0), _fila("B", "RF", r2_test=0.35)]
    r = compute_report(rows, requested_skus=["A", "B"])
    assert r["pct_degenerate"] == 50.0


def test_compute_report_degeneracion_no_confunde_cercano_con_exacto():
    # Regresion clave del hallazgo de #97: 0.999999 NO es degenerado, solo
    # el valor EXACTO 1.0 (o 0.0) lo es -- comparacion de float exacta, no
    # "cercano a".
    rows = [_fila("A", "RF", r2_test=0.999999), _fila("B", "RF", r2_test=0.000001)]
    r = compute_report(rows, requested_skus=["A", "B"])
    assert r["pct_degenerate"] == 0.0, "0.999999/0.000001 no son degenerados, solo el valor EXACTO 0.0/1.0 lo es"


def test_compute_report_brecha_chica_con_r2_alto_no_es_lo_mismo_que_degenerado():
    # El caso central que #97 encontro: dos corridas pueden tener la MISMA
    # brecha chica train-test, una con senal real y otra degenerada -- el
    # reporte debe distinguirlas via pct_degenerate, no colapsarlas.
    rows_bueno = [_fila("A", "RF", r2_train=0.82, r2_test=0.80)]
    rows_degenerado = [_fila("A", "RF", r2_train=0.0, r2_test=0.0)]

    r_bueno = compute_report(rows_bueno, requested_skus=["A"])
    r_degenerado = compute_report(rows_degenerado, requested_skus=["A"])

    assert abs(r_bueno["mean_train_test_gap"] - 0.02) < 1e-9
    assert r_degenerado["mean_train_test_gap"] == 0.0
    # brechas parecidas (ambas chicas), pero un cuadro totalmente distinto:
    assert r_bueno["pct_degenerate"] == 0.0
    assert r_degenerado["pct_degenerate"] == 100.0
    assert r_bueno["median_r2_test"] == 0.80
    assert r_degenerado["median_r2_test"] == 0.0


def test_compute_report_sin_filas_todo_none():
    r = compute_report([], requested_skus=["A", "B"])
    assert r["median_r2_test"] is None
    assert r["mean_train_test_gap"] is None
    assert r["pct_estable"] is None
    assert r["pct_degenerate"] is None
    assert r["coverage_pct"] == 0.0


def test_compute_report_sin_skus_solicitados_cobertura_es_none():
    r = compute_report([_fila("A", "RF", r2_test=0.5)], requested_skus=[])
    assert r["coverage_pct"] is None


# -------------------------------------------------------------------------
# format_report -- smoke test, solo confirma que separa los 4 numeros
# -------------------------------------------------------------------------

def test_format_report_incluye_los_4_criterios_separados_y_flag_degeneracion():
    rows = [
        _fila("A", "RF", r2_train=0.0, r2_test=0.0, estable=True),
        _fila("B", "RF", r2_train=0.0, r2_test=0.0, estable=True),
    ]
    report_total = compute_report(rows, requested_skus=["A", "B"])
    reports_by_model = {"RF": report_total}
    texto = format_report("v-test", ["A", "B"], report_total, reports_by_model)

    assert "r2_test walk-forward (mediana" in texto
    assert "Brecha train-test" in texto
    assert "informativo, NO usar aislado" in texto
    assert "% estable=True" in texto
    assert "Cobertura" in texto
    assert "DEGENERACION" in texto
    assert "SOSPECHOSO" in texto, f"100% degenerado deberia superar el umbral ({DEGENERACY_FLAG_THRESHOLD_PCT}%) y flaggear"
    assert "Modelo: RF" in texto


if __name__ == "__main__":
    test_parse_args_skus_explicitos()
    test_parse_args_random_n()
    test_parse_args_env_repetible()
    test_parse_args_requiere_skus_o_random_n()
    test_parse_args_skus_y_random_n_son_mutuamente_excluyentes()
    test_parse_explicit_skus_recorta_espacios_y_descarta_vacios()
    test_generate_version_usa_explicito_si_se_paso()
    test_generate_version_autogenera_con_timestamp_si_no_se_paso()
    test_generate_version_ignora_string_vacio()
    test_build_env_fija_persist_catalog_only_skus_version()
    test_build_env_atajos_dedicados()
    test_build_env_atajos_ausentes_no_agregan_keys()
    test_build_env_escape_hatch_generico()
    test_build_env_extra_env_tiene_la_ultima_palabra_sobre_atajo()
    test_build_env_extra_env_sin_signo_igual_lanza_valueerror()
    test_compute_report_mediana_r2_test_real_no_solo_booleano()
    test_compute_report_brecha_train_test_informativa_separada()
    test_compute_report_pct_estable_ignora_nulos()
    test_compute_report_cobertura_detecta_muestra_incompleta()
    test_compute_report_cobertura_ignora_skus_con_solo_filas_sin_r2_test()
    test_compute_report_degeneracion_cero_exacto()
    test_compute_report_degeneracion_uno_exacto()
    test_compute_report_degeneracion_no_confunde_cercano_con_exacto()
    test_compute_report_brecha_chica_con_r2_alto_no_es_lo_mismo_que_degenerado()
    test_compute_report_sin_filas_todo_none()
    test_compute_report_sin_skus_solicitados_cobertura_es_none()
    test_format_report_incluye_los_4_criterios_separados_y_flag_degeneracion()
    print("OK - test_compare_hyperparams.py")
