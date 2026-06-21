import math
import os
from datetime import datetime, timedelta

import requests


FRED_SERIES = {
    "us02y": "DGS2",
    "us05y": "DGS5",
    "us10y": "DGS10",
    "us30y": "DGS30",
    "tips_5y": "DFII5",
    "tips_10y": "DFII10",
    "breakeven_5y": "T5YIE",
    "breakeven_10y": "T10YIE",
}


def _as_float(value):
    try:
        if value in (None, "", ".", "---"):
            return None
        return float(value)
    except Exception:
        return None


def _fmt(value, digits=2, suffix=""):
    value = _as_float(value)
    if value is None or math.isnan(value):
        return "---"
    return f"{value:.{digits}f}{suffix}"


def _flatten_global_assets(global_data):
    categories = global_data.get("categories", global_data) if isinstance(global_data, dict) else {}
    assets = []
    if isinstance(categories, dict):
        for items in categories.values():
            if isinstance(items, list):
                assets.extend([item for item in items if isinstance(item, dict)])
    return assets


def _find_asset(global_data, *terms):
    terms = [term.lower() for term in terms]
    for item in _flatten_global_assets(global_data):
        name = str(item.get("name", "")).lower()
        symbol = str(item.get("symbol", "")).lower()
        if any(term in name or term in symbol for term in terms):
            return item
    return {}


def _fred_api_key():
    return os.getenv("FRED_API_KEY") or os.getenv("FRED_KEY") or ""


def _fetch_fred_series(series_id, api_key, timeout=8):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,
        "observation_start": (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
    }
    response = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=timeout)
    response.raise_for_status()
    observations = response.json().get("observations", [])
    values = []
    for obs in observations:
        value = _as_float(obs.get("value"))
        if value is not None:
            values.append({"date": obs.get("date"), "value": value})
    if len(values) < 2:
        return None
    return values[0], values[1]


def _load_fred_curve_data():
    api_key = _fred_api_key()
    if not api_key:
        return {}
    data = {}
    for key, series_id in FRED_SERIES.items():
        try:
            latest, previous = _fetch_fred_series(series_id, api_key)
            data[key] = latest["value"]
            data[f"{key}_change_bps"] = round((latest["value"] - previous["value"]) * 100, 2)
            data[f"{key}_date"] = latest["date"]
        except Exception:
            continue
    return data


def _load_market_fallback(global_data):
    mapping = {
        "us05y": ("us 05y", "5y", "^fvx"),
        "us10y": ("us 10y", "us10y", "^tnx"),
        "us30y": ("us 30y", "us30y", "^tyx"),
        "dxy": ("dxy", "dolar index", "dollar index"),
        "vix": ("vix", "^vix"),
        "sp500": ("s&p 500", "sp 500", "^gspc"),
        "nasdaq": ("nasdaq", "^ixic"),
        "ewz": ("ewz",),
        "usbrl": ("usdbrl", "brl=x"),
        "oil": ("brent", "wti", "oil"),
        "gold": ("gold", "ouro", "xau"),
        "bitcoin": ("bitcoin", "btc"),
    }
    data = {}
    for key, terms in mapping.items():
        item = _find_asset(global_data, *terms)
        price = _as_float(item.get("price")) if item else None
        change = _as_float(item.get("change")) if item else None
        if price is not None:
            data[key] = price
        if change is not None:
            data[f"{key}_change_pct"] = change
            if key.startswith("us"):
                data[f"{key}_change_bps"] = round(price * change, 2) if price is not None else None
    return data


def _merge_curve_data(global_data=None):
    global_data = global_data or {}
    data = _load_market_fallback(global_data)
    fred_data = _load_fred_curve_data()
    data.update({key: value for key, value in fred_data.items() if value is not None})
    if data.get("us10y") is not None and data.get("us02y") is not None:
        data["spread_10y_2y"] = round(data["us10y"] - data["us02y"], 3)
    if data.get("us30y") is not None and data.get("us05y") is not None:
        data["spread_30y_5y"] = round(data["us30y"] - data["us05y"], 3)
    if data.get("us10y_change_bps") is not None and data.get("us02y_change_bps") is not None:
        data["spread_10y_2y_change_bps"] = round(data["us10y_change_bps"] - data["us02y_change_bps"], 2)
    if data.get("us30y_change_bps") is not None and data.get("us05y_change_bps") is not None:
        data["spread_30y_5y_change_bps"] = round(data["us30y_change_bps"] - data["us05y_change_bps"], 2)
    return data


