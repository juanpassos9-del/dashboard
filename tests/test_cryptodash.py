from execution import cryptodash


def test_provider_priority_and_unsupported_assets(monkeypatch):
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
        ("BTC", "Binance"), ("ETH", "BingX")
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
