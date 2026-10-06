from datetime import datetime, timedelta, timezone

import pytest

from execution.market_data_engine import normalize_market_snapshot, quote_age_seconds


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_normalize_snapshot_stamps_class_freshness_and_reference():
    timestamp = (NOW - timedelta(minutes=11)).isoformat()
    payload = {
        "metadata": {"generated_at_utc": "old"},
        "categories": {
            "📊 ÍNDICES": [
                {"symbol": f"SYM{i}", "name": f"Index {i}", "price": i + 100, "source": "test", "source_timestamp": timestamp}
                for i in range(6)
            ],
            "🇺🇸 TREASURIES (YIELDS)": [
                {"symbol": "US10Y", "name": "US 10Y Yield", "price": 4.2, "source": "test", "source_timestamp": timestamp}
            ],
        },
    }

    normalized = normalize_market_snapshot(payload, now=NOW)
    equity = normalized["categories"]["📊 ÍNDICES"][0]
    treasury = normalized["categories"]["🇺🇸 TREASURIES (YIELDS)"][0]

    assert equity["quote_class"] == "equity"
    assert equity["data_status"] == "stale"
    assert equity["max_age_seconds"] == 600
    assert equity["change_basis"] == "previous_session_close"
    assert treasury["quote_class"] == "treasury"
    assert treasury["data_status"] == "fresh"
    assert normalized["metadata"]["schema_version"] == "market_quotes_v2"
    assert normalized["metadata"]["generated_at_utc"] == NOW.isoformat()


def test_normalize_rejects_invalid_and_future_quotes():
    future = (NOW + timedelta(minutes=10)).isoformat()
    payload = {"categories": {"📊 ÍNDICES": [
        {"symbol": "BAD", "price": -1, "source": "test"},
        {"symbol": "FUTURE", "price": 100, "source": "test", "source_timestamp": future},
    ]}}

    with pytest.raises(ValueError, match="somente 0 cotações válidas"):
        normalize_market_snapshot(payload, now=NOW)


def test_missing_timestamp_is_kept_but_explicitly_unknown():
    payload = {"categories": {"📊 ÍNDICES": [
        {"symbol": f"SYM{i}", "price": 100 + i, "source": "test"}
        for i in range(6)
    ]}}

    normalized = normalize_market_snapshot(payload, now=NOW)

    assert normalized["categories"]["📊 ÍNDICES"][0]["data_status"] == "unknown"
    assert normalized["metadata"]["quote_quality"]["unknown"] == 6


def test_retrieval_timestamp_does_not_masquerade_as_market_timestamp():
    quote = {
        "source_timestamp": NOW.isoformat(),
        "timestamp_type": "retrieved_at",
        "age_seconds": 0,
        "market_delay_seconds": None,
    }

    assert quote_age_seconds(quote, now=NOW) is None
    quote["market_delay_seconds"] = 37
    assert quote_age_seconds(quote, now=NOW) == 37


def test_mixed_commodity_crypto_category_classifies_by_asset():
    timestamp = (NOW - timedelta(minutes=11)).isoformat()
    payload = {"categories": {"🛢️ COMMODITIES & CRIPTO": [
        {"symbol": "BZ=F", "name": "BRENT OIL", "price": 80, "source_timestamp": timestamp},
        {"symbol": "GC=F", "name": "GOLD", "price": 2300, "source_timestamp": timestamp},
        {"symbol": "BTC-USD", "name": "BITCOIN", "price": 60000, "source_timestamp": timestamp},
        {"symbol": "CL=F", "name": "WTI OIL", "price": 75, "source_timestamp": timestamp},
        {"symbol": "ETH-USD", "name": "ETHEREUM", "price": 3000, "source_timestamp": timestamp},
        {"symbol": "SOL-USD", "name": "SOLANA", "price": 150, "source_timestamp": timestamp},
    ]}}

    normalized = normalize_market_snapshot(payload, now=NOW)
    assets = {item["symbol"]: item for item in normalized["categories"]["🛢️ COMMODITIES & CRIPTO"]}

    assert assets["BZ=F"]["quote_class"] == "commodity"
    assert assets["BZ=F"]["max_age_seconds"] == 900
    assert assets["BZ=F"]["data_status"] == "fresh"
    assert assets["GC=F"]["quote_class"] == "commodity"
    assert assets["BTC-USD"]["quote_class"] == "crypto"
    assert assets["BTC-USD"]["data_status"] == "stale"
