"""Binance public provider for the TTS Crypto Terminal."""

from __future__ import annotations

import time
from typing import Any

try:
    from execution.crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

BASE_URL = "https://api.binance.com"
FAPI_URL = "https://fapi.binance.com"
CACHE_NAME = "crypto_binance.json"

DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "SUIUSDT",
]


def _ticker_map(symbols: list[str]) -> tuple[dict[str, Any], int]:
    data, latency = request_json(f"{BASE_URL}/api/v3/ticker/24hr", timeout=10)
    wanted = set(symbols)
    out = {}
    for item in data if isinstance(data, list) else []:
        symbol = item.get("symbol")
        if symbol in wanted:
            last = safe_float(item.get("lastPrice"))
            quote_volume = safe_float(item.get("quoteVolume"))
            out[symbol] = {
                "symbol": symbol,
                "price": last,
                "change_pct_24h": safe_float(item.get("priceChangePercent")),
                "volume": safe_float(item.get("volume")),
                "quote_volume": quote_volume,
                "high_24h": safe_float(item.get("highPrice")),
                "low_24h": safe_float(item.get("lowPrice")),
                "vwap_24h": safe_float(item.get("weightedAvgPrice")),
                "trade_count": int(safe_float(item.get("count"))),
            }
    return out, latency


def _klines(symbol: str, interval: str = "1h", limit: int = 80) -> list[dict[str, Any]]:
    data, _ = request_json(
        f"{BASE_URL}/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=10,
    )
    rows = []
    for row in data if isinstance(data, list) else []:
        rows.append({
            "time": int(row[0] / 1000),
            "open": safe_float(row[1]),
            "high": safe_float(row[2]),
            "low": safe_float(row[3]),
            "close": safe_float(row[4]),
            "volume": safe_float(row[5]),
            "quote_volume": safe_float(row[7]),
        })
    return rows


def _futures_metrics(symbols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol in symbols:
        try:
            premium, _ = request_json(f"{FAPI_URL}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=8)
            oi, _ = request_json(f"{FAPI_URL}/fapi/v1/openInterest", params={"symbol": symbol}, timeout=8)
            out[symbol] = {
                "funding_rate": safe_float(premium.get("lastFundingRate")),
                "mark_price": safe_float(premium.get("markPrice")),
                "index_price": safe_float(premium.get("indexPrice")),
                "open_interest": safe_float(oi.get("openInterest")),
            }
            time.sleep(0.05)
        except Exception as exc:
            out[symbol] = {"warning": str(exc)}
    return out


def fetch_binance_crypto_snapshot(symbols: list[str] | None = None, save_file: bool = True) -> dict[str, Any]:
    symbols = symbols or DEFAULT_SYMBOLS
    try:
        tickers, ticker_latency = _ticker_map(symbols)
        futures = _futures_metrics([s for s in symbols if s.endswith("USDT")])
        assets = []
        for symbol in symbols:
            item = dict(tickers.get(symbol) or {"symbol": symbol})
            item.update(futures.get(symbol) or {})
            try:
                candles = _klines(symbol, "1h", 80)
            except Exception:
                candles = []
            item["candles_1h"] = candles
            if candles:
                first = candles[0]["close"] or item.get("price", 0)
                last = candles[-1]["close"] or item.get("price", 0)
                item["trend_80h_pct"] = ((last - first) / first * 100) if first else 0
            assets.append(item)
        payload = {
            "source": "Binance Public API",
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": ticker_latency,
            "data": {"assets": assets, "symbols": symbols},
            "warnings": [],
        }
        if save_file:
            save_cache(CACHE_NAME, payload)
        mark_source("Crypto Binance", "ok", rows=len(assets), message="Snapshot cripto carregado.", source="Binance")
        return payload
    except Exception as exc:
        warning = f"Binance indisponivel: {exc}"
        mark_source("Crypto Binance", "error", message=warning, source="Binance")
        return stale_payload(CACHE_NAME, "Binance Public API", warning)


if __name__ == "__main__":
    print(fetch_binance_crypto_snapshot())
