"""Dados oficiais e leitura determinística para o Monitor BR."""

from __future__ import annotations

import json
import math
import re
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
CALENDAR_TOPICS = {
    "inflation": ("IPCA", "IPCA-15", "INPC", "IGP-M", "IGP M", "inflação", "inflacao", "preços ao consumidor"),
    "consumption_activity": ("vendas no varejo", "vendas a retalho", "pesquisa mensal de comércio", "pesquisa mensal de comercio", "pesquisa mensal de serviços", "pesquisa mensal de servicos", "PIM-PF", "produção industrial", "producao industrial", "serviços", "servicos", "IBC-Br", "IBC Br", "PIB", "contas nacionais trimestrais", "atividade econômica", "atividade economica", "consumo"),
    "labor": ("desemprego", "desocupação", "desocupacao", "PNAD", "CAGED", "emprego", "criação de empregos", "criacao de empregos", "salários", "salarios", "mercado de trabalho"),
    "monetary_policy": ("Copom", "Selic", "decisão da taxa de juros", "decisao da taxa de juros", "ata do Copom", "Relatório de Política Monetária"),
    "credit": ("crédito", "credito", "inadimplência", "inadimplencia", "concessões", "concessoes"),
    "external": ("balança comercial", "balanca comercial", "conta corrente", "transações correntes", "transacoes correntes", "investimento direto", "reservas internacionais", "exportações", "exportacoes", "importações", "importacoes"),
    "fiscal": ("resultado primário", "resultado primario", "resultado fiscal", "dívida pública", "divida publica", "dívida bruta", "divida bruta", "receitas do governo", "arrecadação", "arrecadacao"),
}
CALENDAR_TOPIC_LABELS = {
    "inflation": "Inflação",
    "consumption_activity": "Consumo e atividade",
    "labor": "Mercado de trabalho",
    "monetary_policy": "Política monetária",
    "credit": "Crédito",
    "external": "Setor externo",
    "fiscal": "Fiscal e dívida",
}


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
    horizons = {}
    for forecast_year, year_values in years.items():
        if not isinstance(year_values, dict):
            continue
        horizons[str(forecast_year)] = {}
        for key in ("IPCA", "Selic", "PIB", "Cambio"):
            node = year_values.get(key) or {}
            current_value = _number(node.get("hoje"))
            four_weeks = _number(node.get("4_sem"))
            horizons[str(forecast_year)][key] = {
                "value": current_value,
                "delta_4w": round(current_value - four_weeks, 4) if current_value is not None and four_weeks is not None else None,
            }
    return {
        "publish_date": focus.get("publish_date"),
        "updated_at": focus.get("updated_at"),
        "source": focus.get("source", "Banco Central do Brasil · Boletim Focus"),
        "year": year,
        "indicators": indicators,
        "horizons": horizons,
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


def _calendar_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("\u00a0", " ")
    if text in {"", "---", "-", "N/A"}:
        return None
    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix in {"K", "M", "B"}:
        multiplier = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}[suffix]
        text = text[:-1].strip()
    text = text.replace("%", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    value_number = _number(text)
    return value_number * multiplier if value_number is not None else None


def _classify_br_calendar_event(event: dict[str, Any]) -> str | None:
    currency = str(event.get("currency") or event.get("País") or event.get("Pais") or "").upper()
    country = str(event.get("country") or event.get("país") or event.get("pais") or "").lower()
    title = " ".join(str(event.get(key) or "") for key in ("event", "Evento", "research", "nome_produto"))
    if currency not in {"BRL", "BR", "BRAZIL", "BRASIL"} and not any(term in country for term in ("brasil", "brazil")):
        return None
    lowered = title.casefold()
    for topic, keywords in CALENDAR_TOPICS.items():
        if any(keyword.casefold() in lowered for keyword in keywords):
            return topic
    return None


def _calendar_event_reading(event: dict[str, Any], topic: str) -> dict[str, Any]:
    title = str(event.get("event") or event.get("Evento") or "Evento")
    actual_raw = event.get("actual") or event.get("Atual")
    forecast_raw = event.get("forecast") or event.get("Previsão") or event.get("Previsao")
    previous_raw = event.get("previous") or event.get("Anterior")
    actual, forecast, previous = map(_calendar_number, (actual_raw, forecast_raw, previous_raw))
    event_date = str(event.get("date") or event.get("Data") or "")
    status = "divulgado" if actual is not None else "aguardando"
    surprise = actual - forecast if actual is not None and forecast is not None else None
    lowered = title.casefold()
    inverse_labor = topic == "labor" and any(term in lowered for term in ("desemprego", "desocupação", "desocupacao"))
    movement = actual - previous if actual is not None and previous is not None else None
    if movement is None:
        movement_label = "Sem comparação com o anterior"
    elif topic == "inflation":
        movement_label = "Inflação acelerou vs. anterior" if movement > 0 else "Inflação desacelerou vs. anterior" if movement < 0 else "Estável vs. anterior"
    elif topic == "consumption_activity":
        movement_label = "Atividade avançou vs. anterior" if movement > 0 else "Atividade recuou vs. anterior" if movement < 0 else "Estável vs. anterior"
    elif topic == "labor":
        stronger = movement < 0 if inverse_labor else movement > 0
        movement_label = ("Mercado de trabalho melhorou vs. anterior" if stronger else "Mercado de trabalho enfraqueceu vs. anterior") if movement != 0 else "Estável vs. anterior"
    else:
        movement_label = "Acima do dado anterior" if movement > 0 else "Abaixo do dado anterior" if movement < 0 else "Estável vs. anterior"

    if surprise is not None:
        if abs(surprise) < 1e-12:
            comparison = "Em linha com o consenso"
            tone = "neutro"
        else:
            if topic == "inflation":
                adverse = surprise > 0
                tone = "inflacionário" if adverse else "desinflacionário"
                comparison = "Surpresa inflacionária" if adverse else "Surpresa desinflacionária"
            elif topic == "labor":
                stronger = surprise < 0 if inverse_labor else surprise > 0
                tone = "mercado de trabalho mais forte" if stronger else "mercado de trabalho mais fraco"
                comparison = "Trabalho mais forte que o consenso" if stronger else "Trabalho mais fraco que o consenso"
            elif topic == "monetary_policy":
                tone = "hawkish" if surprise > 0 else "dovish"
                comparison = "Taxa acima do consenso · viés hawkish" if surprise > 0 else "Taxa abaixo do consenso · viés dovish"
            elif topic == "credit" and any(term in lowered for term in ("inadimpl", "atraso")):
                tone = "crédito mais arriscado" if surprise > 0 else "crédito menos arriscado"
                comparison = "Inadimplência acima do consenso" if surprise > 0 else "Inadimplência abaixo do consenso"
            elif topic in {"consumption_activity", "external", "credit", "fiscal"}:
                tone = "acima" if surprise > 0 else "abaixo"
                comparison = "Acima do consenso" if surprise > 0 else "Abaixo do consenso"
            else:
                tone = "acima" if surprise > 0 else "abaixo"
                comparison = "Acima do consenso" if surprise > 0 else "Abaixo do consenso"
    elif actual is not None:
        comparison = "Divulgado; sem consenso para comparar"
        tone = "sem referência"
    elif event.get("official_release") and event_date <= datetime.now(BR_TZ).date().isoformat():
        comparison = "Data oficial de divulgação; valor/consenso indisponível nesta fonte"
        tone = "sem valor"
        status = "data divulgada"
    elif event.get("official_release"):
        comparison = "Divulgação prevista pelo calendário oficial do IBGE"
        tone = "agenda oficial"
        status = "agendado"
    else:
        comparison = "Aguardando divulgação"
        tone = "pendente"

    return {
        "date": str(event.get("date") or event.get("Data") or ""),
        "time": str(event.get("time") or event.get("Horário") or event.get("Horario") or ""),
        "topic": topic,
        "topic_label": CALENDAR_TOPIC_LABELS[topic],
        "event": title,
        "actual": actual_raw or "---",
        "forecast": forecast_raw or "---",
        "previous": previous_raw or "---",
        "comparison": comparison,
        "movement_vs_previous": movement_label,
        "tone": tone,
        "status": status,
        "source": event.get("source") or "Calendário econômico integrado",
        "reference_period": event.get("reference_period", ""),
    }


def _br_calendar_snapshot(events: Any) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {topic: [] for topic in CALENDAR_TOPICS}
    deduplicated = {}
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        topic = _classify_br_calendar_event(event)
        if topic:
            key = (
                str(event.get("date") or event.get("Data") or ""),
                str(event.get("time") or event.get("Horário") or event.get("Horario") or ""),
                str(event.get("currency") or event.get("País") or event.get("Pais") or "").casefold(),
                " ".join(str(event.get("event") or event.get("Evento") or "").casefold().split()),
            )
            existing = deduplicated.get(key, {})
            deduplicated[key] = {**event, **existing, **{k: v for k, v in event.items() if _has_calendar_value(v)}}
    for event in deduplicated.values():
        topic = _classify_br_calendar_event(event)
        if topic:
            grouped[topic].append(_calendar_event_reading(event, topic))
    for items in grouped.values():
        items.sort(key=lambda item: (item["date"], item["time"]), reverse=True)
    all_events = [item for items in grouped.values() for item in items]
    released = [item for item in all_events if item["status"] in {"divulgado", "data divulgada"}]
    return {
        "groups": grouped,
        "total_events": len(all_events),
        "latest_date": max((item["date"] for item in all_events), default=None),
        "latest_released_date": max((item["date"] for item in released), default=None),
        "earliest_date": min((item["date"] for item in all_events), default=None),
        "official_release_count": sum(1 for item in all_events if str(item.get("source", "")).startswith("IBGE")),
        "source": "Calendário econômico integrado; cobertura brasileira filtrada por moeda/país e palavras-chave",
    }


def _has_calendar_value(value: Any) -> bool:
    return value is not None and str(value).strip().casefold() not in {"", "---", "-", "n/a", "none"}


def build_monitor_br_payload(global_data: Any = None, focus: Any = None, di: Any = None, flow: Any = None, calendar_events: Any = None, calendar_history: Any = None) -> dict[str, Any]:
    """Build a payload from official series and existing market snapshots."""
    errors: list[str] = []
    try:
        from execution.monitor_br_history import fetch_monitor_br_history
        official_history = fetch_monitor_br_history()
        errors.extend(official_history.get("errors", []))
    except Exception as exc:
        official_history = {"series": [], "errors": [f"Histórico oficial: {type(exc).__name__}: {exc}"]}
        errors.extend(official_history["errors"])
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
    try:
        from execution.monetary_policy import build_monetary_policy_snapshot, fetch_copom_documents
        copom_documents = fetch_copom_documents()
    except Exception as exc:
        copom_documents = []
        errors.append(f"Publicações do Copom: {type(exc).__name__}: {exc}")
    current_selic = selic.get("value")
    front_di = _number(curve[0].get("rate", curve[0].get("price"))) if curve else None
    selic_di_spread = round(front_di - current_selic, 3) if front_di is not None and current_selic is not None else None
    calendar_br = _br_calendar_snapshot(
        [
            *(calendar_events if isinstance(calendar_events, list) else []),
            *(calendar_history.get("events", []) if isinstance(calendar_history, dict) else []),
        ]
    )

    payload = {
        "schema_version": "monitor_br_v1",
        "updated_at": datetime.now(BR_TZ).isoformat(timespec="seconds"),
        "sources": {"official": "BCB SGS + IBGE SIDRA", "market": "Snapshot central do dashboard", "curve": (di or {}).get("source") if isinstance(di, dict) else None},
        "official": {"selic": selic, "ipca": ipca, "ibc_br": ibc_br, "ibge_ipca_monthly": ibge_ipca},
        "official_history": official_history,
        "focus": _focus_snapshot(focus),
        "monetary_policy": build_monetary_policy_snapshot(selic, _focus_snapshot(focus), copom_documents),
        "foreign_flow": _flow_snapshot(flow),
        "calendar_br": calendar_br,
        "calendar_history": {
            "updated_at": calendar_history.get("updated_at") if isinstance(calendar_history, dict) else None,
            "backfill_status": calendar_history.get("backfill_status") if isinstance(calendar_history, dict) else "not_available",
            "event_count": calendar_history.get("event_count", 0) if isinstance(calendar_history, dict) else 0,
            "retention_days": calendar_history.get("retention_days") if isinstance(calendar_history, dict) else None,
            "ibge_calendar_updated_at": calendar_history.get("ibge_calendar_updated_at") if isinstance(calendar_history, dict) else None,
            "ibge_calendar_status": calendar_history.get("ibge_calendar_status") if isinstance(calendar_history, dict) else "not_available",
            "official_release_count": calendar_br.get("official_release_count", 0),
        },
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
