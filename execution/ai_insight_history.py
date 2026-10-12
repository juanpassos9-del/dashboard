"""Normalize and deduplicate macro direction history snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MIN_REPEAT_INTERVAL = timedelta(minutes=30)
MAX_HISTORY = 5


def _timestamp(item: dict[str, Any]) -> datetime | None:
    raw = item.get("updated_at")
    if raw:
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=SAO_PAULO)
            return value.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    try:
        return datetime.fromtimestamp(float(item.get("id")), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _direction_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(item.get(key) for key in (
        "sentiment", "macro_regime", "confidence", "curve_regime", "curve_bias",
    ))


def _score(item: dict[str, Any]) -> float | None:
    try:
        return float(item.get("macro_score"))
    except (TypeError, ValueError):
        return None


def _material_change(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    if _direction_signature(previous) != _direction_signature(current):
        return True
    previous_score, current_score = _score(previous), _score(current)
    return previous_score is not None and current_score is not None and abs(current_score - previous_score) >= 3


def _compact(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        current = dict(item)
        if result:
            previous = result[-1]
            previous_time, current_time = _timestamp(previous), _timestamp(current)
            close_in_time = (
                previous_time is not None and current_time is not None
                and timedelta(0) <= current_time - previous_time < MIN_REPEAT_INTERVAL
            )
            if close_in_time and not _material_change(previous, current):
                continue
        result.append(current)
    return result[-MAX_HISTORY:]


def append_direction_history(
    history: Any,
    insight: dict[str, Any],
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return compact history and whether a new meaningful snapshot was added."""
    existing = _compact(history if isinstance(history, list) else [])
    current_time = now or _timestamp(insight) or datetime.now(SAO_PAULO)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=SAO_PAULO)
    current_time = current_time.astimezone(SAO_PAULO)
    entry = {
        "sentiment": insight.get("sentiment", "NEUTRO"),
        "updated_at": current_time.isoformat(timespec="seconds"),
        "insight": insight.get("insight", ""),
        "macro_regime": insight.get("macro_regime", ""),
        "confidence": insight.get("confidence", ""),
        "macro_score": insight.get("macro_score"),
        "curve_regime": insight.get("curve_regime", ""),
        "curve_bias": insight.get("curve_bias", ""),
        "drivers": insight.get("drivers", []),
        "provider": insight.get("provider", ""),
        "id": int(current_time.timestamp()),
    }
    if existing:
        previous = existing[-1]
        previous_time = _timestamp(previous)
        elapsed = current_time.astimezone(timezone.utc) - previous_time if previous_time else None
        if (
            elapsed is not None and timedelta(0) <= elapsed < MIN_REPEAT_INTERVAL
            and not _material_change(previous, entry)
        ):
            return existing, False
    return (existing + [entry])[-MAX_HISTORY:], True


def format_history_time(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SAO_PAULO)
        return parsed.astimezone(SAO_PAULO).strftime("%d/%m %H:%M:%S")
    except (TypeError, ValueError):
        return raw or "horário indisponível"


def freshness_minutes(value: Any, now: datetime | None = None) -> float | None:
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=SAO_PAULO)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=SAO_PAULO)
        return max(0.0, (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 60)
    except (TypeError, ValueError):
        return None
