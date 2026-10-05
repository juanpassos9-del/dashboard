from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def quote_freshness_label(asset: dict[str, Any], now: datetime | None = None) -> tuple[str, str]:
    """Return a compact provider/freshness label without treating unknown time as fresh."""
    source = str(asset.get("source") or "Fonte indisponível").strip()
    raw_timestamp = asset.get("source_timestamp") or asset.get("updated_at")
    age_seconds = None
    if raw_timestamp:
        try:
            source_time = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if source_time.tzinfo is None:
                source_time = source_time.replace(tzinfo=timezone.utc)
            reference = now or datetime.now(timezone.utc)
            age_seconds = max(0, (reference - source_time.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            pass
    if age_seconds is None:
        age_seconds = asset.get("age_seconds")

    if age_seconds is None:
        freshness = "HORÁRIO INDISPONÍVEL"
        state = "unknown"
    else:
        age_seconds = max(0, float(age_seconds))
        if age_seconds < 60:
            age_text = f"{int(age_seconds)}s"
        elif age_seconds < 3600:
            age_text = f"{int(age_seconds // 60)}min"
        else:
            age_text = f"{int(age_seconds // 3600)}h"
        threshold_seconds = float(asset.get("max_age_seconds") or 15 * 60)
        state = "stale" if age_seconds > threshold_seconds else "fresh"
        freshness = f"{age_text} atrás" if state == "fresh" else f"ATRASADA · {age_text}"
    return f"{source} · {freshness}", state
