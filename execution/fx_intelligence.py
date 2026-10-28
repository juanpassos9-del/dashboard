"""Deterministic FX cross-market correlation context."""

from __future__ import annotations

import pandas as pd


FX_MACRO_RELATIONSHIPS = (
    ("EURUSD", "DXY", "inversa", "Dólar amplo e diferencial Fed/BCE"),
    ("GBPUSD", "DXY", "inversa", "Dólar amplo e diferencial Fed/BoE"),
    ("USDJPY", "US02Y", "direta", "Juros curtos dos EUA versus BoJ"),
    ("USDJPY", "VIX", "inversa", "Iene como moeda defensiva em episódios de aversão a risco"),
    ("USDCHF", "EURUSD", "inversa", "Relação entre duas cotações com USD em lados opostos"),
    ("USDCHF", "VIX", "direta", "Franco suíço como moeda defensiva; relação pode variar por regime"),
    ("AUDUSD", "COPPER", "direta", "Ciclo de commodities e demanda global/China"),
    ("AUDUSD", "SPX", "direta", "Apetite por risco global"),
    ("NZDUSD", "SPX", "direta", "Apetite por risco global"),
    ("USDCAD", "WTI", "inversa", "Petróleo e termos de troca do Canadá"),
)


def build_fx_macro_correlation_rows(
    prices: pd.DataFrame,
    *,
    window: int = 60,
    min_observations: int = 30,
) -> list[dict]:
    """Correlate aligned daily percentage returns; omit pairs with short samples."""
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return []

    returns = prices.apply(pd.to_numeric, errors="coerce").pct_change(fill_method=None)
    rows = []
    for pair, driver, expected, context in FX_MACRO_RELATIONSHIPS:
        if pair not in returns.columns or driver not in returns.columns:
            continue
        sample = returns[[pair, driver]].dropna().tail(max(1, int(window)))
        observations = len(sample)
        if observations < min_observations:
            continue
        correlation = sample[pair].corr(sample[driver])
        if pd.isna(correlation):
            continue
        value = float(correlation)
        if abs(value) < 0.15:
            reading = "Fraca/indefinida"
        else:
            aligned = (expected == "direta" and value > 0) or (expected == "inversa" and value < 0)
            reading = "Alinhada" if aligned else "Divergente"
        rows.append({
            "Par": pair,
            "Driver": driver,
            "Correlação": round(value, 2),
            "Relação de referência": expected,
            "Leitura": reading,
            "Pregões": observations,
            "Contexto": context,
        })
    return rows
