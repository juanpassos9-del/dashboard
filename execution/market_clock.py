"""Helpers for the sidebar market clock."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")
MARKET_CURRENCIES = {"USD", "BRL", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "NZD", "CHF"}


def select_upcoming_calendar_events(
    calendar_data: Any,
    now: datetime | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return future calendar events in Brasilia time with fields safe to serialize."""
    if isinstance(calendar_data, dict):
        calendar_data = calendar_data.get("events") or calendar_data.get("value") or []
    if not isinstance(calendar_data, list):
        return []

    current = now or datetime.now(BR_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BR_TZ)
    else:
        current = current.astimezone(BR_TZ)

    events = []
    for event in calendar_data:
        if not isinstance(event, dict):
            continue
        date_value = str(event.get("date", ""))[:10]
        time_value = str(event.get("time", ""))[:5]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value) or not re.fullmatch(r"\d{2}:\d{2}", time_value):
            continue
        try:
            event_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M").replace(tzinfo=BR_TZ)
        except ValueError:
            continue
        if event_time < current:
            continue

        currency = str(event.get("currency", "")).upper()[:5]
        if currency not in MARKET_CURRENCIES:
            continue
        impact = str(event.get("impact", "LOW")).upper()
        if impact not in {"HIGH", "MEDIUM", "LOW"}:
            continue
        events.append({
            "timestamp": int(event_time.timestamp()),
            "date": date_value,
            "time": time_value,
            "currency": currency,
            "event": str(event.get("event") or "Evento econômico")[:180],
            "impact": impact,
            "icon": str(event.get("icon") or "")[:8],
        })

    events.sort(key=lambda item: (item["timestamp"], {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[item["impact"]]))
    return events[:max(0, limit)]
