from __future__ import annotations
from typing import Dict, Iterable, Optional

import pandas as pd

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

    q = f"""
        SELECT
            fecha,
            sku,
            SUM(cantidad) AS cantidad
        FROM {tbl}
        GROUP BY fecha, sku
        ORDER BY sku, fecha
    """
    df = pd.read_sql_query(q, con=engine, parse_dates=["fecha"])

    df = df.rename(columns={"Fecha": "fecha", "SKU": "sku", "Cantidad": "cantidad"})

    # Normalizamos datos primero
    df = df.dropna(subset=["fecha", "sku", "cantidad"]).copy()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(float)
    df = df.sort_values(["sku", "fecha"])

    # Si se pasaron skus explícitos, los usamos
    if only_skus:
        only = set(s.strip() for s in only_skus if s and s.strip())
        df = df[df["sku"].isin(only)].copy()
    # Si no, y se pidió top_n, calculamos top_n por suma histórica
    elif top_n and isinstance(top_n, int) and top_n > 0:
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
