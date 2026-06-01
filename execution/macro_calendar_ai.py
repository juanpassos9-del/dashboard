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


def calculate_projection(event: EconomicEvent) -> tuple[Optional[float], Optional[float], str]:
    if event.forecast is None or event.previous is None:
        return None, None, "projecao indisponivel"

    projected_value = event.forecast - event.previous
    projected_pct = None if event.previous == 0 else projected_value / abs(event.previous)
    event_name = _plain_text(event.event)

    if event.category in ["inflation", "central_bank"] or event.unit == "%":
        abs_value = abs(projected_value)
        if abs_value < 0.05:
            label = "projecao em linha"
        elif projected_value >= 0.15:
            label = "projecao muito acima"
        elif projected_value > 0.05:
            label = "projecao acima"
        elif projected_value <= -0.15:
            label = "projecao muito abaixo"
        else:
            label = "projecao abaixo"
    elif "pmi" in event_name or "ism" in event_name or "confidence" in event_name:
        abs_value = abs(projected_value)
        if abs_value < 0.3:
            label = "projecao em linha"
        elif projected_value >= 1.0:
            label = "projecao muito acima"
        elif projected_value > 0.3:
            label = "projecao acima"
        elif projected_value <= -1.0:
            label = "projecao muito abaixo"
        else:
            label = "projecao abaixo"
    else:
        if projected_pct is None or abs(projected_pct) < 0.05:
            label = "projecao em linha"
        elif projected_pct >= 0.20:
            label = "projecao muito acima"
        elif projected_pct > 0.05:
            label = "projecao acima"
        elif projected_pct <= -0.20:
            label = "projecao muito abaixo"
        else:
            label = "projecao abaixo"
    return projected_value, projected_pct, f"{label} vs anterior"


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
    if score >= 50:
        return "Risk-on forte"
    if score >= 20:
        return "Risk-on moderado"
    if score > -20:
        return "Neutro"
    if score > -50:
        return "Risk-off moderado"
    return "Risk-off forte"


def _label_base(surprise_label: str) -> str:
    return (surprise_label or "").replace("projecao ", "").replace(" vs anterior", "")


def _importance_weight(importance: str) -> float:
    value = _plain_text(importance)
    if "high" in value or "alto" in value:
        return 1.15
    if "medium" in value or "medio" in value or "moderate" in value:
        return 1.0
    if "low" in value or "baixo" in value:
        return 0.75
    return 1.0


def _is_wages_event(event_name: str) -> bool:
    name = _plain_text(event_name)
    return any(x in name for x in ["earnings", "wages", "salarios", "salario", "hourly"])


def _is_inflation_regime(regime: str) -> bool:
    return "inflacao" in _plain_text(regime) or "aperto" in _plain_text(regime)


def _is_recession_regime(regime: str) -> bool:
    plain = _plain_text(regime)
    return "recessao" in plain or "stress" in plain or "risk-off" in plain


def _points_from_map(label: str, points: dict[str, int]) -> int:
    return points.get(_label_base(label), 0)


def _surprise_score(event: EconomicEvent, surprise_label: str, dominant_regime: str) -> int:
    inflation_points = {
        "muito acima": -35,
        "acima": -20,
        "em linha": 0,
        "abaixo": 20,
        "muito abaixo": 35,
    }
    growth_points = {
        "muito acima": 30,
        "acima": 15,
        "em linha": 0,
        "abaixo": -15,
        "muito abaixo": -35,
    }
    activity_inflation_regime = {
        "muito acima": -20,
        "acima": -10,
        "em linha": 0,
        "abaixo": 10,
        "muito abaixo": -30,
    }
    commodities_points = {
        "muito acima": -20,
        "acima": -10,
        "em linha": 0,
        "abaixo": 10,
        "muito abaixo": 20,
    }

    if event.category == "inflation" or _is_wages_event(event.event):
        score = _points_from_map(surprise_label, inflation_points)
    elif event.category in ["activity", "employment"]:
        if _is_inflation_regime(dominant_regime):
            score = _points_from_map(surprise_label, activity_inflation_regime)
        else:
            score = _points_from_map(surprise_label, growth_points)
        if is_higher_worse(event.event):
            score *= -1
    elif event.category == "central_bank":
        score = _points_from_map(surprise_label, inflation_points)
    elif event.category == "commodities":
        score = _points_from_map(surprise_label, commodities_points)
    elif event.category == "china":
        score = _points_from_map(surprise_label, growth_points)
    else:
        score = int(_points_from_map(surprise_label, growth_points) * 0.5)
    return score


