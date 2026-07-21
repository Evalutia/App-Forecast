"""
Issue #101: herramienta de comparacion de hiperparametros (busqueda
hipotesis-dirigida). Automatiza el proceso manual que llevo al fix de #97
(3 experimentos: setear env vars a mano, correr eval_walkforward.py dentro
del contenedor etl, escribir a mano una query SQL contra catalogo_modelos
para interpretar el resultado).

Todos los hiperparametros relevantes YA son configurables por env var, leidos
a tiempo de importacion en eval_walkforward.py/models.py (EVAL_LAGS,
EVAL_HORIZON, EVAL_MAX_FOLDS, RF_MAX_DEPTH, XGB_LEARNING_RATE, etc.) -- por
eso este script NO reimplementa el walk-forward, solo orquesta una corrida
de eval_walkforward.py como SUBPROCESO (con el os.environ modificado) y
despues lee catalogo_modelos para esa corrida.

Subproceso, no import + llamada directa: los hiperparametros de
eval_walkforward.py/models.py se leen una sola vez a nivel de modulo
(X = int(os.getenv("X", "default"))) -- una segunda llamada a main() en el
mismo proceso Python no vuelve a leer el env var, ya quedo fijado por el
primer import. Un subproceso fresco por corrida es la unica forma de que
cada hipotesis use sus propios valores.

Leccion de diseño critica de #97, reflejada en el reporte: una brecha chica
entre r2_train y r2_test NO alcanza como evidencia de buen aprendizaje -- un
modelo casi-constante (muy poca historia util) puede dar r2 EXACTAMENTE 0.0
o EXACTAMENTE 1.0 tanto en train como en test, "coincidiendo" a la perfeccion
sin haber aprendido nada. Por eso el reporte separa explicitamente "mediana
r2_test real" de "brecha train-test" de "% degenerado" -- nunca los colapsa
en un solo numero.

Uso (siempre desde services/python-worker, mismo patron que
ml.eval_walkforward/ml.apply_elegibilidad):

    # Sample explicito de SKUs, un solo override (EVAL_LAGS=4)
    python3 -m ml.compare_hyperparams --skus E00204,E00428,E00678 --env EVAL_LAGS=4

    # Sample aleatorio de 5 SKUs actualmente elegibles, override de un
    # hiperparametro especifico de RF, version explicita (si no se pasa
    # --version se autogenera como compare-<timestamp>)
    python3 -m ml.compare_hyperparams --random-n 5 --env RF_MAX_DEPTH=3 --version compare-rf-depth3

    # Atajos dedicados (lags/horizon/max-folds) combinados con el escape
    # hatch generico --env para cualquier otro hiperparametro de models.py
    python3 -m ml.compare_hyperparams --random-n 10 --lags 4 --horizon 4 --env XGB_LEARNING_RATE=0.05

Pensado para uso SECUENCIAL (una hipotesis a la vez, se interpreta el
resultado antes de decidir la siguiente) -- no lanzar corridas en paralelo
(contencion de recursos real confirmada en #101: la misma corrida de
walk-forward con Prophet tardo 5m28s una vez y 9m34s otra en la misma Mac).

No es responsabilidad de este script limpiar catalogo_modelos despues --
esa tabla esta pensada para acumular historico entre corridas (por eso el
tag de EVAL_VERSION), el mismo run queda disponible para comparacion manual
de seguimiento.

No hace sampling estratificado por longitud de historia ni compara dos
corridas pasadas entre si -- fuera de alcance de #101 (YAGNI), ver el issue.
"""
from __future__ import annotations

import argparse
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import pandas as pd
from sqlalchemy import text

from ioworker.db import DBConfig, get_engine

# Issue #101: umbral de "esto se ve sospechoso" para la flag de degeneracion
# -- no es un hard-fail, solo cambia como se imprime el reporte. #97
# encontro ~96% degenerado en el catalogo completo; cualquier corrida por
# encima de este piso amerita revisar antes de confiar en el r2_test.
DEGENERACY_FLAG_THRESHOLD_PCT = 15.0


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Corre eval_walkforward.py con una hipotesis de hiperparametros sobre una muestra de SKUs y reporta los 4 criterios de #97/#101 leidos de catalogo_modelos.",
    )
    sample = parser.add_mutually_exclusive_group(required=True)
    sample.add_argument("--skus", type=str, default=None, help="SKUs explicitos, separados por coma (ej. E00204,E00428).")
    sample.add_argument("--random-n", type=int, default=None, help="N SKUs aleatorios entre los actualmente elegibles (articulos_elegibilidad_econometrico WHERE elegible=1).")

    parser.add_argument("--version", type=str, default=None, help="Tag EVAL_VERSION para esta corrida. Si no se pasa, se autogenera como compare-<timestamp>.")

    # Atajos dedicados para los hiperparametros mas comunes -- el resto se
    # cubre con --env (escape hatch generico, cualquier KEY=VALUE).
    parser.add_argument("--lags", type=int, default=None, help="Override de EVAL_LAGS.")
    parser.add_argument("--horizon", type=int, default=None, help="Override de EVAL_HORIZON.")
    parser.add_argument("--max-folds", type=int, default=None, help="Override de EVAL_MAX_FOLDS.")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="Override arbitrario de env var (ej. RF_MAX_DEPTH=3, XGB_LEARNING_RATE=0.05). Repetible.")

    return parser.parse_args(argv)


