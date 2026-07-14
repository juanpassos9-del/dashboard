import json
import math
import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT_DIR / ".tmp"
CACHE_PATH = TMP_DIR / "macro_fred_monitor.json"
HISTORY_PATH = TMP_DIR / "macro_fred_history.json"
CACHE_TTL_SECONDS = 6 * 60 * 60
BR_TZ = ZoneInfo("America/Sao_Paulo")


FRED_SERIES = {
    "inflation": [
        {"id": "CPIAUCSL", "name": "CPI", "kind": "price_index", "weight": 1.0},
        {"id": "CPILFESL", "name": "Core CPI", "kind": "price_index", "weight": 1.2},
        {"id": "PCEPI", "name": "PCE", "kind": "price_index", "weight": 1.0},
        {"id": "PCEPILFE", "name": "Core PCE", "kind": "price_index", "weight": 1.3},
        {"id": "PPIACO", "name": "PPI", "kind": "price_index", "weight": 0.8},
        {"id": "T5YIE", "name": "5Y Breakeven", "kind": "rate", "weight": 0.8},
        {"id": "T10YIE", "name": "10Y Breakeven", "kind": "rate", "weight": 0.7},
    ],
    "labor": [
        {"id": "PAYEMS", "name": "Payroll", "kind": "level_diff", "weight": 1.0},
        {"id": "UNRATE", "name": "Unemployment Rate", "kind": "rate_inverted", "weight": 1.1},
        {"id": "ICSA", "name": "Initial Claims", "kind": "level_inverted", "weight": 0.9},
        {"id": "CES0500000003", "name": "Average Hourly Earnings", "kind": "price_index", "weight": 0.8},
        {"id": "U6RATE", "name": "U-6 Unemployment", "kind": "rate_inverted", "weight": 0.8},
    ],
    "growth": [
        {"id": "INDPRO", "name": "Industrial Production", "kind": "price_index", "weight": 1.0},
        {"id": "RSAFS", "name": "Retail Sales", "kind": "price_index", "weight": 1.0},
        {"id": "PCEC96", "name": "Real PCE", "kind": "price_index", "weight": 1.0},
        {"id": "HOUST", "name": "Housing Starts", "kind": "price_index", "weight": 0.8},
        {"id": "PERMIT", "name": "Building Permits", "kind": "price_index", "weight": 0.8},
        {"id": "TCU", "name": "Capacity Utilization", "kind": "rate", "weight": 0.8},
        {"id": "CFNAI", "name": "CFNAI", "kind": "level", "weight": 1.0},
    ],
    "financial_conditions": [
        {"id": "DFF", "name": "Fed Funds", "kind": "rate_tightening", "weight": 0.8},
        {"id": "DGS2", "name": "US 2Y", "kind": "rate_tightening", "weight": 1.0},
        {"id": "DGS10", "name": "US 10Y", "kind": "rate_tightening", "weight": 1.0},
        {"id": "T10Y2Y", "name": "10Y-2Y Spread", "kind": "curve", "weight": 1.0},
        {"id": "BAMLH0A0HYM2", "name": "HY Spread", "kind": "rate_tightening", "weight": 1.2},
        {"id": "NFCI", "name": "NFCI", "kind": "level_tightening", "weight": 1.1},
        {"id": "VIXCLS", "name": "VIX", "kind": "level_tightening", "weight": 0.9},
        {"id": "DTWEXBGS", "name": "Trade Weighted Dollar", "kind": "price_tightening", "weight": 0.9},
    ],
    "recession": [
        {"id": "SAHMREALTIME", "name": "Sahm Rule", "kind": "level_tightening", "weight": 1.2},
        {"id": "RECPROUSM156N", "name": "Recession Probability", "kind": "level_tightening", "weight": 1.1},
    ],
}


EVENT_RULES = [
    ("cpi", "inflation", 1),
    ("pce", "inflation", 1),
    ("ppi", "inflation", 1),
    ("prices", "inflation", 1),
    ("precos", "inflation", 1),
    ("inflation", "inflation", 1),
    ("payroll", "labor", 1),
    ("nonfarm", "labor", 1),
    ("jolts", "labor", 1),
    ("unemployment", "labor", -1),
    ("desemprego", "labor", -1),
    ("claims", "labor", -1),
    ("jobless", "labor", -1),
    ("retail sales", "growth", 1),
    ("vendas no varejo", "growth", 1),
    ("ism", "growth", 1),
    ("pmi", "growth", 1),
    ("gdp", "growth", 1),
    ("pib", "growth", 1),
    ("industrial production", "growth", 1),
    ("producao industrial", "growth", 1),
    ("fomc", "fed", 1),
    ("fed", "fed", 1),
    ("copom", "brl", 1),
    ("selic", "brl", 1),
    ("ipca", "brl_inflation", 1),
]


