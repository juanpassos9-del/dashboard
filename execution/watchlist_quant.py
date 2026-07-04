"""Deterministic quant screening for the WATCHLIST QUANT page.

The module reuses the dashboard/watchlist universe and builds simple,
explainable quant screens: momentum, mean reversion and pairs/stat-arb.
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf

from execution.watchlist_ai import ASSET_GROUPS


def _safe_float(value, default=0.0) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def _asset_universe(limit_per_block: int = 12) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for block, group in ASSET_GROUPS.items():
        for symbol, meta in list(group.get("assets", {}).items())[:limit_per_block]:
            rows.append({
                "symbol": symbol,
                "ticker": meta["ticker"],
                "block": block,
                "sector": meta.get("sector", block),
                "driver": meta.get("driver", ""),
            })
    return rows


def _download_history(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    unique = sorted(set(tickers))
    for start in range(0, len(unique), 8):
        chunk = unique[start:start + 8]
        data = pd.DataFrame()
        for attempt in range(2):
            try:
                data = yf.download(
                    chunk,
                    period=period,
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    auto_adjust=False,
                    threads=False,
                    timeout=18,
                )
                if data is not None and not data.empty:
                    break
            except Exception:
                time.sleep(0.8 + attempt)
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
        time.sleep(0.25)
    return frames


def _ret(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    prev = _safe_float(close.iloc[-periods - 1], 0.0)
    last = _safe_float(close.iloc[-1], 0.0)
    return ((last / prev) - 1) * 100 if prev > 0 else 0.0


def _atr(df: pd.DataFrame, length: int = 14) -> float:
    if len(df) < length + 1:
        return 0.0
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return _safe_float(tr.rolling(length).mean().iloc[-1], 0.0)


def _snapshot(asset: dict[str, str], df: pd.DataFrame) -> dict[str, Any] | None:
    if df.empty or len(df) < 80:
        return None
    close = df["Close"].astype(float)
    price = _safe_float(close.iloc[-1])
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1])
    ma50 = _safe_float(close.rolling(50).mean().iloc[-1])
    ma200 = _safe_float(close.rolling(200).mean().iloc[-1], ma50)
    ret20 = _ret(close, 20)
    ret60 = _ret(close, 60)
    ret120 = _ret(close, 120)
    vol20 = _safe_float(close.pct_change().tail(20).std() * math.sqrt(252) * 100, 0.0)
    atr14 = _atr(df)
    z20 = 0.0
    std20 = _safe_float(close.tail(20).std(), 0.0)
    if std20 > 0:
        z20 = (price - ma20) / std20
    return {
        **asset,
        "price": price,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "ret20": ret20,
        "ret60": ret60,
        "ret120": ret120,
        "vol20": vol20,
        "atr14": atr14,
        "z20": z20,
        "support": _safe_float(df["Low"].astype(float).tail(20).min(), price),
        "resistance": _safe_float(df["High"].astype(float).tail(20).max(), price),
    }


def _momentum_signal(s: dict[str, Any]) -> dict[str, Any]:
    up = s["price"] > s["ma50"] and s["ma20"] >= s["ma50"]
    down = s["price"] < s["ma50"] and s["ma20"] <= s["ma50"]
    raw = 50 + s["ret20"] * 1.2 + s["ret60"] * 0.65 + (8 if up else -8 if down else 0)
    score = max(0, min(100, raw - max(0, s["vol20"] - 45) * 0.18))
    direction = "compra" if score >= 55 else "venda"
    if direction == "venda":
        entry = max(s["price"], s["ma20"])
        stop = max(s["resistance"], entry + s["atr14"] * 2.0)
        target = entry - s["atr14"] * 3.0
    else:
        entry = min(s["price"], s["ma20"])
        stop = min(s["support"], entry - s["atr14"] * 2.0)
        target = entry + s["atr14"] * 3.0
    return {
        **s,
        "strategy": "Momentum",
        "direction": direction,
        "score": round(score, 1),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "setup": "tendencia persistente" if direction == "compra" else "tendencia baixista persistente",
    }


def _mean_reversion_signal(s: dict[str, Any]) -> dict[str, Any] | None:
    if abs(s["z20"]) < 1.35:
        return None
    direction = "venda" if s["z20"] > 1.35 else "compra"
    score = min(100, 55 + abs(s["z20"]) * 14 + max(0, 35 - s["vol20"]) * 0.25)
    entry = s["price"]
    if direction == "venda":
        stop = entry + max(s["atr14"] * 1.6, abs(entry - s["ma20"]) * 0.65)
        target = s["ma20"]
    else:
        stop = entry - max(s["atr14"] * 1.6, abs(entry - s["ma20"]) * 0.65)
        target = s["ma20"]
    return {
        **s,
        "strategy": "Mean Reversion",
        "direction": direction,
        "score": round(score, 1),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "setup": f"z-score 20d {s['z20']:.2f}; retorno esperado ate media 20",
    }


def _event_driven_signal(s: dict[str, Any]) -> dict[str, Any] | None:
    impulse = abs(s["ret20"])
    if impulse < 4.0 and abs(s["z20"]) < 1.1:
        return None
    direction = "compra" if s["ret20"] > 0 and s["price"] >= s["ma20"] else "venda"
    score = min(100, 48 + impulse * 2.1 + abs(s["z20"]) * 8 + min(s["vol20"], 80) * 0.12)
    entry = s["price"]
    risk = max(s["atr14"] * 1.8, entry * 0.025)
    if direction == "venda":
        stop = entry + risk
        target = entry - risk * 1.8
    else:
        stop = entry - risk
        target = entry + risk * 1.8
    return {
        **s,
        "strategy": "Event-driven",
        "direction": direction,
        "score": round(score, 1),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "setup": f"impulso 20d {s['ret20']:.2f}% com z-score {s['z20']:.2f}; monitorar continuidade pos-catalisador",
    }


def _volatility_signal(s: dict[str, Any]) -> dict[str, Any] | None:
    if s["vol20"] <= 0 or s["atr14"] <= 0:
        return None
    compression = s["vol20"] < 24 and abs(s["z20"]) < 1.0
    expansion = s["vol20"] >= 38 and abs(s["z20"]) >= 1.0
    if not compression and not expansion:
        return None
    direction = "breakout" if compression else ("compra volatilidade" if s["z20"] < 0 else "venda volatilidade")
    score = 58 + (24 - s["vol20"]) * 0.9 if compression else 54 + min(s["vol20"], 90) * 0.38 + abs(s["z20"]) * 6
    entry = s["price"]
    stop = entry - s["atr14"] * 1.5 if direction != "venda volatilidade" else entry + s["atr14"] * 1.5
    target = entry + s["atr14"] * 2.4 if direction != "venda volatilidade" else entry - s["atr14"] * 2.4
    return {
        **s,
        "strategy": "Volatility",
        "direction": direction,
        "score": round(max(0, min(100, score)), 1),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "setup": "compressao de volatilidade; aguardar rompimento" if compression else "expansao de volatilidade; operar com stop mais curto",
    }


def _crypto_quant_signal(s: dict[str, Any]) -> dict[str, Any] | None:
    block = str(s.get("block", "")).lower()
    sector = str(s.get("sector", "")).lower()
    ticker = str(s.get("ticker", "")).upper()
    if not any(token in f"{block} {sector} {ticker}" for token in ["cripto", "crypto", "btc", "eth", "sol", "usdt"]):
        return None
    trend_bias = s["ret20"] * 1.4 + s["ret60"] * 0.7
    direction = "compra" if trend_bias >= 0 else "venda"
    score = min(100, 52 + abs(trend_bias) * 0.9 + abs(s["z20"]) * 6 + min(s["vol20"], 120) * 0.08)
    entry = s["price"]
    risk = max(s["atr14"] * 2.1, entry * 0.035)
    if direction == "venda":
        stop = entry + risk
        target = entry - risk * 2.0
    else:
        stop = entry - risk
        target = entry + risk * 2.0
    return {
        **s,
        "strategy": "Crypto Quant",
        "direction": direction,
        "score": round(score, 1),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "setup": f"cripto beta; ret20 {s['ret20']:.2f}% ret60 {s['ret60']:.2f}% vol20 {s['vol20']:.2f}%",
    }


def _pairs_signals(universe: list[dict[str, str]], frames: dict[str, pd.DataFrame], max_pairs: int = 12) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    by_ticker = {item["ticker"]: item for item in universe}
    tickers = list(frames.keys())
    closes = {}
    for ticker in tickers:
        close = frames[ticker]["Close"].astype(float).tail(160)
        if len(close) >= 80:
            closes[ticker] = close
    for i, a in enumerate(list(closes.keys())):
        for b in list(closes.keys())[i + 1:]:
            if by_ticker.get(a, {}).get("block") != by_ticker.get(b, {}).get("block"):
                continue
            joined = pd.concat([closes[a], closes[b]], axis=1).dropna()
            if len(joined) < 80:
                continue
            joined.columns = ["a", "b"]
            corr = _safe_float(joined["a"].pct_change().corr(joined["b"].pct_change()), 0.0)
            if corr < 0.72:
                continue
            ratio = joined["a"] / joined["b"]
            mean = _safe_float(ratio.tail(80).mean(), 0.0)
            std = _safe_float(ratio.tail(80).std(), 0.0)
            if std <= 0:
                continue
            z = _safe_float((ratio.iloc[-1] - mean) / std, 0.0)
            if abs(z) < 1.45:
                continue
            long_ticker, short_ticker = (b, a) if z > 0 else (a, b)
            score = min(100, 50 + corr * 25 + abs(z) * 12)
            signals.append({
                "strategy": "Pairs/StatArb",
                "pair": f"{by_ticker[a]['symbol']} / {by_ticker[b]['symbol']}",
                "block": by_ticker[a]["block"],
                "long": by_ticker[long_ticker]["symbol"],
                "short": by_ticker[short_ticker]["symbol"],
                "corr": round(corr, 2),
                "zscore": round(z, 2),
                "score": round(score, 1),
                "setup": "spread acima da media" if z > 0 else "spread abaixo da media",
            })
    return sorted(signals, key=lambda row: row["score"], reverse=True)[:max_pairs]


def build_watchlist_quant(global_data: dict | None = None, max_items: int = 12) -> dict[str, Any]:
    del global_data
    universe = _asset_universe()
    frames = _download_history([item["ticker"] for item in universe])
    snapshots = []
    for item in universe:
        snap = _snapshot(item, frames.get(item["ticker"], pd.DataFrame()))
        if snap:
            snapshots.append(snap)

    momentum = sorted((_momentum_signal(s) for s in snapshots), key=lambda row: row["score"], reverse=True)[:max_items]
    mean_reversion = sorted(
        [signal for signal in (_mean_reversion_signal(s) for s in snapshots) if signal],
        key=lambda row: row["score"],
        reverse=True,
    )[:max_items]
    pairs = _pairs_signals(universe, frames, max_pairs=max_items)
    event_driven = sorted(
        [signal for signal in (_event_driven_signal(s) for s in snapshots) if signal],
        key=lambda row: row["score"],
        reverse=True,
    )[:max_items]
    volatility = sorted(
        [signal for signal in (_volatility_signal(s) for s in snapshots) if signal],
        key=lambda row: row["score"],
        reverse=True,
    )[:max_items]
    crypto_quant = sorted(
        [signal for signal in (_crypto_quant_signal(s) for s in snapshots) if signal],
        key=lambda row: row["score"],
        reverse=True,
    )[:max_items]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assets_loaded": len(snapshots),
        "momentum": momentum,
        "mean_reversion": mean_reversion,
        "pairs": pairs,
        "event_driven": event_driven,
        "volatility": volatility,
        "crypto_quant": crypto_quant,
        "summary": {
            "top_momentum": momentum[0]["symbol"] if momentum else "---",
            "top_reversion": mean_reversion[0]["symbol"] if mean_reversion else "---",
            "top_pair": pairs[0]["pair"] if pairs else "---",
            "top_event": event_driven[0]["symbol"] if event_driven else "---",
            "top_volatility": volatility[0]["symbol"] if volatility else "---",
            "top_crypto": crypto_quant[0]["symbol"] if crypto_quant else "---",
        },
    }
