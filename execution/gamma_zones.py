"""Daily EWZ options data and heuristic gamma exposure estimates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import erf, exp, log, pi, sqrt
import time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BRAPI_BASE = "https://brapi.dev/api/v2/options"
NEW_YORK = ZoneInfo("America/New_York")


def _get_yfinance():
    try:
        import yfinance
    except ImportError as exc:
        raise RuntimeError(f"yfinance indisponível: {exc}") from None
    return yfinance


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


def fetch_ewz_brapi_options(api_key: str, as_of: date | None = None, max_expirations: int = 8) -> dict[str, Any]:
    """Fetch daily options analytics from brapi as a fallback provider."""
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
    result["source_note"] = "Fonte alternativa: gregas e open interest reportados pela brapi, com referência diária."
    return result


def fetch_ewz_yahoo_options(as_of: date | None = None, max_expirations: int = 8) -> dict[str, Any]:
    """Fetch Yahoo chains and calculate option gamma locally from IV."""
    market_date = as_of or datetime.now(NEW_YORK).date()
    ticker = None
    yahoo_expirations = ()
    yahoo_request_error = None
    for attempt in range(2):
        try:
            ticker = _get_yfinance().Ticker("EWZ")
            yahoo_expirations = tuple(ticker.options or ())
            yahoo_request_error = None
        except Exception as exc:
            yahoo_expirations = ()
            yahoo_request_error = exc
        if yahoo_expirations:
            break
        if attempt == 0:
            time.sleep(0.5)
    if not yahoo_expirations:
        if yahoo_request_error:
            detail = str(yahoo_request_error).strip().replace("\n", " ")[:180] or type(yahoo_request_error).__name__
            raise RuntimeError(f"Yahoo não respondeu à cadeia do EWZ após duas consultas: {detail}") from None
        raise ValueError("Yahoo retornou a cadeia do EWZ sem datas de vencimento após duas consultas.")
    expirations = []
    for value in yahoo_expirations:
        try:
            expiry = date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
        if market_date <= expiry <= market_date + timedelta(days=365):
            expirations.append(expiry)
    expirations = sorted(set(expirations))[:max_expirations]
    if not expirations:
        valid_dates = sorted(str(value)[:10] for value in yahoo_expirations if str(value)[:10] >= market_date.isoformat())
        next_expiry = valid_dates[0] if valid_dates else "nenhum vencimento futuro listado"
        raise ValueError(
            f"Yahoo listou {next_expiry} como próximo vencimento, fora da janela de 12 meses a partir de {market_date.isoformat()}."
        )

    rows: list[dict[str, Any]] = []
    spot = None
    for expiry in expirations:
        chain = ticker.option_chain(expiry.isoformat())
        underlying = getattr(chain, "underlying", None) or {}
        if spot is None:
            for key in ("regularMarketPrice", "currentPrice", "regularMarketPreviousClose"):
                try:
                    candidate = float(underlying.get(key) or 0)
                except (TypeError, ValueError):
                    continue
                if candidate > 0:
                    spot = candidate
                    break
        for side, contracts in (("call", chain.calls), ("put", chain.puts)):
            if contracts is None or contracts.empty:
                continue
            for contract in contracts.to_dict("records"):
                try:
                    strike = float(contract["strike"])
                    oi = float(contract.get("openInterest") or 0)
                    iv = float(contract.get("impliedVolatility") or 0)
                    contract_size = str(contract.get("contractSize") or "REGULAR").upper()
                    multiplier = 100.0 if contract_size == "REGULAR" else 0.0
                except (TypeError, ValueError, KeyError):
                    continue
                if oi <= 0 or iv <= 0 or strike <= 0 or multiplier <= 0:
                    continue
                days = max((expiry - market_date).days, 1)
                years = days / 365
                rows.append({
                    "symbol": str(contract.get("contractSymbol") or ""),
                    "side": side,
                    "strike": strike,
                    "underlyingPrice": spot,
                    "openInterest": oi,
                    "allocationRoundLot": multiplier,
                    "impliedVolatility": iv,
                    "timeToExpirationYears": years,
                    "riskFreeRate": 0.04,
                    "dividendYield": 0.03,
                    "gamma": _bs_gamma(spot, strike, years, iv, 0.04, 0.03) if spot else 0,
                    "expirationDate": expiry.isoformat(),
                    "openInterestDate": "",
                    "confidence": "estimated from Yahoo IV",
                    "volume": float(contract.get("volume") or 0),
                    "bid": float(contract.get("bid") or 0),
                    "ask": float(contract.get("ask") or 0),
                    "lastTradeDate": str(contract.get("lastTradeDate") or ""),
                })
    if not spot or not rows:
        raise ValueError("Yahoo não retornou spot, IV e open interest utilizáveis para o EWZ.")
    result = build_gamma_exposure(rows, as_of=market_date.isoformat(), market_date=market_date)
    result["expirations_requested"] = [item.isoformat() for item in expirations]
    result["source"] = "Yahoo Finance via yfinance · cadeia de opções"
    result["source_note"] = (
        "Yahoo pode fornecer cotações com atraso; open interest pode refletir a sessão anterior. "
        "Gamma calculada localmente por Black-Scholes com taxa livre de risco de 4% e dividend yield de 3% assumidos."
    )
    result["notes"] = [result["source_note"]]
    return result


def fetch_ewz_daily_history(period: str = "1y", as_of: date | None = None) -> dict[str, Any]:
    """Return completed daily EWZ bars and the most recent regular-session close."""
    market_date = as_of or datetime.now(NEW_YORK).date()
    now_ny = datetime.now(NEW_YORK)
    history = _fetch_yahoo_chart_frame(interval="1d", period=period)
    if history is None or history.empty or "Close" not in history:
        raise ValueError("Yahoo não retornou histórico diário de fechamento do EWZ.")
    frame = history.dropna(subset=["Close"]).copy()
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if index.tz is None:
        index = index.tz_localize(NEW_YORK)
    else:
        index = index.tz_convert(NEW_YORK)
    frame.index = index
    if frame.index[-1].date() == market_date and now_ny.date() == market_date and now_ny.hour < 16 and len(frame) > 1:
        frame = frame.iloc[:-1]
    if frame.empty:
        raise ValueError("Não há pregão completo no histórico diário do EWZ.")
    return {
        "history": frame.tail(260),
        "last_close": float(frame["Close"].iloc[-1]),
        "last_close_date": frame.index[-1].date().isoformat(),
        "source": "Yahoo Finance · histórico diário",
    }


def _fetch_yahoo_chart_frame(interval: str, period: str) -> pd.DataFrame:
    response = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/EWZ",
        params={"interval": interval, "range": period, "includePrePost": "false", "events": "history"},
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError("Yahoo retornou erro para as barras intradiárias do EWZ.")
    result = (chart.get("result") or [None])[0]
    if not result:
        raise ValueError("Yahoo não retornou histórico intradiário para EWZ.")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not timestamps or not quote:
        raise ValueError("Resposta Yahoo sem candles intradiários para EWZ.")
    return pd.DataFrame(
        {
            "Open": quote.get("open", []),
            "High": quote.get("high", []),
            "Low": quote.get("low", []),
            "Close": quote.get("close", []),
            "Volume": quote.get("volume", []),
        },
        index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(NEW_YORK),
    )


def fetch_ewz_intraday_bars(interval: str = "5m", period: str = "5d") -> dict[str, Any]:
    """Fetch real intraday OHLCV bars directly from Yahoo's chart endpoint."""
    frame = _fetch_yahoo_chart_frame(interval=interval, period=period)
    frame = frame.rename(columns=str.lower)
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_index()
    if frame.empty:
        raise ValueError("Yahoo não retornou candles OHLC completos para EWZ.")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    frame["vwap_d"] = (
        ((frame["high"] + frame["low"] + frame["close"]) / 3 * frame["volume"])
        .groupby(frame.index.date).cumsum()
        / frame["volume"].groupby(frame.index.date).cumsum().replace(0, np.nan)
    )
    return {
        "bars": frame,
        "source": "Yahoo Finance chart · intraday direto",
        "interval": interval,
        "period": period,
        "last_bar_at": frame.index[-1].isoformat(),
        "last_price": float(frame["close"].iloc[-1]),
    }


