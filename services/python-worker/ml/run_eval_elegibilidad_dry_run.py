"""
Issue #102: automatiza la MEDICION periodica de elegibilidad -- corre
eval_walkforward.py sobre el catalogo COMPLETO (sin EVAL_ONLY_SKUS) y
apply_elegibilidad.py en modo dry-run, dejando el resultado registrado en
jobs_historial (tipo_job='eval_elegibilidad'). Nunca aplica el resultado a
produccion -- eso sigue siendo, siempre, una decision humana explicita (ver
issue #102 y el criterio ya usado en #73->#75/#97: medir y decidir primero,
desplegar despues como paso separado).

Por que subproceso, no import + llamada directa a eval_walkforward.main():
los hiperparametros de eval_walkforward.py/models.py se leen una sola vez a
nivel de modulo (X = int(os.getenv("X", "default"))) -- mismo problema que
ya resolvio ml/compare_hyperparams.py (#101), que es la referencia mas
cercana para el patron de invocacion. A diferencia de compare_hyperparams
(pensado para iterar hipotesis de hiperparametros sobre una muestra chica),
este script es mas simple: sin overrides de hiperparametros, y SIEMPRE
full-catalog (nunca EVAL_ONLY_SKUS) -- el objetivo es detectar SKUs que
recien cruzaron el umbral de elegibilidad a medida que se acumula mas
historia de ventas, no medir de nuevo solo los ya elegibles.

Por que este job nunca puede persistir en articulos_elegibilidad_econometrico:
llama a apply_elegibilidad.get_elegibilidad_summary(engine, version), que es
de LECTURA pura (2 SELECT, cero INSERT/UPDATE, no lee APPLY_PERSIST) -- no
existe, ni por error de env var, un camino de codigo en este script que
escriba en esa tabla. Aplicar el resultado sigue siendo un paso manual
separado: correr apply_elegibilidad.py a mano con APPLY_PERSIST=true una vez
que un humano revise el resumen.

Uso mensual (via Ofelia, ver ofelia.ini y services/etl/run_eval_elegibilidad_mensual.sh):
no requiere invocacion manual, corre solo.

Uso manual, fuera de la cadencia mensual (ej. justo despues de desplegar
#98/#99/#101, para ver el impacto de un modelo/hiperparametro nuevo sobre la
elegibilidad SIN esperar al proximo primero de mes):

    docker compose exec etl bash -lc \\
        "cd /app/services/python-worker && MYSQL_PASS=evalutia python3 -m ml.run_eval_elegibilidad_dry_run"

Esto corre exactamente la misma medicion full-catalog que el cron mensual
(mismo codigo, mismo EVAL_VERSION autogenerado con el mes actual) y deja el
mismo tipo de fila en jobs_historial -- no hace falta pasar por Ofelia/cron
para una corrida puntual.

Para iterar mas rapido en desarrollo sobre una muestra chica de SKUs (en vez
de esperar la corrida full-catalog, que puede tardar bastante -- una corrida
completa de referencia esta sesion tardo ~40 minutos tras el fix de #97):
setear EVAL_ONLY_SKUS a mano ANTES de invocar este modulo, ej.:

    EVAL_ONLY_SKUS=E00204,E00428 docker compose exec -e EVAL_ONLY_SKUS etl bash -lc \\
        "cd /app/services/python-worker && MYSQL_PASS=evalutia python3 -m ml.run_eval_elegibilidad_dry_run"

Esto es solo para desarrollo/debug -- la corrida real (manual o mensual) NO
debe tener EVAL_ONLY_SKUS seteado. Por eso build_env() lo elimina
explicitamente del entorno base antes de lanzar el subproceso: si quedara
seteado por accidente en el entorno del contenedor (ej. una sesion de
desarrollo anterior que no lo limpio), este script lo ignoraria igual y
corre siempre full-catalog.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text

from ioworker.db import DBConfig, get_engine, insert_job_start, update_job_end
from ml.apply_elegibilidad import get_elegibilidad_summary

TIPO_JOB = "eval_elegibilidad"

# Issue #105: corrida real post-#104 (ventas_historicas paso a decenas de
# millones de filas con el backfill de 10 anios) colgo la VM de produccion
# (t3.medium, 3.7GB RAM) -- load_series_by_sku_mysql sin EVAL_ONLY_SKUS trae
# la tabla entera a memoria de una. El fix de fondo (#105) empuja el filtro
# de SKUs al SQL (ver ioworker/data.py), pero una corrida full-catalog SIN
# EVAL_ONLY_SKUS igual carga todo de una. EVAL_BATCH_SIZE, si se setea (>0),
# parte el catalogo completo en lotes de ese tamanio y corre eval_walkforward.py
# una vez por lote (mismo EVAL_VERSION en todos, catalogo_modelos acumula sin
# pisarse entre lotes -- ver fetch_catalogo en apply_elegibilidad.py, dedupea
# por (sku, modelo) quedandose con la fecha_estimacion mas reciente). Default
# "0" mantiene el comportamiento anterior (una sola corrida full-catalog).
BATCH_SIZE = int(os.getenv("EVAL_BATCH_SIZE", "0"))


# -------------------------------------------------------------------------
# Version autogenerada (grano mensual -- coherente con la cadencia del job)
# -------------------------------------------------------------------------

def generate_version(now: Optional[datetime] = None) -> str:
    """
    Ej. 'eval-mensual-2026-07'. Grano de mes, no de segundo (a diferencia de
    compare_hyperparams.generate_version, pensado para uso secuencial
    puntual): este job corre una vez al mes, y correrlo mas de una vez en el
    mismo mes (ej. una corrida manual el mismo mes que ya corrio el cron)
    debe pisar la medicion de ese mes, no acumular versiones indistinguibles
    -- catalogo_modelos igual conserva el historico completo por
    fecha_estimacion, asi que no se pierde nada.
    """
    now = now or datetime.now()
    return f"eval-mensual-{now.strftime('%Y-%m')}"


# -------------------------------------------------------------------------
# Env para el subproceso de eval_walkforward.py
# -------------------------------------------------------------------------

def build_env(base_env: Dict[str, str], version: str) -> Dict[str, str]:
    """
    Full-catalog, siempre -- pop explicito de EVAL_ONLY_SKUS del env base
    (ver docstring del modulo: asegura que una corrida real nunca herede un
    filtro dejado por una sesion de desarrollo anterior). EVAL_PERSIST_CATALOG
    fijo en '1' (este job SI persiste en catalogo_modelos, esa tabla es
    historico puro sin impacto en produccion -- distinto de
    articulos_elegibilidad_econometrico, que este script nunca toca).
    """
    env = dict(base_env)
    env.pop("EVAL_ONLY_SKUS", None)
    env["EVAL_PERSIST_CATALOG"] = "1"
    env["EVAL_VERSION"] = version
    return env


def run_eval_walkforward(env: Dict[str, str], cwd: Optional[str] = None) -> "subprocess.CompletedProcess[bytes]":
    """
    Subproceso fresco, mismo patron que compare_hyperparams.run_eval_walkforward
    (#101) -- cwd=None usa el directorio de trabajo actual, este script se
    corre desde services/python-worker (misma convencion que ml.eval_walkforward/
    ml.apply_elegibilidad/ml.compare_hyperparams).
    """
    return subprocess.run(["python3", "-m", "ml.eval_walkforward"], env=env, cwd=cwd, check=False)


# -------------------------------------------------------------------------
# Modo por lotes (#105) -- puro (chunk_skus) + una query de lectura
# -------------------------------------------------------------------------

def chunk_skus(skus: List[str], batch_size: int) -> List[List[str]]:
    """Puro, sin DB -- parte una lista de SKUs en lotes de tamanio batch_size
    (el ultimo lote puede quedar mas chico). batch_size <= 0 devuelve un
    unico lote con todos los SKUs (equivalente a no batchear)."""
    if batch_size <= 0 or not skus:
        return [skus] if skus else []
    return [skus[i : i + batch_size] for i in range(0, len(skus), batch_size)]


def fetch_all_skus(engine) -> List[str]:
    """Universo completo de SKUs que procesaria una corrida full-catalog sin
    EVAL_ONLY_SKUS -- mismo universo que ventas_historicas ve sin filtro
    (ver ioworker.data.load_series_by_sku_mysql)."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT sku FROM ventas_historicas ORDER BY sku"))
        return [r[0] for r in rows]


