"""Lightweight source-health registry for dashboard data providers.

The dashboard should never block or hide stale data silently. This module keeps a
small JSON registry in `.tmp` so UI pages can show which providers are fresh,
using fallback data, or failing.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_HEALTH_PATH = os.path.join(PROJECT_ROOT, ".tmp", "source_health.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_registry() -> dict[str, Any]:
    try:
        if not os.path.exists(SOURCE_HEALTH_PATH):
            return {}
        with open(SOURCE_HEALTH_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(registry: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(SOURCE_HEALTH_PATH), exist_ok=True)
        with open(SOURCE_HEALTH_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def mark_source(
    name: str,
    status: str,
    *,
    message: str = "",
    rows: int | None = None,
    source: str = "",
) -> None:
    """Persist provider status without raising errors.

    status should be one of: ok, stale, error, disabled.
    """
    if not name:
        return
    normalized_status = status if status in {"ok", "stale", "error", "disabled"} else "error"
    registry = _load_registry()
    previous = registry.get(name, {}) if isinstance(registry.get(name), dict) else {}
    registry[name] = {
        "name": name,
        "status": normalized_status,
        "message": str(message or "")[:240],
        "rows": rows,
        "source": source,
        "updated_at": _utc_now_iso(),
        "updated_ts": time.time(),
        "last_ok_at": _utc_now_iso() if normalized_status == "ok" else previous.get("last_ok_at"),
        "last_ok_ts": time.time() if normalized_status == "ok" else previous.get("last_ok_ts"),
    }
    _save_registry(registry)


def get_source_health(max_age_seconds: int = 3600) -> dict[str, Any]:
    registry = _load_registry()
    now = time.time()
    out: dict[str, Any] = {}
    for name, item in registry.items():
        if not isinstance(item, dict):
            continue
        age = now - float(item.get("updated_ts") or 0)
        normalized = dict(item)
        normalized["age_seconds"] = age
        if age > max_age_seconds and normalized.get("status") == "ok":
            normalized["status"] = "stale"
            normalized["message"] = normalized.get("message") or "Sem atualizacao recente."
        out[name] = normalized
    return out