def build_price_zone_levels(gex_result: dict[str, Any], reference_price: float, max_per_side: int = 3) -> dict[str, list[dict[str, float]]]:
    """Select nearby net-positive (damping) and net-negative (amplification) strikes."""
    strikes = gex_result.get("by_strike")
    if not isinstance(strikes, pd.DataFrame) or strikes.empty or reference_price <= 0:
        return {"defense": [], "acceleration": []}
    frame = strikes.copy()
    frame["distance_pct"] = (frame["strike"] / reference_price - 1).abs() * 100
    frame = frame[frame["distance_pct"] <= 18]
    positive = frame[frame["gex_usd_1pct"] > 0].nlargest(max_per_side, "gex_usd_1pct")
    negative = frame[frame["gex_usd_1pct"] < 0].nsmallest(max_per_side, "gex_usd_1pct")

    def rows(data: pd.DataFrame) -> list[dict[str, float]]:
        return [
            {"price": float(row.strike), "gex_usd_1pct": float(row.gex_usd_1pct)}
            for row in data.itertuples(index=False)
        ]

    return {"defense": rows(positive), "acceleration": rows(negative)}


def fetch_ewz_options(api_key: str = "", as_of: date | None = None, max_expirations: int = 8) -> dict[str, Any]:
    """Prefer Yahoo's free chain; fall back to brapi when Yahoo is unavailable."""
    try:
        return fetch_ewz_yahoo_options(as_of=as_of, max_expirations=max_expirations)
    except Exception as yahoo_error:
        yahoo_detail = str(yahoo_error).strip().replace("\n", " ")[:220] or type(yahoo_error).__name__
        if not api_key:
            raise ValueError(
                f"Yahoo não conseguiu carregar as opções do EWZ: {yahoo_detail}. "
                "Sem BRAPI_API_KEY, o GEX fica indisponível; preços intraday continuam acessíveis."
            ) from None
        result = fetch_ewz_brapi_options(api_key, as_of=as_of, max_expirations=max_expirations)
        result["source_note"] = f"Yahoo indisponível ({yahoo_detail}); usando fallback brapi. " + result["source_note"]
        result["notes"] = [result["source_note"], *result.get("notes", [])]
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
