"""BGeometrics Bitcoin on-chain snapshot provider."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

try:
    from execution.crypto_common import PROJECT_ROOT, load_cache, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import PROJECT_ROOT, load_cache, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

CACHE_NAME = "crypto_bgeometrics.json"
SOURCE = "BGeometrics"
SNAPSHOT_URL = "https://bitcoin-data.com/api/v1/snapshot"


def _read_env_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value

    try:
        import streamlit as st  # type: ignore

        secret_value = st.secrets.get(name, "") if hasattr(st, "secrets") else ""
        if secret_value:
            return str(secret_value).strip()
    except Exception:
        pass

    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return ""
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if not clean or clean.startswith("#") or "=" not in clean:
                    continue
                key, raw_value = clean.split("=", 1)
                if key.strip() == name:
                    return raw_value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _normalize_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": raw.get("date"),
        "btc_price": safe_float(raw.get("btcPrice")),
        "realized_price": safe_float(raw.get("realizedPrice")),
        "mvrv": safe_float(raw.get("mvrv")),
        "mvrv_z_score": safe_float(raw.get("mvrvZscore")),
        "fear_greed": safe_float(raw.get("fearGreed")),
        "hashrate": safe_float(raw.get("hashrate")),
        "active_addresses": safe_float(raw.get("activeAddresses")),
        "puell_multiple": safe_float(raw.get("puellMultiple")),
        "mayer_multiple": safe_float(raw.get("mayerMultiple")),
        "aviv": safe_float(raw.get("aviv")),
    }


def fetch_bgeometrics_snapshot(max_age_seconds: int = 21600, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch latest Bitcoin on-chain snapshot, using long cache to respect free-tier limits."""
    if not force_refresh:
        cached = load_cache(CACHE_NAME, max_age_seconds=max_age_seconds)
        if cached:
            mark_source("Crypto BGeometrics", "ok", rows=1, source=SOURCE, message="Snapshot em cache.")
            return cached

    api_key = _read_env_key("BGEOMETRICS_API_KEY")
    if not api_key:
        payload = stale_payload(CACHE_NAME, SOURCE, "BGEOMETRICS_API_KEY nao configurada.")
        payload["status"] = "disabled" if not payload.get("data") else payload.get("status", "stale")
        mark_source("Crypto BGeometrics", payload["status"], rows=0, source=SOURCE, message="Chave ausente.")
        return payload

    started = time.perf_counter()
    try:
        response = requests.get(
            SNAPSHOT_URL,
            timeout=15,
            headers={
                "User-Agent": "TTS-Crypto-Terminal/1.0",
                "X-API-KEY": api_key,
            },
        )
        response.raise_for_status()
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = response.json()
        data = _normalize_snapshot(raw if isinstance(raw, dict) else {})
        payload = {
            "source": SOURCE,
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency_ms,
            "data": data,
            "warnings": [],
        }
        save_cache(CACHE_NAME, payload)
        mark_source("Crypto BGeometrics", "ok", rows=1, source=SOURCE, message=f"MVRV snapshot carregado em {latency_ms}ms.")
        return payload
    except Exception as exc:
        warning = f"Falha BGeometrics: {exc}"
        payload = stale_payload(CACHE_NAME, SOURCE, warning)
        mark_source("Crypto BGeometrics", payload.get("status", "error"), rows=0, source=SOURCE, message=warning)
        return payload


if __name__ == "__main__":
    snapshot = fetch_bgeometrics_snapshot(force_refresh=True)
    print({k: snapshot.get(k) for k in ("source", "status", "updated_at", "warnings")})
    print(snapshot.get("data"))
