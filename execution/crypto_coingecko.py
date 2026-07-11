"""CoinGecko public provider for aggregate crypto data."""

from __future__ import annotations

import time
from typing import Any

try:
    from execution.crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

CACHE_NAME = "crypto_coingecko.json"
BASE_URL = "https://api.coingecko.com/api/v3"


def fetch_coingecko_crypto_snapshot(save_file: bool = True) -> dict[str, Any]:
    try:
        global_data, latency = request_json(f"{BASE_URL}/global", timeout=10)
        markets, latency_2 = request_json(
            f"{BASE_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 50,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d,30d",
            },
            timeout=10,
        )
        data = global_data.get("data", {}) if isinstance(global_data, dict) else {}
        payload = {
            "source": "CoinGecko Public API",
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency + latency_2,
            "data": {
                "total_market_cap_usd": safe_float((data.get("total_market_cap") or {}).get("usd")),
                "total_volume_usd": safe_float((data.get("total_volume") or {}).get("usd")),
                "market_cap_change_pct_24h": safe_float(data.get("market_cap_change_percentage_24h_usd")),
                "btc_dominance": safe_float((data.get("market_cap_percentage") or {}).get("btc")),
                "eth_dominance": safe_float((data.get("market_cap_percentage") or {}).get("eth")),
                "active_cryptocurrencies": data.get("active_cryptocurrencies"),
                "markets": markets if isinstance(markets, list) else [],
            },
            "warnings": [],
        }
        if save_file:
            save_cache(CACHE_NAME, payload)
        mark_source("Crypto CoinGecko", "ok", rows=len(payload["data"]["markets"]), message="Agregados cripto carregados.", source="CoinGecko")
        return payload
    except Exception as exc:
        warning = f"CoinGecko indisponivel: {exc}"
        mark_source("Crypto CoinGecko", "error", message=warning, source="CoinGecko")
        return stale_payload(CACHE_NAME, "CoinGecko Public API", warning)


if __name__ == "__main__":
    print(fetch_coingecko_crypto_snapshot())
