from datetime import date

import pytest

from execution.gamma_zones import build_gamma_exposure, fetch_ewz_options


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


def test_fetch_requires_brapi_token():
    with pytest.raises(ValueError, match="BRAPI_API_KEY"):
        fetch_ewz_options("")
