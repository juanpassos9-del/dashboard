from datetime import datetime, timedelta, timezone

import pandas as pd

from execution import fetch_global_markets as market_collector


def _quote(source, age_seconds, **extra):
    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {
        "name": "US 10Y (Yield)",
        "symbol": "^TNX",
        "price": 4.2,
        "source": source,
        "source_timestamp": timestamp,
        "age_seconds": age_seconds,
        **extra,
    }


def _disable_other_sources(monkeypatch):
    monkeypatch.setattr(market_collector, "_fetch_fred_yield_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_brapi_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_lse_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_twelve_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_alpha_candidate", lambda *_: None)


def test_fresh_primary_skips_tradingview(monkeypatch):
    primary = _quote("Yahoo Finance", 30)
    monkeypatch.setattr(market_collector, "_candidate_from_frame", lambda *_args, **_kwargs: primary)
    monkeypatch.setattr(
        market_collector,
        "fetch_tradingview_treasury_candidate",
        lambda *_: (_ for _ in ()).throw(AssertionError("TradingView should not be called")),
    )
    _disable_other_sources(monkeypatch)

    result = market_collector._quote_candidates("US 10Y (Yield)", "^TNX", pd.DataFrame({"Close": [4.2]}))

    assert result == [primary]


def test_stale_primary_uses_tradingview_fallback(monkeypatch):
    primary = _quote("Yahoo Finance", 2 * 60 * 60)
    tv = {
        **_quote("TradingView OTC Yields", 0, timestamp_type="retrieved_at", market_delay_seconds=20),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    monkeypatch.setattr(market_collector, "_candidate_from_frame", lambda *_args, **_kwargs: primary)
    monkeypatch.setattr(market_collector, "fetch_tradingview_treasury_candidate", lambda *_: dict(tv))
    _disable_other_sources(monkeypatch)

    result = market_collector._quote_candidates("US 10Y (Yield)", "^TNX", pd.DataFrame({"Close": [4.2]}))

    assert len(result) == 1
    assert result[0]["source"] == "TradingView OTC Yields"
    assert result[0]["fallback_reason"] == "primary_stale"
    assert result[0]["fallback_for_source"] == "Yahoo Finance"


def test_explicitly_stale_tradingview_falls_through_to_other_provider(monkeypatch):
    primary = _quote("Yahoo Finance", 2 * 60 * 60)
    tv = {
        **_quote("TradingView OTC Yields", 3 * 60 * 60, timestamp_type="retrieved_at", market_delay_seconds=3 * 60 * 60),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    backup = _quote("Twelve Data", 45)
    monkeypatch.setattr(market_collector, "_candidate_from_frame", lambda *_args, **_kwargs: primary)
    monkeypatch.setattr(market_collector, "fetch_tradingview_treasury_candidate", lambda *_: dict(tv))
    monkeypatch.setattr(market_collector, "_fetch_fred_yield_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_brapi_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_lse_candidate", lambda *_: None)
    monkeypatch.setattr(market_collector, "_fetch_twelve_candidate", lambda *_: backup)
    monkeypatch.setattr(market_collector, "_fetch_alpha_candidate", lambda *_: None)

    result = market_collector._quote_candidates("US 10Y (Yield)", "^TNX", pd.DataFrame({"Close": [4.2]}))
    selected = market_collector._select_best_candidate(result, max_age_seconds=60 * 60)

    assert selected["source"] == "Twelve Data"