BLOCK_LABELS = {
    "inflation": "Inflação",
    "labor": "Mercado de trabalho",
    "growth": "Atividade",
    "financial_conditions": "Condições financeiras",
    "recession": "Risco de recessão",
}


def _read_secret_file(name: str) -> str:
    secrets_path = ROOT_DIR / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""
    try:
        import tomllib

        with secrets_path.open("rb") as fh:
            data = tomllib.load(fh)
        value = data.get(name)
        return str(value) if value else ""
    except Exception:
        return ""


def _fred_api_key() -> str:
    for name in ("FRED_API_KEY", "FRED_KEY"):
        value = os.getenv(name) or _read_secret_file(name)
        if not value:
            try:
                import streamlit as st

                value = st.secrets.get(name, "")
            except Exception:
                value = ""
        if value:
            return str(value)
    return ""


def _to_float(value: Any) -> float | None:
    if value in (None, "", ".", "---"):
        return None
    try:
        text = str(value).strip().replace("\u00a0", " ")
        text = text.replace("%", "").replace("K", "").replace("k", "")
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        return float(text)
    except Exception:
        return None


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    number = _to_float(value)
    if number is None or not math.isfinite(number):
        return "---"
    return f"{number:.{digits}f}{suffix}"


def _clip_score(value: float, lower: float = -3.0, upper: float = 3.0) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(min(value, upper), lower)


def _fetch_fred_observations(series_id: str, api_key: str, years: int = 15, limit: int = 240) -> list[dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": (datetime.now(BR_TZ) - timedelta(days=365 * years)).strftime("%Y-%m-%d"),
        "sort_order": "desc",
        "limit": limit,
    }
    response = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=12)
    response.raise_for_status()
    observations = []
    for item in response.json().get("observations", []):
        value = _to_float(item.get("value"))
        if value is None:
            continue
        observations.append({"date": item.get("date"), "value": value})
    observations.reverse()
    return observations


def _pct_change(values: list[float], periods: int) -> float | None:
    if len(values) <= periods:
        return None
    prev = values[-1 - periods]
    if prev == 0:
        return None
    return (values[-1] / prev - 1) * 100


def _zscore(values: list[float], window: int = 120) -> float | None:
    sample = values[-window:] if len(values) >= window else values
    if len(sample) < 12:
        return None
    avg = statistics.fmean(sample)
    std = statistics.pstdev(sample)
    if std <= 0:
        return None
    return (values[-1] - avg) / std


def _percentile(values: list[float]) -> float | None:
    if len(values) < 12:
        return None
    current = values[-1]
    below = sum(1 for value in values if value <= current)
    return round(100 * below / len(values), 1)


def _series_score(values: list[float], kind: str) -> tuple[float, str]:
    if len(values) < 4:
        return 0.0, "Histórico insuficiente"
    latest = values[-1]
    previous = values[-2]
    z = _zscore(values)
    mom_1 = latest - previous
    yoy = _pct_change(values, 12)
    mom_3 = None
    if len(values) > 3:
        mom_3 = latest - values[-4]

    if kind == "price_index":
        score = 0.0
        if yoy is not None:
            score += max(min((yoy - 2.0) / 2.0, 2), -2)
        if mom_3 is not None:
            score += max(min(mom_3 / max(abs(latest), 1) * 100, 2), -2)
        return _clip_score(score), "Índice acelerando" if score > 0.4 else "Índice desacelerando" if score < -0.4 else "Índice estável"
    if kind == "level_diff":
        score = (values[-1] - values[-4]) / max(abs(values[-4]), 1) * 100 if len(values) > 4 else mom_1
        return _clip_score(score), "Ganho de tração" if score > 0 else "Perdendo tração"
    if kind in {"rate", "level"}:
        score = z if z is not None else mom_1
        return _clip_score(score), "Acima da média histórica" if score > 0.4 else "Abaixo da média histórica" if score < -0.4 else "Perto da média"
    if kind in {"rate_inverted", "level_inverted"}:
        score = -(z if z is not None else mom_1)
        return _clip_score(score), "Melhora no trabalho/risco" if score > 0.4 else "Piora no trabalho/risco" if score < -0.4 else "Neutro"
    if kind in {"rate_tightening", "level_tightening", "price_tightening"}:
        score = z if z is not None else mom_1
        return _clip_score(score), "Aperto financeiro" if score > 0.4 else "Alívio financeiro" if score < -0.4 else "Neutro"
    if kind == "curve":
        score = -1 if latest < -0.5 else 1 if latest > 0.5 else 0
        return score, "Curva normal" if score > 0 else "Curva invertida" if score < 0 else "Curva pouco inclinada"
    return 0.0, "Neutro"


