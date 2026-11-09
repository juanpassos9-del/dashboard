"""Consolidated public crypto quotes with Binance-first exchange fallbacks."""

from __future__ import annotations

import time
from typing import Any

from execution.crypto_common import request_json, safe_float

ASSETS = [
    "BTC", "ETH", "ZEC", "SOL", "JCT", "XRP", "HYPE", "1000PEPE", "DOGE", "NEAR",
    "BNB", "ON", "AVAX", "ENA", "SUI", "UNI", "WLD", "PUMP", "AIOT", "HOT",
]
PROVIDERS = ("Binance", "BingX", "OKX")
MAX_QUOTE_AGE_SECONDS = 180


def _binance_tickers() -> dict[str, dict[str, Any]]:
    rows, _ = request_json("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=10)
    result = {}
    for row in rows if isinstance(rows, list) else []:
        symbol = str(row.get("symbol") or "")
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            result[base] = {
                "price": safe_float(row.get("lastPrice")),
                "change_pct_24h": safe_float(row.get("priceChangePercent")),
                "quote_volume_24h": safe_float(row.get("quoteVolume")),
                "high_24h": safe_float(row.get("highPrice")),
                "low_24h": safe_float(row.get("lowPrice")),
                "timestamp_ms": int(safe_float(row.get("closeTime"))),
                "instrument": symbol,
            }
    return result


def _bingx_tickers() -> dict[str, dict[str, Any]]:
    data, _ = request_json("https://open-api.bingx.com/openApi/spot/v1/ticker/24hr", timeout=10)
    rows = data.get("data", []) if isinstance(data, dict) else []
    result = {}
    for row in rows if isinstance(rows, list) else []:
        symbol = str(row.get("symbol") or "")
        if symbol.endswith("-USDT"):
            base = symbol[:-5]
            result[base] = {
                "price": safe_float(row.get("lastPrice")),
                "change_pct_24h": safe_float(row.get("priceChangePercent")),
                "quote_volume_24h": safe_float(row.get("quoteVolume")),
                "high_24h": safe_float(row.get("highPrice")),
                "low_24h": safe_float(row.get("lowPrice")),
                "timestamp_ms": int(safe_float(row.get("closeTime") or row.get("time"))),
                "instrument": symbol,
            }
    return result


def _okx_tickers() -> dict[str, dict[str, Any]]:
    data, _ = request_json("https://www.okx.com/api/v5/market/tickers", params={"instType": "SPOT"}, timeout=10)
    rows = data.get("data", []) if isinstance(data, dict) else []
    result = {}
    for row in rows if isinstance(rows, list) else []:
        symbol = str(row.get("instId") or "")
        if symbol.endswith("-USDT"):
            base = symbol[:-5]
            last = safe_float(row.get("last"))
            open_24h = safe_float(row.get("open24h"))
            result[base] = {
                "price": last,
                "change_pct_24h": ((last / open_24h) - 1) * 100 if open_24h else 0.0,
                "quote_volume_24h": safe_float(row.get("volCcy24h")) * last,
                "high_24h": safe_float(row.get("high24h")),
                "low_24h": safe_float(row.get("low24h")),
                "timestamp_ms": int(safe_float(row.get("ts"))),
                "instrument": symbol,
            }
    return result


def fetch_cryptodash_quotes(assets: list[str] | None = None) -> dict[str, Any]:
    """Fetch each exchange in priority order and fill missing/stale quotes."""
    assets = [str(asset).upper() for asset in (assets or ASSETS)]
    loaders = (("Binance", _binance_tickers), ("BingX", _bingx_tickers), ("OKX", _okx_tickers))
    provider_data: dict[str, dict[str, dict[str, Any]]] = {}
    provider_errors: dict[str, str] = {}
    for provider, loader in loaders:
        try:
            provider_data[provider] = loader()
        except Exception as exc:
            provider_errors[provider] = str(exc)[:240]
            provider_data[provider] = {}

    now_ms = int(time.time() * 1000)
    quotes = []
    unsupported = []
    for asset in assets:
        selected = None
        for provider in PROVIDERS:
            item = provider_data[provider].get(asset)
            if not item or item.get("price", 0) <= 0:
                continue
            stamp = int(item.get("timestamp_ms") or 0)
            age = max(0, (now_ms - stamp) / 1000) if stamp else 0
            if stamp and age > MAX_QUOTE_AGE_SECONDS:
                continue
            selected = {
                "asset": asset,
                **item,
                "exchange": provider,
                "age_seconds": round(age) if stamp else None,
                "stale": False,
            }
            break
        if selected:
            quotes.append(selected)
        else:
            unsupported.append(asset)

    return {
        "quotes": quotes,
        "unsupported": unsupported,
        "provider_errors": provider_errors,
        "updated_at": time.time(),
        "providers": list(PROVIDERS),
    }