def _detect_dominant_regime(market_map: dict[str, Optional[float]]) -> str:
    us10y = market_map.get("US10Y")
    dxy = market_map.get("DXY")
    vix = market_map.get("VIX")
    sp500 = market_map.get("S&P 500")
    nasdaq = market_map.get("NASDAQ")

    if us10y is not None and dxy is not None and vix is not None:
        if us10y > 0.15 and dxy > 0.3 and vix > 3:
            return "Inflacao dominante / aperto financeiro"
        if us10y < -0.15 and dxy < -0.3 and sp500 is not None and sp500 > 0.5:
            return "Liquidez favoravel / risk-on"

    if vix is not None and sp500 is not None and vix > 5 and sp500 < -0.5:
        return "Risk-off / stress"
    if sp500 is not None and nasdaq is not None and vix is not None:
        if sp500 > 0.3 and nasdaq > 0.3 and vix < -2:
            return "Goldilocks / risk-on"
    return "Neutro"


def _regime_points(dominant_regime: str) -> int:
    points = {
        "Inflacao dominante / aperto financeiro": -15,
        "Risk-off / stress": -25,
        "Liquidez favoravel / risk-on": 25,
        "Goldilocks / risk-on": 20,
        "Neutro": 0,
    }
    return points.get(dominant_regime, 0)


def _build_market_map(global_data: Optional[dict]) -> dict[str, Optional[float]]:
    return {
        "S&P 500": _market_change(global_data, ["S&P 500", "SPY (S&P 500)", "SPY (S&P 500 ETF)"]),
        "NASDAQ": _market_change(global_data, ["NASDAQ", "NASDAQ (Futuro)"]),
        "DXY": _market_change(global_data, ["DXY (DÃ³lar Index)", "DXY (Dolar Index)"]),
        "VIX": _market_change(global_data, ["VIX"]),
        "EWZ": _market_change(global_data, ["EWZ (Brazil ETF)"]),
        "USD/BRL": _market_change(global_data, ["USDBRL (Comercial)", "USDBRL"]),
        "US10Y": _market_change(global_data, ["US 10Y (Yield)", "US10Y"]),
        "US30Y": _market_change(global_data, ["US 30Y (Yield)", "US30Y"]),
        "Bitcoin": _market_change(global_data, ["BITCOIN", "Bitcoin"]),
        "Brent": _market_change(global_data, ["BRENT OIL", "Brent"]),
        "WTI": _market_change(global_data, ["WTI OIL", "PetrÃ³leo WTI", "Petroleo WTI"]),
        "Gold": _market_change(global_data, ["GOLD", "Ouro"]),
    }


def _market_confirmation(market_map: dict[str, Optional[float]]) -> tuple[int, list[dict], float]:
    rules = [
        ("US10Y", -0.15, 0.15, 10, "queda de juros", "alta de juros"),
        ("DXY", -0.2, 0.2, 10, "dolar fraco", "dolar forte"),
        ("VIX", -2.0, 2.0, 10, "volatilidade cedendo", "volatilidade subindo"),
        ("S&P 500", 0.3, -0.3, 10, "indice forte", "indice fraco"),
        ("NASDAQ", 0.3, -0.3, 10, "tech forte", "tech fraco"),
        ("EWZ", 0.3, -0.3, 7, "Brasil forte", "Brasil fraco"),
        ("USD/BRL", -0.3, 0.3, 7, "real forte", "real fraco"),
        ("Bitcoin", 0.5, -0.5, 5, "cripto forte", "cripto fraco"),
        ("Brent", 0.5, -0.5, 4, "energia firme", "energia fraca"),
    ]
    contribution = 0
    confirmations = []
    for asset, risk_on_threshold, risk_off_threshold, points, on_label, off_label in rules:
        change = market_map.get(asset)
        if change is None:
            continue
        signal = "neutro"
        asset_points = 0
        if risk_on_threshold >= 0 and change > risk_on_threshold:
            signal = f"Risk-on: {on_label}"
            asset_points = points
        elif risk_on_threshold < 0 and change < risk_on_threshold:
            signal = f"Risk-on: {on_label}"
            asset_points = points
        elif risk_off_threshold >= 0 and change > risk_off_threshold:
            signal = f"Risk-off: {off_label}"
            asset_points = -points
        elif risk_off_threshold < 0 and change < risk_off_threshold:
            signal = f"Risk-off: {off_label}"
            asset_points = -points
        contribution += asset_points
        confirmations.append({"Ativo": asset, "Var %": change, "Sinal": signal, "Contrib.": asset_points})

    directional = [item for item in confirmations if item["Contrib."] != 0]
    aligned = [item for item in directional if (contribution >= 0 and item["Contrib."] > 0) or (contribution < 0 and item["Contrib."] < 0)]
    ratio = len(aligned) / len(directional) if directional else 0.0
    return contribution, confirmations, ratio


