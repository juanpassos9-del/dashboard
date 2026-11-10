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
    for asset in ("ZEC", "XRP", "HYPE", "DOGE", "BNB", "AVAX", "SUI", "UNI", "WLD"):
        assert f"TOKENIZED_CRYPTO:{asset}" in GLOBAL_REALTIME_MAP
    for ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"):
        assert f"TOKENIZED_STOCK:{ticker}" in GLOBAL_REALTIME_MAP
    assert "TOKENIZED_INDEX:BINGX_INDEX_H100" in GLOBAL_REALTIME_MAP
    assert "TOKENIZED_INDEX:BINGX_INDEX_KOSPI" in GLOBAL_REALTIME_MAP


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

    spx = result["categories"]["🌍 ÍNDICES TOKENIZADOS"][0]
    vix = result["categories"]["Índices"][0]
    assert spx["price"] == 5010
    assert spx["change"] == 0.4
    assert spx["is_realtime"] is True
    assert spx["source"] == "BingX WebSocket"
    assert spx["source_symbol"] == "NCSISP5002USD-USDT"
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
    stale_spx = stale["categories"]["🌍 ÍNDICES TOKENIZADOS"][0]
    assert stale_spx["price"] == 5000
    assert stale_spx["realtime_pending"] is True


def test_overlay_populates_new_categories_and_marks_missing_ticks_as_pending():
    result = apply_global_realtime_overlay(
        {"categories": {}, "metadata": {}},
        {
            ("Binance", "ZEC", "Spot"): {"price": 1150, "change_pct_24h": 2.0, "received_at": 1000},
            ("Binance", "AAPL", "Perpétuo USDⓈ-M"): {"price": 350, "change_pct_24h": -1.0, "received_at": 1000},
            ("BingX", "BINGX_INDEX_KOSPI", "Perpétuo"): {"price": 800, "change_pct_24h": 0.5, "received_at": 1000},
        },
        now=1002,
    )

    crypto = result["categories"]["🪙 CRIPTOMOEDAS · WEBSOCKET"][0]
    stock = result["categories"]["🇺🇸 7 MAGNÍFICAS · TOKENIZADAS"][0]
    index = next(row for row in result["categories"]["🌍 ÍNDICES TOKENIZADOS"] if row["name"] == "KOSPI")
    assert (crypto["name"], crypto["price"], crypto["source"]) == ("ZEC", 1150, "Binance WebSocket")
    assert crypto["display_symbol"] == "ZEC"
    assert (stock["name"], stock["price"], stock["source"]) == ("AAPL", 350, "Binance WebSocket")
    assert stock["display_symbol"] == "AAPL"
    assert (index["name"], index["price"], index["source"]) == ("KOSPI", 800, "BingX WebSocket")

    stale = apply_global_realtime_overlay(
        {"categories": {}, "metadata": {}},
        {("Binance", "ZEC", "Spot"): {"price": 1150, "received_at": 900}},
        now=1000,
    )
    pending_crypto = stale["categories"]["🪙 CRIPTOMOEDAS · WEBSOCKET"][0]
    assert pending_crypto["name"] == "ZEC"
    assert pending_crypto["price"] is None
    assert pending_crypto["realtime_pending"] is True


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
