from execution import cryptodash


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
    assert cryptodash.FX_ASSETS == ["USDBRL"]
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


def test_bingx_is_used_only_after_binance_and_okx(monkeypatch):
    monkeypatch.setattr(cryptodash, "_binance_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_okx_tickers", lambda: {})
    monkeypatch.setattr(cryptodash, "_bingx_tickers", lambda: {
        "COPPER": {"price": 4.2, "change_pct_24h": 0.4, "quote_volume_24h": 5, "timestamp_ms": 0, "instrument": "COPPER-USDT"}
    })

    result = cryptodash.fetch_cryptodash_quotes(["COPPER"])

    assert result["quotes"][0]["exchange"] == "BingX"


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
