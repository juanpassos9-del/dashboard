"""Alternative.me Fear & Greed provider."""

from __future__ import annotations

import time

try:
    from execution.crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import request_json, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

CACHE_NAME = "crypto_fear_greed.json"
URL = "https://api.alternative.me/fng/"


def fetch_fear_greed_snapshot(save_file: bool = True) -> dict:
    try:
        data, latency = request_json(URL, params={"limit": 60, "format": "json"}, timeout=10)
        rows = data.get("data", []) if isinstance(data, dict) else []
        values = [safe_float(item.get("value")) for item in rows]
        current = rows[0] if rows else {}
        avg_7 = sum(values[:7]) / len(values[:7]) if values[:7] else 0
        avg_30 = sum(values[:30]) / len(values[:30]) if values[:30] else 0
        payload = {
            "source": "Alternative.me Fear & Greed",
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency,
            "data": {
                "current": {
                    "value": safe_float(current.get("value")),
                    "classification": current.get("value_classification", "---"),
                    "timestamp": current.get("timestamp"),
                },
                "avg_7": round(avg_7, 2),
                "avg_30": round(avg_30, 2),
                "history": rows,
            },
            "warnings": [],
        }
        if save_file:
            save_cache(CACHE_NAME, payload)
        mark_source("Crypto Fear Greed", "ok", rows=len(rows), message="Fear & Greed carregado.", source="Alternative.me")
        return payload
    except Exception as exc:
        warning = f"Fear & Greed indisponivel: {exc}"
        mark_source("Crypto Fear Greed", "error", message=warning, source="Alternative.me")
        return stale_payload(CACHE_NAME, "Alternative.me Fear & Greed", warning)


if __name__ == "__main__":
    print(fetch_fear_greed_snapshot())
