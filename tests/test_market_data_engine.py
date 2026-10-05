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
