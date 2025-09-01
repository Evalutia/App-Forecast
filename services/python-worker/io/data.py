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
