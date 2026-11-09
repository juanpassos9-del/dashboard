import gzip
import json

from execution import cryptodash
from execution.cryptodash_ws import CryptoDashRealtimeHub


def test_provider_priority_binance_then_okx_then_bingx(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {
        "BTC": {"price": 60000, "change_pct_24h": 1.5, "quote_volume_24h": 100, "timestamp_ms": 0, "instrument": "BTCUSDT"}
    })
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {
        "ETH": {"price": 3000, "change_pct_24h": 2, "quote_volume_24h": 50, "timestamp_ms": 0, "instrument": "ETH-USDT"}
    })
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {
        "ETH": {"price": 2999, "change_pct_24h": 1, "quote_volume_24h": 45, "timestamp_ms": 0, "instrument": "ETH-USDT"}
    })

    result = cryptodash.fetch_cryptodash_quotes(["BTC", "ETH", "UNKNOWN"])

    assert [(row["asset"], row["exchange"]) for row in result["quotes"]] == [
        ("BTC", "Binance"), ("ETH", "OKX")
    ]
    assert result["unsupported"] == ["UNKNOWN"]


def test_failed_provider_is_reported_and_remaining_sources_are_used(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {
        "SOL": {"price": 150, "change_pct_24h": -1, "quote_volume_24h": 20, "timestamp_ms": 0, "instrument": "SOL-USDT"}
    })

    result = cryptodash.fetch_cryptodash_quotes(["SOL"])

    assert result["quotes"][0]["exchange"] == "OKX"
    assert result["provider_errors"]["Binance"] == "offline"


def test_commodity_contracts_are_requested_by_default():
    assert cryptodash.COMMODITIES == ["XAU", "XAG", "BZ", "CL", "XPD", "XPT", "COPPER", "NATGAS"]
    assert "USDBRL" in cryptodash.FX_ASSETS
    assert "EURUSD" in cryptodash.FX_ASSETS
    assert len(cryptodash.FX_ASSETS) == len(cryptodash.BINGX_FX_INSTRUMENTS)
    assert cryptodash.SECURITIES == [
        "SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "V", "BE", "BX",
        "GS", "HD", "KO", "MP", "MU", "ZM", "ZS", "ACN", "AMC", "AMD", "APP", "ARM",
        "SOXL", "SNDK", "SKHYNIX", "SOXS", "KORU", "SPCX", "SKHY", "SNXX", "INTC", "MSTR", "TQQQ", "EWY",
        "SAMSUNG", "DRAM",
    ]


def test_asset_classes_match_dashboard_groups():
    assert cryptodash.asset_class("BTC") == "Cripto"
    assert cryptodash.asset_class("AAPL") == "7 Magníficas"
    assert cryptodash.asset_class("SPY") == "Índices"
    assert cryptodash.asset_class("XAU") == "Commodities"
    assert cryptodash.asset_class("USDBRL") == "FX"
    assert cryptodash.asset_class("GS") == "Ações/ETFs"


def test_board_labels_and_logos_use_asset_names_not_instrument_ids():
    assert cryptodash.asset_display_name("BTC") == "Bitcoin"
    assert cryptodash.asset_display_name("AAPL") == "Apple"
    assert cryptodash.asset_display_name("XAU") == "Ouro"
    assert "BTCUSDT" not in cryptodash.asset_logo_url("BTC")
    assert "tradingview" not in cryptodash.asset_logo_url("BTC")
    assert cryptodash.asset_logo_url("AAPL").startswith("https://www.google.com/s2/favicons?")


def test_quote_direction_for_flash_feedback():
    assert cryptodash.quote_change_direction(None, 10) == ""
    assert cryptodash.quote_change_direction(10, 11) == "up"
    assert cryptodash.quote_change_direction(11, 10) == "down"
    assert cryptodash.quote_change_direction(10, 10) == ""


def test_snapshot_includes_exchange_instruments_for_websocket_subscriptions(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {
        "BTC": {"price": 60000, "timestamp_ms": 0, "instrument": "BTCUSDT", "market_type": "Spot"}
    })
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {})

    result = cryptodash.fetch_cryptodash_quotes(["BTC"])

    assert result["realtime_subscriptions"]["Binance"] == [
        {"asset": "BTC", "instrument": "BTCUSDT", "market_type": "Spot"}
    ]


def test_bingx_compressed_websocket_ticker_updates_live_quote_store():
    hub = CryptoDashRealtimeHub()
    row = {"asset": "EURUSD", "instrument": "NCFXEUR2USD-USDT", "market_type": "Índice Forex perpétuo"}
    payload = {
        "dataType": "NCFXEUR2USD-USDT@ticker",
        "data": {"s": "NCFXEUR2USD-USDT", "c": "1.12", "P": "0.7", "v": "12", "h": "1.13", "l": "1.11", "T": 1710000000000},
    }

    hub._on_message("bingx_swap", gzip.compress(json.dumps(payload).encode()), [row])

    quote = hub.latest_quotes()[("BingX", "EURUSD", "Índice Forex perpétuo")]
    assert quote["price"] == 1.12
    assert quote["source"] == "WebSocket"