def _confidence(event: EconomicEvent, surprise_label: str, score: int, confirmations: list[dict], alignment_ratio: float) -> str:
    directional_count = len([item for item in confirmations if item.get("Contrib.")])
    levels = ["Baixa", "Media", "Alta", "Muito alta"]
    level = 0
    if alignment_ratio >= 0.75:
        level = 2
    elif alignment_ratio >= 0.55:
        level = 1

    if event.importance.upper() == "HIGH" and _label_base(surprise_label) in ["muito acima", "muito abaixo"]:
        level += 1
    if abs(score) < 20:
        level -= 1
    if directional_count < 5:
        level -= 1
    return levels[max(0, min(len(levels) - 1, level))]


def _macro_shock(event: EconomicEvent, surprise_label: str, dominant_regime: str, score: int) -> str:
    direction = 1 if _surprise_score(event, surprise_label, dominant_regime) > 0 else -1 if _surprise_score(event, surprise_label, dominant_regime) < 0 else 0
    if direction == 0:
        return "Neutro"
    if event.category == "inflation" or _is_wages_event(event.event):
        return "desinflacionario / dovish" if direction > 0 else "inflacionario / hawkish"
    if event.category in ["activity", "employment", "china"]:
        if _is_inflation_regime(dominant_regime) and direction < 0:
            return "hawkish / juros pressionados"
        return "pro-crescimento" if direction > 0 else "recessivo"
    if event.category == "central_bank":
        return "dovish" if direction > 0 else "hawkish"
    if event.category == "commodities":
        return "baixista para energia / desinflacionario" if direction > 0 else "altista para energia / inflacionario"
    return "favoravel ao risco" if score > 0 else "desfavoravel ao risco"


def _asset_impacts(score: int, macro_shock: str) -> dict[str, str]:
    if score >= 50:
        equities = "risk-on forte"
    elif score > 20:
        equities = "risk-on moderado"
    elif score <= -50:
        equities = "risk-off forte"
    elif score < -20:
        equities = "risk-off moderado"
    else:
        equities = "neutro"

    risk_on = score > 20
    risk_off = score < -20
    inflationary = "inflacionario" in macro_shock or "hawkish" in macro_shock
    disinflationary = "desinflacionario" in macro_shock or "dovish" in macro_shock
    return {
        "Juros": "pressao de alta" if inflationary else ("alivio / queda" if disinflationary else "neutro"),
        "Inflacao": "pressao inflacionaria" if inflationary else ("alivio inflacionario" if disinflationary else "neutra"),
        "DXY": "tende a subir" if risk_off or inflationary else ("tende a cair" if risk_on or disinflationary else "neutro"),
        "Petroleo": "suporte por crescimento" if risk_on else ("pressao por desaceleracao" if risk_off else "neutro"),
        "S&P 500": equities,
        "Nasdaq": equities,
        "Dow Jones": equities,
    }


def _macro_effect_text(asset_impacts: dict[str, str], risk_classification: str) -> str:
    return (
        f"Juros: {asset_impacts.get('Juros', 'neutro')}; "
        f"inflacao: {asset_impacts.get('Inflacao', 'neutra')}; "
        f"DXY: {asset_impacts.get('DXY', 'neutro')}; "
        f"petroleo: {asset_impacts.get('Petroleo', 'neutro')}; "
        f"indices americanos: S&P 500 {asset_impacts.get('S&P 500', risk_classification)}, "
        f"Nasdaq {asset_impacts.get('Nasdaq', risk_classification)} e "
        f"Dow Jones {asset_impacts.get('Dow Jones', risk_classification)}."
    )