def classify_yield_curve(data):
    us02 = _as_float(data.get("us02y_change_bps"))
    us10 = _as_float(data.get("us10y_change_bps"))
    us30 = _as_float(data.get("us30y_change_bps"))
    spread_change = _as_float(data.get("spread_10y_2y_change_bps"))
    if us02 is None or us10 is None or spread_change is None:
        return "Neutro"
    if max(abs(us02), abs(us10), abs(us30 or 0), abs(spread_change)) < 1:
        return "Neutro"
    if us02 > 0 and us10 > 0 and us02 > us10 and spread_change < 0:
        return "Bear Flattening"
    if us02 > 0 and us10 > 0 and us10 > us02 and spread_change > 0:
        return "Bear Steepening"
    if us02 < 0 and us10 < 0 and abs(us02) > abs(us10) and spread_change > 0:
        return "Bull Steepening"
    if us02 < 0 and us10 < 0 and abs(us10) > abs(us02) and spread_change < 0:
        return "Bull Flattening"
    if us30 is not None:
        if us02 > 0 and us10 > 0 and us30 > 0 and max(us02, us10, us30) - min(us02, us10, us30) <= 5:
            return "Parallel Up"
        if us02 < 0 and us10 < 0 and us30 < 0 and max(abs(us02), abs(us10), abs(us30)) - min(abs(us02), abs(us10), abs(us30)) <= 5:
            return "Parallel Down"
    return "Neutro"


def _confidence(data, regime):
    if regime == "Neutro":
        return "Baixo"
    available = sum(1 for key in ["us02y", "us05y", "us10y", "us30y", "dxy_change_pct", "vix_change_pct", "tips_5y", "tips_10y"] if data.get(key) is not None)
    spread_move = abs(_as_float(data.get("spread_10y_2y_change_bps")) or 0)
    if available >= 7 and spread_move >= 4:
        return "Alto"
    if available >= 5 or spread_move >= 2:
        return "Medio"
    return "Baixo"


def _bias_for_assets(regime, data):
    dxy = _as_float(data.get("dxy_change_pct")) or 0
    vix = _as_float(data.get("vix_change_pct")) or 0
    ewz = _as_float(data.get("ewz_change_pct")) or 0
    risk_off_confirmed = dxy > 0 and vix > 0
    risk_on_confirmed = dxy < 0 and vix <= 0

    if regime in {"Bear Steepening", "Bear Flattening", "Parallel Up"}:
        return {
            "S&P Futuro": "Venda moderada",
            "Nasdaq Futuro": "Venda",
            "DXY": "Compra" if dxy >= 0 else "Neutro",
            "Ouro": "Venda" if regime != "Bear Steepening" or dxy >= 0 else "Neutro",
            "Petroleo": "Neutro" if regime == "Bear Steepening" else "Venda moderada",
            "Bitcoin": "Venda",
            "EWZ": "Venda" if ewz <= 0 or risk_off_confirmed else "Neutro",
            "WIN": "Venda em repiques" if risk_off_confirmed else "Neutro/venda seletiva",
            "WDO": "Compra em pullbacks" if dxy >= 0 else "Neutro",
        }
    if regime in {"Bull Flattening", "Parallel Down"}:
        return {
            "S&P Futuro": "Compra moderada" if risk_on_confirmed else "Neutro",
            "Nasdaq Futuro": "Compra" if risk_on_confirmed else "Neutro",
            "DXY": "Venda" if dxy <= 0 else "Neutro",
            "Ouro": "Compra moderada",
            "Petroleo": "Neutro",
            "Bitcoin": "Compra moderada" if risk_on_confirmed else "Neutro",
            "EWZ": "Compra" if ewz >= 0 and risk_on_confirmed else "Neutro",
            "WIN": "Compra em pullbacks" if risk_on_confirmed else "Neutro",
            "WDO": "Venda em repiques" if dxy <= 0 else "Neutro",
        }
    if regime == "Bull Steepening":
        return {
            "S&P Futuro": "Compra moderada" if risk_on_confirmed else "Neutro",
            "Nasdaq Futuro": "Compra moderada" if risk_on_confirmed else "Neutro",
            "DXY": "Venda" if dxy < 0 else "Neutro",
            "Ouro": "Compra moderada",
            "Petroleo": "Neutro",
            "Bitcoin": "Neutro",
            "EWZ": "Compra seletiva" if ewz >= 0 and risk_on_confirmed else "Neutro",
            "WIN": "Compra apenas com fluxo" if risk_on_confirmed else "Evitar agressao",
            "WDO": "Venda em repiques" if dxy < 0 else "Neutro",
        }
    return {asset: "Neutro" for asset in ["S&P Futuro", "Nasdaq Futuro", "DXY", "Ouro", "Petroleo", "Bitcoin", "EWZ", "WIN", "WDO"]}


