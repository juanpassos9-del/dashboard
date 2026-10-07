"""Archive observed official-series values and source revisions."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BR_TZ = ZoneInfo("America/Sao_Paulo")
MAX_VINTAGE_ROWS = 20_000
VINTAGES_CACHE_PATH = Path(__file__).resolve().parents[1] / ".tmp" / "monitor_br_vintages.json"


def save_monitor_br_vintages_cache(archive: dict[str, Any]) -> None:
    VINTAGES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    VINTAGES_CACHE_PATH.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")


def load_monitor_br_vintages_cache() -> dict[str, Any] | None:
    try:
        result = json.loads(VINTAGES_CACHE_PATH.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def merge_monitor_br_vintages(
    existing: Any,
    official_history: Any,
    collected_at: str | None = None,
    max_rows: int = MAX_VINTAGE_ROWS,
) -> dict[str, Any]:
    """Keep the first observed timestamp for each distinct value vintage."""
    archive = existing if isinstance(existing, dict) else {}
    records = [dict(row) for row in archive.get("observations", []) if isinstance(row, dict)]
    seen = {
        (row.get("series_key"), row.get("reference_period"), row.get("value"))
        for row in records
    }
    stamp = collected_at or datetime.now(BR_TZ).isoformat(timespec="seconds")
    added = 0
    series = official_history.get("series", []) if isinstance(official_history, dict) else []
    for item in series if isinstance(series, list) else []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        for observation in item.get("observations", []):
            if not isinstance(observation, dict):
                continue
            period = observation.get("period") or observation.get("date")
            value = observation.get("value")
            if period is None or value is None:
                continue
            signature = (item["key"], str(period), value)
            if signature in seen:
                continue
            seen.add(signature)
            records.append({
                "series_key": item["key"],
                "name": item.get("name", item["key"]),
                "topic": item.get("topic"),
                "unit": item.get("unit"),
                "source": item.get("source"),
                "reference_period": str(period),
                "value": value,
                "weight": observation.get("weight"),
                "contribution_pp_approx": observation.get("contribution_pp_approx"),
                "first_collected_at": stamp,
            })
            added += 1
    records.sort(key=lambda row: (row.get("first_collected_at", ""), row.get("series_key", ""), row.get("reference_period", "")))
    records = records[-max(1, int(max_rows)):]
    return {
        "schema_version": 1,
        "updated_at": stamp,
        "observation_count": len(records),
        "added_observations": added,
        "revision_count": sum(
            max(0, count - 1)
            for count in _vintage_counts(records).values()
        ),
        "observations": records,
    }


def _vintage_counts(records: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in records:
        key = (str(row.get("series_key", "")), str(row.get("reference_period", "")))
        counts[key] = counts.get(key, 0) + 1
    return counts


def latest_monitor_br_revisions(archive: Any, limit: int = 100) -> list[dict[str, Any]]:
    """Return observations whose reference period has more than one stored value."""
    if not isinstance(archive, dict):
        return []
    records = archive.get("observations", [])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in records if isinstance(records, list) else []:
        if isinstance(row, dict):
            key = (str(row.get("series_key", "")), str(row.get("reference_period", "")))
            groups.setdefault(key, []).append(row)
    revised = []
    for values in groups.values():
        if len(values) < 2:
            continue
        values.sort(key=lambda row: row.get("first_collected_at", ""))
        prior, latest = values[-2:]
        revised.append({
            "Série": latest.get("name"),
            "Período": latest.get("reference_period"),
            "Valor anterior": prior.get("value"),
            "Valor atual": latest.get("value"),
            "Unidade": latest.get("unit"),
            "Revisado em": latest.get("first_collected_at"),
            "Fonte": latest.get("source"),
        })
    return sorted(revised, key=lambda row: str(row.get("Revisado em", "")), reverse=True)[:max(0, int(limit))]
