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


def test_report_adds_aligned_trend_and_volume_confirmation(monkeypatch):
    monkeypatch.setattr(terminal_b3, "ASSET_UNIVERSE", [
        {"symbol": "AAA3", "ticker": "AAA3.SA", "name": "A", "class": "Ação", "sector": "Bancos"},
    ])
    values = np.arange(100, 160, dtype=float)
    volumes = [100] * 59 + [200]
    report = terminal_b3.build_terminal_b3_report({
        "AAA3.SA": _frame(values, volumes),
        terminal_b3.BENCHMARK_TICKER: _frame(values),
    })

    row = report["rows"][0]
    assert row["trend"] == "Alta alinhada"
    assert row["volume_ratio"] == pytest.approx(2)
    assert row["volume_signal"] == "Confirma alta"


def test_sector_regime_and_winner_concentration_are_reported(monkeypatch):
    monkeypatch.setattr(terminal_b3, "ASSET_UNIVERSE", [
        {"symbol": "AAA3", "ticker": "AAA3.SA", "name": "A", "class": "Ação", "sector": "Bancos"},
        {"symbol": "BBB3", "ticker": "BBB3.SA", "name": "B", "class": "Ação", "sector": "Bancos"},
    ])
    base = np.full(30, 100.0)
    base[-22] = 120
    leader = base.copy()
    leader[-1] = 110
    laggard = base.copy()
    laggard[-1] = 95
    report = terminal_b3.build_terminal_b3_report({
        "AAA3.SA": _frame(leader),
        "BBB3.SA": _frame(laggard),
        terminal_b3.BENCHMARK_TICKER: _frame(base),
    })

    sector = report["sectors"][0]
    assert sector["weekly_breadth"] == pytest.approx(50)
    assert sector["weekly_leader_share"] == pytest.approx(100)
    assert sector["regime"] == "Recuperação de curto prazo"
    assert sector["observations_5d"] == 2
    assert sector["weekly_participation"] == "Mista"
    assert report["market_breadth"]["weekly_leader_share"] == pytest.approx(100)


def test_macro_context_uses_existing_global_and_foreign_flow_observations():
    context = terminal_b3.build_macro_context(
        {"categories": {"FX": [{"symbol": "DX-Y.NYB", "change": 0.4, "source": "Yahoo", "source_timestamp": "10:00"}, {"symbol": "BRL=X", "change": -0.3}, {"symbol": "BZ=F", "change": 1.2}]}},
        {"regime": "Curva DI abrindo", "avg_change": 0.1},
        {"records": [{"date": "2026-10-10", "foreigners": 15000}, {"date": "2026-10-09", "foreigners": -5000}]},
    )

    assert context["quotes"]["DXY"]["change"] == pytest.approx(0.4)
    assert context["quotes"]["USD/BRL"]["change"] == pytest.approx(-0.3)
    assert context["quotes"]["Brent"]["change"] == pytest.approx(1.2)
    assert context["di_regime"] == "Curva DI abrindo"
    assert context["flow_5d_millions"] == pytest.approx(10)
    assert context["flow_observations"] == 2


