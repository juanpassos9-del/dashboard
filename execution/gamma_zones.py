"""Daily EWZ options data and heuristic gamma exposure estimates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import erf, exp, log, pi, sqrt
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BRAPI_BASE = "https://brapi.dev/api/v2/options"
NEW_YORK = ZoneInfo("America/New_York")


def _normal_pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2 * pi)


def _bs_gamma(spot: float, strike: float, years: float, volatility: float, rate: float, dividend: float) -> float:
    if min(spot, strike, years, volatility) <= 0:
        return 0.0
    root_time = sqrt(years)
    d1 = (log(spot / strike) + (rate - dividend + 0.5 * volatility**2) * years) / (volatility * root_time)
    return exp(-dividend * years) * _normal_pdf(d1) / (spot * volatility * root_time)


def _get_json(session: requests.Session, endpoint: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    response = session.get(
        f"{BRAPI_BASE}/{endpoint}",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=(5, 20),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in {401, 403}:
            raise ValueError("A brapi recusou o acesso às opções do EWZ. Confira o token e se o plano inclui dados de opções (Pro).") from None
        raise ValueError(f"A brapi respondeu HTTP {status or 'indisponível'} ao consultar opções do EWZ.") from None
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Resposta inválida da brapi em {endpoint}.")
    return payload


def fetch_ewz_options(api_key: str, as_of: date | None = None, max_expirations: int = 8) -> dict[str, Any]:
    """Fetch daily options analytics for near-term EWZ expirations."""
    if not api_key:
        raise ValueError("Configure BRAPI_API_KEY nos Secrets do Streamlit para acessar opções do EWZ.")
    market_date = as_of or datetime.now(NEW_YORK).date()
    session = requests.Session()
    expirations_payload = _get_json(session, "expirations", {"underlying": "EWZ"}, api_key)
    expirations = expirations_payload.get("expirations") or []
    eligible = []
    for value in expirations:
        try:
            expiry = date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
        if market_date <= expiry <= market_date + timedelta(days=60):
            eligible.append(expiry)
    eligible = sorted(set(eligible))[:max_expirations]
    if not eligible:
        raise ValueError("A brapi não retornou vencimentos futuros do EWZ nos próximos 60 dias.")

    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    dates: list[str] = []
    for expiry in eligible:
        params = {"underlying": "EWZ", "expirationDate": expiry.isoformat()}
        try:
            payload = _get_json(session, "analytics", {**params, "limit": 500}, api_key)
            analytics = payload.get("analytics") or []
            if not analytics:
                notes.append(f"Sem gregas calculadas para {expiry.isoformat()}.")
                continue
            if payload.get("date"):
                dates.append(str(payload["date"])[:10])
            rows.extend(analytics)
        except requests.RequestException as exc:
            notes.append(f"Falha de rede no vencimento {expiry.isoformat()}: {type(exc).__name__}.")
    if not rows:
        raise ValueError("Não há gregas/open interest utilizáveis para EWZ. Confira plano, token e cobertura da brapi.")
    result = build_gamma_exposure(rows, as_of=max(dates) if dates else None, market_date=market_date)
    result["expirations_requested"] = [item.isoformat() for item in eligible]
    result["notes"] = notes
    result["source"] = "brapi options analytics · fechamento diário"
    return result


def build_gamma_exposure(
    option_rows: list[dict[str, Any]],
    as_of: str | None = None,
    market_date: date | None = None,
    grid_points: int = 241,
) -> dict[str, Any]:
    """Build signed GEX estimates; calls positive / puts negative is an explicit heuristic."""
    normalized = []
    for row in option_rows:
        try:
            side = str(row.get("side", "")).lower()
            strike = float(row["strike"])
            spot = float(row["underlyingPrice"])
            oi = float(row.get("openInterest") or 0)
            multiplier = float(row.get("allocationRoundLot") or 100)
            gamma = float(row.get("gamma") or 0)
            iv = float(row.get("impliedVolatility") or 0)
            expiry = date.fromisoformat(str(row["expirationDate"])[:10])
            if side not in {"call", "put"} or min(strike, spot, multiplier) <= 0 or oi <= 0:
                continue
            years = float(row.get("timeToExpirationYears") or 0)
            if years <= 0:
                days = max((expiry - (market_date or date.today())).days, 0)
                years = max(days, 1) / 365
            if gamma <= 0 and iv > 0:
                gamma = _bs_gamma(spot, strike, years, iv, float(row.get("riskFreeRate") or 0), float(row.get("dividendYield") or 0))
            if gamma <= 0:
                continue
            normalized.append({
                "symbol": str(row.get("symbol") or ""),
                "side": side,
                "strike": strike,
                "spot": spot,
                "open_interest": oi,
                "multiplier": multiplier,
                "gamma": gamma,
                "iv": iv,
                "years": years,
                "rate": float(row.get("riskFreeRate") or 0),
                "dividend": float(row.get("dividendYield") or 0),
                "expiration": expiry.isoformat(),
                "open_interest_date": str(row.get("openInterestDate") or row.get("date") or "")[:10],
                "confidence": str(row.get("confidence") or "unknown"),
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not normalized:
        raise ValueError("A cadeia não trouxe linhas com gamma e open interest válidos.")

    frame = pd.DataFrame(normalized)
    spot = float(frame["spot"].median())
    frame["signed_gex"] = np.where(frame["side"].eq("call"), 1.0, -1.0) * frame["gamma"] * frame["open_interest"] * frame["multiplier"] * spot**2 * 0.01
    by_strike = frame.groupby("strike", as_index=False).agg(
        gex_usd_1pct=("signed_gex", "sum"),
        call_gex=("signed_gex", lambda values: float(values[frame.loc[values.index, "side"].eq("call")].sum())),
        put_gex=("signed_gex", lambda values: float(values[frame.loc[values.index, "side"].eq("put")].sum())),
        open_interest=("open_interest", "sum"),
    ).sort_values("strike").reset_index(drop=True)
    net_gex = float(frame["signed_gex"].sum())

    low, high = max(spot * 0.75, 0.01), spot * 1.25
    price_grid = np.linspace(low, high, max(int(grid_points), 41))
    curve = np.zeros_like(price_grid)
    for row in frame.itertuples(index=False):
        if row.iv <= 0:
            continue
        sign = 1.0 if row.side == "call" else -1.0
        gamma_values = np.array([
            _bs_gamma(float(price), row.strike, row.years, row.iv, row.rate, row.dividend)
            for price in price_grid
        ])
        curve += sign * gamma_values * row.open_interest * row.multiplier * price_grid**2 * 0.01
    flip = None
    for index in range(len(price_grid) - 1):
        left, right = curve[index], curve[index + 1]
        if left == 0 or left * right < 0:
            fraction = 0.0 if left == 0 else abs(left) / (abs(left) + abs(right))
            candidate = float(price_grid[index] + fraction * (price_grid[index + 1] - price_grid[index]))
            if flip is None or abs(candidate - spot) < abs(flip - spot):
                flip = candidate

    current_date = market_date or datetime.now(NEW_YORK).date()
    same_session_data = str(as_of or "")[:10] == current_date.isoformat()
    frame["is_0dte"] = frame["expiration"].eq(current_date.isoformat()) & same_session_data
    gex_0dte = float(frame.loc[frame["is_0dte"], "signed_gex"].sum())
    call_rows = by_strike[by_strike["call_gex"] > 0]
    put_rows = by_strike[by_strike["put_gex"] < 0]
    top_call = call_rows.loc[call_rows["call_gex"].idxmax()].to_dict() if not call_rows.empty else None
    top_put = put_rows.loc[put_rows["put_gex"].idxmin()].to_dict() if not put_rows.empty else None
    by_expiration = frame.groupby("expiration", as_index=False).agg(
        gex_usd_1pct=("signed_gex", "sum"),
        open_interest=("open_interest", "sum"),
    ).sort_values("expiration")
    profile = pd.DataFrame({"spot_scenario": price_grid, "gex_usd_1pct": curve})
    return {
        "underlying": "EWZ",
        "spot": spot,
        "as_of": as_of or max(frame["open_interest_date"].dropna().tolist(), default=""),
        "market_date": current_date.isoformat(),
        "net_gex_usd_1pct": net_gex,
        "gamma_flip": flip,
        "call_wall": top_call,
        "put_wall": top_put,
        "gex_0dte_usd_1pct": gex_0dte,
        "gex_0dte_share_pct": abs(gex_0dte) / max(float(frame["signed_gex"].abs().sum()), 1e-12) * 100,
        "option_count": len(frame),
        "expiration_count": int(frame["expiration"].nunique()),
        "zero_dte_available": bool(frame["is_0dte"].any()),
        "zero_dte_expiration_present": bool(frame["expiration"].eq(current_date.isoformat()).any()),
        "zero_dte_freshness_confirmed": same_session_data,
        "by_strike": by_strike,
        "by_expiration": by_expiration,
        "profile": profile,
        "options": frame,
        "sign_convention": "calls + / puts - (heurística de dealer positioning)",
    }
