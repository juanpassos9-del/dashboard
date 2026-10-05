from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from execution.market_data_engine import quote_age_seconds


def quote_freshness_label(asset: dict[str, Any], now: datetime | None = None) -> tuple[str, str]:
    """Return a compact provider/freshness label without treating unknown time as fresh."""
    source = str(asset.get("source") or "Fonte indisponível").strip()
    if asset.get("fallback_reason"):
        reason = "fonte principal atrasada" if asset["fallback_reason"] == "primary_stale" else "fonte principal indisponível"
        source = f"{source} · fallback ({reason})"
    age_seconds = quote_age_seconds(asset, now=now or datetime.now(timezone.utc))

    if age_seconds is None:
        freshness = "ATRASO DO MERCADO INDISPONÍVEL" if asset.get("timestamp_type") == "retrieved_at" else "HORÁRIO INDISPONÍVEL"
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
