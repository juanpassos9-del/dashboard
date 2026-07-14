"""Lightweight global momentum screener for the Terminal Global page.

The module is intentionally compact: it computes a daily snapshot from a
curated cross-asset universe and caches the result locally so Streamlit does
not need to recalculate the whole ranking on every rerun.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


ROOT_DIR = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT_DIR / ".tmp" / "global_momentum_screener.json"
CACHE_TTL_SECONDS = 30 * 60


ASSET_UNIVERSE: list[dict[str, str]] = [
    {"symbol": "SPY", "ticker": "SPY", "name": "S&P 500 ETF", "asset_class": "Equity", "benchmark": "SPY"},
    {"symbol": "QQQ", "ticker": "QQQ", "name": "Nasdaq 100 ETF", "asset_class": "Equity", "benchmark": "SPY"},
    {"symbol": "IWM", "ticker": "IWM", "name": "Russell 2000 ETF", "asset_class": "Equity", "benchmark": "SPY"},
    {"symbol": "DIA", "ticker": "DIA", "name": "Dow Jones ETF", "asset_class": "Equity", "benchmark": "SPY"},
    {"symbol": "XLK", "ticker": "XLK", "name": "Technology", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "XLE", "ticker": "XLE", "name": "Energy", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "XLF", "ticker": "XLF", "name": "Financials", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "SMH", "ticker": "SMH", "name": "Semiconductors", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "XLP", "ticker": "XLP", "name": "Staples", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "XLU", "ticker": "XLU", "name": "Utilities", "asset_class": "Sectors", "benchmark": "SPY"},
    {"symbol": "EWZ", "ticker": "EWZ", "name": "Brazil ETF", "asset_class": "Emerging", "benchmark": "EEM"},
    {"symbol": "EEM", "ticker": "EEM", "name": "Emerging Markets", "asset_class": "Emerging", "benchmark": "ACWI"},
    {"symbol": "EFA", "ticker": "EFA", "name": "Developed ex-US", "asset_class": "Equity", "benchmark": "ACWI"},
    {"symbol": "ACWI", "ticker": "ACWI", "name": "Global Equity", "asset_class": "Equity", "benchmark": "ACWI"},
    {"symbol": "PBR", "ticker": "PBR", "name": "Petrobras ADR", "asset_class": "Brazil ADR", "benchmark": "EWZ"},
    {"symbol": "VALE", "ticker": "VALE", "name": "Vale ADR", "asset_class": "Brazil ADR", "benchmark": "EWZ"},
    {"symbol": "ITUB", "ticker": "ITUB", "name": "Itau ADR", "asset_class": "Brazil ADR", "benchmark": "EWZ"},
    {"symbol": "BBD", "ticker": "BBD", "name": "Bradesco ADR", "asset_class": "Brazil ADR", "benchmark": "EWZ"},
    {"symbol": "DXY", "ticker": "DX-Y.NYB", "name": "Dollar Index", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "UUP", "ticker": "UUP", "name": "Dollar ETF", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "EURUSD", "ticker": "EURUSD=X", "name": "Euro/Dollar", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "USDJPY", "ticker": "JPY=X", "name": "Dollar/Yen", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "USDBRL", "ticker": "BRL=X", "name": "Dollar/Real", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "AUDUSD", "ticker": "AUDUSD=X", "name": "Aussie/Dollar", "asset_class": "FX", "benchmark": "UUP"},
    {"symbol": "BRENT", "ticker": "BZ=F", "name": "Brent Oil", "asset_class": "Commodities", "benchmark": "DBC"},
    {"symbol": "WTI", "ticker": "CL=F", "name": "WTI Oil", "asset_class": "Commodities", "benchmark": "DBC"},
    {"symbol": "GOLD", "ticker": "GC=F", "name": "Gold", "asset_class": "Metals", "benchmark": "DBC"},
    {"symbol": "SILVER", "ticker": "SI=F", "name": "Silver", "asset_class": "Metals", "benchmark": "DBC"},
    {"symbol": "COPPER", "ticker": "HG=F", "name": "Copper", "asset_class": "Metals", "benchmark": "DBC"},
    {"symbol": "DBC", "ticker": "DBC", "name": "Commodity Basket", "asset_class": "Commodities", "benchmark": "DBC"},
    {"symbol": "TLT", "ticker": "TLT", "name": "20Y+ Treasuries", "asset_class": "Bonds", "benchmark": "AGG"},
    {"symbol": "IEF", "ticker": "IEF", "name": "7-10Y Treasuries", "asset_class": "Bonds", "benchmark": "AGG"},
    {"symbol": "SHY", "ticker": "SHY", "name": "1-3Y Treasuries", "asset_class": "Bonds", "benchmark": "AGG"},
    {"symbol": "HYG", "ticker": "HYG", "name": "High Yield", "asset_class": "Credit", "benchmark": "AGG"},
    {"symbol": "LQD", "ticker": "LQD", "name": "Investment Grade", "asset_class": "Credit", "benchmark": "AGG"},
    {"symbol": "AGG", "ticker": "AGG", "name": "Aggregate Bonds", "asset_class": "Bonds", "benchmark": "AGG"},
    {"symbol": "BTC", "ticker": "BTC-USD", "name": "Bitcoin", "asset_class": "Crypto", "benchmark": "BTC-USD"},
    {"symbol": "ETH", "ticker": "ETH-USD", "name": "Ethereum", "asset_class": "Crypto", "benchmark": "BTC-USD"},
    {"symbol": "SOL", "ticker": "SOL-USD", "name": "Solana", "asset_class": "Crypto", "benchmark": "BTC-USD"},
    {"symbol": "BNB", "ticker": "BNB-USD", "name": "BNB", "asset_class": "Crypto", "benchmark": "BTC-USD"},
    {"symbol": "LINK", "ticker": "LINK-USD", "name": "Chainlink", "asset_class": "Crypto", "benchmark": "BTC-USD"},
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def _read_cache(max_age_seconds: int = CACHE_TTL_SECONDS) -> dict[str, Any] | None:
    try:
        if not CACHE_PATH.exists():
            return None
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        generated_ts = float(payload.get("generated_ts", 0))
        if max_age_seconds > 0 and time.time() - generated_ts > max_age_seconds:
            return None
        return payload
    except Exception:
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cached_global_momentum(max_age_seconds: int = CACHE_TTL_SECONDS) -> dict[str, Any] | None:
    return _read_cache(max_age_seconds=max_age_seconds)


def _download_history(tickers: list[str], period: str = "18mo") -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    unique = sorted(set(tickers))
    for start in range(0, len(unique), 10):
        chunk = unique[start:start + 10]
        data = pd.DataFrame()
        for attempt in range(2):
            try:
                data = yf.download(
                    chunk,
                    period=period,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                    timeout=18,
                )
                if data is not None and not data.empty:
                    break
            except Exception:
                time.sleep(0.6 + attempt * 0.5)
        if data is None or data.empty:
            continue
        for ticker in chunk:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in set(data.columns.get_level_values(0)):
                        continue
                    df = data[ticker].dropna(subset=["Close"]).copy()
                else:
                    df = data.dropna(subset=["Close"]).copy()
                if not df.empty:
                    frames[ticker] = df
            except Exception:
                continue
        time.sleep(0.15)
    return frames


def _return(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    current = _safe_float(close.iloc[-1])
    previous = _safe_float(close.iloc[-periods - 1])
    return ((current / previous) - 1.0) * 100.0 if previous > 0 else 0.0


def _volatility(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    returns = close.pct_change().tail(periods).dropna()
    return _safe_float(returns.std() * math.sqrt(252) * 100.0)


def _atr(df: pd.DataFrame, length: int = 14) -> float:
    if len(df) < length + 1:
        return 0.0
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return _safe_float(true_range.rolling(length).mean().iloc[-1])


def _linear_regression_score(close: pd.Series, periods: int = 60) -> tuple[float, float]:
    if len(close) < periods + 2:
        return 0.0, 0.0
    y = close.tail(periods).astype(float)
    y = y[y > 0]
    if len(y) < periods * 0.8:
        return 0.0, 0.0
    log_y = y.map(math.log).to_numpy()
    x = pd.Series(range(len(log_y)), dtype=float).to_numpy()
    x_mean = x.mean()
    y_mean = log_y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom <= 0:
        return 0.0, 0.0
    beta = float(((x - x_mean) * (log_y - y_mean)).sum() / denom)
    fitted = y_mean + beta * (x - x_mean)
    ss_res = float(((log_y - fitted) ** 2).sum())
    ss_tot = float(((log_y - y_mean) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    annualized_slope = (math.exp(beta * 252) - 1.0) * 100.0
    return annualized_slope, max(0.0, min(1.0, r2))


def _relative_strength(asset_close: pd.Series, bench_close: pd.Series, periods: int = 63) -> float:
    if asset_close.empty or bench_close.empty:
        return 0.0
    joined = pd.concat([asset_close.astype(float), bench_close.astype(float)], axis=1, join="inner").dropna()
    if len(joined) <= periods:
        return 0.0
    asset_ret = ((joined.iloc[-1, 0] / joined.iloc[-periods - 1, 0]) - 1.0) * 100.0
    bench_ret = ((joined.iloc[-1, 1] / joined.iloc[-periods - 1, 1]) - 1.0) * 100.0
    return _safe_float(asset_ret - bench_ret)


def _score_row(asset: dict[str, str], df: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> dict[str, Any] | None:
    if df.empty or len(df) < 90:
        return None
    close = df["Close"].astype(float).dropna()
    if close.empty:
        return None
    price = _safe_float(close.iloc[-1])
    mom21 = _return(close, 21)
    mom63 = _return(close, 63)
    mom126 = _return(close, 126)
    vol21 = _volatility(close, 21)
    vol63 = _volatility(close, 63)
    vol_base = max(vol63, 8.0)
    vol_adjusted = (0.45 * mom21 + 0.35 * mom63 + 0.20 * mom126) / vol_base
    slope60, r2 = _linear_regression_score(close, 60)
    acceleration = mom21 - _return(close.iloc[:-5], 21) if len(close) > 30 else 0.0
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1], price)
    ma50 = _safe_float(close.rolling(50).mean().iloc[-1], price)
    ma200 = _safe_float(close.rolling(200).mean().iloc[-1], ma50)
    atr14 = _atr(df)
    distance_ema20_atr = (price - ma20) / atr14 if atr14 > 0 else 0.0
    trend_structure = 0.0
    trend_structure += 20 if price > ma20 else -20
    trend_structure += 20 if price > ma50 else -20
    trend_structure += 20 if price > ma200 else -20
    trend_structure += 20 if ma20 > ma50 else -20
    trend_structure += 20 if ma50 > ma200 else -20

    volume_score = 0.0
    rvol20 = None
    if "Volume" in df.columns:
        vol = df["Volume"].astype(float)
        vol_avg = _safe_float(vol.tail(20).mean())
        last_vol = _safe_float(vol.iloc[-1])
        if vol_avg > 0 and last_vol > 0:
            rvol20 = last_vol / vol_avg
            volume_score = max(-30.0, min(30.0, (rvol20 - 1.0) * 35.0))

    benchmark_ticker = asset.get("benchmark", "")
    bench_df = frames.get(benchmark_ticker, pd.DataFrame())
    relative_strength = _relative_strength(close, bench_df.get("Close", pd.Series(dtype=float)), 63)

    multi_momentum = 0.45 * mom21 + 0.35 * mom63 + 0.20 * mom126
    raw_score = (
        0.30 * max(-100, min(100, multi_momentum * 2.4))
        + 0.20 * max(-100, min(100, vol_adjusted * 55))
        + 0.20 * max(-100, min(100, relative_strength * 3.0))
        + 0.15 * max(-100, min(100, acceleration * 7.0))
        + 0.10 * trend_structure
        + 0.05 * volume_score
    )
    stretch_penalty = max(0.0, abs(distance_ema20_atr) - 2.4) * 5.0
    volatility_penalty = max(0.0, vol63 - 65.0) * 0.12
    adjusted_score = max(-100.0, min(100.0, raw_score - math.copysign(stretch_penalty + volatility_penalty, raw_score)))

    if adjusted_score >= 70:
        regime = "Comprador extremo"
    elif adjusted_score >= 40:
        regime = "Comprador forte"
    elif adjusted_score >= 15:
        regime = "Comprador moderado"
    elif adjusted_score <= -70:
        regime = "Vendedor extremo"
    elif adjusted_score <= -40:
        regime = "Vendedor forte"
    elif adjusted_score <= -15:
        regime = "Vendedor moderado"
    else:
        regime = "Neutro/lateral"
    if adjusted_score > 35 and distance_ema20_atr > 2.8:
        regime = "Comprador esticado"
    elif adjusted_score < -35 and distance_ema20_atr < -2.8:
        regime = "Vendedor esticado"

    return {
        "symbol": asset["symbol"],
        "ticker": asset["ticker"],
        "name": asset["name"],
        "asset_class": asset["asset_class"],
        "price": round(price, 4),
        "daily_change": round(_return(close, 1), 2),
        "mom21": round(mom21, 2),
        "mom63": round(mom63, 2),
        "mom126": round(mom126, 2),
        "vol63": round(vol63, 2),
        "vol_adjusted": round(vol_adjusted, 2),
        "relative_strength": round(relative_strength, 2),
        "acceleration": round(acceleration, 2),
        "r2": round(r2, 2),
        "distance_ema20_atr": round(distance_ema20_atr, 2),
        "rvol20": round(rvol20, 2) if rvol20 is not None else None,
        "raw_score": round(raw_score, 1),
        "adjusted_score": round(adjusted_score, 1),
        "regime": regime,
        "updated_at": str(close.index[-1])[:19],
    }


def _class_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["asset_class"], []).append(row)
    out = []
    for asset_class, items in grouped.items():
        scores = [_safe_float(item.get("adjusted_score")) for item in items]
        median = sorted(scores)[len(scores) // 2] if scores else 0.0
        strong_buy = sum(1 for score in scores if score >= 40)
        strong_sell = sum(1 for score in scores if score <= -40)
        if median >= 25:
            regime = "Força compradora"
        elif median <= -25:
            regime = "Pressão vendedora"
        else:
            regime = "Seletivo/neutro"
        out.append({
            "asset_class": asset_class,
            "median_score": round(median, 1),
            "strong_buy": strong_buy,
            "strong_sell": strong_sell,
            "regime": regime,
            "count": len(items),
        })
    return sorted(out, key=lambda item: item["median_score"], reverse=True)


def build_global_momentum_screener(force_refresh: bool = False, max_age_seconds: int = CACHE_TTL_SECONDS) -> dict[str, Any]:
    if not force_refresh:
        cached = _read_cache(max_age_seconds=max_age_seconds)
        if cached:
            return cached

    tickers = [asset["ticker"] for asset in ASSET_UNIVERSE]
    tickers.extend(asset["benchmark"] for asset in ASSET_UNIVERSE if asset.get("benchmark"))
    frames = _download_history(tickers)
    rows = []
    failures = []
    for asset in ASSET_UNIVERSE:
        row = _score_row(asset, frames.get(asset["ticker"], pd.DataFrame()), frames)
        if row:
            rows.append(row)
        else:
            failures.append(asset["symbol"])

    top_buy = sorted(rows, key=lambda item: item["adjusted_score"], reverse=True)[:10]
    top_sell = sorted(rows, key=lambda item: item["adjusted_score"])[:10]
    classes = _class_summary(rows)
    median_score = 0.0
    if rows:
        scores = sorted(_safe_float(row["adjusted_score"]) for row in rows)
        median_score = scores[len(scores) // 2]
    pct_positive = (sum(1 for row in rows if row["adjusted_score"] > 15) / len(rows) * 100.0) if rows else 0.0
    pct_negative = (sum(1 for row in rows if row["adjusted_score"] < -15) / len(rows) * 100.0) if rows else 0.0
    if median_score >= 20 and pct_positive >= 55:
        global_regime = "Broad Risk-on"
    elif median_score > 5 and pct_positive > pct_negative:
        global_regime = "Selective Risk-on"
    elif median_score <= -20 and pct_negative >= 55:
        global_regime = "Broad Risk-off"
    elif median_score < -5 and pct_negative > pct_positive:
        global_regime = "Selective Risk-off"
    else:
        global_regime = "Neutro/seletivo"

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generated_ts": time.time(),
        "assets_loaded": len(rows),
        "failures": failures,
        "global_regime": global_regime,
        "median_score": round(median_score, 1),
        "pct_positive": round(pct_positive, 1),
        "pct_negative": round(pct_negative, 1),
        "class_summary": classes,
        "top_buy": top_buy,
        "top_sell": top_sell,
        "rows": sorted(rows, key=lambda item: item["adjusted_score"], reverse=True),
    }
    _write_cache(payload)
    return payload


if __name__ == "__main__":
    result = build_global_momentum_screener(force_refresh=True)
    print(json.dumps({
        "generated_at": result["generated_at"],
        "assets_loaded": result["assets_loaded"],
        "global_regime": result["global_regime"],
        "top_buy": [item["symbol"] for item in result["top_buy"][:5]],
        "top_sell": [item["symbol"] for item in result["top_sell"][:5]],
    }, ensure_ascii=False, indent=2))
