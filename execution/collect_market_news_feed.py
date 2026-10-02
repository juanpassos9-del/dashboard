"""Collect approved public RSS sources and cache them in Supabase app_state."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.app_state_sync import get_service_client, sync_app_state_value
from execution.fetch_source_news import fetch_free_market_rss_news


APP_STATE_KEY = "market_news_feed"
# Official central-bank feeds can publish less frequently than market outlets.
MAX_HISTORY_HOURS = 168
MAX_ITEMS = 150


def _read_previous_snapshot(client):
    try:
        result = client.table("app_state").select("value").eq("key", APP_STATE_KEY).limit(1).execute()
        if result.data and isinstance(result.data[0].get("value"), dict):
            return result.data[0]["value"]
    except Exception as exc:
        print(f"[WARN] Previous news snapshot unavailable: {type(exc).__name__}")
    return {}


def collect_and_sync() -> dict:
    client = get_service_client()
    previous = _read_previous_snapshot(client)
    fresh_items, source_status = fetch_free_market_rss_news(limit_per_source=12)

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=MAX_HISTORY_HOURS)).timestamp()
    previous_items = previous.get("items", []) if isinstance(previous, dict) else []
    combined = []
    seen_ids = set()
    for item in fresh_items + (previous_items if isinstance(previous_items, list) else []):
        try:
            timestamp = float(item.get("timestamp") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        item_id = str(item.get("id") or item.get("link") or item.get("title_en") or "")
        if not item_id or item_id in seen_ids or timestamp < cutoff:
            continue
        seen_ids.add(item_id)
        combined.append(item)
    combined.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
    combined = combined[:MAX_ITEMS]

    previous_by_source = {}
    if isinstance(previous_items, list):
        for item in previous_items:
            if isinstance(item, dict) and item.get("source"):
                source = str(item["source"])
                previous_by_source[source] = previous_by_source.get(source, 0) + 1
    for source, status in source_status.items():
        if status["status"] == "error" and previous_by_source.get(source, 0):
            status["status"] = "stale"
            status["items"] = previous_by_source[source]
            status["message"] = "Fonte indisponivel; mantendo itens em cache."

    if not fresh_items and not combined:
        raise RuntimeError("Nenhuma fonte RSS respondeu e nao ha historico para manter.")

    payload = {
        "updated_at": now.astimezone().isoformat(),
        "updated_ts": now.timestamp(),
        "stale": not bool(fresh_items),
        "items": combined,
        "sources": sorted({str(item.get("source")) for item in combined if item.get("source")}),
        "source_status": source_status,
    }
    sync_app_state_value(APP_STATE_KEY, payload, client)
    ok_count = sum(1 for status in source_status.values() if status["status"] == "ok")
    print(f"Synced {len(combined)} headlines from {ok_count}/{len(source_status)} RSS sources.")
    for source, status in sorted(source_status.items()):
        print(f"{source}: {status['status']} ({status['items']} items)")
    return payload


if __name__ == "__main__":
    collect_and_sync()