def test_binance_combined_stream_ticker_updates_live_quote_store():
    hub = CryptoDashRealtimeHub()
    row = {"asset": "BTC", "instrument": "BTCUSDT", "market_type": "Spot"}
    payload = {"stream": "btcusdt@ticker", "data": {"s": "BTCUSDT", "c": "61000", "P": "1.5", "q": "100", "h": "62000", "l": "59000", "E": 1710000000000}}

    hub._on_message("binance_spot", json.dumps(payload), [row])

    quote = hub.latest_quotes()[("Binance", "BTC", "Spot")]
    assert quote["price"] == 61000


def test_bingx_is_used_only_after_binance_and_okx(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {
        "COPPER": {"price": 4.2, "change_pct_24h": 0.4, "quote_volume_24h": 5, "timestamp_ms": 0, "instrument": "COPPER-USDT"}
    })

    result = cryptodash.fetch_cryptodash_quotes(["COPPER"])

    assert result["quotes"][0]["exchange"] == "BingX"


def test_bingx_forex_contracts_are_normalized_to_currency_pairs(monkeypatch):
    def fake_request(url, timeout):
        if "spot" in url:
            return ({"data": []}, 1)
        return ({"data": [{
            "symbol": "NCFXEUR2USD-USDT", "lastPrice": "1.12", "priceChangePercent": "0.7",
            "quoteVolume": "1234", "highPrice": "1.13", "lowPrice": "1.11", "time": "1710000000000",
        }]}, 1)

    monkeypatch.setattr(cryptodash, "request_json", fake_request)
    result = cryptodash._bingx_tickers()

    assert result["EURUSD"]["price"] == 1.12
    assert result["EURUSD"]["instrument"] == "NCFXEUR2USD-USDT"
    assert result["EURUSD"]["market_type"] == "Índice Forex perpétuo"


def test_bingx_has_priority_for_forex_only(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {
        "EURUSD": {"price": 1.1, "change_pct_24h": 0, "timestamp_ms": 0, "instrument": "EURUSDUSDT"}
    })
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {
        "EURUSD": {"price": 1.12, "change_pct_24h": 0.7, "timestamp_ms": 0, "instrument": "NCFXEUR2USD-USDT"}
    })

    result = cryptodash.fetch_cryptodash_quotes(["EURUSD"])

    assert result["quotes"][0]["exchange"] == "BingX"
    assert result["quotes"][0]["price"] == 1.12


def test_old_last_trade_is_kept_and_marked_stale_when_no_fresh_fallback(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {
        "HD": {"price": 355, "change_pct_24h": 1, "quote_volume_24h": 10, "timestamp_ms": 1, "instrument": "HDUSDT"}
    })
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {})

    result = cryptodash.fetch_cryptodash_quotes(["HD"])

    assert result["quotes"][0]["asset"] == "HD"
    assert result["quotes"][0]["stale"] is True
    assert result["unsupported"] == []


def test_binance_spot_retries_official_hosts_and_keeps_spot_if_futures_fail(monkeypatch):
    def fake_request(url, timeout):
        if "data-api.binance.vision" in url:
            raise RuntimeError("network blocked")
        if url.startswith("https://api.binance.com/"):
            return ([{"symbol": "BTCUSDT", "lastPrice": "60000", "priceChangePercent": "1", "quoteVolume": "10", "closeTime": "1000"}], 12)
        raise RuntimeError("USD-M offline")

    monkeypatch.setattr(cryptodash, "request_json", fake_request)
    result = cryptodash._binance_tickers()

    assert result["BTC"]["instrument"] == "BTCUSDT"
    assert "_warnings" in result
    assert any("USDⓈ-M" in warning for warning in result["_warnings"])


def test_binance_futures_survive_spot_endpoint_outage(monkeypatch):
    def fake_request(url, timeout):
        if "fapi.binance.com" in url:
            return ([{"symbol": "XAUUSDT", "lastPrice": "4100", "priceChangePercent": "0.5", "quoteVolume": "100", "highPrice": "4120", "lowPrice": "4050", "closeTime": "1000"}], 15)
        raise RuntimeError("spot offline")

    monkeypatch.setattr(cryptodash, "request_json", fake_request)
    result = cryptodash._binance_tickers()

    assert result["XAU"]["instrument"] == "XAUUSDT"
    assert "Spot Binance indisponível" in result["_warnings"][0]
