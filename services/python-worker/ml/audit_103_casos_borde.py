"""
Issue #103: re-audita los casos borde de baja frecuencia de venta y quiebre
de stock ya identificados por #76, ahora con la muestra ampliada y con
ETS/SARIMA (#98/#99) como candidatos nuevos en el walk-forward.

No es una herramienta reusable -- script ad hoc de una sola corrida, mismo
espiritu que la auditoria original de #76 (que no dejo script commiteado).
Se deja en el repo solo para que la identificacion de candidatos y la
corrida sean reproducibles, no para correr de nuevo periodicamente (para
eso ya existe ml/run_eval_elegibilidad_dry_run.py, #102).

Por que un piso de 10 trimestres (30 meses) y no los 16 que uso #76: se
probo primero con 8 trimestres (24 meses, el piso nominal de produccion),
pero resulto ser un piso que NO discrimina nada en los datos locales --
5535 de los 5550 SKUs de ventas_historicas ya tienen >=24 meses de historia
(confirmado por query directa), asi que ese umbral deja pasar
practicamente todo el catalogo, no un subconjunto real de "historia
suficiente". La poblacion recien se vuelve selectiva en 30 meses (10
trimestres): ahi el conteo de SKUs con esa historia cae de 5535 a 103, y el
conteo de candidatos con el patron borde (baja frecuencia/quiebre) se
estabiliza en 8+9=17 -- mismo numero desde piso=10 hasta piso=16, señal de
que 10 trimestres ya captura el universo real sin la inflacion artificial
de un piso demasiado bajo. Contra los 5+2=7 candidatos que uso #76 (piso=16),
esto es una expansion real y justificada, no arbitraria.

Uso (dentro del contenedor etl, mismo patron que compare_hyperparams.py):

    cd /app/services/python-worker
    MYSQL_PASS=evalutia python3 -m ml.audit_103_casos_borde
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, List

import pandas as pd
from sqlalchemy import text

from ioworker.db import DBConfig, get_engine
from ml.apply_elegibilidad import build_decisiones, fetch_catalogo

EVAL_VERSION = "eval-audit-103"

# Issue #76 (CONTEXTO.md, commit 055e4c7): mismos criterios de dominio via
# planilla_ventas_calculada (tickets_mes/estado_mes, ya validados contra el
# cliente en #36-39). Unica diferencia real: el piso de historia (10
# trimestres, el punto donde la poblacion local deja de estar inflada por
# el piso de 24 meses que no discrimina nada -- ver docstring del modulo).
PISO_TRIMESTRES = 10

QUERY_BAJA_FRECUENCIA = text(
    """
    WITH hist AS (
        SELECT sku, TIMESTAMPDIFF(MONTH, MIN(fecha), MAX(fecha)) + 1 AS meses_historia
        FROM ventas_historicas GROUP BY sku
    ),
    mensual AS (
        SELECT sku,
               COUNT(*) AS meses_totales,
               SUM(CASE WHEN tickets_mes BETWEEN 1 AND 3 AND ventas_cantidad > 0 THEN 1 ELSE 0 END) AS meses_patron
        FROM planilla_ventas_calculada
        GROUP BY sku
    )
    SELECT m.sku
    FROM mensual m
    JOIN hist h ON h.sku = m.sku
    WHERE m.meses_patron >= 0.5 * m.meses_totales
      AND h.meses_historia >= :piso_meses
    """
)

QUERY_QUIEBRE = text(
    """
    WITH hist AS (
        SELECT sku, TIMESTAMPDIFF(MONTH, MIN(fecha), MAX(fecha)) + 1 AS meses_historia
        FROM ventas_historicas GROUP BY sku
    ),
    mensual AS (
        SELECT sku,
               COUNT(*) AS meses_totales,
               SUM(CASE WHEN estado_mes IN ('quiebre_parcial','sin_stock') AND ventas_cantidad > 0 THEN 1 ELSE 0 END) AS meses_patron
        FROM planilla_ventas_calculada
        GROUP BY sku
    )
    SELECT m.sku
    FROM mensual m
    JOIN hist h ON h.sku = m.sku
    WHERE m.meses_patron >= 0.30 * m.meses_totales
      AND h.meses_historia >= :piso_meses
    """
)


def find_candidates(engine, piso_trimestres: int) -> Dict[str, List[str]]:
    piso_meses = piso_trimestres * 3
    baja_frecuencia = pd.read_sql_query(QUERY_BAJA_FRECUENCIA, con=engine, params={"piso_meses": piso_meses})
    quiebre = pd.read_sql_query(QUERY_QUIEBRE, con=engine, params={"piso_meses": piso_meses})
    return {
        "baja_frecuencia": sorted(baja_frecuencia["sku"].tolist()),
        "quiebre": sorted(quiebre["sku"].tolist()),
    }


def run_eval_walkforward(skus: List[str]) -> "subprocess.CompletedProcess[bytes]":
    env = os.environ.copy()
    env["EVAL_ONLY_SKUS"] = ",".join(skus)
    env["EVAL_PERSIST_CATALOG"] = "1"
    env["EVAL_VERSION"] = EVAL_VERSION
    return subprocess.run(["python3", "-m", "ml.eval_walkforward"], env=env, cwd=os.getcwd(), check=False)


def main() -> None:
    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    candidatos = find_candidates(engine, PISO_TRIMESTRES)
    print(f"[audit_103] piso={PISO_TRIMESTRES} trimestres -- baja_frecuencia={len(candidatos['baja_frecuencia'])} quiebre={len(candidatos['quiebre'])}")

    caso_por_sku = {sku: "baja_frecuencia" for sku in candidatos["baja_frecuencia"]}
    caso_por_sku.update({sku: "quiebre" for sku in candidatos["quiebre"]})
    todos = sorted(caso_por_sku.keys())

    if not todos:
        print("[audit_103] sin candidatos, nada para correr.")
        return

    print(f"[audit_103] corriendo eval_walkforward.py sobre {len(todos)} SKUs (version={EVAL_VERSION})...")
    proc = run_eval_walkforward(todos)
    if proc.returncode != 0:
        print(f"[WARN] eval_walkforward.py termino con returncode={proc.returncode}")

    catalogo = fetch_catalogo(engine, EVAL_VERSION)
    decisiones = build_decisiones(catalogo)
    for d in decisiones:
        d["caso"] = caso_por_sku.get(d["sku"], "?")

    print(f"\n[audit_103] {len(decisiones)}/{len(todos)} SKUs con al menos 1 modelo evaluable")
    print("sku,caso,modelo,r2_test,estable,elegible")
    for d in sorted(decisiones, key=lambda d: d["sku"]):
        print(f"{d['sku']},{d['caso']},{d['modelo']},{d['r2_test']:.3f},{d['estable']},{d['elegible']}")

    n_elegibles = sum(1 for d in decisiones if d["elegible"])
    if decisiones:
        print(f"\n[audit_103] elegibles: {n_elegibles}/{len(decisiones)} ({n_elegibles / len(decisiones) * 100:.1f}%)")


if __name__ == "__main__":
    main()
