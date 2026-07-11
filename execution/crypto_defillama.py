"""DefiLlama provider for TVL and stablecoin liquidity."""

from __future__ import annotations

import time

try:
    from execution.crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

CACHE_NAME = "crypto_defillama.json"


def fetch_defillama_crypto_snapshot(save_file: bool = True) -> dict:
    try:
        chains, latency = request_json("https://api.llama.fi/v2/chains", timeout=12)
        stablecoins, latency_2 = request_json("https://stablecoins.llama.fi/stablecoins", timeout=12)
        chain_rows = chains if isinstance(chains, list) else []
        stable_rows = stablecoins.get("peggedAssets", []) if isinstance(stablecoins, dict) else []
        total_tvl = sum(safe_float(row.get("tvl")) for row in chain_rows)
        stable_mcap = 0.0
        for asset in stable_rows:
            stable_mcap += safe_float((asset.get("circulating") or {}).get("peggedUSD"))
        payload = {
            "source": "DefiLlama Public API",
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency + latency_2,
            "data": {
                "total_tvl_usd": total_tvl,
                "top_chains": sorted(chain_rows, key=lambda r: safe_float(r.get("tvl")), reverse=True)[:12],
                "stablecoin_market_cap_usd": stable_mcap,
                "stablecoins": sorted(stable_rows, key=lambda r: safe_float((r.get("circulating") or {}).get("peggedUSD")), reverse=True)[:20],
            },
            "warnings": [],
        }
        if save_file:
            save_cache(CACHE_NAME, payload)
        mark_source("Crypto DefiLlama", "ok", rows=len(chain_rows), message="TVL/stablecoins carregados.", source="DefiLlama")
        return payload
    except Exception as exc:
        warning = f"DefiLlama indisponivel: {exc}"
        mark_source("Crypto DefiLlama", "error", message=warning, source="DefiLlama")
        return stale_payload(CACHE_NAME, "DefiLlama Public API", warning)


if __name__ == "__main__":
    print(fetch_defillama_crypto_snapshot())
