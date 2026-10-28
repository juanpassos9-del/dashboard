import numpy as np
import pandas as pd

from execution.fx_intelligence import (
    build_fx_macro_correlation_rows,
    build_fx_market_brief,
    build_fx_intraday_correlation_rows,
    currency_strength_from_pair_returns,
)


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
    assert eur_dxy["Correlação 20d"] == -1.0
    assert eur_dxy["Correlação 60d"] == -1.0
    assert eur_dxy["Relação de referência"] == "inversa"
    assert eur_dxy["Leitura"] == "Alinhada"
    assert eur_dxy["Pregões"] == 60
    assert eur_dxy["Último pregão"] == index[-1].strftime("%Y-%m-%d")


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


def test_currency_strength_excludes_unobserved_currencies_and_reports_pair_coverage():
    strength, coverage = currency_strength_from_pair_returns(
        {"EURUSD": 0.5, "USDJPY": -0.2},
        {"EURUSD": ("EUR", "USD"), "USDJPY": ("USD", "JPY"), "GBPUSD": ("GBP", "USD")},
    )

    assert set(strength) == {"EUR", "USD", "JPY"}
    assert coverage == {"EUR": 1, "USD": 2, "JPY": 1}
    assert "GBP" not in coverage


def test_market_brief_does_not_treat_missing_or_divergent_data_as_confirmation():
    brief = build_fx_market_brief(
        {"USD": 50, "EUR": -50},
        {"USD": 1, "EUR": 1},
        dxy_change=-0.4,
        spx_change=None,
        vix_change=1.2,
        best_pair={"Par": "EURUSD", "Direcao": "SHORT", "Score": 70, "Alinhado": "Divergente"},
        divergent_pairs=[{"Par": "EURUSD"}],
    )

    assert any("diverge do DXY" in line for line in brief["divergences"])
    assert any("EURUSD" in line for line in brief["divergences"])
    assert not any("EURUSD" in line for line in brief["confirms"])
    assert any("falta S&P 500 ou VIX" in line for line in brief["notes"])


def test_macro_correlations_are_conditioned_by_observed_risk_regime():
    index = pd.date_range("2026-01-01", periods=100, freq="B")
    steps = np.arange(len(index))
    dxy_returns = 0.001 * np.sin(steps / 3)
    spx_returns = np.where(steps % 3 == 0, 0.01, np.where(steps % 3 == 1, -0.01, 0.001))
    vix_returns = np.where(steps % 3 == 0, -0.01, np.where(steps % 3 == 1, 0.01, 0.001))
    prices = pd.DataFrame({
        "DXY": 100 * (1 + pd.Series(dxy_returns, index=index)).cumprod(),
        "EURUSD": 1.2 * (1 - pd.Series(dxy_returns, index=index)).cumprod(),
        "SPX": 4000 * (1 + pd.Series(spx_returns, index=index)).cumprod(),
        "VIX": 20 * (1 + pd.Series(vix_returns, index=index)).cumprod(),
    }, index=index)

    row = next(
        item for item in build_fx_macro_correlation_rows(prices)
        if item["Par"] == "EURUSD" and item["Driver"] == "DXY"
    )

    assert row["N risk-on"] >= 10
    assert row["N risk-off"] >= 10
    assert row["Corr. risk-on"] is not None
    assert row["Corr. risk-off"] is not None


def test_intraday_correlations_use_synchronized_changes_not_rebased_levels():
    index = pd.date_range("2026-10-01", periods=50, freq="5min")
    increments = np.sin(np.arange(len(index)) / 3)
    pair_performance = pd.DataFrame({"EURUSD": -np.cumsum(increments)}, index=index)
    driver_performance = pd.DataFrame({"DXY": np.cumsum(increments)}, index=index)

    rows = build_fx_intraday_correlation_rows(
        pair_performance,
        driver_performance,
        pairs=["EURUSD"],
        inverse_pairs={"EURUSD"},
        inverse_drivers={"DXY"},
    )

    assert rows[0]["Correlação"] == -1.0
    assert rows[0]["Observações"] == 49
    assert rows[0]["Leitura"] == "confirma"
