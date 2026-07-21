"""
Issue #73: aplica el criterio de elegibilidad de #70 sobre las metricas
crudas que #72 ya persistio en catalogo_modelos.

El ganador por SKU se recalcula aca (mejor r2_test, criterio de #88/#89) en
vez de reusar el ganador que #72 dejo en articulos_elegibilidad_econometrico
-- ese usaba el criterio viejo de seleccion (menor RMSE in-sample), que
quedo desalineado con lo que predict.py corre en produccion desde #89 (ver
sesion de grilling de #73, 2026-07-17: 481/1476 SKUs, 32.6%, tenian un
ganador distinto entre ambos criterios). No hace falta re-correr
walk-forward -- catalogo_modelos ya tiene las 3 metricas por (sku, modelo).

Uso:
    APPLY_VERSION=catalogo-completo-72 APPLY_PERSIST=true python3 -m ml.apply_elegibilidad

Issue #102: `get_elegibilidad_summary` extrae el computo de resumen (los
mismos numeros que ya imprimia main(): evaluados/elegibles/ganan/pierden/
sin_cambio/revocados) en una funcion reusable que devuelve un dict en vez de
solo imprimir. Es de LECTURA pura -- no tiene ningun codigo de persistencia
(no lee ni usa APPLY_PERSIST) -- para que la automatizacion mensual de #102
(ver ml/run_eval_elegibilidad_dry_run.py) pueda calcular el mismo resumen
sin que exista, ni siquiera por error, un camino de codigo que escriba en
articulos_elegibilidad_econometrico. main() sigue siendo el unico lugar que
persiste, y solo si APPLY_PERSIST=true.

APPLY_VERSION/APPLY_PERSIST se leen DENTRO de main(), no a nivel de modulo
(issue #102, hallazgo real al integrar get_elegibilidad_summary): un import
de este modulo por otro script (como ml/run_eval_elegibilidad_dry_run.py,
que solo necesita get_elegibilidad_summary) no debe exigir APPLY_VERSION
seteado en el entorno solo por importar -- eso rompia exactamente el punto
de exponer funciones reusables. Mismo valor por default (KeyError si falta,
mismo comportamiento que antes) pero exigido recien cuando main() corre de
verdad como CLI.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from ioworker.db import DBConfig, get_engine


def _estable_normalizado(valor) -> Optional[bool]:
    """
    Normaliza 'estable' a None/True/False. None cubre tanto el None real
    (WalkForwardResult.stable con 1 solo fold) como el NaN que produce
    pandas al leer un NULL de MySQL en una columna float64 -- bool(nan) es
    True en Python, asi que sin este chequeo un SKU no-evaluable colaria
    como "estable". Tambien sanea antes de persistir: pymysql rechaza NaN en
    columnas numericas ("nan can not be used with MySQL"), mismo problema
    que ya documento #86 (_finite en eval_walkforward.py).
    """
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return bool(valor)


def _int_normalizado(valor) -> Optional[int]:
    """
    Mismo saneo que _estable_normalizado, para n_folds: la columna es
    nullable en el schema (aunque el escritor actual, eval_walkforward.py,
    siempre la completa junto con r2_test) -- pandas puede upcastear toda la
    columna a float64 si CUALQUIER fila del batch (no necesariamente la
    ganadora) trae NULL, y un NaN en el bind param de un UPDATE rompe con el
    mismo error de pymysql que ya se vio en estable.
    """
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return int(valor)


def elegir_ganador_y_elegibilidad(filas_sku: List[Dict]) -> Optional[Dict]:
    """
    Issue #73/#70: dado el detalle de catalogo_modelos para UN sku (una fila
    por modelo evaluado), elige el ganador por mejor r2_test (criterio de
    #88/#89) y aplica el criterio de elegibilidad de #70: r2_test >= 0 y
    estable=True. Un SKU con solo 1 fold evaluable tiene estable=None
    (ver _estable_normalizado), que ya excluye automaticamente -- no hace
    falta un caso especial. La volatilidad SI descalifica aca (a diferencia
    de #88, donde es solo informativa para la seleccion de predict.py) --
    son dos decisiones distintas: #88 elige QUE modelo corre, #70/#73
    deciden SI el SKU es candidato al modelo econometrico en absoluto.

    No chequea meses_historia por separado -- el piso de 24 meses de #70 ya
    queda cubierto indirectamente por n_folds/estable (8 trimestres minimo
    para tener >=2 folds evaluables, ver sesion de #72 en CONTEXTO.md).
    """
    validas = [f for f in filas_sku if f["r2_test"] is not None and math.isfinite(f["r2_test"])]
    if not validas:
        return None
    ganador = max(validas, key=lambda f: f["r2_test"])
    estable = _estable_normalizado(ganador["estable"])
    return {
        "modelo": ganador["modelo"],
        "r2_test": ganador["r2_test"],
        "estable": estable,
        "n_folds": _int_normalizado(ganador["n_folds"]),
        "elegible": bool(ganador["r2_test"] >= 0) and bool(estable),
    }


def upsert_elegibilidad(engine, rows: List[Dict]) -> int:
    """
    UPDATE, no INSERT -- si el sku no tiene fila (nunca se corrio #72 para
    el), no hay nada que marcar, #72 corre primero. No toca meses_historia
    (propiedad del sku, no del modelo ganador -- #72 ya lo calculo bien).
    """
    sql = text(
        """
        UPDATE articulos_elegibilidad_econometrico
        SET r2_test = :r2_test, estable = :estable, n_folds = :n_folds,
            elegible = :elegible, evaluado_en = NOW(6)
        WHERE sku = :sku
        """
    )
    total = 0
    with engine.begin() as conn:
        for row in rows:
            res = conn.execute(sql, row)
            total += res.rowcount
    return total


def revocar_elegibilidad_sin_medicion(engine, huerfanos: List[str]) -> List[str]:
    """
    Issue #73: un SKU elegible=TRUE sin ninguna fila en catalogo_modelos
    para esta version (ej. sobrante del seed original de #71, sin ventas
    reales que medir) no tiene evidencia que sostenga esa elegibilidad --
    #70 exige medir antes de decidir, "elegible por default" no es una
    opcion. `huerfanos` ya viene calculado por el caller (una sola vez,
    contra el mismo snapshot que se usa para el resumen -- evita
    recalcularlo aca contra un estado potencialmente distinto tras el
    upsert). Devuelve los SKUs revocados.

    Issue #97 (code review): tambien limpia r2_test/estable/n_folds --
    antes solo se tocaba 'elegible', dejando el r2_test/estable de una
    medicion VIEJA (potencialmente degenerada, de antes del fix de #97)
    en un SKU que hoy no tiene ninguna medicion real. "Sin evidencia" debe
    verse como NULL, no como un numero de una corrida anterior que ya no
    aplica.
    """
    if not huerfanos:
        return []
    sql = text(
        "UPDATE articulos_elegibilidad_econometrico "
        "SET elegible = FALSE, r2_test = NULL, estable = NULL, n_folds = NULL, evaluado_en = NOW(6) "
        "WHERE sku = :sku"
    )
    with engine.begin() as conn:
        for sku in huerfanos:
            conn.execute(sql, {"sku": sku})
    return huerfanos


def fetch_catalogo(engine, version: str) -> pd.DataFrame:
    """
    Lee catalogo_modelos para esta version_modelo. catalogo_modelos acumula
    historico (sin UNIQUE en sku+modelo+version) -- si esta version se
    corrio mas de una vez (ej. reanudada tras un corte), se queda solo con
    la re-estimacion mas reciente por (sku, modelo). Devuelve un DataFrame
    vacio (no None) si no hay filas, para que el caller pueda chequear
    .empty sin un caso especial.
    """
    catalogo = pd.read_sql_query(
        text(
            "SELECT sku, modelo, r2_test, estable, n_folds, fecha_estimacion "
            "FROM catalogo_modelos WHERE version_modelo = :version"
        ),
        con=engine,
        params={"version": version},
    )
    if catalogo.empty:
        return catalogo
    return catalogo.sort_values("fecha_estimacion", ascending=False).drop_duplicates(
        subset=["sku", "modelo"], keep="first"
    )


def fetch_actual_elegibilidad(engine) -> Dict[str, bool]:
    """Estado actual de produccion (sku -> elegible), para comparar contra
    las decisiones de esta corrida (ganan/pierden/sin cambio)."""
    actual = pd.read_sql_query(text("SELECT sku, elegible FROM articulos_elegibilidad_econometrico"), con=engine)
    return dict(zip(actual["sku"], actual["elegible"].astype(bool)))


def build_decisiones(catalogo: pd.DataFrame) -> List[Dict]:
    """Aplica elegir_ganador_y_elegibilidad por SKU sobre un catalogo ya
    deduplicado (ver fetch_catalogo). Puro dado el DataFrame -- sin DB."""
    decisiones = []
    for sku, grupo in catalogo.groupby("sku"):
        resultado = elegir_ganador_y_elegibilidad(grupo.to_dict("records"))
        if resultado is None:
            continue
        resultado["sku"] = sku
        decisiones.append(resultado)
    return decisiones


def compute_summary(decisiones: List[Dict], actual_map: Dict[str, bool], skus_medidos) -> Dict:
    """
    Issue #102: el computo puro detras de los numeros que main() ya
    imprimia (SKUs evaluados/elegibles/ganan/pierden/sin_cambio) mas los
    SKUs "huerfanos" (elegibles en produccion sin ninguna medicion real en
    esta version, ver revocar_elegibilidad_sin_medicion). Sin DB, sin
    side-effects -- decisiones/actual_map/skus_medidos ya vienen calculados
    por el caller (fetch_catalogo/fetch_actual_elegibilidad/build_decisiones).
    """
    n_evaluados = len(decisiones)
    if n_evaluados == 0:
        return {
            "skus_evaluados": 0,
            "elegibles": 0,
            "ganan": 0,
            "pierden": 0,
            "sin_cambio": 0,
            "revocados_sin_medicion": [],
        }

    n_elegibles = sum(1 for d in decisiones if d["elegible"])
    ganan = sum(1 for d in decisiones if d["elegible"] and not actual_map.get(d["sku"], False))
    pierden = sum(1 for d in decisiones if not d["elegible"] and actual_map.get(d["sku"], False))
    mantienen = n_evaluados - ganan - pierden

    huerfanos = sorted(
        sku for sku, elegible in actual_map.items() if elegible and sku not in skus_medidos
    )

    return {
        "skus_evaluados": n_evaluados,
        "elegibles": n_elegibles,
        "ganan": ganan,
        "pierden": pierden,
        "sin_cambio": mantienen,
        "revocados_sin_medicion": huerfanos,
    }


def get_elegibilidad_summary(engine, version: str) -> Dict:
    """
    Issue #102: orquesta fetch_catalogo + fetch_actual_elegibilidad +
    build_decisiones + compute_summary contra una version dada. Puramente
    de LECTURA (2 SELECT, cero INSERT/UPDATE) -- pensada para que la
    automatizacion mensual (ml/run_eval_elegibilidad_dry_run.py) obtenga el
    mismo resumen que ya calculaba main() sin pasar por APPLY_PERSIST ni por
    ningun codigo de escritura.
    """
    catalogo = fetch_catalogo(engine, version)
    if catalogo.empty:
        return compute_summary([], {}, set())
    actual_map = fetch_actual_elegibilidad(engine)
    decisiones = build_decisiones(catalogo)
    skus_medidos = set(catalogo["sku"].unique())
    return compute_summary(decisiones, actual_map, skus_medidos)


def main() -> None:
    apply_version = os.environ["APPLY_VERSION"]
    apply_persist = os.getenv("APPLY_PERSIST", "").strip().lower() in ("1", "true", "yes")

    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    catalogo = fetch_catalogo(engine, apply_version)
    if catalogo.empty:
        print(f"[APLICAR_ELEGIBILIDAD] Sin filas en catalogo_modelos para version={apply_version!r}.")
        return

    actual_map = fetch_actual_elegibilidad(engine)
    decisiones = build_decisiones(catalogo)

    if not decisiones:
        print(f"[APLICAR_ELEGIBILIDAD] version={apply_version!r}: ninguna fila con r2_test valido, nada para decidir.")
        return

    skus_medidos = set(catalogo["sku"].unique())
    resumen = compute_summary(decisiones, actual_map, skus_medidos)

    print(f"[APLICAR_ELEGIBILIDAD] version={apply_version!r}")
    print(f"SKUs evaluados: {resumen['skus_evaluados']}")
    print(f"Elegibles bajo el criterio real (r2_test>=0 y estable): {resumen['elegibles']} ({resumen['elegibles'] / resumen['skus_evaluados'] * 100:.1f}%)")
    print(f"Ganan elegibilidad: {resumen['ganan']} | Pierden elegibilidad: {resumen['pierden']} | Sin cambio: {resumen['sin_cambio']}")

    huerfanos = resumen["revocados_sin_medicion"]
    if huerfanos:
        print(f"Elegibles sin ninguna medición real (revocados): {len(huerfanos)} -- {', '.join(huerfanos)}")

    if apply_persist:
        n = upsert_elegibilidad(engine, decisiones)
        print(f"\n[PERSIST] {n} filas actualizadas en articulos_elegibilidad_econometrico.")
        if n != resumen["skus_evaluados"]:
            print(f"[WARN] Se esperaban {resumen['skus_evaluados']} filas actualizadas, se actualizaron {n} -- "
                  f"{resumen['skus_evaluados'] - n} SKU(s) medidos por esta version no tenían fila previa (¿#72 no corrió para ellos?).")
        if huerfanos:
            revocados = revocar_elegibilidad_sin_medicion(engine, huerfanos)
            print(f"[PERSIST] {len(revocados)} filas revocadas por falta de medición real.")
    else:
        print("\n[DRY-RUN] APPLY_PERSIST no está activo -- no se escribió nada. Setear APPLY_PERSIST=true para aplicar.")


if __name__ == "__main__":
    main()
