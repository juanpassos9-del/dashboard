import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class EconomicEvent:
    event_id: str
    datetime: Optional[datetime]
    country: str
    currency: str
    event: str
    category: str
    importance: str
    previous_raw: str
    forecast_raw: str
    actual_raw: str
    previous: Optional[float]
    forecast: Optional[float]
    actual: Optional[float]
    unit: Optional[str]
    source: str = "Investing"


def _first(raw: dict, aliases: list[str], default=""):
    lower_map = {str(k).lower(): v for k, v in raw.items()}
    for alias in aliases:
        if alias in raw and raw[alias] not in [None, ""]:
            return raw[alias]
        value = lower_map.get(alias.lower())
        if value not in [None, ""]:
            return value
    return default


def _plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def parse_economic_value(value) -> tuple[Optional[float], Optional[str]]:
    if value is None:
        return None, None
    raw = str(value).strip()
    if not raw or raw in ["---", "-", "N/A", "nan"]:
        return None, None

    raw = raw.replace("−", "-")
    multiplier = 1.0
    unit = "index"
    if raw.endswith("%"):
        unit = "%"
        raw = raw[:-1]
    elif raw.upper().endswith("K"):
        unit = "abs"
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.upper().endswith("M"):
        unit = "abs"
        multiplier = 1_000_000
        raw = raw[:-1]
    elif raw.upper().endswith("B"):
        unit = "abs"
        multiplier = 1_000_000_000
        raw = raw[:-1]

    raw = raw.replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")

    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None, None
    return float(match.group(0)) * multiplier, unit


def infer_event_category(event_name: str) -> str:
    name = _plain_text(event_name)
    if any(x in name for x in ["cpi", "consumer price", "pce", "ppi", "inflation", "ipca", "core cpi", "core pce", "precos", "preco"]):
        return "inflation"
    if any(x in name for x in ["nonfarm", "payroll", "unemployment", "jobless", "jolts", "adp", "earnings", "emprego", "desemprego"]):
        return "employment"
    if any(x in name for x in ["gdp", "pmi", "ism", "retail sales", "industrial production", "durable goods", "consumer confidence", "chicago pmi", "gastos de construcao", "construcao", "novos pedidos", "industrial", "manufatureiro"]):
        return "activity"
    if any(x in name for x in ["interest rate", "rate decision", "fomc", "fed", "copom", "selic", "ecb", "boe", "boj", "monetary", "banco central"]):
        return "central_bank"
    if any(x in name for x in ["crude oil inventories", "gasoline inventories", "distillate", "oil inventories", "estoques de petroleo"]):
        return "commodities"
    if any(x in name for x in ["china", "caixin", "new loans", "aggregate financing"]):
        return "china"
    return "other"


def is_higher_worse(event_name: str) -> bool:
    name = _plain_text(event_name)
    return any(x in name for x in [
        "unemployment rate",
        "initial jobless claims",
        "continuing jobless claims",
        "jobless claims",
        "crude oil inventories",
        "gasoline inventories",
        "distillate inventories",
    ])


def normalize_event(raw_event: dict) -> EconomicEvent:
    date_value = _first(raw_event, ["datetime", "date", "data", "horario", "data_hora"])
    time_value = _first(raw_event, ["time", "hora"], "")
    event_name = str(_first(raw_event, ["event", "indicador", "evento", "name", "title"], "Evento"))
    actual_raw = str(_first(raw_event, ["actual", "realizado", "atual"], "---"))
    forecast_raw = str(_first(raw_event, ["forecast", "previsao", "previsão", "consensus", "consenso"], "---"))
    previous_raw = str(_first(raw_event, ["previous", "anterior"], "---"))
    actual, actual_unit = parse_economic_value(actual_raw)
    forecast, forecast_unit = parse_economic_value(forecast_raw)
    previous, previous_unit = parse_economic_value(previous_raw)

    dt = None
    try:
        if date_value and time_value and len(str(date_value)) == 10:
            dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
        elif date_value:
            dt = datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
    except Exception:
        dt = None

    event_id = "|".join([str(date_value), str(time_value), str(_first(raw_event, ["currency", "moeda"], "")), event_name])
    return EconomicEvent(
        event_id=event_id,
        datetime=dt,
        country=str(_first(raw_event, ["country", "pais", "país"], "")),
        currency=str(_first(raw_event, ["currency", "moeda"], "")),
        event=event_name,
        category=infer_event_category(event_name),
        importance=str(_first(raw_event, ["importance", "importancia", "importância", "impact"], "")),
        previous_raw=previous_raw,
        forecast_raw=forecast_raw,
        actual_raw=actual_raw,
        previous=previous,
        forecast=forecast,
        actual=actual,
        unit=actual_unit or forecast_unit or previous_unit,
        source=str(raw_event.get("source", "Investing")),
    )


