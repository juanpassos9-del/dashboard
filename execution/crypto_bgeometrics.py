"""BGeometrics Bitcoin on-chain snapshot provider."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

try:
    from execution.crypto_common import PROJECT_ROOT, load_cache, safe_float, save_cache, stale_payload, utc_now_iso
    from execution.source_health import mark_source
except ModuleNotFoundError:
    from crypto_common import PROJECT_ROOT, load_cache, safe_float, save_cache, stale_payload, utc_now_iso
    from source_health import mark_source

CACHE_NAME = "crypto_bgeometrics.json"
HISTORY_CACHE_NAME = "crypto_bgeometrics_mvrv_zscore_history.json"
SOURCE = "BGeometrics"
SNAPSHOT_URL = "https://bitcoin-data.com/api/v1/snapshot"
MVRV_ZSCORE_URL = "https://bitcoin-data.com/api/v1/mvrv-zscore"
PUBLIC_MVRV_CHART_URL = "https://charts.bgeometrics.com/graphics/mvrv_400.html"
PUBLIC_MVRV_PRICE_URL = "https://charts.bgeometrics.com/files/mvrv_zscore_btc_price.json"


def _read_env_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value

    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return ""
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if not clean or clean.startswith("#") or "=" not in clean:
                    continue
                key, raw_value = clean.split("=", 1)
                if key.strip() == name:
                    return raw_value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _normalize_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": raw.get("date"),
        "btc_price": safe_float(raw.get("btcPrice")),
        "realized_price": safe_float(raw.get("realizedPrice")),
        "mvrv": safe_float(raw.get("mvrv")),
        "mvrv_z_score": safe_float(raw.get("mvrvZscore")),
        "fear_greed": safe_float(raw.get("fearGreed")),
        "hashrate": safe_float(raw.get("hashrate")),
        "active_addresses": safe_float(raw.get("activeAddresses")),
        "puell_multiple": safe_float(raw.get("puellMultiple")),
        "mayer_multiple": safe_float(raw.get("mayerMultiple")),
        "aviv": safe_float(raw.get("aviv")),
    }


def _normalize_mvrv_history(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    points: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        value = safe_float(item.get("mvrvZscore"))
        unix_ts = int(safe_float(item.get("unixTs")))
        date_value = item.get("d")
        if not value and value != 0:
            continue
        if not unix_ts and date_value:
            try:
                unix_ts = int(datetime.fromisoformat(str(date_value)).replace(tzinfo=timezone.utc).timestamp())
            except Exception:
                unix_ts = 0
        if not unix_ts:
            continue
        points.append({
            "time": unix_ts,
            "date": date_value,
            "value": round(value, 4),
        })
    points.sort(key=lambda row: int(row.get("time") or 0))
    return points


def _normalize_highcharts_pairs(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    points: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, list) or len(item) < 2:
            continue
        value = safe_float(item[1])
        millis = int(safe_float(item[0]))
        if not millis:
            continue
        points.append({
            "time": int(millis / 1000),
            "date": datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date().isoformat(),
            "value": round(value, 4),
        })
    points.sort(key=lambda row: int(row.get("time") or 0))
    return points


def _fetch_public_mvrv_chart_history(days: int) -> tuple[list[dict[str, Any]], int]:
    started = time.perf_counter()
    response = requests.get(
        PUBLIC_MVRV_CHART_URL,
        timeout=20,
        headers={"User-Agent": "TTS-Crypto-Terminal/1.0"},
    )
    response.raise_for_status()
    latency_ms = int((time.perf_counter() - started) * 1000)
    z_match = re.search(r"const\s+data_mvrv_zscore\s*=\s*(\[.*?\]);", response.text, re.S)
    mvrv_match = re.search(r"const\s+data_mvrv\s*=\s*(\[.*?\]);", response.text, re.S)
    if not z_match:
        return [], latency_ms
    import json

    try:
        points = _normalize_highcharts_pairs(json.loads(z_match.group(1)))
        mvrv_points = _normalize_highcharts_pairs(json.loads(mvrv_match.group(1))) if mvrv_match else []
    except Exception:
        return [], latency_ms
    mvrv_by_time = {int(row.get("time") or 0): safe_float(row.get("value")) for row in mvrv_points}
    try:
        price_response = requests.get(
            PUBLIC_MVRV_PRICE_URL,
            timeout=15,
            headers={"User-Agent": "TTS-Crypto-Terminal/1.0"},
        )
        price_response.raise_for_status()
        price_rows = _normalize_highcharts_pairs(price_response.json())
    except Exception:
        price_rows = []
    price_by_time = {int(row.get("time") or 0): safe_float(row.get("value")) for row in price_rows}
    enriched: list[dict[str, Any]] = []
    for row in points:
        item = dict(row)
        ts = int(item.get("time") or 0)
        mvrv = mvrv_by_time.get(ts)
        price = price_by_time.get(ts)
        if mvrv:
            item["mvrv"] = round(mvrv, 4)
        if price:
            item["btc_price"] = round(price, 2)
        if mvrv and price:
            item["realized_price"] = round(price / mvrv, 2)
        enriched.append(item)
    return enriched[-int(days):], latency_ms


def fetch_bgeometrics_snapshot(max_age_seconds: int = 21600, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch latest Bitcoin on-chain snapshot, using long cache to respect free-tier limits."""
    if not force_refresh:
        cached = load_cache(CACHE_NAME, max_age_seconds=max_age_seconds)
        if cached:
            mark_source("Crypto BGeometrics", "ok", rows=1, source=SOURCE, message="Snapshot em cache.")
            return cached

    api_key = _read_env_key("BGEOMETRICS_API_KEY")
    if not api_key:
        payload = stale_payload(CACHE_NAME, SOURCE, "BGEOMETRICS_API_KEY nao configurada.")
        payload["status"] = "disabled" if not payload.get("data") else payload.get("status", "stale")
        mark_source("Crypto BGeometrics", payload["status"], rows=0, source=SOURCE, message="Chave ausente.")
        return payload

    started = time.perf_counter()
    try:
        response = requests.get(
            SNAPSHOT_URL,
            timeout=15,
            headers={
                "User-Agent": "TTS-Crypto-Terminal/1.0",
                "X-API-KEY": api_key,
            },
        )
        response.raise_for_status()
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = response.json()
        data = _normalize_snapshot(raw if isinstance(raw, dict) else {})
        payload = {
            "source": SOURCE,
            "status": "ok",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency_ms,
            "data": data,
            "warnings": [],
        }
        save_cache(CACHE_NAME, payload)
        mark_source("Crypto BGeometrics", "ok", rows=1, source=SOURCE, message=f"MVRV snapshot carregado em {latency_ms}ms.")
        return payload
    except Exception as exc:
        warning = f"Falha BGeometrics: {exc}"
        payload = stale_payload(CACHE_NAME, SOURCE, warning)
        mark_source("Crypto BGeometrics", payload.get("status", "error"), rows=0, source=SOURCE, message=warning)
        return payload


