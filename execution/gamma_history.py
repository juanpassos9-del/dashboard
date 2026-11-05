"""Compact daily history for the free Yahoo-based EWZ gamma model."""

from __future__ import annotations

from datetime import date
from typing import Any

MAX_DAILY_SNAPSHOTS = 180


def make_gamma_snapshot(result: dict[str, Any], observed_at: str) -> dict[str, Any]:
    """Keep only reproducible headline values, not the full options chain."""
    market_date = str(result.get("market_date") or result.get("as_of") or observed_at)[:10]
    return {
        "underlying": str(result.get("underlying") or "EWZ").upper(),
        "market_date": market_date,
        "observed_at": observed_at,
        "spot": _number(result.get("spot")),
        "net_gex_usd_1pct": _number(result.get("net_gex_usd_1pct")),
        "gamma_flip": _number(result.get("gamma_flip")),
        "call_wall": _number((result.get("call_wall") or {}).get("strike")),
        "put_wall": _number((result.get("put_wall") or {}).get("strike")),
        "option_count": int(result.get("option_count") or 0),
        "expiration_count": int(result.get("expiration_count") or 0),
        "source": str(result.get("source") or "Yahoo Finance"),
        "as_of": str(result.get("as_of") or ""),
    }


def merge_gamma_snapshots(
    history: Any,
    snapshot: dict[str, Any],
    limit: int = MAX_DAILY_SNAPSHOTS,
) -> list[dict[str, Any]]:
    """Replace the same trading date and return chronological bounded history."""
    rows = history if isinstance(history, list) else []
    normalized = [row for row in rows if isinstance(row, dict) and row.get("market_date")]
    normalized = [row for row in normalized if row["market_date"] != snapshot["market_date"]]
    normalized.append(snapshot)
    normalized.sort(key=lambda row: (str(row.get("market_date", "")), str(row.get("observed_at", ""))))
    return normalized[-max(1, int(limit)):]


def recent_gamma_snapshots(history: Any, count: int = 5) -> list[dict[str, Any]]:
    rows = history if isinstance(history, list) else []
    valid = [row for row in rows if isinstance(row, dict) and row.get("market_date")]
    valid.sort(key=lambda row: str(row.get("market_date", "")))
    return valid[-max(1, int(count)):]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number == number and abs(number) != float("inf") else None
