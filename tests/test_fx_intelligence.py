import numpy as np
import pandas as pd

from execution.fx_intelligence import build_fx_macro_correlation_rows


def test_macro_correlations_use_daily_returns_and_report_sample_size():
    index = pd.date_range("2026-01-01", periods=80, freq="B")
    driver_returns = np.linspace(-0.01, 0.012, len(index))
    inverse_returns = -driver_returns
    prices = pd.DataFrame({
        "DXY": 100 * (1 + pd.Series(driver_returns, index=index)).cumprod(),
        "EURUSD": 1.2 * (1 + pd.Series(inverse_returns, index=index)).cumprod(),
    }, index=index)

    rows = build_fx_macro_correlation_rows(prices)

    eur_dxy = next(row for row in rows if row["Par"] == "EURUSD" and row["Driver"] == "DXY")
    assert eur_dxy["Correlação"] == -1.0
    assert eur_dxy["Relação de referência"] == "inversa"
    assert eur_dxy["Leitura"] == "Alinhada"
    assert eur_dxy["Pregões"] == 60


def test_short_or_missing_history_is_not_reported_as_a_correlation():
    index = pd.date_range("2026-01-01", periods=20, freq="B")
    prices = pd.DataFrame({
        "DXY": np.arange(100, 120),
        "EURUSD": np.arange(120, 140),
    }, index=index)

    assert build_fx_macro_correlation_rows(prices) == []


def test_missing_driver_series_is_skipped_without_fabricating_values():
    index = pd.date_range("2026-01-01", periods=80, freq="B")
    prices = pd.DataFrame({"EURUSD": np.linspace(1.1, 1.2, 80)}, index=index)

    assert build_fx_macro_correlation_rows(prices) == []


def test_near_zero_correlation_is_not_called_aligned():
    index = pd.date_range("2026-01-01", periods=80, freq="B")
    steps = np.arange(len(index))
    dxy_returns = 0.001 * np.sin(2 * np.pi * steps / 60)
    eurusd_returns = 0.001 * np.cos(2 * np.pi * steps / 60)
    prices = pd.DataFrame({
        "DXY": 100 * (1 + pd.Series(dxy_returns, index=index)).cumprod(),
        "EURUSD": 1.2 * (1 + pd.Series(eurusd_returns, index=index)).cumprod(),
    }, index=index)

    rows = build_fx_macro_correlation_rows(prices)
    eur_dxy = next(row for row in rows if row["Par"] == "EURUSD" and row["Driver"] == "DXY")

    assert eur_dxy["Leitura"] == "Fraca/indefinida"