def parse_explicit_skus(raw: str) -> List[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def generate_version(explicit: Optional[str], now: Optional[datetime] = None) -> str:
    """
    Si no se pasa --version, autogenera un tag distinguible por timestamp.
    Granularidad de segundos alcanza porque la herramienta esta pensada para
    uso secuencial (una corrida a la vez, ver docstring del modulo) -- no
    hace falta un sufijo random para evitar colisiones entre corridas
    concurrentes que no deberian existir.
    """
    if explicit and explicit.strip():
        return explicit.strip()
    now = now or datetime.now()
    return f"compare-{now.strftime('%Y%m%d-%H%M%S')}"


def build_env(base_env: Dict[str, str], skus: List[str], version: str,
              lags: Optional[int] = None, horizon: Optional[int] = None,
              max_folds: Optional[int] = None, extra_env: Sequence[str] = ()) -> Dict[str, str]:
    """
    Arma el os.environ para el subproceso de eval_walkforward.py: copia
    base_env y pisa encima EVAL_PERSIST_CATALOG/EVAL_ONLY_SKUS/EVAL_VERSION
    (fijos, controlados por esta herramienta) mas cualquier override de
    hiperparametros pedido. --env tiene la ultima palabra incluso sobre
    --lags/--horizon/--max-folds si se repite la misma key, para que el
    escape hatch generico pueda forzar cualquier valor.
    """
    env = dict(base_env)
    env["EVAL_PERSIST_CATALOG"] = "1"
    env["EVAL_ONLY_SKUS"] = ",".join(skus)
    env["EVAL_VERSION"] = version
    if lags is not None:
        env["EVAL_LAGS"] = str(lags)
    if horizon is not None:
        env["EVAL_HORIZON"] = str(horizon)
    if max_folds is not None:
        env["EVAL_MAX_FOLDS"] = str(max_folds)
    for item in extra_env:
        if "=" not in item:
            raise ValueError(f"--env espera el formato KEY=VALUE, se recibio: {item!r}")
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"--env con key vacia: {item!r}")
        env[key] = value
    return env


# -------------------------------------------------------------------------
# Sampling de SKUs (DB) -- sin sampling estratificado, YAGNI (ver #101)
# -------------------------------------------------------------------------

def fetch_random_eligible_skus(engine, n: int) -> List[str]:
    """Mismo patron de query usado a mano en los pilotos de #97: N SKUs al
    azar entre los actualmente elegibles."""
    df = pd.read_sql_query(
        text("SELECT sku FROM articulos_elegibilidad_econometrico WHERE elegible = 1 ORDER BY RAND() LIMIT :n"),
        con=engine,
        params={"n": n},
    )
    return df["sku"].tolist()


# -------------------------------------------------------------------------
# Subproceso de eval_walkforward.py
# -------------------------------------------------------------------------

def run_eval_walkforward(env: Dict[str, str], cwd: Optional[str] = None) -> "subprocess.CompletedProcess[bytes]":
    """
    Invoca eval_walkforward.py como proceso fresco (ver docstring del
    modulo: los hiperparametros se leen a tiempo de importacion, un import
    reusado en el mismo proceso Python no los actualizaria). cwd=None usa el
    directorio de trabajo actual -- este script ya se corre desde
    services/python-worker (misma convencion que ml.eval_walkforward /
    ml.apply_elegibilidad), asi que 'python3 -m ml.eval_walkforward' resuelve
    igual que la invocacion manual de siempre.
    """
    return subprocess.run(["python3", "-m", "ml.eval_walkforward"], env=env, cwd=cwd, check=False)


# -------------------------------------------------------------------------
# Lectura de catalogo_modelos para la version de esta corrida
# -------------------------------------------------------------------------