def _macro_reading(regime, data):
    dxy = _as_float(data.get("dxy_change_pct")) or 0
    vix = _as_float(data.get("vix_change_pct")) or 0
    tips5 = _as_float(data.get("tips_5y_change_bps"))
    be10 = _as_float(data.get("breakeven_10y_change_bps"))
    confirmations = []
    if dxy > 0:
        confirmations.append("DXY confirma pressao em moedas e emergentes")
    elif dxy < 0:
        confirmations.append("DXY alivia condicoes financeiras globais")
    if vix > 0:
        confirmations.append("VIX confirma defesa")
    elif vix < 0:
        confirmations.append("VIX reduz risco sistemico")
    if tips5 is not None:
        confirmations.append("juro real sobe" if tips5 > 0 else "juro real cai")
    if be10 is not None:
        confirmations.append("breakeven sobe" if be10 > 0 else "breakeven cai")
    suffix = "; ".join(confirmations[:3]) or "confirmacoes externas ainda incompletas"
    descriptions = {
        "Bear Flattening": "Ponta curta sobe mais que a longa: mercado precifica Fed mais duro, menos cortes ou aperto real.",
        "Bear Steepening": "Ponta longa sobe mais: mercado precifica premio fiscal, inflacao, prazo ou crescimento nominal forte.",
        "Bull Flattening": "Ponta longa cai mais: desinflacao, busca por duration ou medo de crescimento.",
        "Bull Steepening": "Ponta curta cai mais: cortes de juros, desaceleracao ou risco de recessao.",
        "Parallel Up": "Toda a curva sobe: choque amplo de juros e condicoes financeiras mais apertadas.",
        "Parallel Down": "Toda a curva cai: alivio amplo de juros, positivo se VIX e DXY tambem cederem.",
        "Neutro": "Curva sem deslocamento dominante ou dados insuficientes; evitar vies forte isolado.",
    }
    return f"{descriptions.get(regime, descriptions['Neutro'])} Confirmacoes: {suffix}."


def _operational_bias(regime, data):
    dxy = _as_float(data.get("dxy_change_pct")) or 0
    vix = _as_float(data.get("vix_change_pct")) or 0
    ewz = _as_float(data.get("ewz_change_pct")) or 0
    if regime in {"Bear Steepening", "Bear Flattening", "Parallel Up"} and dxy > 0 and vix > 0:
        return "Risk-off forte"
    if regime in {"Bear Steepening", "Bear Flattening", "Parallel Up"}:
        return "Risk-off moderado"
    if regime in {"Bull Flattening", "Parallel Down"} and dxy < 0 and vix <= 0 and ewz >= 0:
        return "Risk-on forte"
    if regime in {"Bull Flattening", "Bull Steepening", "Parallel Down"}:
        return "Risk-on moderado" if dxy <= 0 and vix <= 0 else "Neutro"
    return "Neutro"


def _trader_sentence(regime, bias):
    if "Risk-off" in bias:
        return "Priorizar venda em repiques nos indices e compra em pullbacks no dolar, sempre com confirmacao de fluxo."
    if "Risk-on" in bias:
        return "Procurar compra em pullbacks nos ativos de risco e venda em repiques no dolar, sem operar apenas pela curva."
    if regime == "Bull Steepening":
        return "Confirmar se a queda de juros e alivio benigno ou medo de recessao antes de aumentar mao."
    return "Evitar operacao direcional forte; operar apenas com confirmacao de preco, VWAP, volume e fluxo."


def analyze_yield_curve_regime(global_data=None):
    data = _merge_curve_data(global_data)
    regime = classify_yield_curve(data)
    confidence = _confidence(data, regime)
    impacts = _bias_for_assets(regime, data)
    bias = _operational_bias(regime, data)
    return {
        "data": data,
        "regime": regime,
        "confidence": confidence,
        "macro_reading": _macro_reading(regime, data),
        "impacts": impacts,
        "operational_bias": bias,
        "trader_sentence": _trader_sentence(regime, bias),
        "source": "FRED + cache mercados globais" if _fred_api_key() else "Cache mercados globais",
    }