def calculate_surprise(event: EconomicEvent) -> tuple[Optional[float], Optional[float], str]:
    benchmark = event.forecast
    benchmark_label = ""
    if benchmark is None and event.previous is not None:
        benchmark = event.previous
        benchmark_label = " vs anterior"

    if event.actual is None or benchmark is None:
        return None, None, "indisponivel"
    surprise_value = event.actual - benchmark
    surprise_pct = None if benchmark == 0 else surprise_value / abs(benchmark)

    event_name = _plain_text(event.event)
    if event.category in ["inflation", "central_bank"] or event.unit == "%":
        abs_value = abs(surprise_value)
        if abs_value < 0.05:
            label = "em linha"
        elif surprise_value >= 0.15:
            label = "muito acima"
        elif surprise_value > 0.05:
            label = "acima"
        elif surprise_value <= -0.15:
            label = "muito abaixo"
        else:
            label = "abaixo"
    elif "pmi" in event_name or "ism" in event_name or "confidence" in event_name:
        abs_value = abs(surprise_value)
        if abs_value < 0.3:
            label = "em linha"
        elif surprise_value >= 1.0:
            label = "muito acima"
        elif surprise_value > 0.3:
            label = "acima"
        elif surprise_value <= -1.0:
            label = "muito abaixo"
        else:
            label = "abaixo"
    else:
        if surprise_pct is None or abs(surprise_pct) < 0.05:
            label = "em linha"
        elif surprise_pct >= 0.20:
            label = "muito acima"
        elif surprise_pct > 0.05:
            label = "acima"
        elif surprise_pct <= -0.20:
            label = "muito abaixo"
        else:
            label = "abaixo"
    return surprise_value, surprise_pct, f"{label}{benchmark_label}"


def _market_change(global_data: dict, target_names: list[str]) -> Optional[float]:
    categories = (global_data or {}).get("categories", global_data or {})
    for assets in categories.values():
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if asset.get("name") in target_names:
                try:
                    return float(asset.get("change"))
                except Exception:
                    return None
    return None


def _risk_classification(score: int) -> str:
    if score >= 70:
        return "Risk-on forte"
    if score >= 30:
        return "Risk-on moderado"
    if score > -30:
        return "Neutro"
    if score > -70:
        return "Risk-off moderado"
    return "Risk-off forte"


