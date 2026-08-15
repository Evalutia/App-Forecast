"""Self-check para la automatizacion mensual de medicion de elegibilidad (#102).

No mockea el subproceso de eval_walkforward.py ni la conexion a DB (mismo
criterio que test_compare_hyperparams.py, #101) -- se enfoca en las partes
puras: date-stamping de EVAL_VERSION, armado del env del subproceso (en
particular que EVAL_ONLY_SKUS se elimine siempre, la garantia central de
full-catalog de #102) y construccion del detalle JSON para jobs_historial.

Corre sin pytest (mismo patron que el resto de tests/). Modo modulo:
    python3 -m tests.test_run_eval_elegibilidad_dry_run
"""
from __future__ import annotations

from datetime import datetime

from ml.run_eval_elegibilidad_dry_run import (
    generate_version,
    build_env,
    build_env_for_batch,
    chunk_skus,
    build_detalle_exitoso,
    build_detalle_fallido,
    decide_estado_final,
    TIPO_JOB,
)


# -------------------------------------------------------------------------
# generate_version -- grano mensual, no de segundo (a diferencia de
# compare_hyperparams.generate_version)
# -------------------------------------------------------------------------

def test_generate_version_formato_mensual():
    v = generate_version(now=datetime(2026, 7, 21, 15, 30, 0))
    assert v == "eval-mensual-2026-07"


def test_generate_version_mismo_mes_da_mismo_tag():
    v1 = generate_version(now=datetime(2026, 7, 1, 4, 0, 0))
    v2 = generate_version(now=datetime(2026, 7, 31, 23, 59, 0))
    assert v1 == v2 == "eval-mensual-2026-07"


def test_generate_version_distinto_mes_da_distinto_tag():
    v1 = generate_version(now=datetime(2026, 7, 21))
    v2 = generate_version(now=datetime(2026, 8, 1))
    assert v1 != v2


# -------------------------------------------------------------------------
# build_env -- la garantia central de #102: full-catalog siempre
# -------------------------------------------------------------------------

def test_build_env_fija_persist_catalog_y_version():
    env = build_env({"PATH": "/usr/bin"}, version="eval-mensual-2026-07")
    assert env["EVAL_PERSIST_CATALOG"] == "1"
    assert env["EVAL_VERSION"] == "eval-mensual-2026-07"
    assert env["PATH"] == "/usr/bin", "no debe pisar el resto del os.environ base"


def test_build_env_elimina_eval_only_skus_heredado():
    # Regresion critica de #102: si EVAL_ONLY_SKUS quedo seteado en el
    # entorno (ej. sesion de desarrollo anterior sin limpiar), una corrida
    # real de este script NO debe heredarlo -- full-catalog siempre.
    env = build_env({"EVAL_ONLY_SKUS": "E00204,E00428"}, version="v-test")
    assert "EVAL_ONLY_SKUS" not in env


def test_build_env_sin_eval_only_skus_no_falla():
    env = build_env({}, version="v-test")
    assert "EVAL_ONLY_SKUS" not in env
    assert env["EVAL_VERSION"] == "v-test"


# -------------------------------------------------------------------------
# chunk_skus / build_env_for_batch -- modo por lotes (#105), evita cargar
# ventas_historicas entera en memoria de una en una VM chica
# -------------------------------------------------------------------------

def test_chunk_skus_parte_en_lotes_del_tamanio_pedido():
    lotes = chunk_skus(["A", "B", "C", "D", "E"], batch_size=2)
    assert lotes == [["A", "B"], ["C", "D"], ["E"]]


def test_chunk_skus_batch_size_cero_devuelve_un_solo_lote():
    lotes = chunk_skus(["A", "B", "C"], batch_size=0)
    assert lotes == [["A", "B", "C"]]


def test_chunk_skus_lista_vacia_devuelve_lista_vacia():
    assert chunk_skus([], batch_size=100) == []


def test_build_env_for_batch_fija_only_skus_al_lote():
    env = build_env_for_batch({"PATH": "/usr/bin"}, version="v-test", skus_batch=["A", "B"])
    assert env["EVAL_ONLY_SKUS"] == "A,B"
    assert env["EVAL_VERSION"] == "v-test"
    assert env["EVAL_PERSIST_CATALOG"] == "1"
    assert env["PATH"] == "/usr/bin"


# -------------------------------------------------------------------------
# build_detalle_exitoso / build_detalle_fallido -- lo que termina en
# jobs_historial.detalle
# -------------------------------------------------------------------------

def test_build_detalle_exitoso_incluye_resumen_y_metadata():
    summary = {"skus_evaluados": 10, "elegibles": 4, "ganan": 1, "pierden": 0,
               "sin_cambio": 3, "revocados_sin_medicion": []}
    detalle = build_detalle_exitoso(summary, version="eval-mensual-2026-07", eval_returncode=0)
    assert detalle["skus_evaluados"] == 10
    assert detalle["elegibles"] == 4
    assert detalle["eval_version"] == "eval-mensual-2026-07"
    assert detalle["eval_walkforward_returncode"] == 0


def test_build_detalle_fallido_incluye_error_y_version():
    detalle = build_detalle_fallido(RuntimeError("boom"), version="eval-mensual-2026-07")
    assert detalle["error"] == "boom"
    assert detalle["eval_version"] == "eval-mensual-2026-07"


# -------------------------------------------------------------------------
# decide_estado_final -- issue #148: antes jobs_historial cerraba SIEMPRE
# "exitoso" aunque un lote hubiera fallado (worst_returncode se trackeaba
# pero nunca se usaba para decidir el estado persistido)
# -------------------------------------------------------------------------

def test_decide_estado_final_exitoso_cuando_todos_los_lotes_ok():
    assert decide_estado_final(worst_returncode=0) == "exitoso"


def test_decide_estado_final_fallido_cuando_algun_lote_fallo():
    assert decide_estado_final(worst_returncode=1) == "fallido"


def test_decide_estado_final_fallido_con_returncode_negativo():
    # subprocess.returncode negativo == terminado por señal (ej. OOM killer)
    assert decide_estado_final(worst_returncode=-9) == "fallido"


def test_tipo_job_es_eval_elegibilidad():
    # Confirma el valor exacto que la migracion de #102 agrega al ENUM de
    # jobs_historial.tipo_job -- si este string no matchea, insert_job_start
    # falla contra la DB real con "Data truncated for column 'tipo_job'".
    assert TIPO_JOB == "eval_elegibilidad"


if __name__ == "__main__":
    test_generate_version_formato_mensual()
    test_generate_version_mismo_mes_da_mismo_tag()
    test_generate_version_distinto_mes_da_distinto_tag()
    test_build_env_fija_persist_catalog_y_version()
    test_build_env_elimina_eval_only_skus_heredado()
    test_build_env_sin_eval_only_skus_no_falla()
    test_build_detalle_exitoso_incluye_resumen_y_metadata()
    test_build_detalle_fallido_incluye_error_y_version()
    test_decide_estado_final_exitoso_cuando_todos_los_lotes_ok()
    test_decide_estado_final_fallido_cuando_algun_lote_fallo()
    test_decide_estado_final_fallido_con_returncode_negativo()
    test_tipo_job_es_eval_elegibilidad()
    print("OK - test_run_eval_elegibilidad_dry_run.py")
