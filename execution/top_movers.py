"""Source selection policy for the B3 Top Movers widget."""

from __future__ import annotations

from typing import Any


def choose_top_movers_payload(
    primary: dict[str, Any] | None,
    fallback: dict[str, Any] | None,
    minimum_rows: int,
) -> dict[str, Any]:
    """Keep the primary when sufficiently complete; otherwise use better coverage."""
    primary = primary or {}
    fallback = fallback or {}
    primary_count = int(primary.get("rows_count") or 0)
    fallback_count = int(fallback.get("rows_count") or 0)
    if primary_count >= minimum_rows:
        return primary
    if fallback_count > primary_count and fallback.get("rows_count"):
        return fallback
    if primary.get("gainers") or primary.get("losers"):
        return primary
    if fallback.get("gainers") or fallback.get("losers"):
        return fallback
    return {"gainers": [], "losers": [], "updated_at": "", "source": "Yahoo Finance/Brapi"}
