from __future__ import annotations

import threading

from execution.cryptodash_ws import CryptoDashRealtimeHub
from execution.market_realtime import (
    GLOBAL_REALTIME_MAP,
    apply_global_realtime_overlay,
    global_market_subscriptions,
)


def test_global_subscriptions_cover_live_markets_without_faking_unavailable_assets():
    subscriptions = global_market_subscriptions()

    assert subscriptions["Binance"]
    assert subscriptions["OKX"]
    assert subscriptions["BingX"]
    assert "^VIX" not in GLOBAL_REALTIME_MAP
    assert "^BVSP" not in GLOBAL_REALTIME_MAP
    assert "DGS2" not in GLOBAL_REALTIME_MAP
    assert "DI1F27" not in GLOBAL_REALTIME_MAP
    assert "6L=F" not in GLOBAL_REALTIME_MAP
    assert any(row["instrument"] == "NCSINASDAQ1002USD-USDT" for row in subscriptions["BingX"])


def test_overlay_updates_only_fresh_quotes_and_preserves_fallback_rows():
    snapshot = {
        "metadata": {"last_updated": "snapshot time"},
        "categories": {
            "Índices": [
                {"symbol": "^GSPC", "name": "S&P 500", "price": 5000, "change": 0.2},
                {"symbol": "^VIX", "name": "VIX", "price": 18, "change": -1.0},
            ]
        },
    }
    result = apply_global_realtime_overlay(
        snapshot,
        {
            ("BingX", "BINGX_INDEX_SP500", "Perpétuo"): {
                "price": 5010,
                "change_pct_24h": 0.4,
                "high_24h": 5020,
                "low_24h": 4980,
                "timestamp_ms": 1_800_000_000_000,
                "received_at": 1_800_000_000,
            }
        },
        now=1_800_000_005,
    )

    spx, vix = result["categories"]["Índices"]
    assert spx["price"] == 5010
    assert spx["change"] == 0.4
    assert spx["is_realtime"] is True
    assert spx["reference_type"] == "synthetic_reference"
    assert "sintético" in spx["mapping_note"]
    assert vix["price"] == 18
    assert "realtime_overlay" not in snapshot["metadata"]
    assert result["metadata"]["realtime_overlay"]["quotes_updated"] == 1

    stale = apply_global_realtime_overlay(
        snapshot,
        {
            ("BingX", "BINGX_INDEX_SP500", "Perpétuo"): {
                "price": 5010,
                "received_at": 1_799_999_900,
            }
        },
        now=1_800_000_000,
    )
    assert stale["categories"]["Índices"][0]["price"] == 5000


def test_hub_keeps_subscriptions_from_independent_dashboard_groups(monkeypatch):
    class NoNetworkThread:
        def __init__(self, *args, **kwargs):
            self.name = kwargs.get("name")

        def start(self):
            pass

        def is_alive(self):
            return False

    monkeypatch.setattr(threading, "Thread", NoNetworkThread)
    hub = CryptoDashRealtimeHub()
    hub.configure_group("cryptodash", {
        "Binance": [{"asset": "BTC", "instrument": "BTCUSDT", "market_type": "Spot"}],
    })
    hub.configure_group("global_markets", {
        "Binance": [{"asset": "BTC", "instrument": "BTCUSDT", "market_type": "Spot"}],
        "BingX": [{"asset": "BINGX_INDEX_SP500", "instrument": "NCSISP5002USD-USDT", "market_type": "Perpétuo"}],
    })

    assert ("BTC", "BTCUSDT") in hub._signatures["binance_spot"]
    assert ("BINGX_INDEX_SP500", "NCSISP5002USD-USDT") in hub._signatures["bingx_swap_00"]


def test_websocket_tick_can_update_multiple_aliases_for_same_contract():
    hub = CryptoDashRealtimeHub()
    rows = [
        {"asset": "ALIAS_A", "instrument": "BTC-USDT", "market_type": "Spot"},
        {"asset": "ALIAS_B", "instrument": "BTC-USDT", "market_type": "Spot"},
    ]
    hub._on_message(
        "okx",
        '{"arg":{"channel":"tickers"},"data":[{"instId":"BTC-USDT","last":"60000","open24h":"59000","ts":"1800000000000"}]}',
        rows,
    )

    quotes = hub.latest_quotes()
    assert quotes[("OKX", "ALIAS_A", "Spot")]["price"] == 60000
    assert quotes[("OKX", "ALIAS_B", "Spot")]["price"] == 60000
