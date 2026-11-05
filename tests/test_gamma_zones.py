from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from execution import gamma_zones
from execution.gamma_zones import build_gamma_exposure, build_price_zone_levels, fetch_ewz_daily_history, fetch_ewz_intraday_bars, fetch_ewz_options
from execution.gamma_history import make_gamma_snapshot, merge_gamma_snapshots, recent_gamma_snapshots


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
    timestamps = [
        int(pd.Timestamp(f"2026-11-05 {clock}", tz="America/New_York").timestamp())
        for clock in ("04:00", "09:30", "16:00", "20:00")
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [{
                        "timestamp": timestamps,
                        "indicators": {"quote": [{
                            "open": [32.0, 32.1, 32.2, 32.3],
                            "high": [32.2, 32.3, 32.4, 32.5],
                            "low": [31.9, 32.0, 32.1, 32.2],
                            "close": [32.1, 32.2, 32.3, 32.4],
                            "volume": [1000, 2000, 3000, 4000],
                        }]},
                    }],
                    "error": None,
                }
            }

    request_params = {}

    def fake_get(*args, **kwargs):
        request_params.update(kwargs["params"])
        return FakeResponse()

    monkeypatch.setattr(gamma_zones.requests, "get", fake_get)
    result = fetch_ewz_intraday_bars()

    assert len(result["bars"]) == 4
    assert result["bars"].iloc[-1]["close"] == 32.4
    assert result["bars"]["session"].tolist() == ["Pré-mercado", "Regular", "Pós-mercado", "Overnight (barra fornecida pela fonte)"]
    assert result["bars"]["vwap_d"].notna().tolist() == [False, True, False, False]
    assert request_params["includePrePost"] == "true"
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


def test_yahoo_retries_empty_expirations_and_accepts_longer_dated_chain(monkeypatch):
    attempts = {"count": 0}

    class FakeTicker:
        def __init__(self, expiries):
            self.options = expiries

        def option_chain(self, expiry):
            return _fake_chain(expiry)

    def make_ticker(symbol):
        attempts["count"] += 1
        expiries = () if attempts["count"] == 1 else ("2027-04-05",)
        return FakeTicker(expiries)

    monkeypatch.setattr(gamma_zones, "_get_yfinance", lambda: SimpleNamespace(Ticker=make_ticker))
    monkeypatch.setattr(gamma_zones.time, "sleep", lambda seconds: None)

    result = fetch_ewz_options("", as_of=date(2026, 11, 5))

    assert attempts["count"] == 2
    assert result["expiration_count"] == 1
    assert result["expirations_requested"] == ["2027-04-05"]


def test_yahoo_retries_transient_chain_request_error_and_preserves_cause(monkeypatch):
    attempts = {"count": 0}

    class FakeTicker:
        @property
        def options(self):
            attempts["count"] += 1
            raise ConnectionError("DNS lookup failed")

    monkeypatch.setattr(gamma_zones, "_get_yfinance", lambda: SimpleNamespace(Ticker=lambda symbol: FakeTicker()))
    monkeypatch.setattr(gamma_zones.time, "sleep", lambda seconds: None)

    with pytest.raises(RuntimeError, match="DNS lookup failed"):
        gamma_zones.fetch_ewz_yahoo_options(as_of=date(2026, 11, 5))

    assert attempts["count"] == 2


def test_brapi_is_used_only_when_yahoo_fails(monkeypatch):
    fallback = {"source": "brapi", "notes": [], "source_note": "daily"}
    monkeypatch.setattr(gamma_zones, "fetch_ewz_yahoo_options", lambda **kwargs: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(gamma_zones, "fetch_ewz_brapi_options", lambda *args, **kwargs: fallback.copy())

    result = fetch_ewz_options("test-token", as_of=date(2026, 11, 5))

    assert result["source"] == "brapi"
    assert "Yahoo indisponível" in result["source_note"]


def test_missing_yahoo_and_brapi_key_returns_clear_message(monkeypatch):
    monkeypatch.setattr(gamma_zones, "fetch_ewz_yahoo_options", lambda **kwargs: (_ for _ in ()).throw(ConnectionError("Yahoo timeout")))
    with pytest.raises(ValueError, match="BRAPI_API_KEY") as error:
        fetch_ewz_options("")
    assert "Yahoo timeout" in str(error.value)
    assert "preços intraday continuam acessíveis" in str(error.value)


def test_gamma_history_replaces_same_day_and_keeps_latest_five():
    history = []
    for day in range(1, 7):
        snapshot = make_gamma_snapshot({
            "market_date": f"2026-11-{day:02d}",
            "spot": 50 + day,
            "net_gex_usd_1pct": day * 1e6,
            "option_count": 40,
        }, f"2026-11-{day:02d}T21:00:00+00:00")
        history = merge_gamma_snapshots(history, snapshot)

    replacement = make_gamma_snapshot({
        "market_date": "2026-11-06",
        "spot": 60,
        "net_gex_usd_1pct": 9e6,
        "option_count": 42,
    }, "2026-11-06T22:00:00+00:00")
    history = merge_gamma_snapshots(history, replacement)

    recent = recent_gamma_snapshots(history, 5)
    assert len(history) == 6
    assert len(recent) == 5
    assert recent[-1]["spot"] == 60
    assert recent[-1]["net_gex_usd_1pct"] == 9e6


def test_gamma_snapshot_keeps_only_compact_headline_fields():
    snapshot = make_gamma_snapshot({
        "market_date": "2026-11-05",
        "spot": 50,
        "net_gex_usd_1pct": -2500000,
        "gamma_flip": 51.2,
        "call_wall": {"strike": 55},
        "put_wall": {"strike": 48},
        "option_count": 250,
        "expiration_count": 4,
        "options": [{"symbol": "EWZ"}],
    }, "2026-11-05T21:00:00+00:00")

    assert snapshot["gamma_flip"] == 51.2
    assert snapshot["call_wall"] == 55
    assert "options" not in snapshot
