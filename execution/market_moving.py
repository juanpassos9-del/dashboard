"""Market Moving event detector.

Builds market-moving news cards by matching high-impact headlines to proxy
assets and measuring the intraday move after the headline timestamp.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

BR_TZ = ZoneInfo("America/Sao_Paulo")

ASSET_RULES = [
    {
        "tags": ["Energy", "Oil", "Geopolitics"],
        "keywords": ["oil", "crude", "brent", "wti", "opec", "hormuz", "iran", "israel", "strait", "tanker"],
        "assets": [
            {"symbol": "WTI", "label": "WTI Crude Oil", "ticker": "CL=F"},
            {"symbol": "BRENT", "label": "Brent Oil", "ticker": "BZ=F"},
            {"symbol": "XLE", "label": "Energy ETF", "ticker": "XLE"},
        ],
    },
    {
        "tags": ["Rates", "USD", "US Bonds"],
        "keywords": ["fed", "fomc", "powell", "treasury", "treasuries", "yield", "rate", "inflation", "cpi", "pce", "ppi"],
        "assets": [
            {"symbol": "DXY", "label": "DXY", "ticker": "DX-Y.NYB"},
            {"symbol": "SPX", "label": "S&P 500", "ticker": "^GSPC"},
            {"symbol": "GOLD", "label": "Gold", "ticker": "GC=F"},
        ],
    },
    {
        "tags": ["US Indexes", "Risk"],
        "keywords": ["s&p", "spx", "nasdaq", "dow", "stocks", "futures", "risk", "tariff", "trump"],
        "assets": [
            {"symbol": "SPX", "label": "S&P 500", "ticker": "^GSPC"},
            {"symbol": "NASDAQ", "label": "Nasdaq", "ticker": "^IXIC"},
            {"symbol": "DXY", "label": "DXY", "ticker": "DX-Y.NYB"},
        ],
    },
    {
        "tags": ["Crypto", "Liquidity"],
        "keywords": ["bitcoin", "btc", "ethereum", "crypto", "etf"],
        "assets": [
            {"symbol": "BTC", "label": "Bitcoin", "ticker": "BTC-USD"},
            {"symbol": "ETH", "label": "Ethereum", "ticker": "ETH-USD"},
            {"symbol": "NASDAQ", "label": "Nasdaq", "ticker": "^IXIC"},
        ],
    },
    {
        "tags": ["Brazil", "FX"],
        "keywords": ["brazil", "brasil", "real", "ibovespa", "bcb", "copom", "selic"],
        "assets": [
            {"symbol": "IBOV", "label": "Ibovespa", "ticker": "^BVSP"},
            {"symbol": "USDBRL", "label": "USD/BRL", "ticker": "BRL=X"},
            {"symbol": "EWZ", "label": "Brazil ETF", "ticker": "EWZ"},
        ],
    },
]

FALLBACK_24H_ASSETS = [
    {"symbol": "BTC", "label": "Bitcoin 24/7 Risk Proxy", "ticker": "BTC-USD"},
    {"symbol": "ETH", "label": "Ethereum 24/7 Risk Proxy", "ticker": "ETH-USD"},
]


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title_en") or item.get("title") or item.get("title_pt") or "").strip()


def _summary(item: dict[str, Any]) -> str:
    return str(item.get("summary") or item.get("description") or "").strip()


def _event_dt(item: dict[str, Any]) -> datetime | None:
    ts = item.get("timestamp")
    try:
        if ts:
            value = float(ts)
            if value > 10_000_000_000:
                value = value / 1000
            return datetime.fromtimestamp(value, timezone.utc)
    except Exception:
        pass
    for key in ["published_at", "published", "datetime", "time_br"]:
        raw = item.get(key)
        if not raw:
            continue
        try:
            parsed = pd.to_datetime(raw)
            if pd.notna(parsed):
                dt = parsed.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=BR_TZ)
                return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _event_timestamp_for_index(event_dt: datetime, idx: pd.Index) -> pd.Timestamp:
    """Convert the news instant to the candle index timezone without changing the instant."""
    event_ts = pd.Timestamp(event_dt)
    if event_ts.tzinfo is None:
        event_ts = event_ts.tz_localize("UTC")
    idx_tz = getattr(idx, "tz", None)
    if idx_tz is not None:
        return event_ts.tz_convert(idx_tz)
    return event_ts.tz_convert("UTC").tz_localize(None)


def _display_dt_br(event_dt: datetime) -> datetime:
    event_ts = pd.Timestamp(event_dt)
    if event_ts.tzinfo is None:
        event_ts = event_ts.tz_localize("UTC")
    return event_ts.tz_convert(BR_TZ).to_pydatetime()


def impact_score(item: dict[str, Any]) -> tuple[str, int]:
    text = f"{_title(item)} {_summary(item)} {item.get('source', '')}".lower()
    score = 0
    rules = [
        (5, ["fed", "fomc", "powell", "interest rate", "treasury", "yields"]),
        (5, ["cpi", "pce", "ppi", "inflation", "payroll", "jobs", "gdp", "ism", "pmi"]),
        (8, ["iran", "israel", "war", "strike", "strikes", "attack", "missile", "military", "sanction", "hormuz"]),
        (4, ["oil", "crude", "brent", "wti", "opec", "dxy", "dollar"]),
        (3, ["s&p", "nasdaq", "dow", "bitcoin", "crypto", "ibovespa", "brazil"]),
    ]
    for weight, keywords in rules:
        if any(keyword in text for keyword in keywords):
            score += weight
    if any(word in text for word in ["breaking", "urgent", "alert", "unexpected", "surprise"]):
        score += 3
    if score >= 12:
        return "URGENTE", score
    if score >= 8:
        return "ALTO IMPACTO", score
    return "MEDIO", score


def infer_assets(item: dict[str, Any], limit: int = 3) -> tuple[list[dict[str, str]], list[str]]:
    text = f"{_title(item)} {_summary(item)}".lower()
    selected: list[dict[str, str]] = []
    tags: list[str] = []
    for rule in ASSET_RULES:
        if any(keyword in text for keyword in rule["keywords"]):
            tags.extend(rule["tags"])
            for asset in rule["assets"]:
                if asset["ticker"] not in {a["ticker"] for a in selected}:
                    selected.append(asset)
    if not selected:
        selected = [
            {"symbol": "SPX", "label": "S&P 500", "ticker": "^GSPC"},
            {"symbol": "DXY", "label": "DXY", "ticker": "DX-Y.NYB"},
        ]
        tags.append("Macro")
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)
    return selected[:limit], unique_tags[:5]


def _download_intraday(ticker: str) -> pd.DataFrame:
    for attempt in range(2):
        try:
            df = yf.download(
                ticker,
                period="5d",
                interval="1m",
                progress=False,
                auto_adjust=False,
                prepost=True,
                threads=False,
                timeout=12,
            )
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df.dropna(subset=["Close"]).copy()
        except Exception:
            time.sleep(0.5 + attempt)
    return pd.DataFrame()


def _candles_around_event(df: pd.DataFrame, event_dt: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    idx = df.index
    event_ts = _event_timestamp_for_index(event_dt, idx)
    start = event_ts - pd.Timedelta(minutes=30)
    end = event_ts + pd.Timedelta(minutes=180)
    sliced = df.loc[(idx >= start) & (idx <= end)].copy()
    if sliced.empty:
        return pd.DataFrame()
    return sliced


def _resample_5m(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    try:
        out = df.resample("5min").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
        })
        if "Volume" in df.columns:
            out["Volume"] = df["Volume"].resample("5min").sum()
        return out.dropna(subset=["Open", "High", "Low", "Close"])
    except Exception:
        return df


def _serialize_candles(df: pd.DataFrame) -> list[dict[str, Any]]:
    candles = []
    for ts, row in df.iterrows():
        try:
            timestamp = int(pd.Timestamp(ts).timestamp())
            candles.append({
                "time": timestamp,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            })
        except Exception:
            continue
    return candles


def _reaction_metrics(df: pd.DataFrame, event_dt: datetime) -> dict[str, Any]:
    if df.empty:
        return {}
    idx = df.index
    event_ts = _event_timestamp_for_index(event_dt, idx)
    after = df.loc[idx >= event_ts].copy()
    before = df.loc[idx <= event_ts].copy()
    if after.empty or before.empty:
        return {}
    base = float(after["Close"].iloc[0])
    if not math.isfinite(base) or base <= 0:
        return {}

    def ret_after(minutes: int) -> float | None:
        target = event_ts + pd.Timedelta(minutes=minutes)
        window = df.loc[idx <= target]
        if window.empty:
            return None
        return ((float(window["Close"].iloc[-1]) / base) - 1) * 100

    high_after = float(after["High"].head(60).max())
    low_after = float(after["Low"].head(60).min())
    return {
        "base": round(base, 4),
        "ret_5m": None if ret_after(5) is None else round(ret_after(5), 2),
        "ret_15m": None if ret_after(15) is None else round(ret_after(15), 2),
        "ret_30m": None if ret_after(30) is None else round(ret_after(30), 2),
        "max_60m": round(((high_after / base) - 1) * 100, 2),
        "min_60m": round(((low_after / base) - 1) * 100, 2),
    }


def build_market_moving_events(news_items: list[dict[str, Any]], max_events: int = 6) -> list[dict[str, Any]]:
    candidates = []
    for item in news_items or []:
        label, score = impact_score(item)
        if score < 8:
            continue
        event_dt = _event_dt(item)
        if not event_dt:
            continue
        assets, tags = infer_assets(item)
        candidates.append((score, event_dt, item, label, assets, tags))
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)

    events = []
    for score, event_dt, item, label, assets, tags in candidates[:max_events]:
        charts = []
        display_dt = _display_dt_br(event_dt)
        tried_tickers: set[str] = set()

        def append_chart(asset: dict[str, str], is_fallback: bool = False) -> None:
            if asset["ticker"] in tried_tickers:
                return
            tried_tickers.add(asset["ticker"])
            df = _download_intraday(asset["ticker"])
            window = _candles_around_event(df, event_dt)
            window_5m = _resample_5m(window)
            candles = _serialize_candles(window_5m)
            if not candles:
                return
            label_text = asset["label"]
            if is_fallback and "Proxy" not in label_text:
                label_text = f"{label_text} 24/7 Proxy"
            charts.append({
                **asset,
                "label": label_text,
                "candles": candles,
                "event_time": int(pd.Timestamp(event_dt).timestamp()),
                "timeframe": "5m",
                "metrics": _reaction_metrics(window_5m, event_dt),
            })

        for asset in assets:
            append_chart(asset)
        if not charts:
            for asset in FALLBACK_24H_ASSETS:
                append_chart(asset, is_fallback=True)
        events.append({
            "title": _title(item),
            "source": item.get("source") or "",
            "impact": label,
            "impact_score": score,
            "event_dt": display_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "event_time_label": display_dt.strftime("%H:%M"),
            "tags": tags,
            "charts": charts,
        })
    return events