def interpret_event(raw_event: dict, global_data: Optional[dict] = None) -> dict:
    event = normalize_event(raw_event)
    surprise_value, surprise_pct, surprise_label = calculate_surprise(event)

    released = event.actual is not None
    if not released:
        return {
            "status": "Aguardando divulgacao",
            "event": event.event,
            "category": event.category,
            "surprise_label": "aguardando",
            "macro_shock": "Aguardando dado realizado",
            "dominant_regime": "Neutro",
            "risk_score": 0,
            "risk_classification": "Neutro",
            "confidence": "Baixa",
            "operational_summary": "Aguardando o campo Atual do calendario Investing. Assim que o dado for divulgado, a IA calcula surpresa, choque macro e vies operacional.",
            "asset_impacts": {},
            "surprise_value": None,
            "surprise_pct": None,
        }

    surprise_direction = surprise_label.replace(" vs anterior", "")

    direction = 0
    if surprise_direction in ["acima", "muito acima"]:
        direction = 1
    elif surprise_direction in ["abaixo", "muito abaixo"]:
        direction = -1
    if is_higher_worse(event.event):
        direction *= -1

    macro_shock = "Neutro"
    base_score = 0
    if direction != 0 and event.category == "inflation":
        macro_shock = "inflacionario / hawkish" if direction > 0 else "desinflacionario / dovish"
        base_score = -35 if direction > 0 else 35
    elif direction != 0 and event.category == "employment":
        macro_shock = "pro-crescimento" if direction > 0 else "recessivo"
        base_score = 25 if direction > 0 else -30
    elif direction != 0 and event.category in ["activity", "china"]:
        macro_shock = "pro-crescimento" if direction > 0 else "recessivo"
        base_score = 30 if direction > 0 else -35
    elif direction != 0 and event.category == "central_bank":
        macro_shock = "hawkish" if direction > 0 else "dovish"
        base_score = -35 if direction > 0 else 35
    elif direction != 0 and event.category == "commodities":
        macro_shock = "altista para petroleo" if direction > 0 else "baixista para petroleo"
        base_score = -10 if direction > 0 else 10

    score = base_score
    confirmations = []
    market_map = {
        "S&P 500": _market_change(global_data, ["S&P 500", "SPY (S&P 500)"]),
        "NASDAQ": _market_change(global_data, ["NASDAQ"]),
        "DXY": _market_change(global_data, ["DXY (Dólar Index)", "DXY (Dolar Index)"]),
        "VIX": _market_change(global_data, ["VIX"]),
        "EWZ": _market_change(global_data, ["EWZ (Brazil ETF)"]),
        "USD/BRL": _market_change(global_data, ["USDBRL (Comercial)"]),
        "Bitcoin": _market_change(global_data, ["BITCOIN"]),
        "Brent": _market_change(global_data, ["BRENT OIL"]),
    }
    for asset, change in market_map.items():
        if change is None:
            continue
        contribution = 0
        if asset in ["S&P 500", "NASDAQ", "EWZ", "Bitcoin"] and change > 0.3:
            contribution = 6
        elif asset in ["S&P 500", "NASDAQ", "EWZ", "Bitcoin"] and change < -0.3:
            contribution = -6
        elif asset in ["DXY", "VIX", "USD/BRL"] and change > 0.2:
            contribution = -6
        elif asset in ["DXY", "VIX", "USD/BRL"] and change < -0.2:
            contribution = 6
        score += contribution
        confirmations.append({"Ativo": asset, "Var %": change, "Contrib.": contribution})

    score = max(-100, min(100, int(score)))
    risk_classification = _risk_classification(score)
    confidence = "Alta" if abs(score) >= 50 and surprise_direction in ["muito acima", "muito abaixo"] else ("Media" if abs(score) >= 25 else "Baixa")

    if score > 20:
        win_bias = "comprador"
        conduct = "priorizar compras em pullbacks se EWZ/indices seguirem firmes e USD/BRL nao pressionar."
    elif score < -20:
        win_bias = "vendedor"
        conduct = "priorizar vendas em repiques se EWZ/indices seguirem fracos e USD/BRL/DXY pressionarem."
    else:
        win_bias = "neutro"
        conduct = "reduzir lote e aguardar confirmacao tecnica."

    benchmark_text = f"consenso {event.forecast_raw}" if event.forecast is not None else f"anterior {event.previous_raw}"
    summary = (
        f"{risk_classification}. Evento {event.event} com surpresa {surprise_label} "
        f"({event.actual_raw} vs {benchmark_text}), choque {macro_shock}. "
        f"Para WIN, vies {win_bias}: {conduct}"
    )

    return {
        "status": "Interpretado",
        "event": event.event,
        "category": event.category,
        "surprise_value": surprise_value,
        "surprise_pct": surprise_pct,
        "surprise_label": surprise_label,
        "macro_shock": macro_shock,
        "dominant_regime": "Automatico / intermercado",
        "risk_score": score,
        "risk_classification": risk_classification,
        "confidence": confidence,
        "operational_summary": summary,
        "asset_impacts": {
            "WIN": win_bias,
            "S&P 500": "comprador" if score > 20 else ("vendedor" if score < -20 else "neutro"),
            "Nasdaq": "comprador" if score > 20 else ("vendedor" if score < -20 else "neutro"),
            "DXY": "vendedor" if score > 20 else ("comprador" if score < -20 else "neutro"),
            "USD/BRL": "queda" if score > 20 else ("alta" if score < -20 else "neutro"),
        },
        "confirmations": confirmations,
    }
