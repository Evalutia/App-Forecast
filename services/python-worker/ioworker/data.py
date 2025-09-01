from __future__ import annotations

from typing import Dict, Iterable, Optional

import pandas as pd


def _prepare_series(df: pd.DataFrame, freq: str) -> pd.Series:
    # Suma mensual de 'cantidad' por defecto; fechas al inicio de mes
    s = (
        df.resample(freq, on="fecha")["cantidad"]
        .sum()
        .asfreq(freq, fill_value=0)
        .astype(float)
    )
    s.index = s.index.to_period("M").to_timestamp()
    return s


def load_series_by_sku(csv_path: str, freq: str = "MS", only_skus: Optional[Iterable[str]] = None) -> Dict[str, pd.Series]:
    """
    Lee calendario_ventas.csv y devuelve dict sku -> Serie mensual (float), index datetime (inicio de mes).
    """
    df = pd.read_csv(csv_path, parse_dates=["fecha"])
    df = df.rename(columns={"Fecha": "fecha", "SKU": "sku", "Cantidad": "cantidad"})
    required = {"fecha", "sku", "cantidad"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {missing}")

    if only_skus:
        df = df[df["sku"].isin(set(only_skus))].copy()

    # Ordena y limpia
    df = df.dropna(subset=["fecha", "sku", "cantidad"]).copy()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(float)
    df = df.sort_values(["sku", "fecha"])

    series_by_sku: Dict[str, pd.Series] = {}
    for sku, g in df.groupby("sku"):
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
) -> Dict[str, pd.Series]:
    """
    Lee ventas históricas desde MySQL (tabla 'ventas_historicas' por defecto),
    agrega a nivel DIARIO por (fecha, sku) sumando 'cantidad' (posibles múltiples 'fuente'),
    y devuelve series MENSUALES por SKU resampleadas a 'freq' (MS = inicio de mes).
    """
    tbl = f"{schema}.{table}" if schema else table

    # Agregación a nivel diario por si hay múltiples 'fuente' para mismo día/SKU
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

    # Normalización de columnas y filtros
    df = df.rename(columns={"Fecha": "fecha", "SKU": "sku", "Cantidad": "cantidad"})
    if only_skus:
        only = set(s.strip() for s in only_skus if s and s.strip())
        df = df[df["sku"].isin(only)].copy()

    df = df.dropna(subset=["fecha", "sku", "cantidad"]).copy()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(float)
    df = df.sort_values(["sku", "fecha"])

    # Resampleo mensual por SKU
    series_by_sku: Dict[str, pd.Series] = {}
    for sku, g in df.groupby("sku", sort=False):
        s = (
            g.set_index("fecha")["cantidad"]
             .resample(freq)
             .sum()
             .asfreq(freq, fill_value=0.0)
        )
        # Aseguramos índice en primer día del mes
        s.index = s.index.to_period("M").to_timestamp()
        if len(s) > 0:
            series_by_sku[sku] = s
    return series_by_sku
