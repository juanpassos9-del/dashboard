import numpy as np
import pandas as pd
import pytest

from execution import terminal_b3


def _frame(values, volumes=None):
    index = pd.bdate_range("2026-08-01", periods=len(values))
    return pd.DataFrame({
        "Close": values,
        "Volume": volumes if volumes is not None else [1000] * len(values),
    }, index=index)


def test_report_calculates_five_and_twenty_one_session_returns(monkeypatch):
    monkeypatch.setattr(terminal_b3, "ASSET_UNIVERSE", [
        {"symbol": "AAA3", "ticker": "AAA3.SA", "name": "A", "class": "Ação", "sector": "Bancos"},
        {"symbol": "BBB11", "ticker": "BBB11.SA", "name": "B", "class": "ETF", "sector": "Índice amplo"},
    ])
    frames = {
        "AAA3.SA": _frame(np.arange(100, 130, dtype=float)),
        "BBB11.SA": _frame(np.arange(100, 130, dtype=float) * 1.01),
        terminal_b3.BENCHMARK_TICKER: _frame(np.arange(100, 130, dtype=float)),
    }

    report = terminal_b3.build_terminal_b3_report(frames)

    stock = next(row for row in report["rows"] if row["symbol"] == "AAA3")
    assert stock["return_5d"] == pytest.approx((129 / 124 - 1) * 100)
    assert stock["return_21d"] == pytest.approx((129 / 108 - 1) * 100)
    assert stock["relative_5d"] == pytest.approx(0)
    assert report["sectors"][0]["weekly_breadth"] == 100
    assert report["coverage"] == {"available": 2, "universe": 2}


def test_report_skips_missing_assets_and_marks_unavailable_periods(monkeypatch):
    monkeypatch.setattr(terminal_b3, "ASSET_UNIVERSE", [
        {"symbol": "AAA3", "ticker": "AAA3.SA", "name": "A", "class": "Ação", "sector": "Bancos"},
        {"symbol": "MISS3", "ticker": "MISS3.SA", "name": "Missing", "class": "Ação", "sector": "Bancos"},
    ])
    report = terminal_b3.build_terminal_b3_report({
        "AAA3.SA": _frame([100, 101, 102]),
        terminal_b3.BENCHMARK_TICKER: _frame([100, 100, 100]),
    })

    assert report["coverage"] == {"available": 1, "universe": 2}
    assert report["missing_assets"] == ["MISS3"]
    assert report["rows"][0]["return_5d"] is None
    assert report["sectors"][0]["weekly"] is None
    assert terminal_b3.market_read(report)[0].startswith("Na semana") is False


def test_volume_ratio_compares_latest_with_previous_twenty_sessions(monkeypatch):
    monkeypatch.setattr(terminal_b3, "ASSET_UNIVERSE", [
        {"symbol": "AAA3", "ticker": "AAA3.SA", "name": "A", "class": "Ação", "sector": "Bancos"},
    ])
    volumes = [100] * 29 + [300]
    report = terminal_b3.build_terminal_b3_report({
        "AAA3.SA": _frame(np.arange(100, 130, dtype=float), volumes),
        terminal_b3.BENCHMARK_TICKER: _frame(np.arange(100, 130, dtype=float)),
    })

    assert report["rows"][0]["volume_ratio"] == pytest.approx(3)