def _to_float_or_none(valor) -> Optional[float]:
    """Mismo saneo que _finite (eval_walkforward.py) / _estable_normalizado
    (apply_elegibilidad.py): pandas lee un NULL de MySQL en columna float64
    como NaN, no None -- hay que normalizar antes de comparar/promediar."""
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _to_bool_or_none(valor) -> Optional[bool]:
    """Mismo saneo que _estable_normalizado en apply_elegibilidad.py:
    bool(float('nan')) es True en Python, asi que sin este chequeo un
    'estable' NULL colaria como True."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return bool(valor)


def fetch_catalog_rows(engine, version: str) -> List[Dict]:
    """Lee catalogo_modelos para esta version_modelo y normaliza r2_train/
    r2_test/estable (NaN de pandas -> None) antes de devolver."""
    df = pd.read_sql_query(
        text(
            "SELECT sku, modelo, r2_train, r2_test, rmse_train, rmse_test, n_obs_train, n_folds, estable "
            "FROM catalogo_modelos WHERE version_modelo = :version"
        ),
        con=engine,
        params={"version": version},
    )
    rows = df.to_dict("records")
    return [
        {
            "sku": r["sku"],
            "modelo": r["modelo"],
            "r2_train": _to_float_or_none(r.get("r2_train")),
            "r2_test": _to_float_or_none(r.get("r2_test")),
            "estable": _to_bool_or_none(r.get("estable")),
        }
        for r in rows
    ]


# -------------------------------------------------------------------------
# Computo del reporte (puro -- sin DB ni subproceso, es la parte con tests)
# -------------------------------------------------------------------------

def compute_report(rows: List[Dict], requested_skus: Sequence[str]) -> Dict:
    """
    Calcula los 4 criterios de #97/#101 a partir de filas YA normalizadas
    (ver fetch_catalog_rows: r2_train/r2_test son float o None, estable es
    bool o None). Los 4 numeros se devuelven SEPARADOS, nunca combinados en
    un solo score -- esa es la advertencia central de #97: brecha chica +
    r2 alto genuino no es lo mismo que brecha chica + r2 degenerado (0.0/1.0
    exacto en ambos), y colapsarlos en un promedio esconde justo esa
    distincion.

    - median_r2_test: mediana real de r2_test entre filas con valor valido.
    - mean_train_test_gap: informativo, NUNCA usar aislado (label explicito
      en el reporte impreso) -- una brecha chica no prueba generalizacion.
    - pct_estable: % de filas con estable=True, sobre las que tienen
      estable no-nulo (folds/SKUs evaluables, no solo un acierto suelto).
    - coverage_pct: fraccion de la MUESTRA PEDIDA que produjo al menos una
      fila con r2_test valido (no NULL) para esta version -- el numero que
      hubiera detectado el error de #97 (un hiperparametro que "gana" en
      r2 pero silenciosamente excluye al 96% de la muestra de la medicion).
    - pct_degenerate: % de filas con r2_test EXACTAMENTE 0.0 o 1.0 (igualdad
      de float exacta, no "cercano a") -- la flag de degeneracion.
    """
    valid_r2_test = [r for r in rows if r.get("r2_test") is not None]
    r2_test_values = [r["r2_test"] for r in valid_r2_test]
    median_r2_test = statistics.median(r2_test_values) if r2_test_values else None

    gap_rows = [r for r in rows if r.get("r2_train") is not None and r.get("r2_test") is not None]
    gaps = [r["r2_train"] - r["r2_test"] for r in gap_rows]
    mean_train_test_gap = statistics.mean(gaps) if gaps else None

    estable_rows = [r for r in rows if r.get("estable") is not None]
    pct_estable = (sum(1 for r in estable_rows if r["estable"]) / len(estable_rows) * 100) if estable_rows else None

    requested = {s for s in requested_skus if s}
    skus_con_resultado_valido = {r["sku"] for r in valid_r2_test}
    n_covered = len(skus_con_resultado_valido & requested)
    coverage_pct = (n_covered / len(requested) * 100) if requested else None

    n_degenerate = sum(1 for v in r2_test_values if v == 0.0 or v == 1.0)
    pct_degenerate = (n_degenerate / len(r2_test_values) * 100) if r2_test_values else None

    return {
        "n_rows": len(rows),
        "n_rows_r2_test_valido": len(r2_test_values),
        "median_r2_test": median_r2_test,
        "mean_train_test_gap": mean_train_test_gap,
        "n_gap_rows": len(gaps),
        "pct_estable": pct_estable,
        "n_estable_rows": len(estable_rows),
        "coverage_pct": coverage_pct,
        "n_skus_requested": len(requested),
        "n_skus_covered": n_covered,
        "pct_degenerate": pct_degenerate,
        "n_degenerate": n_degenerate,
    }


# -------------------------------------------------------------------------
# Formato del reporte para terminal
# -------------------------------------------------------------------------

def _fmt_pct(valor: Optional[float]) -> str:
    return f"{valor:.1f}%" if valor is not None else "s/d"


def _fmt_r2(valor: Optional[float]) -> str:
    return f"{valor:.4f}" if valor is not None else "s/d"


def _format_scope(nombre: str, report: Dict) -> List[str]:
    lineas = [f"-- {nombre} --"]
    lineas.append(f"r2_test walk-forward (mediana, real):            {_fmt_r2(report['median_r2_test'])}  (n={report['n_rows_r2_test_valido']})")
    lineas.append(f"Brecha train-test (r2_train - r2_test):          {_fmt_r2(report['mean_train_test_gap'])}  (n={report['n_gap_rows']}) -- informativo, NO usar aislado")
    lineas.append(f"% estable=True (entre filas evaluables):         {_fmt_pct(report['pct_estable'])}  (n={report['n_estable_rows']})")
    if report["n_skus_requested"]:
        lineas.append(f"Cobertura (SKUs con resultado valido / pedidos): {_fmt_pct(report['coverage_pct'])}  ({report['n_skus_covered']}/{report['n_skus_requested']})")
    degeneracy_line = f"DEGENERACION -- % r2_test EXACTAMENTE 0.0 o 1.0: {_fmt_pct(report['pct_degenerate'])}  (n={report['n_degenerate']}/{report['n_rows_r2_test_valido']})"
    if report["pct_degenerate"] is not None and report["pct_degenerate"] >= DEGENERACY_FLAG_THRESHOLD_PCT:
        degeneracy_line += f"  <-- SOSPECHOSO (>= {DEGENERACY_FLAG_THRESHOLD_PCT:.0f}%), revisar antes de confiar en el r2_test de arriba"
    lineas.append(degeneracy_line)
    return lineas


def format_report(version: str, requested_skus: Sequence[str], report_total: Dict, reports_by_model: Dict[str, Dict]) -> str:
    lineas = []
    lineas.append("== Reporte de comparacion de hiperparametros (#101) ==")
    lineas.append(f"EVAL_VERSION: {version}")
    lineas.append(f"SKUs solicitados: {len(set(s for s in requested_skus if s))}")
    lineas.append(f"Filas totales en catalogo_modelos para esta version: {report_total['n_rows']}")
    lineas.append("")
    lineas.extend(_format_scope("TOTAL (todos los modelos)", report_total))
    for modelo in sorted(reports_by_model):
        lineas.append("")
        lineas.extend(_format_scope(f"Modelo: {modelo}", reports_by_model[modelo]))
    return "\n".join(lineas)


# -------------------------------------------------------------------------
# main
# -------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    if args.skus:
        skus = parse_explicit_skus(args.skus)
    else:
        skus = fetch_random_eligible_skus(engine, args.random_n)

    if not skus:
        print("[ERROR] La muestra de SKUs quedo vacia (revisar --skus o si hay SKUs elegibles para --random-n).")
        sys.exit(1)

    version = generate_version(args.version)
    env = build_env(os.environ.copy(), skus=skus, version=version, lags=args.lags,
                     horizon=args.horizon, max_folds=args.max_folds, extra_env=args.env)

    print(f"[compare_hyperparams] version={version} n_skus={len(skus)} overrides={args.env or '(ninguno)'} "
          f"lags={args.lags} horizon={args.horizon} max_folds={args.max_folds}")
    proc = run_eval_walkforward(env, cwd=os.getcwd())
    if proc.returncode != 0:
        print(f"[WARN] eval_walkforward.py termino con returncode={proc.returncode} -- el reporte de abajo puede reflejar una corrida parcial (persistencia incremental, ver eval_walkforward.py).")

    rows = fetch_catalog_rows(engine, version)
    if not rows:
        print(f"\n[compare_hyperparams] Sin filas en catalogo_modelos para version={version!r} -- nada para reportar.")
        return

    report_total = compute_report(rows, skus)
    reports_by_model: Dict[str, Dict] = {}
    for modelo in sorted({r["modelo"] for r in rows}):
        reports_by_model[modelo] = compute_report([r for r in rows if r["modelo"] == modelo], skus)

    print()
    print(format_report(version, skus, report_total, reports_by_model))


if __name__ == "__main__":
    main()
