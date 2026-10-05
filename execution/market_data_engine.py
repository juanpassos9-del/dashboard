"""Central collection, quality checks, and publication for dashboard quotes."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


FRESHNESS_LIMITS_SECONDS = {
    "equity": 10 * 60,
    "fx": 10 * 60,
    "treasury": 60 * 60,
    "di": 30 * 60,
    "commodity": 15 * 60,
    "crypto": 10 * 60,
    "other": 15 * 60,
}


def _quote_class(category: str, asset: dict[str, Any]) -> str:
    text = f"{category} {asset.get('name', '')} {asset.get('symbol', '')}".upper()
    if "DI FUTURO" in text or "(DI FUTURO)" in text:
        return "di"
    if "TREASUR" in text or "YIELD" in text:
        return "treasury"
    if "FOREX" in text or "MOEDAS" in text or any(pair in text for pair in ("EURUSD", "GBPUSD", "USDBRL", "BRLUSD", "USDJPY")):
        return "fx"
    if "CRYPTO" in text or "CRIPTO" in text or "BITCOIN" in text or "ETHEREUM" in text or "SOLANA" in text:
        return "crypto"
    if "COMMODIT" in text or any(name in text for name in ("BRENT", "WTI", "GOLD", "SILVER", "COPPER", "NATURAL GAS")):
        return "commodity"
    if any(word in text for word in ("ÍNDICES", "INDICES", "ETF", "EMERGENTES", "BRASIL", "SECTORIAIS")):
        return "equity"
    return "other"


def _timestamp_age(timestamp: Any, now: datetime) -> tuple[str | None, float | None]:
    if not timestamp:
        return None, None
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (now - parsed.astimezone(timezone.utc)).total_seconds()
        if age < -300:
            raise ValueError("timestamp more than five minutes in the future")
        return parsed.astimezone(timezone.utc).isoformat(), max(0.0, age)
    except (TypeError, ValueError, OverflowError):
        return None, None


def normalize_market_snapshot(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("categories"), dict):
        raise ValueError("Coletor retornou snapshot sem categories.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    categories: dict[str, list[dict[str, Any]]] = {}
    counts = {"fresh": 0, "stale": 0, "unknown": 0, "rejected": 0}
    for category, rows in payload["categories"].items():
        if not isinstance(rows, list):
            continue
        normalized_rows = []
        for original in rows:
            if not isinstance(original, dict):
                counts["rejected"] += 1
                continue
            try:
                price = float(original.get("price"))
                if not math.isfinite(price) or price <= 0:
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                counts["rejected"] += 1
                continue

            item = dict(original)
            quote_class = _quote_class(str(category), item)
            raw_timestamp = item.get("source_timestamp") or item.get("updated_at")
            parsed_timestamp, computed_age = _timestamp_age(raw_timestamp, now)
            age = computed_age if parsed_timestamp else item.get("age_seconds")
            try:
                age = max(0.0, float(age)) if age is not None and math.isfinite(float(age)) else None
            except (TypeError, ValueError, OverflowError):
                age = None
            if computed_age is None and raw_timestamp:
                counts["rejected"] += 1
                continue

            max_age = FRESHNESS_LIMITS_SECONDS[quote_class]
            status = "unknown" if age is None else "stale" if age > max_age else "fresh"
            item.update({
                "quote_class": quote_class,
                "source_timestamp": parsed_timestamp or raw_timestamp,
                "age_seconds": round(age, 1) if age is not None else None,
                "max_age_seconds": max_age,
                "data_status": status,
                "change_basis": item.get("change_basis") or "previous_session_close",
            })
            counts[status] += 1
            normalized_rows.append(item)
        categories[str(category)] = normalized_rows

    row_count = sum(len(rows) for rows in categories.values())
    if row_count < 6:
        raise ValueError(f"Snapshot rejeitado: somente {row_count} cotações válidas.")

    metadata = dict(payload.get("metadata") or {})
    metadata.update({
        "schema_version": "market_quotes_v2",
        "snapshot_updated_at": now.isoformat(),
        "generated_at_utc": now.isoformat(),
        "full_timestamp": now.isoformat(),
        "collector": "execution.market_data_engine",
        "quote_quality": {**counts, "total": row_count},
        "freshness_limits_seconds": FRESHNESS_LIMITS_SECONDS,
    })
    return {**payload, "categories": categories, "metadata": metadata}


def collect_and_publish_market_snapshot(client=None) -> dict[str, Any]:
    from execution.app_state_sync import get_service_client, sync_app_state_value
    from execution.fetch_global_markets import fetch_global_data

    raw = fetch_global_data(save_file=False)
    if not raw:
        raise RuntimeError("Coletor de cotações não retornou dados; snapshot anterior preservado.")
    snapshot = normalize_market_snapshot(raw)
    sync_app_state_value("mercados_globais", snapshot, client or get_service_client())
    return snapshot
