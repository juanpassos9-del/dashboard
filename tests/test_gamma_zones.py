from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from execution import gamma_zones
from execution.gamma_zones import build_gamma_exposure, build_price_zone_levels, fetch_ewz_daily_history, fetch_ewz_intraday_bars, fetch_ewz_options


def _option(symbol, side, strike, expiry, oi, *, iv=0.35, spot=100.0):
    return {
        "symbol": symbol,
        "side": side,
        "strike": strike,
        "expirationDate": expiry,
        "openInterest": oi,
        "allocationRoundLot": 100,
        "underlyingPrice": spot,
        "gamma": 0.02,
        "impliedVolatility": iv,
        "timeToExpirationYears": 14 / 365,
        "riskFreeRate": 0.04,
        "dividendYield": 0.02,
        "openInterestDate": "2026-11-04",
        "confidence": "medium",
    }


def test_gex_uses_documented_call_put_sign_convention_and_0dte_subset():
    rows = [
        _option("EWZC100", "call", 100, "2026-11-05", 1000),
        _option("EWZP100", "put", 100, "2026-11-12", 400),
    ]
    result = build_gamma_exposure(rows, as_of="2026-11-05", market_date=date(2026, 11, 5))

    assert result["net_gex_usd_1pct"] > 0
    assert result["zero_dte_available"] is True
    assert result["gex_0dte_usd_1pct"] > 0
    assert result["option_count"] == 2
    assert result["call_wall"]["strike"] == 100
    assert result["put_wall"]["strike"] == 100


def test_prior_session_chain_does_not_claim_fresh_0dte_data():
    result = build_gamma_exposure(
        [_option("EWZC100", "call", 100, "2026-11-05", 1000)],
        as_of="2026-11-04",
        market_date=date(2026, 11, 5),
    )

    assert result["zero_dte_expiration_present"] is True
    assert result["zero_dte_available"] is False
    assert result["gex_0dte_usd_1pct"] == 0


def test_gex_flip_is_interpolated_from_scenario_curve():
    rows = [
        _option("EWZC110", "call", 110, "2026-11-19", 3000),
        _option("EWZP90", "put", 90, "2026-11-19", 3000),
    ]
    result = build_gamma_exposure(rows, market_date=date(2026, 11, 5), grid_points=401)

    assert result["gamma_flip"] is not None
    assert 75 <= result["gamma_flip"] <= 125


def test_price_overlay_separates_defense_and_acceleration_strikes():
    rows = [
        _option("EWZC101", "call", 101, "2026-11-19", 3000),
        _option("EWZP99", "put", 99, "2026-11-19", 4000),
        _option("EWZC130", "call", 130, "2026-11-19", 9999),
    ]
    exposure = build_gamma_exposure(rows, market_date=date(2026, 11, 5))

    zones = build_price_zone_levels(exposure, reference_price=100)

    assert [item["price"] for item in zones["defense"]] == [101]
    assert [item["price"] for item in zones["acceleration"]] == [99]


def test_daily_history_excludes_incomplete_current_session(monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 5, 10, 0, tzinfo=tz)

    history = pd.DataFrame(
        {"Close": [30.0, 31.0, 32.0]},
        index=pd.to_datetime(["2026-11-03", "2026-11-04", "2026-11-05"]).tz_localize("America/New_York"),
    )
    monkeypatch.setattr(gamma_zones, "_fetch_yahoo_chart_frame", lambda **kwargs: history)
    monkeypatch.setattr(gamma_zones, "datetime", FrozenDateTime)
    result = fetch_ewz_daily_history(as_of=date(2026, 11, 5))

    assert result["last_close"] == 31.0
    assert result["last_close_date"] == "2026-11-04"


def test_intraday_fetch_parses_yahoo_ohlcv_and_calculates_session_vwap(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1793899800, 1793900100],
                        "indicators": {"quote": [{
                            "open": [32.0, 32.1],
                            "high": [32.2, 32.3],
                            "low": [31.9, 32.0],
                            "close": [32.1, 32.2],
                            "volume": [1000, 2000],
                        }]},
                    }],
                    "error": None,
                }
            }

    monkeypatch.setattr(gamma_zones.requests, "get", lambda *args, **kwargs: FakeResponse())
    result = fetch_ewz_intraday_bars()

    assert len(result["bars"]) == 2
    assert result["bars"].iloc[-1]["close"] == 32.2
    assert result["bars"]["vwap_d"].notna().all()
    assert "Yahoo Finance" in result["source"]


def test_invalid_or_missing_open_interest_rows_are_excluded():
    result = build_gamma_exposure([
        _option("EWZC100", "call", 100, "2026-11-19", 500),
        _option("EWZP90", "put", 90, "2026-11-19", 0),
    ], market_date=date(2026, 11, 5))

    assert result["option_count"] == 1
    assert result["net_gex_usd_1pct"] > 0


def test_empty_usable_chain_raises_clear_error():
    with pytest.raises(ValueError, match="gamma e open interest"):
        build_gamma_exposure([{"side": "call", "strike": 100}], market_date=date(2026, 11, 5))


def _fake_chain(expiry):
    contracts = pd.DataFrame([{
        "contractSymbol": f"EWZC{expiry.replace('-', '')}",
        "strike": 50,
        "openInterest": 1200,
        "impliedVolatility": 0.32,
        "contractSize": "REGULAR",
        "volume": 250,
        "bid": 1.2,
        "ask": 1.3,
        "lastTradeDate": "2026-11-05",
    }])
    return SimpleNamespace(calls=contracts, puts=contracts.assign(contractSymbol=f"EWZP{expiry.replace('-', '')}"), underlying={"regularMarketPrice": 50.0})


def test_yahoo_is_primary_and_does_not_require_brapi_key(monkeypatch):
    class FakeTicker:
        options = ("2026-11-05", "2026-11-12")

        def option_chain(self, expiry):
            return _fake_chain(expiry)

    monkeypatch.setattr(gamma_zones, "_get_yfinance", lambda: SimpleNamespace(Ticker=lambda symbol: FakeTicker()))
    result = fetch_ewz_options("", as_of=date(2026, 11, 5))

    assert result["source"].startswith("Yahoo Finance")
    assert result["option_count"] == 4
    assert result["zero_dte_available"] is True


def test_brapi_is_used_only_when_yahoo_fails(monkeypatch):
    fallback = {"source": "brapi", "notes": [], "source_note": "daily"}
    monkeypatch.setattr(gamma_zones, "fetch_ewz_yahoo_options", lambda **kwargs: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(gamma_zones, "fetch_ewz_brapi_options", lambda *args, **kwargs: fallback.copy())

    result = fetch_ewz_options("test-token", as_of=date(2026, 11, 5))

    assert result["source"] == "brapi"
    assert "Yahoo indisponível" in result["source_note"]


def test_missing_yahoo_and_brapi_key_returns_clear_message(monkeypatch):
    monkeypatch.setattr(gamma_zones, "fetch_ewz_yahoo_options", lambda **kwargs: (_ for _ in ()).throw(ConnectionError("down")))
    with pytest.raises(ValueError, match="BRAPI_API_KEY"):
        fetch_ewz_options("")