def fetch_bgeometrics_mvrv_zscore_history(
    days: int = 730,
    max_age_seconds: int = 86400,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch MVRV Z-Score history for cycle charting."""
    if not force_refresh:
        cached = load_cache(HISTORY_CACHE_NAME, max_age_seconds=max_age_seconds)
        if cached:
            rows = len((cached.get("data") or {}).get("points") or [])
            mark_source("Crypto BGeometrics MVRV", "ok", rows=rows, source=SOURCE, message="Historico MVRV em cache.")
            return cached

    try:
        points, latency_ms = _fetch_public_mvrv_chart_history(days)
        if points:
            payload = {
                "source": f"{SOURCE} Public Chart",
                "status": "ok",
                "updated_at": utc_now_iso(),
                "updated_ts": time.time(),
                "latency_ms": latency_ms,
                "data": {
                    "metric": "MVRV Z-Score",
                    "points": points,
                    "latest": points[-1],
                    "startday": points[0].get("date"),
                },
                "warnings": ["Historico carregado pelo grafico publico da BGeometrics."],
            }
            save_cache(HISTORY_CACHE_NAME, payload)
            mark_source("Crypto BGeometrics MVRV", "ok", rows=len(points), source=SOURCE, message="Historico publico MVRV carregado.")
            return payload
    except Exception:
        pass

    api_key = _read_env_key("BGEOMETRICS_API_KEY")
    if not api_key:
        try:
            points, latency_ms = _fetch_public_mvrv_chart_history(days)
            payload = {
                "source": f"{SOURCE} Public Chart",
                "status": "ok" if points else "empty",
                "updated_at": utc_now_iso(),
                "updated_ts": time.time(),
                "latency_ms": latency_ms,
                "data": {
                    "metric": "MVRV Z-Score",
                    "points": points,
                    "latest": points[-1] if points else {},
                    "startday": points[0].get("date") if points else None,
                },
                "warnings": ["Historico carregado pelo grafico publico da BGeometrics."],
            }
            save_cache(HISTORY_CACHE_NAME, payload)
            mark_source("Crypto BGeometrics MVRV", "ok" if points else "stale", rows=len(points), source=SOURCE, message="Historico publico MVRV carregado.")
            return payload
        except Exception as exc:
            payload = stale_payload(HISTORY_CACHE_NAME, SOURCE, f"BGEOMETRICS_API_KEY nao configurada e fallback publico falhou: {exc}")
            payload["status"] = "disabled" if not payload.get("data") else payload.get("status", "stale")
            mark_source("Crypto BGeometrics MVRV", payload["status"], rows=0, source=SOURCE, message="Chave ausente.")
            return payload

    start_day = (datetime.now(timezone.utc) - timedelta(days=max(30, int(days)))).date().isoformat()
    started = time.perf_counter()
    try:
        response = requests.get(
            MVRV_ZSCORE_URL,
            params={"startday": start_day, "size": int(days) + 10},
            timeout=20,
            headers={
                "User-Agent": "TTS-Crypto-Terminal/1.0",
                "X-API-KEY": api_key,
            },
        )
        response.raise_for_status()
        latency_ms = int((time.perf_counter() - started) * 1000)
        points = _normalize_mvrv_history(response.json())[-int(days):]
        latest = points[-1] if points else {}
        payload = {
            "source": SOURCE,
            "status": "ok" if points else "empty",
            "updated_at": utc_now_iso(),
            "updated_ts": time.time(),
            "latency_ms": latency_ms,
            "data": {
                "metric": "MVRV Z-Score",
                "points": points,
                "latest": latest,
                "startday": start_day,
            },
            "warnings": [] if points else ["Historico MVRV vazio."],
        }
        save_cache(HISTORY_CACHE_NAME, payload)
        mark_source("Crypto BGeometrics MVRV", "ok" if points else "stale", rows=len(points), source=SOURCE, message=f"Historico MVRV carregado em {latency_ms}ms.")
        return payload
    except Exception as exc:
        try:
            points, latency_ms = _fetch_public_mvrv_chart_history(days)
            payload = {
                "source": f"{SOURCE} Public Chart",
                "status": "ok" if points else "empty",
                "updated_at": utc_now_iso(),
                "updated_ts": time.time(),
                "latency_ms": latency_ms,
                "data": {
                    "metric": "MVRV Z-Score",
                    "points": points,
                    "latest": points[-1] if points else {},
                    "startday": points[0].get("date") if points else None,
                },
                "warnings": [f"API historica BGeometrics indisponivel; usando grafico publico. Detalhe: {exc}"],
            }
            save_cache(HISTORY_CACHE_NAME, payload)
            mark_source("Crypto BGeometrics MVRV", "ok" if points else "stale", rows=len(points), source=SOURCE, message="Fallback publico MVRV carregado.")
            return payload
        except Exception as fallback_exc:
            warning = f"Falha historico MVRV BGeometrics: {exc}; fallback publico: {fallback_exc}"
            payload = stale_payload(HISTORY_CACHE_NAME, SOURCE, warning)
            mark_source("Crypto BGeometrics MVRV", payload.get("status", "error"), rows=0, source=SOURCE, message=warning)
            return payload


if __name__ == "__main__":
    snapshot = fetch_bgeometrics_snapshot(force_refresh=True)
    print({k: snapshot.get(k) for k in ("source", "status", "updated_at", "warnings")})
    print(snapshot.get("data"))
