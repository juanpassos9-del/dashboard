"""Merge recurring economic-calendar snapshots into a durable event archive."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


BR_TZ = ZoneInfo("America/Sao_Paulo")
PLACEHOLDERS = {"", "---", "-", "n/a", "none"}
MERGED_FIELDS = (
    "actual", "forecast", "previous", "impact", "bull_count", "source", "currency", "event", "time",
    "official_release", "reference_period", "source_url", "release_id", "research_id", "research",
)


def _event_key(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("date") or "")[:10],
        str(event.get("time") or "").strip(),
        str(event.get("currency") or "").strip().upper(),
        " ".join(str(event.get("event") or "").casefold().split()),
    )


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip().casefold() not in PLACEHOLDERS


def _is_brazil_event(event: dict[str, Any]) -> bool:
    currency = str(event.get("currency") or event.get("País") or event.get("Pais") or "").strip().casefold()
    country = str(event.get("country") or event.get("país") or event.get("pais") or "").strip().casefold()
    return currency in {"brl", "br", "brazil", "brasil"} or country in {"brazil", "brasil"}


def merge_calendar_history(
    previous: dict[str, Any] | None,
    incoming_batches: list[list[dict[str, Any]]],
    now: datetime | None = None,
    retention_days: int = 365 * 3,
    backfill_status: str | None = None,
) -> dict[str, Any]:
    """Merge snapshots while preserving released values and first-seen dates."""
    now = now or datetime.now(BR_TZ)
    old_events = previous.get("events", []) if isinstance(previous, dict) else []
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for raw in [*old_events, *(event for batch in incoming_batches for event in batch)]:
        if not isinstance(raw, dict) or not raw.get("date") or not raw.get("event") or not _is_brazil_event(raw):
            continue
        key = _event_key(raw)
        if not key[0] or not key[2]:
            continue
        current = merged.setdefault(key, {**raw, "first_seen_at": raw.get("first_seen_at") or now.isoformat()})
        for field in MERGED_FIELDS:
            if _has_value(raw.get(field)):
                current[field] = raw[field]
        current["last_seen_at"] = now.isoformat()

    cutoff = (now.date() - timedelta(days=retention_days)).isoformat()
    events = [event for event in merged.values() if str(event.get("date", ""))[:10] >= cutoff]
    events.sort(key=lambda event: _event_key(event))
    prior_status = previous.get("backfill_status") if isinstance(previous, dict) else None
    return {
        "schema_version": "economic_calendar_history_v1",
        "updated_at": now.isoformat(timespec="seconds"),
        "source": "Investing.com + IBGE official release calendars",
        "retention_days": retention_days,
        "backfill_status": backfill_status or prior_status or "not_attempted",
        "event_count": len(events),
        "events": events,
    }
