"""Shared helpers for the TTS Crypto Terminal providers."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, ".tmp")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path(name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


def load_cache(name: str, max_age_seconds: int | None = None) -> dict[str, Any] | None:
    path = cache_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if max_age_seconds is not None:
            age = time.time() - float(payload.get("updated_ts") or 0)
            if age > max_age_seconds:
                return None
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def save_cache(name: str, payload: dict[str, Any]) -> None:
    payload.setdefault("updated_at", utc_now_iso())
    payload.setdefault("updated_ts", time.time())
    with open(cache_path(name), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def request_json(url: str, *, params: dict[str, Any] | None = None, timeout: int = 10) -> tuple[Any, int]:
    started = time.perf_counter()
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "TTS-Crypto-Terminal/1.0"},
    )
    response.raise_for_status()
    latency_ms = int((time.perf_counter() - started) * 1000)
    return response.json(), latency_ms


def stale_payload(cache_name: str, source: str, warning: str) -> dict[str, Any]:
    cached = load_cache(cache_name)
    if cached:
        cached = dict(cached)
        cached["status"] = "stale"
        cached.setdefault("warnings", [])
        cached["warnings"] = list(cached.get("warnings") or []) + [warning]
        return cached
    return {
        "source": source,
        "status": "error",
        "updated_at": utc_now_iso(),
        "updated_ts": time.time(),
        "latency_ms": None,
        "data": {},
        "warnings": [warning],
    }


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default
