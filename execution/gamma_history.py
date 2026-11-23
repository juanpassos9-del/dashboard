"""Compact daily history for the free Yahoo-based EWZ gamma model."""

from __future__ import annotations

from datetime import date
import math
from typing import Any

import pandas as pd

MAX_DAILY_SNAPSHOTS = 180
MAX_CHAIN_HISTORY_SNAPSHOTS = 15
MAX_CHAIN_STRIKES_PER_EXPIRY = 35


def make_gamma_snapshot(result: dict[str, Any], observed_at: str) -> dict[str, Any]:
    """Store headline values and a compact near-spot OI slice for later comparison."""
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
        "chain_oi": _compact_chain_oi(result.get("options"), _number(result.get("spot"))),
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
    normalized = normalized[-max(1, int(limit)):]
    chain_rows = [index for index, row in enumerate(normalized) if isinstance(row.get("chain_oi"), list)]
    for index in chain_rows[:-MAX_CHAIN_HISTORY_SNAPSHOTS]:
        normalized[index].pop("chain_oi", None)
    return normalized


def recent_gamma_snapshots(history: Any, count: int = 5) -> list[dict[str, Any]]:
    rows = history if isinstance(history, list) else []
    valid = [row for row in rows if isinstance(row, dict) and row.get("market_date")]
    valid.sort(key=lambda row: str(row.get("market_date", "")))
    return valid[-max(1, int(count)):]


def compare_chain_open_interest(current: Any, previous: Any) -> list[dict[str, Any]]:
    """Compare compact chain OI snapshots; this is OI change, not trade direction."""
    prior = {
        (str(row.get("expiration", "")), _number(row.get("strike")), str(row.get("side", ""))): _number(row.get("open_interest")) or 0.0
        for row in (previous if isinstance(previous, list) else [])
        if isinstance(row, dict) and _number(row.get("strike")) is not None
    }
    changes = []
    for row in current if isinstance(current, list) else []:
        if not isinstance(row, dict) or _number(row.get("strike")) is None:
            continue
        key = (str(row.get("expiration", "")), _number(row.get("strike")), str(row.get("side", "")))
        current_oi = _number(row.get("open_interest")) or 0.0
        previous_oi = prior.get(key)
        if previous_oi is None:
            continue
        delta = current_oi - previous_oi
        changes.append({
            "expiration": key[0],
            "strike": key[1],
            "side": key[2],
            "current_oi": current_oi,
            "previous_oi": previous_oi,
            "delta_oi": delta,
            "delta_pct": (delta / previous_oi * 100) if previous_oi else None,
        })
    return sorted(changes, key=lambda row: abs(row["delta_oi"]), reverse=True)


def _compact_chain_oi(options: Any, spot: float | None) -> list[dict[str, Any]]:
    if not isinstance(options, pd.DataFrame) or options.empty or not spot:
        return []
    required = {"expiration", "strike", "side", "open_interest"}
    if not required.issubset(options.columns):
        return []
    frame = options[list(required)].copy()
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame["open_interest"] = pd.to_numeric(frame["open_interest"], errors="coerce").fillna(0)
    frame["side"] = frame["side"].astype(str).str.lower()
    frame = frame[
        frame["strike"].between(spot * 0.85, spot * 1.15)
        & frame["side"].isin(["call", "put"])
    ]
    if frame.empty:
        return []
    pivot = frame.pivot_table(
        index=["expiration", "strike"], columns="side", values="open_interest", aggfunc="sum", fill_value=0
    ).reset_index()
    for side in ("call", "put"):
        if side not in pivot:
            pivot[side] = 0.0
    pivot["total_oi"] = pivot["call"] + pivot["put"]
    selected = (
        pivot.sort_values(["expiration", "total_oi"], ascending=[True, False])
        .groupby("expiration", sort=True)
        .head(MAX_CHAIN_STRIKES_PER_EXPIRY)
        .sort_values(["expiration", "strike"])
    )
    return [
        {"expiration": str(row.expiration), "strike": float(row.strike), "side": side, "open_interest": float(getattr(row, side))}
        for row in selected.itertuples(index=False)
        for side in ("call", "put")
    ]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None
