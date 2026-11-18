"""Intraday cross-asset candles from public BingX and Hyperliquid endpoints."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from execution.market_realtime import GLOBAL_REALTIME_MAP


WINDOW_HOURS = 24
SESSION_TIMEZONE = ZoneInfo("America/Sao_Paulo")
CANDLE_INTERVAL = "5m"
CANDLE_LIMIT = WINDOW_HOURS * 12
REQUEST_TIMEOUT_SECONDS = 10

INSTRUMENTS = (
    {"label": "S&P 500", "symbol": "^GSPC", "provider": "BingX", "kind": "price", "note": "Perpétuo sintético referenciado ao S&P 500."},
    {"label": "Nasdaq 100", "symbol": "^IXIC", "provider": "BingX", "kind": "price", "note": "Perpétuo sintético referenciado ao Nasdaq 100."},
    {"label": "Ouro", "symbol": "GC=F", "provider": "Hyperliquid", "kind": "price", "note": "Perpétuo sintético de ouro."},
    {"label": "Petróleo Brent", "symbol": "BZ=F", "provider": "Hyperliquid", "kind": "price", "note": "Perpétuo sintético referenciado ao Brent."},
    {"label": "DXY", "symbol": "DX-Y.NYB", "provider": "BingX", "kind": "price", "note": "Perpétuo sintético referenciado ao DXY."},
    {"label": "Treasury 2Y", "symbol": "FRED:DGS2", "provider": "Hyperliquid", "kind": "yield", "note": "Yield sintético em % a.a.; variação relativa exibida em %."},
    {"label": "Treasury 10Y", "symbol": "US10Y", "provider": "Hyperliquid", "kind": "yield", "note": "Yield sintético em % a.a.; variação relativa exibida em %."},
    {"label": "Treasury 30Y", "symbol": "US30Y", "provider": "Hyperliquid", "kind": "yield", "note": "Yield sintético em % a.a.; variação relativa exibida em %."},
)


def session_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the current Sao Paulo session open and current time in UTC."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    end_utc = now.astimezone(timezone.utc)
    start_local = now.astimezone(SESSION_TIMEZONE).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start_local.astimezone(timezone.utc), end_utc


def _mapping_for(spec: dict[str, str]) -> dict[str, str]:
    for provider, mapping in GLOBAL_REALTIME_MAP.get(spec["symbol"], ()):
        if provider == spec["provider"]:
            return mapping
    raise ValueError(f"Sem instrumento {spec['provider']} mapeado para {spec['label']}.")


def parse_hyperliquid_candles(payload: Any) -> pd.Series:
    if not isinstance(payload, list):
        raise ValueError("Resposta de candles da Hyperliquid não é uma lista.")
    rows = []
    for candle in payload:
        if not isinstance(candle, dict):
            continue
        try:
            timestamp = int(candle.get("t"))
            close = float(candle.get("c"))
        except (TypeError, ValueError, OverflowError):
            continue
        if timestamp > 0 and close > 0:
            rows.append((timestamp, close))
    return _rows_to_series(rows)


def parse_bingx_candles(payload: Any) -> pd.Series:
    if not isinstance(payload, dict) or int(payload.get("code", -1)) != 0:
        message = payload.get("msg") if isinstance(payload, dict) else "resposta inválida"
        raise ValueError(f"BingX retornou erro: {message or 'código não zero'}")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Resposta de candles da BingX sem lista de dados.")
    rows = []
    for candle in data:
        if not isinstance(candle, dict):
            continue
        try:
            timestamp = int(candle.get("time") or candle.get("timestamp"))
            close = float(candle.get("close"))
        except (TypeError, ValueError, OverflowError):
            continue
        if timestamp > 0 and close > 0:
            rows.append((timestamp, close))
    return _rows_to_series(rows)


def _rows_to_series(rows: list[tuple[int, float]]) -> pd.Series:
    if not rows:
        return pd.Series(dtype="float64")
    frame = pd.DataFrame(rows, columns=["timestamp_ms", "close"])
    frame = frame.drop_duplicates("timestamp_ms", keep="last").sort_values("timestamp_ms")
    index = pd.to_datetime(frame.pop("timestamp_ms"), unit="ms", utc=True)
    return pd.Series(frame["close"].to_numpy(dtype=float), index=index)


def _fetch_one(spec: dict[str, str], start_ms: int, end_ms: int) -> tuple[str, pd.Series]:
    mapping = _mapping_for(spec)
    if spec["provider"] == "Hyperliquid":
        response = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={
                "type": "candleSnapshot",
                "req": {
                    "coin": mapping["instrument"],
                    "interval": CANDLE_INTERVAL,
                    "startTime": start_ms,
                    "endTime": end_ms,
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        candles = parse_hyperliquid_candles(response.json())
    elif spec["provider"] == "BingX":
        response = requests.get(
            "https://open-api.bingx.com/openApi/swap/v3/quote/klines",
            params={
                "symbol": mapping["instrument"],
                "interval": CANDLE_INTERVAL,
                "limit": CANDLE_LIMIT,
                "startTime": start_ms,
                "endTime": end_ms,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        candles = parse_bingx_candles(response.json())
    else:
        raise ValueError(f"Fonte não suportada: {spec['provider']}")
    if candles.empty:
        raise ValueError("A fonte não retornou candles desde a abertura da sessão.")
    return spec["label"], candles


def fetch_intraday_candles(now: datetime | None = None) -> dict[str, Any]:
    """Fetch 5-minute closes from the Sao Paulo midnight session open."""
    start_utc, end_utc = session_window(now)
    end_ms = int(end_utc.timestamp() * 1000)
    start_ms = int(start_utc.timestamp() * 1000)
    series_by_label: dict[str, pd.Series] = {}
    sources: dict[str, dict[str, str]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=len(INSTRUMENTS)) as pool:
        futures = {
            pool.submit(_fetch_one, spec, start_ms, end_ms): spec
            for spec in INSTRUMENTS
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                label, series = future.result()
                series_by_label[label] = series
                sources[label] = {
                    "provider": spec["provider"],
                    "instrument": _mapping_for(spec)["instrument"],
                    "kind": spec["kind"],
                    "note": spec["note"],
                }
            except Exception as exc:
                errors[spec["label"]] = f"{type(exc).__name__}: {str(exc)[:180]}"

    candles = pd.DataFrame(series_by_label).sort_index()
    if not candles.empty:
        candles = candles.loc[candles.index >= pd.Timestamp(start_ms, unit="ms", tz="UTC")]
    return {
        "candles": candles,
        "sources": sources,
        "errors": errors,
        "window_start": start_utc.astimezone(SESSION_TIMEZONE).isoformat(),
        "window_end": end_utc.astimezone(SESSION_TIMEZONE).isoformat(),
    }


def apply_latest_websocket_ticks(
    candles: pd.DataFrame,
    latest_quotes: dict[tuple[str, str, str], dict[str, Any]],
    *,
    now_seconds: float | None = None,
    max_age_seconds: int = 20,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Append only fresh exchange ticks to the candle series; do not synthesize history."""
    now_seconds = datetime.now(timezone.utc).timestamp() if now_seconds is None else now_seconds
    result = candles.copy()
    tick_ages: dict[str, int] = {}
    tick_rows: dict[pd.Timestamp, dict[str, float]] = {}
    for spec in INSTRUMENTS:
        try:
            mapping = _mapping_for(spec)
        except ValueError:
            continue
        quote = latest_quotes.get((spec["provider"], mapping["asset"], mapping["market_type"]))
        if not quote:
            continue
        try:
            received_at = float(quote.get("received_at"))
            price = float(quote.get("price"))
        except (TypeError, ValueError, OverflowError):
            continue
        age = max(0.0, now_seconds - received_at)
        if age > max_age_seconds or price <= 0 or spec["label"] not in result.columns:
            continue
        # Exchange candle indices may use millisecond precision (not nanoseconds).
        stamp = pd.Timestamp(int(round(received_at * 1000)), unit="ms", tz="UTC")
        tick_rows.setdefault(stamp, {})[spec["label"]] = price
        tick_ages[spec["label"]] = int(age)
    if tick_rows:
        tick_frame = pd.DataFrame.from_dict(tick_rows, orient="index")
        tick_frame.index = pd.DatetimeIndex(tick_frame.index)
        result = pd.concat([result, tick_frame], axis=0).sort_index()
        result = result.groupby(level=0, sort=True).last()
    return result.sort_index(), tick_ages


def normalize_performance(candles: pd.DataFrame) -> pd.DataFrame:
    """Normalize price returns and relative yield changes to percent from each base."""
    if candles is None or candles.empty:
        return pd.DataFrame()
    frame = candles.sort_index().ffill(limit=3)
    normalized = pd.DataFrame(index=frame.index)
    specs = {spec["label"]: spec for spec in INSTRUMENTS}
    for label in frame.columns:
        values = pd.to_numeric(frame[label], errors="coerce")
        valid = values.dropna()
        if len(valid) < 2 or valid.iloc[0] == 0:
            continue
        if specs.get(label, {}).get("kind") == "yield":
            normalized[label] = (values / float(valid.iloc[0]) - 1.0) * 100.0
        else:
            normalized[label] = (values / float(valid.iloc[0]) - 1.0) * 100.0
    return normalized