def _interpret_event_legacy(raw_event: dict, global_data: Optional[dict] = None) -> dict:
    event = normalize_event(raw_event)
    surprise_value, surprise_pct, surprise_label = calculate_surprise(event)

    released = event.actual is not None
    if not released:
        projection_value, projection_pct, projection_label = calculate_projection(event)
        if projection_value is not None:
            dominant_regime = "Calendario Investing"
            data_score = int(_surprise_score(event, projection_label, dominant_regime) * _importance_weight(event.importance) * 0.65)
            score = max(-100, min(100, data_score))
            macro_shock = _macro_shock(event, projection_label, dominant_regime, score)
            risk_classification = _risk_classification(score)
            confidence = "Media" if abs(score) >= 15 else "Baixa"
            asset_impacts = _asset_impacts(score, macro_shock)
            if score > 20:
                macro_bias = risk_classification
                conduct = "a projecao cria leitura pre-evento favoravel ao risco, mas depende da confirmacao do Atual no horario da divulgacao."
            elif score < -20:
                macro_bias = risk_classification
                conduct = "a projecao cria leitura pre-evento defensiva, mas depende da confirmacao do Atual no horario da divulgacao."
            else:
                macro_bias = risk_classification
                conduct = "projeção sem assimetria forte; aguardar o Atual antes de tomar direção."
            summary = (
                f"{risk_classification}. Projecao do evento {event.event}: consenso {event.forecast_raw} vs anterior {event.previous_raw}. "
                f"A leitura indica {projection_label} e choque esperado {macro_shock}. "
                f"Efeito esperado: {risk_classification}, usando somente dados do Investing. "
                f"Efeito macro {macro_bias}: {conduct}"
            )
            return {
                "status": "Projecao analisada",
                "event": event.event,
                "category": event.category,
                "surprise_label": projection_label,
                "macro_shock": macro_shock,
                "dominant_regime": dominant_regime,
                "risk_score": score,
                "risk_classification": risk_classification,
                "confidence": confidence,
                "operational_summary": summary,
                "asset_impacts": asset_impacts,
                "surprise_value": projection_value,
                "surprise_pct": projection_pct,
                "score_components": {
                    "projecao": data_score,
                    "regime": 0,
                    "intermercado": 0,
                    "alinhamento": 0.0,
                },
            }
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
            "operational_summary": "Aguardando o campo Atual do calendario Investing. Assim que o dado for divulgado, a IA calcula surpresa, choque macro e efeito em juros, inflacao, DXY, petroleo e indices americanos.",
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
        macro_bias = risk_classification
        conduct = "priorizar compras em pullbacks se EWZ/indices seguirem firmes e USD/BRL nao pressionar."
    elif score < -20:
        macro_bias = risk_classification
        conduct = "priorizar vendas em repiques se EWZ/indices seguirem fracos e USD/BRL/DXY pressionarem."
    else:
        macro_bias = risk_classification
        conduct = "reduzir lote e aguardar confirmacao tecnica."

    benchmark_text = f"consenso {event.forecast_raw}" if event.forecast is not None else f"anterior {event.previous_raw}"
    summary = (
        f"{risk_classification}. Evento {event.event} com surpresa {surprise_label} "
        f"({event.actual_raw} vs {benchmark_text}), choque {macro_shock}. "
        f"Efeito macro {macro_bias}: {conduct}"
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
            "Juros": "alta" if score < -20 else ("queda" if score > 20 else "neutro"),
            "S&P 500": "comprador" if score > 20 else ("vendedor" if score < -20 else "neutro"),
            "Nasdaq": "comprador" if score > 20 else ("vendedor" if score < -20 else "neutro"),
            "DXY": "vendedor" if score > 20 else ("comprador" if score < -20 else "neutro"),
            "USD/BRL": "queda" if score > 20 else ("alta" if score < -20 else "neutro"),
        },
        "confirmations": confirmations,
    }


