"""Dados oficiais e leitura determinística para o Monitor BR."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT_DIR / ".tmp" / "monitor_br.json"
BR_TZ = ZoneInfo("America/Sao_Paulo")
BCB_SERIES = {
    "selic": {"id": 432, "name": "Selic meta", "unit": "% a.a.", "frequency": "diária"},
    "ipca": {"id": 433, "name": "IPCA", "unit": "% m/m", "frequency": "mensal"},
    "ibc_br": {"id": 24363, "name": "IBC-Br dessazonalizado", "unit": "índice", "frequency": "mensal"},
}
SIDRA_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/1737/periodos/{period}/variaveis/63?localidades=N1[all]"


def _number(value: Any) -> float | None:
    try:
        result = float(str(value).replace(",", "."))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _get_json(url: str, timeout: int = 15) -> Any:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "TradingStrategyDashboard/1.0"})
    response.raise_for_status()
    return response.json()


def _fetch_bcb_series(series_id: int, count: int = 15) -> list[dict[str, Any]]:
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados/ultimos/{count}?formato=json"
    records = _get_json(url)
    result = []
    for row in records if isinstance(records, list) else []:
        value = _number(row.get("valor"))
        if value is not None:
            try:
                date = datetime.strptime(str(row.get("data")), "%d/%m/%Y").date()
            except ValueError:
                continue
            if date <= datetime.now(BR_TZ).date():
                result.append({"date": date.strftime("%d/%m/%Y"), "value": value})
    return result


def _fetch_ibge_ipca() -> dict[str, Any] | None:
    period = datetime.now(BR_TZ).strftime("%Y%m")
    year, month = int(period[:4]), int(period[4:])
    for _ in range(4):
        key = f"{year}{month:02d}"
        try:
            data = _get_json(SIDRA_URL.format(period=key))
            series = data[0]["resultados"][0]["series"][0]["serie"]
            value = _number(series.get(key))
            if value is not None:
                return {"date": f"{year}-{month:02d}", "value": value, "source": "IBGE SIDRA, agregado 1737, variável 63"}
        except (IndexError, KeyError, TypeError, requests.RequestException):
            pass
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return None


def _series_reading(values: list[dict[str, Any]], key: str) -> dict[str, Any]:
    latest = values[-1] if values else None
    previous = values[-2] if len(values) > 1 else None
    delta = latest["value"] - previous["value"] if latest and previous else None
    return {
        **(latest or {}),
        "previous": previous.get("value") if previous else None,
        "delta": round(delta, 4) if delta is not None else None,
        "name": BCB_SERIES[key]["name"],
        "unit": BCB_SERIES[key]["unit"],
        "frequency": BCB_SERIES[key]["frequency"],
        "source": f"BCB SGS {BCB_SERIES[key]['id']}",
    }


def _market_asset(global_data: Any, symbols: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(global_data, dict):
        return None
    categories = global_data.get("categories", global_data)
    for rows in categories.values() if isinstance(categories, dict) else []:
        if not isinstance(rows, list):
            continue
        for item in rows:
            if isinstance(item, dict) and str(item.get("symbol", "")).upper() in symbols:
                asset = dict(item)
                timestamp = asset.get("source_timestamp") or asset.get("updated_at")
                age_seconds = asset.get("age_seconds")
                if age_seconds is None and timestamp:
                    try:
                        observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                        if observed.tzinfo is None:
                            observed = observed.replace(tzinfo=BR_TZ)
                        age_seconds = max(0, (datetime.now(BR_TZ) - observed.astimezone(BR_TZ)).total_seconds())
                    except ValueError:
                        age_seconds = None
                asset["age_seconds"] = age_seconds
                asset["freshness"] = "sem horário" if age_seconds is None else "atual" if age_seconds <= 900 else "desatualizada"
                return asset
    return None


def _focus_snapshot(focus: Any) -> dict[str, Any]:
    if not isinstance(focus, dict):
        return {}
    years = focus.get("years") or {}
    year = str(datetime.now(BR_TZ).year)
    current = years.get(year) or {}
    indicators = {}
    for key in ("IPCA", "Selic", "PIB", "Cambio"):
        node = current.get(key) or {}
        now = _number(node.get("hoje"))
        four_weeks = _number(node.get("4_sem"))
        indicators[key] = {
            "value": now,
            "delta_4w": round(now - four_weeks, 4) if now is not None and four_weeks is not None else None,
        }
    return {
        "publish_date": focus.get("publish_date"),
        "updated_at": focus.get("updated_at"),
        "source": focus.get("source", "Banco Central do Brasil · Boletim Focus"),
        "year": year,
        "indicators": indicators,
    }


def _flow_snapshot(flow: Any) -> dict[str, Any]:
    """Summarize investor flow; source records are in R$ thousands."""
    if not isinstance(flow, dict):
        return {"records": [], "source": None, "updated_at": None}
    records = []
    for item in flow.get("records", []):
        if not isinstance(item, dict) or not item.get("date"):
            continue
        value = _number(item.get("foreigners"))
        if value is None:
            continue
        records.append({"date": str(item["date"]), "foreigners_thousands": value})
    records.sort(key=lambda item: item["date"], reverse=True)
    return {
        "latest": records[0] if records else None,
        "sum_5d_thousands": round(sum(row["foreigners_thousands"] for row in records[:5]), 2),
        "sum_20d_thousands": round(sum(row["foreigners_thousands"] for row in records[:20]), 2),
        "records": records[:60],
        "source": flow.get("source", "Dados de Mercado · fluxo por investidor"),
        "updated_at": flow.get("updated_at"),
        "total_records": len(records),
    }


def build_monitor_br_payload(global_data: Any = None, focus: Any = None, di: Any = None, flow: Any = None) -> dict[str, Any]:
    """Build a payload from official series and existing market snapshots."""
    errors: list[str] = []
    observations: dict[str, list[dict[str, Any]]] = {}
    for key, spec in BCB_SERIES.items():
        try:
            observations[key] = _fetch_bcb_series(spec["id"], 15)
            if not observations[key]:
                errors.append(f"BCB {spec['id']}: série sem observações")
        except Exception as exc:
            errors.append(f"BCB {spec['id']}: {exc}")
            observations[key] = []

    try:
        ibge_ipca = _fetch_ibge_ipca()
        if not ibge_ipca:
            errors.append("IBGE SIDRA: IPCA mensal ainda não publicado para o período corrente")
    except Exception as exc:
        ibge_ipca = None
        errors.append(f"IBGE SIDRA IPCA: {exc}")

    market = {
        "IBOV": _market_asset(global_data, ("^BVSP", "IBOV", "IBOVESPA")),
        "USD/BRL": _market_asset(global_data, ("USDBRL=X", "BRL=X", "USD/BRL", "USDBRL")),
    }
    di_contracts = (di or {}).get("principais", []) if isinstance(di, dict) else []
    di_contracts = di_contracts or ((di or {}).get("contracts", []) if isinstance(di, dict) else [])
    di_by_symbol = {str(item.get("symbol")): item for item in di_contracts if isinstance(item, dict)}
    curve = [di_by_symbol[symbol] for symbol in ("DI1F27", "DI1F28", "DI1F29", "DI1F31", "DI1F32", "DI1F40") if symbol in di_by_symbol]

    selic = _series_reading(observations.get("selic", []), "selic")
    ipca = _series_reading(observations.get("ipca", []), "ipca")
    ibc_br = _series_reading(observations.get("ibc_br", []), "ibc_br")
    current_selic = selic.get("value")
    front_di = _number(curve[0].get("rate", curve[0].get("price"))) if curve else None
    selic_di_spread = round(front_di - current_selic, 3) if front_di is not None and current_selic is not None else None

    payload = {
        "schema_version": "monitor_br_v1",
        "updated_at": datetime.now(BR_TZ).isoformat(timespec="seconds"),
        "sources": {"official": "BCB SGS + IBGE SIDRA", "market": "Snapshot central do dashboard", "curve": (di or {}).get("source") if isinstance(di, dict) else None},
        "official": {"selic": selic, "ipca": ipca, "ibc_br": ibc_br, "ibge_ipca_monthly": ibge_ipca},
        "focus": _focus_snapshot(focus),
        "foreign_flow": _flow_snapshot(flow),
        "market": market,
        "di_curve": curve,
        "derived": {"front_di": front_di, "selic_di_spread_pp": selic_di_spread},
        "errors": errors[:8],
    }
    return payload


def save_monitor_br_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_monitor_br_cache() -> dict[str, Any] | None:
    try:
        value = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