def build_env_for_batch(base_env: Dict[str, str], version: str, skus_batch: List[str]) -> Dict[str, str]:
    """Como build_env, pero fija EVAL_ONLY_SKUS al lote en vez de eliminarlo
    -- cada lote es una corrida acotada de eval_walkforward.py sobre ese
    subconjunto, con el fix de #105 (filtro empujado al SQL) evita traer la
    tabla completa a memoria por lote."""
    env = dict(base_env)
    env["EVAL_PERSIST_CATALOG"] = "1"
    env["EVAL_VERSION"] = version
    env["EVAL_ONLY_SKUS"] = ",".join(skus_batch)
    return env


# -------------------------------------------------------------------------
# Construccion del detalle JSON para jobs_historial (puro, testeable)
# -------------------------------------------------------------------------

def build_detalle_exitoso(summary: Dict, version: str, eval_returncode: int) -> Dict:
    return {**summary, "eval_version": version, "eval_walkforward_returncode": eval_returncode}


def build_detalle_fallido(error: Exception, version: str) -> Dict:
    return {"error": str(error), "eval_version": version}


# -------------------------------------------------------------------------
# main
# -------------------------------------------------------------------------

def main() -> None:
    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    version = generate_version()
    job_id = insert_job_start(engine, tipo_job=TIPO_JOB)
    print(f"[run_eval_elegibilidad_dry_run] job_id={job_id} version={version} (full-catalog, dry-run)")

    try:
        worst_returncode = 0
        if BATCH_SIZE > 0:
            skus = fetch_all_skus(engine)
            batches = chunk_skus(skus, BATCH_SIZE)
            print(f"[run_eval_elegibilidad_dry_run] EVAL_BATCH_SIZE={BATCH_SIZE} -- {len(skus)} SKUs en {len(batches)} lotes (issue #105, evita cargar ventas_historicas entera en memoria de una)")
            for i, batch in enumerate(batches, start=1):
                print(f"[run_eval_elegibilidad_dry_run] lote {i}/{len(batches)} ({len(batch)} SKUs)...")
                env = build_env_for_batch(os.environ.copy(), version, batch)
                proc = run_eval_walkforward(env, cwd=os.getcwd())
                if proc.returncode != 0:
                    worst_returncode = proc.returncode
                    print(f"[WARN] lote {i}/{len(batches)} termino con returncode={proc.returncode}")
        else:
            env = build_env(os.environ.copy(), version)
            print("[run_eval_elegibilidad_dry_run] corriendo eval_walkforward.py (esto puede tardar bastante, es un job mensual)...")
            proc = run_eval_walkforward(env, cwd=os.getcwd())
            worst_returncode = proc.returncode
        if worst_returncode != 0:
            print(f"[WARN] eval_walkforward.py termino con returncode={worst_returncode} -- el resumen de abajo puede reflejar una corrida parcial (persistencia incremental, ver eval_walkforward.py).")

        print(f"[run_eval_elegibilidad_dry_run] leyendo resumen dry-run de apply_elegibilidad para version={version!r}...")
        summary = get_elegibilidad_summary(engine, version)
        detalle = build_detalle_exitoso(summary, version=version, eval_returncode=worst_returncode)

        update_job_end(engine, job_id, estado="exitoso", detalle=detalle)
        print(f"[run_eval_elegibilidad_dry_run] jobs_historial id={job_id} estado=exitoso")
        print(json.dumps(detalle, ensure_ascii=False, indent=2))
    except Exception as e:
        try:
            update_job_end(engine, job_id, estado="fallido", detalle=build_detalle_fallido(e, version=version))
        except Exception:
            pass
        print(f"[ERROR] run_eval_elegibilidad_dry_run fallo: {e}")
        raise


if __name__ == "__main__":
    main()