def interpret_event(raw_event: dict, global_data: Optional[dict] = None) -> dict:
    event = normalize_event(raw_event)
    surprise_value, surprise_pct, surprise_label = calculate_surprise(event)

    released = event.actual is not None
    if not released:
        projection_value, projection_pct, projection_label = calculate_projection(event)
        if projection_value is not None:
            dominant_regime = "Calendario Investing"
            data_score = int(_surprise_score(event, projection_label, dominant_regime) * _importance_weight(event.importance) * 0.65)
            score = max(-100, min(100, data_score))
            macro_shock = _macro_shock(event, projection_label, dominant_regime, score)
            risk_classification = _risk_classification(score)
            confidence = "Media" if abs(score) >= 15 else "Baixa"
            asset_impacts = _asset_impacts(score, macro_shock)
            macro_effect = _macro_effect_text(asset_impacts, risk_classification)
            summary = (
                f"{risk_classification}. Projecao do evento {event.event}: consenso {event.forecast_raw} vs anterior {event.previous_raw}. "
                f"A leitura indica {projection_label} e choque esperado {macro_shock}. "
                f"Efeito esperado: {risk_classification}, usando somente dados do Investing. "
                f"{macro_effect} Confirmar a surpresa quando o campo Atual for divulgado."
            )
            return {
                "status": "Projecao analisada",
                "event": event.event,
                "category": event.category,
                "surprise_value": projection_value,
                "surprise_pct": projection_pct,
                "surprise_label": projection_label,
                "macro_shock": macro_shock,
                "dominant_regime": dominant_regime,
                "risk_score": score,
                "risk_classification": risk_classification,
                "confidence": confidence,
                "operational_summary": summary,
                "asset_impacts": asset_impacts,
                "confirmations": [],
                "score_components": {
                    "projecao": data_score,
                    "regime": 0,
                    "intermercado": 0,
                    "alinhamento": 0.0,
                },
            }
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
            "operational_summary": "Aguardando o campo Atual do calendario Investing. Assim que o dado for divulgado, a IA calcula surpresa, choque macro e efeito em juros, inflacao, DXY, petroleo e indices americanos.",
            "asset_impacts": {},
            "surprise_value": None,
            "surprise_pct": None,
        }

    use_market_data = bool(global_data)
    market_map = _build_market_map(global_data) if use_market_data else {}
    dominant_regime = _detect_dominant_regime(market_map) if use_market_data else "Calendario Investing"
    data_score = int(_surprise_score(event, surprise_label, dominant_regime) * _importance_weight(event.importance))
    regime_score = _regime_points(dominant_regime) if use_market_data else 0
    if use_market_data:
        market_score, confirmations, alignment_ratio = _market_confirmation(market_map)
    else:
        market_score, confirmations, alignment_ratio = 0, [], 0.0
    score = max(-100, min(100, int(data_score + regime_score + market_score)))
    macro_shock = _macro_shock(event, surprise_label, dominant_regime, score)
    risk_classification = _risk_classification(score)
    confidence = _confidence(event, surprise_label, score, confirmations, alignment_ratio) if use_market_data else ("Media" if abs(score) >= 20 else "Baixa")
    asset_impacts = _asset_impacts(score, macro_shock)
    macro_effect = _macro_effect_text(asset_impacts, risk_classification)

    benchmark_text = f"consenso {event.forecast_raw}" if event.forecast is not None else f"anterior {event.previous_raw}"
    summary = (
        f"{risk_classification}. Evento {event.event} com surpresa {surprise_label} "
        f"({event.actual_raw} vs {benchmark_text}). Choque {macro_shock}. "
        f"Efeito esperado: {risk_classification}, usando somente dados do Investing. "
        f"{macro_effect}"
    )

    return {
        "status": "Interpretado",
        "event": event.event,
        "category": event.category,
        "surprise_value": surprise_value,
        "surprise_pct": surprise_pct,
        "surprise_label": surprise_label,
        "macro_shock": macro_shock,
        "dominant_regime": dominant_regime,
        "risk_score": score,
        "risk_classification": risk_classification,
        "confidence": confidence,
        "operational_summary": summary,
        "asset_impacts": asset_impacts,
        "confirmations": confirmations,
        "score_components": {
            "surpresa": data_score,
            "regime": regime_score,
            "intermercado": market_score,
            "alinhamento": alignment_ratio,
        },
    }
