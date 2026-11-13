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
    assert subscriptions["Hyperliquid"]
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
        assert any(
            provider == "Hyperliquid" and row["instrument"] == f"xyz:{ticker}"
            for provider, row in GLOBAL_REALTIME_MAP[ticker]
        )
    assert any(row["instrument"] == "xyz:SP500" for row in subscriptions["Hyperliquid"])
    assert any(row["instrument"] == "xyz:BRENTOIL" for row in subscriptions["Hyperliquid"])
    assert {
        row["instrument"] for row in subscriptions["Hyperliquid"]
        if row.get("dex") == "para"
    } == {"para:2Y", "para:10Y", "para:30Y"}
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
        "Hyperliquid": [
            {"asset": "HYPERLIQUID:xyz:AAPL", "instrument": "xyz:AAPL", "market_type": "Perpétuo Hyperliquid · XYZ", "dex": "xyz"},
            {"asset": "BTC", "instrument": "BTC", "market_type": "Perpétuo Hyperliquid", "dex": ""},
            {"asset": "US2Y", "instrument": "para:2Y", "market_type": "Perpétuo de yield Hyperliquid · Paragon", "dex": "para"},
        ],
    })

    assert ("BTC", "BTCUSDT") in hub._signatures["binance_spot"]
    assert ("BINGX_INDEX_SP500", "NCSISP5002USD-USDT") in hub._signatures["bingx_swap_00"]
    assert ("HYPERLIQUID:xyz:AAPL", "xyz:AAPL", "xyz") in hub._signatures["hyperliquid_xyz"]
    assert ("BTC", "BTC", "") in hub._signatures["hyperliquid_default"]
    assert ("US2Y", "para:2Y", "para") in hub._signatures["hyperliquid_para"]


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


def test_hyperliquid_active_asset_context_parses_price_and_previous_day_change():
    hub = CryptoDashRealtimeHub()
    rows = [{
        "asset": "HYPERLIQUID:xyz:AAPL",
        "instrument": "xyz:AAPL",
        "market_type": "Perpétuo Hyperliquid · XYZ",
        "dex": "xyz",
    }]
    hub._on_message(
        "hyperliquid_xyz",
        '{"channel":"activeAssetCtx","data":{"coin":"xyz:AAPL","ctx":{"midPx":"356.4","oraclePx":"356.2","markPx":"356.3","prevDayPx":"350","dayNtlVlm":"1234567"}}}',
        rows,
    )

    quote = hub.latest_quotes()[("Hyperliquid", "HYPERLIQUID:xyz:AAPL", "Perpétuo Hyperliquid · XYZ")]
    assert quote["price"] == 356.4
    assert round(quote["change_pct_24h"], 4) == round((356.4 / 350 - 1) * 100, 4)
    assert quote["change_basis"] == "hyperliquid_previous_day_price"
    assert quote["quote_volume_24h"] == 1234567


def test_hyperliquid_overlay_marks_synthetic_contract_and_preserves_yahoo_high_low():
    result = apply_global_realtime_overlay(
        {"categories": {"Ações": [{"symbol": "AAPL", "name": "Apple", "price": 340, "change": 1.2, "high": 355, "low": 330, "source": "Yahoo Finance"}]}, "metadata": {}},
        {("Hyperliquid", "HYPERLIQUID:xyz:AAPL", "Perpétuo Hyperliquid · XYZ"): {
            "price": 356.4,
            "change_pct_24h": 1.8286,
            "change_basis": "hyperliquid_previous_day_price",
            "received_at": 1_800_000_000,
        }},
        now=1_800_000_001,
    )
    apple = result["categories"]["Ações"][0]
    assert apple["price"] == 356.4
    assert apple["change"] == 1.8286
    assert apple["change_basis"] == "hyperliquid_previous_day_price"
    assert apple["source"] == "Hyperliquid WebSocket"
    assert apple["instrument_type"] == "synthetic_perpetual"
    assert apple["high"] == 355
    assert apple["high_low_source"] == "Yahoo Finance"


def test_hyperliquid_treasury_yields_map_to_live_rates_and_calculate_basis_points():
    for symbol, tenor in (("FRED:DGS2", "2Y"), ("^TNX", "10Y"), ("^TYX", "30Y")):
        provider, mapping = GLOBAL_REALTIME_MAP[symbol][0]
        assert provider == "Hyperliquid"
        assert mapping["instrument"] == f"para:{tenor}"
        assert mapping["quote_unit"] == "yield_percent"

    hub = CryptoDashRealtimeHub()
    yield_rows = [{
        "asset": "US2Y",
        "instrument": "para:2Y",
        "market_type": "Perpétuo de yield Hyperliquid · Paragon",
        "dex": "para",
    }]
    hub._on_message(
        "hyperliquid_para",
        '{"channel":"activeAssetCtx","data":{"coin":"para:2Y","ctx":{"oraclePx":"4.33","midPx":"4.35","markPx":"4.34","prevDayPx":"4.30"}}}',
        yield_rows,
    )
    live_yield = hub.latest_quotes()[("Hyperliquid", "US2Y", "Perpétuo de yield Hyperliquid · Paragon")]
    assert live_yield["price"] == 4.33
    assert live_yield["previous_price"] == 4.30

    result = apply_global_realtime_overlay(
        {"categories": {"Treasuries": [{"symbol": "FRED:DGS2", "name": "US 02Y (Yield)", "price": 4.2, "change": 0.1, "source": "FRED"}]}, "metadata": {}},
        {("Hyperliquid", "US2Y", "Perpétuo de yield Hyperliquid · Paragon"): {
            "price": 4.33,
            "previous_price": 4.30,
            "change_pct_24h": (4.33 / 4.30 - 1) * 100,
            "change_basis": "hyperliquid_previous_day_price",
            "received_at": 1_800_000_000,
        }},
        now=1_800_000_001,
    )
    two_year = result["categories"]["Treasuries"][0]
    assert two_year["price"] == 4.33
    assert two_year["change_bps"] == 3.0
    assert two_year["quote_unit"] == "percent_per_year"
    assert two_year["source"] == "Hyperliquid WebSocket"
    assert "para:2Y" in two_year["yield_source"]

    pending = apply_global_realtime_overlay(
        {"categories": {"Treasuries": [{"symbol": "^TNX", "price": 4.1, "source": "Yahoo Finance"}]}, "metadata": {}},
        {},
        now=1_800_000_001,
    )["categories"]["Treasuries"][0]
    assert pending["price"] == 4.1
    assert pending["realtime_pending"] is True
    assert pending["realtime_pending_instrument"] == "Hyperliquid: para:10Y"


def test_hyperliquid_heartbeat_sends_application_ping(monkeypatch):
    class FakeSocket:
        connected = True

    class FakeWebSocket:
        sock = FakeSocket()
        keep_running = True

        def __init__(self):
            self.sent = []

        def send(self, message):
            self.sent.append(message)

    ws = FakeWebSocket()
    sleep_count = 0

    def stop_after_one_ping(_seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 2:
            ws.keep_running = False

    monkeypatch.setattr("execution.cryptodash_ws.time.sleep", stop_after_one_ping)
    CryptoDashRealtimeHub._hyperliquid_heartbeat(ws)

    assert ws.sent == ['{"method": "ping"}']