def _classify_event(event: dict[str, Any]) -> tuple[str, str, int]:
    text = str(event.get("event") or event.get("Evento") or "").lower()
    for keyword, block, direction in EVENT_RULES:
        if keyword in text:
            return block, keyword, direction
    return "other", "other", 1


def _canonical_block(block: str) -> str:
    if block == "brl_inflation":
        return "inflation"
    if block == "brl":
        return "financial_conditions"
    return block


def _event_surprise(event: dict[str, Any]) -> dict[str, Any]:
    actual = _to_float(event.get("actual") or event.get("Atual"))
    forecast = _to_float(event.get("forecast") or event.get("Previsão") or event.get("Previsao"))
    previous = _to_float(event.get("previous") or event.get("Anterior"))
    impact = str(event.get("impact") or event.get("Impacto") or "").upper()
    bull_count = int(_to_float(event.get("bull_count")) or (3 if impact == "HIGH" else 2 if impact == "MEDIUM" else 1))
    block, keyword, direction = _classify_event(event)
    surprise = None
    status = "aguardando"
    base = None
    if actual is not None and forecast is not None:
        surprise = actual - forecast
        base = "projecao"
        status = "divulgado"
    elif actual is not None and previous is not None:
        surprise = actual - previous
        base = "anterior"
        status = "divulgado"
    elif forecast is not None and previous is not None:
        surprise = forecast - previous
        base = "projecao_vs_anterior"
        status = "pre-evento"

    weighted = 0.0
    if surprise is not None:
        scale = max(abs(forecast or previous or 1), 1)
        normalized = max(min((surprise / scale) * 10, 2), -2)
        weighted = normalized * direction * max(bull_count, 1)

    if block in {"inflation", "brl_inflation"}:
        if weighted > 0.25:
            macro = "inflacao_mais_quente"
            read = "pressiona inflação e juros"
        elif weighted < -0.25:
            macro = "inflacao_mais_fria"
            read = "favorece desinflação e alívio de juros"
        else:
            macro = "inflacao_neutra"
            read = "não muda a leitura de inflação"
    elif block == "labor":
        if weighted > 0.25:
            macro = "trabalho_apertado"
            read = "atividade/trabalho resiliente, viés hawkish"
        elif weighted < -0.25:
            macro = "trabalho_enfraquecendo"
            read = "trabalho esfriando, viés dovish"
        else:
            macro = "trabalho_neutro"
            read = "trabalho sem surpresa relevante"
    elif block == "growth":
        if weighted > 0.25:
            macro = "atividade_forte"
            read = "crescimento resiliente, pode sustentar juros"
        elif weighted < -0.25:
            macro = "atividade_fraca"
            read = "desaceleração de atividade"
        else:
            macro = "atividade_neutra"
            read = "atividade sem surpresa relevante"
    else:
        macro = "neutro"
        read = "evento com baixa leitura quantitativa no motor"

    return {
        "date": event.get("date") or event.get("Data") or "",
        "time": event.get("time") or event.get("Horário") or event.get("Horario") or "",
        "currency": event.get("currency") or event.get("País") or event.get("Pais") or "",
        "event": event.get("event") or event.get("Evento") or "Evento",
        "impact": impact or "LOW",
        "bull_count": bull_count,
        "actual": event.get("actual") or event.get("Atual") or "---",
        "forecast": event.get("forecast") or event.get("Previsão") or event.get("Previsao") or "---",
        "previous": event.get("previous") or event.get("Anterior") or "---",
        "status": status,
        "block": block,
        "canonical_block": _canonical_block(block),
        "keyword": keyword,
        "base": base,
        "surprise": surprise,
        "weighted_score": round(weighted, 2),
        "macro": macro,
        "interpretation": read,
    }


