from datetime import datetime, timezone

import pandas as pd
import pytest

from execution.global_intraday_performance import (
    INSTRUMENTS,
    apply_latest_websocket_ticks,
    normalize_performance,
    parse_bingx_candles,
    parse_hyperliquid_candles,
)


def test_exchange_candle_parsers_return_sorted_utc_series():
    hyperliquid = parse_hyperliquid_candles([
        {"t": 600000, "c": "101"},
        {"t": 300000, "c": "100"},
        {"t": "bad", "c": "bad"},
    ])
    bingx = parse_bingx_candles({"code": 0, "data": [
        {"time": 600000, "close": "101"},
        {"time": 300000, "close": "100"},
    ]})

    assert list(hyperliquid) == [100.0, 101.0]
    assert list(bingx) == [100.0, 101.0]
    assert str(hyperliquid.index.tz) == "UTC"
    assert str(bingx.index.tz) == "UTC"


def test_performance_uses_percent_for_prices_and_basis_points_for_yields():
    index = pd.date_range("2026-11-18T12:00:00Z", periods=2, freq="5min")
    candles = pd.DataFrame({
        "Nasdaq 100": [100.0, 101.0],
        "Treasury 2Y": [4.80, 4.85],
    }, index=index)

    result = normalize_performance(candles)

    assert result["Nasdaq 100"].iloc[-1] == pytest.approx(1.0)
    assert result["Treasury 2Y"].iloc[-1] == pytest.approx(5.0)


def test_websocket_tick_appends_only_when_fresh():
    label = "Nasdaq 100"
    index = pd.DatetimeIndex([pd.Timestamp("2026-11-18T12:00:00Z")])
    candles = pd.DataFrame({label: [100.0]}, index=index)
    instrument = next(spec for spec in INSTRUMENTS if spec["label"] == label)
    from execution.global_intraday_performance import _mapping_for

    mapping = _mapping_for(instrument)
    live = {
        (instrument["provider"], mapping["asset"], mapping["market_type"]): {
            "price": 101.0,
            "received_at": datetime(2026, 11, 18, 12, 0, 10, tzinfo=timezone.utc).timestamp(),
        }
    }

    result, ages = apply_latest_websocket_ticks(
        candles, live,
        now_seconds=datetime(2026, 11, 18, 12, 0, 15, tzinfo=timezone.utc).timestamp(),
    )

    assert result[label].iloc[-1] == 101.0
    assert ages[label] == 5

    stale, stale_ages = apply_latest_websocket_ticks(candles, live, now_seconds=1_800_000_100)
    assert len(stale) == 1
    assert not stale_ages
