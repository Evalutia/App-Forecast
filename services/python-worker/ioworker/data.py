from __future__ import annotations
from typing import Dict, Iterable, Optional

import pandas as pd
from sqlalchemy import text

def _prepare_series(df: pd.DataFrame, freq: str) -> pd.Series:
    """
    Construye la serie mensual/trimestral (o con freq) a partir de un DataFrame por SKU.
    --- NOTA: esta función **asume** que `df` contiene columnas 'fecha' y 'cantidad',
    y que está filtrado para un SKU concreto.
    """
    s = (
        df.resample(freq, on="fecha")["cantidad"]
        .sum()
        .asfreq(freq, fill_value=0)
        .astype(float)
    )
    # Ajuste del índice según freq: inicio de mes o inicio de trimestre
    if str(freq).upper().startswith("Q"):
        s.index = s.index.to_period("Q").to_timestamp()
    else:
        s.index = s.index.to_period("M").to_timestamp()
    return s


def load_series_by_sku(csv_path: str, freq: str = "MS", only_skus: Optional[Iterable[str]] = None, top_n: Optional[int] = None) -> Dict[str, pd.Series]:
    """
    Lee calendario_ventas.csv y devuelve dict sku -> Serie (float), index datetime (inicio de periodo).

    --- MODIFICADO:
    - Añadido parámetro `top_n`.
    - Cambio clave: para cada SKU **cortamos** los registros *antes del resample* para que
      la serie comience en la **primera venta efectiva** (primer fecha con cantidad > 0).
      Si un SKU no tiene ventas (todas las cantidades = 0) se omite.
    """
    df = pd.read_csv(csv_path, parse_dates=["fecha"])
    df = df.rename(columns={"Fecha": "fecha", "SKU": "sku", "Cantidad": "cantidad"})
    required = {"fecha", "sku", "cantidad"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {missing}")

    # Normalizamos datos primero (aseguramos valores numéricos)
    df = df.dropna(subset=["fecha", "sku", "cantidad"]).copy()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(float)
    df = df.sort_values(["sku", "fecha"])

    # Si se pasaron skus explícitos, los usamos tal cual (tienen prioridad)
    if only_skus:
        df = df[df["sku"].isin(set(only_skus))].copy()
    # Si no hay only_skus y se pidió top_n, calculamos los top N por suma histórica
    elif top_n and isinstance(top_n, int) and top_n > 0:
        sku_sums = df.groupby("sku", sort=False)["cantidad"].sum().nlargest(top_n).index
        df = df[df["sku"].isin(sku_sums)].copy()

    series_by_sku: Dict[str, pd.Series] = {}

    # --- MODIFICADO: ahora cortamos por primera venta antes de resamplear
    for sku, g in df.groupby("sku"):
        g = g.sort_values("fecha").copy()

        # encontrar la primera fecha con venta efectiva (> 0)
        sales_positive = g[g["cantidad"] > 0]
        if sales_positive.empty:
            # Si no hubo ventas efectivas, omitimos este SKU
            continue

        first_sale_date = sales_positive["fecha"].min()
        # recortamos el DataFrame para que comience en la fecha de la primera venta efectiva
        g = g[g["fecha"] >= first_sale_date].copy()

        # construir la serie a partir de ese subset (resample+asfreq)
        s = _prepare_series(g, freq=freq)
        if len(s) > 0:
            series_by_sku[sku] = s

    return series_by_sku


def load_series_by_sku_mysql(
    engine,
    table: str = "ventas_historicas",
    schema: str | None = None,
    freq: str = "MS",
    only_skus: Optional[Iterable[str]] = None,
    top_n: Optional[int] = None,
) -> Dict[str, pd.Series]:
    """
    Lee ventas históricas desde MySQL, agrega a nivel DIARIO por (fecha, sku) sumando 'cantidad',
    y devuelve series resampleadas a 'freq' (MS = inicio de mes, QS = inicio de trimestre).

    --- MODIFICADO:
    - Añadido parámetro `top_n`.
    - Cambio clave: para cada SKU **recortamos** las filas *desde la primera venta efectiva*
      (cantidad > 0) antes de resamplear, de modo que la serie comience en la primera venta efectiva.
    """
    tbl = f"{schema}.{table}" if schema else table

    # Filtra por SKU en el propio SQL cuando se pasan only_skus, en vez de
    # traer la tabla completa y filtrar despues en pandas -- con el backfill
    # de 10 anios de #104, ventas_historicas paso a tener decenas de millones
    # de filas, y el filtro post-carga hacia que hasta una corrida de un
    # puñado de SKUs (EVAL_ONLY_SKUS) cargara la tabla entera en memoria
    # igual. Confirmado en produccion: esto colgo la VM (t3.medium, 3.7GB)
    # corriendo el dry-run de #105 sobre el catalogo completo.
    only: set[str] = set()
    params: dict = {}
    where_clause = ""
    if only_skus:
        only = {s.strip() for s in only_skus if s and s.strip()}
        if only:
            placeholders = ", ".join(f":sku{i}" for i in range(len(only)))
            where_clause = f"WHERE sku IN ({placeholders})"
            params = {f"sku{i}": s for i, s in enumerate(sorted(only))}

    q = f"""
        SELECT
            fecha,
            sku,
            SUM(cantidad) AS cantidad
        FROM {tbl}
        {where_clause}
        GROUP BY fecha, sku
        ORDER BY sku, fecha
    """
    df = pd.read_sql_query(text(q), con=engine, params=params, parse_dates=["fecha"])

    df = df.rename(columns={"Fecha": "fecha", "SKU": "sku", "Cantidad": "cantidad"})

    # Normalizamos datos primero
    df = df.dropna(subset=["fecha", "sku", "cantidad"]).copy()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(float)
    df = df.sort_values(["sku", "fecha"])

    # only_skus ya se aplico en el SQL -- si no vino nada (ej. only_skus
    # vacio tras el strip), cae al mismo comportamiento de antes (catalogo
    # completo). top_n si sigue calculandose en pandas: requiere agregar
    # sobre toda la tabla para saber cuales son los top N, no hay forma de
    # empujarlo al SQL sin duplicar la logica de suma historica.
    if not only_skus and top_n and isinstance(top_n, int) and top_n > 0:
        sku_sums = df.groupby("sku", sort=False)["cantidad"].sum().nlargest(top_n).index
        df = df[df["sku"].isin(sku_sums)].copy()

    series_by_sku: Dict[str, pd.Series] = {}
    # --- MODIFICADO: recortar por primera venta antes de resamplear
    for sku, g in df.groupby("sku", sort=False):
        g = g.sort_values("fecha").copy()

        sales_positive = g[g["cantidad"] > 0]
        if sales_positive.empty:
            # Omitimos SKUs sin ventas efectivas
            continue

        first_sale_date = sales_positive["fecha"].min()
        g = g[g["fecha"] >= first_sale_date].copy()

        s = (
            g.set_index("fecha")["cantidad"]
             .resample(freq)
             .sum()
             .asfreq(freq, fill_value=0.0)
        )
        # Ajuste del índice según freq
        if str(freq).upper().startswith("Q"):
            s.index = s.index.to_period("Q").to_timestamp()
        else:
            s.index = s.index.to_period("M").to_timestamp()

        if len(s) > 0:
            series_by_sku[sku] = s
    return series_by_sku