def _filter_week_events(calendar_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = datetime.now(BR_TZ).date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    result = []
    for event in calendar_events or []:
        currency = str(event.get("currency") or event.get("País") or event.get("Pais") or "").upper()
        if currency not in {"USD", "BRL"}:
            continue
        date_text = str(event.get("date") or event.get("Data") or "")[:10]
        try:
            event_date = datetime.fromisoformat(date_text).date()
        except Exception:
            event_date = today
        if start <= event_date <= end:
            result.append(_event_surprise(event))
    result.sort(key=lambda item: (item.get("date", ""), item.get("time", "")))
    return result


def _block_summary(block: str, series_results: list[dict[str, Any]], event_results: list[dict[str, Any]]) -> dict[str, Any]:
    structural_scores = []
    surprise_scores = []
    drivers = []
    for item in series_results:
        if item.get("block") == block and item.get("score") is not None:
            structural_scores.append(float(item["score"]) * float(item.get("weight") or 1))
            drivers.append(f"{item['name']}: {item['reading']}")
    surprise_scores = [float(item.get("weighted_score") or 0) for item in event_results if item.get("canonical_block", item.get("block")) == block]
    if surprise_scores:
        drivers.extend([f"{item['event']}: {item['interpretation']}" for item in event_results if item.get("canonical_block", item.get("block")) == block][:3])

    structural_score = statistics.fmean(structural_scores) if structural_scores else 0.0
    surprise_score = statistics.fmean(surprise_scores) if surprise_scores else 0.0
    score = (0.68 * structural_score) + (0.32 * surprise_score)
    if block == "inflation":
        label = "Inflação subindo" if score > 0.35 else "Inflação cedendo" if score < -0.35 else "Inflação lateral"
        structural_label = "FRED pressionado" if structural_score > 0.35 else "FRED desinflacionário" if structural_score < -0.35 else "FRED lateral"
        surprise_label = "Surpresa inflacionária" if surprise_score > 0.35 else "Surpresa desinflacionária" if surprise_score < -0.35 else "Surpresa neutra"
    elif block == "labor":
        label = "Trabalho apertado" if score > 0.35 else "Trabalho enfraquecendo" if score < -0.35 else "Trabalho neutro"
        structural_label = "FRED apertado" if structural_score > 0.35 else "FRED afrouxando" if structural_score < -0.35 else "FRED lateral"
        surprise_label = "Surpresa hawkish" if surprise_score > 0.35 else "Surpresa dovish" if surprise_score < -0.35 else "Surpresa neutra"
    elif block == "growth":
        label = "Atividade aquecida" if score > 0.35 else "Atividade desacelerando" if score < -0.35 else "Atividade neutra"
        structural_label = "FRED resiliente" if structural_score > 0.35 else "FRED fraco" if structural_score < -0.35 else "FRED lateral"
        surprise_label = "Surpresa positiva" if surprise_score > 0.35 else "Surpresa negativa" if surprise_score < -0.35 else "Surpresa neutra"
    elif block == "financial_conditions":
        label = "Condições apertando" if score > 0.35 else "Condições afrouxando" if score < -0.35 else "Condições neutras"
        structural_label = "FRED apertado" if structural_score > 0.35 else "FRED frouxo" if structural_score < -0.35 else "FRED lateral"
        surprise_label = "Choque hawkish" if surprise_score > 0.35 else "Choque dovish" if surprise_score < -0.35 else "Choque neutro"
    elif block == "recession":
        label = "Risco de recessão maior" if score > 0.35 else "Risco de recessão menor" if score < -0.35 else "Risco estável"
        structural_label = "Risco estrutural maior" if structural_score > 0.35 else "Risco estrutural menor" if structural_score < -0.35 else "Risco estrutural estável"
        surprise_label = "Surpresa aumenta risco" if surprise_score > 0.35 else "Surpresa reduz risco" if surprise_score < -0.35 else "Surpresa neutra"
    else:
        label = "Neutro"
        structural_label = "Estrutural neutro"
        surprise_label = "Surpresa neutra"
    delta_label = "surpresa reforça FRED" if structural_score * surprise_score > 0.1 else "surpresa contraria FRED" if structural_score * surprise_score < -0.1 else "surpresa sem conflito relevante"
    return {
        "block": block,
        "score": round(score, 2),
        "structural_score": round(structural_score, 2),
        "surprise_score": round(surprise_score, 2),
        "label": label,
        "structural_label": structural_label,
        "surprise_label": surprise_label,
        "delta_label": delta_label,
        "drivers": drivers[:5],
        "series_count": sum(1 for item in series_results if item.get("block") == block),
        "event_count": sum(1 for item in event_results if item.get("canonical_block", item.get("block")) == block),
    }


def _macro_regime(blocks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    inflation = blocks.get("inflation", {}).get("score", 0)
    growth = blocks.get("growth", {}).get("score", 0)
    labor = blocks.get("labor", {}).get("score", 0)
    financial = blocks.get("financial_conditions", {}).get("score", 0)
    recession = blocks.get("recession", {}).get("score", 0)
    activity = statistics.fmean([growth, labor])
    if inflation > 0.35 and activity > 0.25:
        regime = "Overheating"
        summary = "Inflação pressionada com atividade ainda resiliente."
    elif inflation > 0.35 and activity <= 0.25:
        regime = "Stagflation risk"
        summary = "Inflação pressionada com sinais de perda de atividade."
    elif inflation < -0.35 and activity > 0.25:
        regime = "Goldilocks"
        summary = "Desinflação com crescimento ainda positivo."
    elif inflation < -0.35 and activity <= 0.25:
        regime = "Slowdown"
        summary = "Inflação cedendo, mas atividade perde tração."
    else:
        regime = "Transição"
        summary = "Dados mistos, sem regime macro dominante."

    fed_score = inflation + 0.45 * labor + 0.35 * growth + 0.25 * financial - 0.35 * recession
    fed_bias = "Hawkish" if fed_score > 0.5 else "Dovish" if fed_score < -0.5 else "Manter/Neutro"
    risk_bias = "Risk-off" if financial > 0.45 or recession > 0.55 or (inflation > 0.5 and growth < 0) else "Risk-on" if inflation < 0 and growth > 0 and financial < 0.35 else "Neutro/seletivo"
    confidence_inputs = sum(1 for block in blocks.values() if block.get("series_count", 0) or block.get("event_count", 0))
    confidence = "Alta" if confidence_inputs >= 5 else "Média" if confidence_inputs >= 3 else "Baixa"
    return {
        "regime": regime,
        "summary": summary,
        "fed_bias": fed_bias,
        "risk_bias": risk_bias,
        "macro_score": round(statistics.fmean([inflation, activity, -financial, -recession]), 2),
        "confidence": confidence,
    }


def _weekly_narrative(blocks: dict[str, dict[str, Any]], regime: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    inflation = blocks.get("inflation", {})
    labor = blocks.get("labor", {})
    growth = blocks.get("growth", {})
    financial = blocks.get("financial_conditions", {})
    recession = blocks.get("recession", {})
    event_count = len(events)
    released_count = sum(1 for item in events if item.get("status") == "divulgado")
    pre_count = sum(1 for item in events if item.get("status") == "pre-evento")
    bullets = [
        f"Inflação: {inflation.get('label', 'neutra')} ({inflation.get('structural_label', 'FRED neutro')}; {inflation.get('surprise_label', 'surpresa neutra')}).",
        f"Atividade: {growth.get('label', 'neutra')} ({growth.get('structural_label', 'FRED neutro')}; {growth.get('surprise_label', 'surpresa neutra')}).",
        f"Trabalho: {labor.get('label', 'neutro')} ({labor.get('structural_label', 'FRED neutro')}; {labor.get('surprise_label', 'surpresa neutra')}).",
        f"Condições financeiras: {financial.get('label', 'neutras')} e {recession.get('label', 'risco estável')}.",
        f"Eventos: {event_count} eventos USD/BRL na semana, {released_count} divulgados e {pre_count} em modo pré-evento.",
    ]
    conclusion = (
        f"Regime {regime.get('regime', 'Transição')}; Fed {regime.get('fed_bias', 'neutro')}; "
        f"risco {regime.get('risk_bias', 'neutro/seletivo')}. "
        "A leitura combina tendência estrutural do FRED com a surpresa marginal dos dados da semana."
    )
    return {"bullets": bullets, "conclusion": conclusion}


def _history_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    blocks = payload.get("blocks", {}) if isinstance(payload, dict) else {}
    regime = payload.get("regime", {}) if isinstance(payload, dict) else {}
    return {
        "updated_at": payload.get("updated_at"),
        "regime": regime.get("regime"),
        "fed_bias": regime.get("fed_bias"),
        "risk_bias": regime.get("risk_bias"),
        "macro_score": regime.get("macro_score"),
        "confidence": regime.get("confidence"),
        "inflation": blocks.get("inflation", {}).get("score"),
        "growth": blocks.get("growth", {}).get("score"),
        "labor": blocks.get("labor", {}).get("score"),
        "financial_conditions": blocks.get("financial_conditions", {}).get("score"),
        "recession": blocks.get("recession", {}).get("score"),
        "events_count": len(payload.get("events", []) or []),
    }


def load_macro_history(limit: int = 12) -> list[dict[str, Any]]:
    try:
        if not HISTORY_PATH.exists():
            return []
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return data[-limit:]
    except Exception:
        return []


def _append_macro_history(payload: dict[str, Any], limit: int = 40) -> None:
    try:
        history = load_macro_history(limit=limit)
        snapshot = _history_snapshot(payload)
        if not snapshot.get("updated_at"):
            return
        if history and history[-1].get("updated_at") == snapshot.get("updated_at"):
            return
        if history:
            try:
                last_dt = datetime.fromisoformat(str(history[-1].get("updated_at")))
                new_dt = datetime.fromisoformat(str(snapshot.get("updated_at")))
                same_state = all(
                    history[-1].get(key) == snapshot.get(key)
                    for key in ("regime", "fed_bias", "risk_bias", "macro_score", "inflation", "growth", "labor")
                )
                if same_state and abs((new_dt - last_dt).total_seconds()) < 300:
                    return
            except Exception:
                pass
        history.append(snapshot)
        HISTORY_PATH.write_text(json.dumps(history[-limit:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def build_macro_fred_monitor(calendar_events: list[dict[str, Any]] | None = None, force_refresh: bool = False) -> dict[str, Any]:
    if not force_refresh:
        cached = load_cached_macro_fred_monitor()
        if cached:
            return cached

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    api_key = _fred_api_key()
    series_results: list[dict[str, Any]] = []
    errors = []

    if api_key:
        for block, series_list in FRED_SERIES.items():
            for config in series_list:
                try:
                    observations = _fetch_fred_observations(config["id"], api_key)
                    values = [obs["value"] for obs in observations]
                    if len(values) < 3:
                        continue
                    score, reading = _series_score(values, config["kind"])
                    latest = observations[-1]
                    previous = observations[-2]
                    series_results.append({
                        "block": block,
                        "series_id": config["id"],
                        "name": config["name"],
                        "date": latest["date"],
                        "value": latest["value"],
                        "previous": previous["value"],
                        "delta": latest["value"] - previous["value"],
                        "z_score": _zscore(values),
                        "percentile": _percentile(values),
                        "score": round(score, 2),
                        "reading": reading,
                        "weight": config.get("weight", 1),
                    })
                except Exception as exc:
                    errors.append(f"{config['id']}: {exc}")
    else:
        errors.append("FRED_API_KEY ausente.")

    event_results = _filter_week_events(calendar_events or [])
    blocks = {
        block: _block_summary(block, series_results, event_results)
        for block in ["inflation", "labor", "growth", "financial_conditions", "recession"]
    }
    regime = _macro_regime(blocks)
    narrative = _weekly_narrative(blocks, regime, event_results)
    top_events = sorted(event_results, key=lambda item: (abs(float(item.get("weighted_score") or 0)), item.get("bull_count", 1)), reverse=True)[:8]
    top_series = sorted(series_results, key=lambda item: abs(float(item.get("score") or 0)), reverse=True)[:10]
    payload = {
        "updated_at": datetime.now(BR_TZ).isoformat(timespec="seconds"),
        "source": "FRED + Calendario Economico",
        "fred_enabled": bool(api_key),
        "regime": regime,
        "weekly_narrative": narrative,
        "blocks": blocks,
        "series": series_results,
        "top_series": top_series,
        "events": event_results,
        "top_events": top_events,
        "errors": errors[:10],
    }
    try:
        CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    _append_macro_history(payload)
    return payload


def load_cached_macro_fred_monitor(max_age_seconds: int = CACHE_TTL_SECONDS) -> dict[str, Any] | None:
    try:
        if not CACHE_PATH.exists():
            return None
        age = datetime.now().timestamp() - CACHE_PATH.stat().st_mtime
        if age > max_age_seconds:
            return None
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    calendar_path = ROOT_DIR / "calendario_economico.json"
    calendar = []
    if calendar_path.exists():
        try:
            calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
        except Exception:
            calendar = []
    data = build_macro_fred_monitor(calendar_events=calendar, force_refresh=True)
    print(json.dumps({
        "updated_at": data.get("updated_at"),
        "regime": data.get("regime"),
        "series": len(data.get("series", [])),
        "events": len(data.get("events", [])),
        "errors": data.get("errors", [])[:3],
    }, ensure_ascii=False, indent=2))
