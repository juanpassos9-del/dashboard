import json
import os
from datetime import datetime

import google.generativeai as genai
from dotenv import load_dotenv

from execution.yield_curve_regime import analyze_yield_curve_regime

load_dotenv()


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        return data
    except Exception:
        return default


def _flatten_assets(global_data):
    categories = global_data.get("categories", global_data) if isinstance(global_data, dict) else {}
    assets = []
    if isinstance(categories, dict):
        for items in categories.values():
            if isinstance(items, list):
                assets.extend([item for item in items if isinstance(item, dict)])
    return assets


def _find_asset(global_data, *terms):
    terms = [term.lower() for term in terms]
    for item in _flatten_assets(global_data):
        name = str(item.get("name", "")).lower()
        symbol = str(item.get("symbol", "")).lower()
        if any(term in name or term in symbol for term in terms):
            return item
    return {}


def _change(item):
    try:
        return float(item.get("change", 0))
    except Exception:
        return 0.0


def _price(item):
    try:
        return float(item.get("price"))
    except Exception:
        return None


def _asset_line(label, item):
    if not item:
        return f"{label}: indisponivel"
    price = _price(item)
    price_txt = "---" if price is None else (f"{price:.2f}" if abs(price) >= 10 else f"{price:.4f}")
    return f"{label}: {price_txt} ({_change(item):+.2f}%)"


def _score_component(label, value, positive_when_up=True, threshold=0.10, weight=1):
    if abs(value) < threshold:
        return 0, f"{label} neutro"
    if positive_when_up:
        point = weight if value > 0 else -weight
    else:
        point = weight if value < 0 else -weight
    direction = "favoravel" if point > 0 else "desfavoravel"
    return point, f"{label} {value:+.2f}% {direction}"


def build_macro_regime_context(local_data, global_data, calendar_data):
    assets = {
        "sp500": _find_asset(global_data, "s&p 500", "sp 500", "^gspc", "spy", "usa500"),
        "nasdaq": _find_asset(global_data, "nasdaq", "^ixic", "usatec"),
        "dow": _find_asset(global_data, "dow", "djia", "^dji"),
        "vix": _find_asset(global_data, "vix", "^vix", "vxx"),
        "dxy": _find_asset(global_data, "dxy", "dolar index", "dollar index", "dx-y"),
        "us10y": _find_asset(global_data, "us 10y", "us10y", "^tnx"),
        "us30y": _find_asset(global_data, "us 30y", "us30y", "^tyx"),
        "eem": _find_asset(global_data, "eem", "emerging"),
        "ewz": _find_asset(global_data, "ewz", "brazil etf"),
        "usbrl": _find_asset(global_data, "usdbrl", "brl=x"),
        "real_cme": _find_asset(global_data, "6l", "real cme"),
        "brent": _find_asset(global_data, "brent", "ukoil"),
        "wti": _find_asset(global_data, "wti", "crude oil"),
        "gold": _find_asset(global_data, "gold", "ouro", "xau"),
        "bitcoin": _find_asset(global_data, "bitcoin", "btc"),
        "ibov": _find_asset(global_data, "ibov", "bovespa", "^bvsp"),
    }
    curve = analyze_yield_curve_regime(global_data)

    score = 0
    reasons = []
    rules = [
        ("S&P 500", _change(assets["sp500"]), True, 0.15, 1),
        ("Nasdaq", _change(assets["nasdaq"]), True, 0.15, 1),
        ("VIX", _change(assets["vix"]), False, 0.25, 2),
        ("DXY", _change(assets["dxy"]), False, 0.12, 2),
        ("US10Y", _change(assets["us10y"]), False, 0.08, 2),
        ("US30Y", _change(assets["us30y"]), False, 0.08, 1),
        ("EEM", _change(assets["eem"]), True, 0.15, 2),
        ("EWZ", _change(assets["ewz"]), True, 0.15, 2),
        ("USDBRL", _change(assets["usbrl"]), False, 0.15, 2),
        ("6L Real CME", _change(assets["real_cme"]), True, 0.10, 1),
        ("Petroleo", _change(assets["brent"]) or _change(assets["wti"]), True, 0.30, 1),
        ("Ouro", _change(assets["gold"]), True, 0.25, 1),
        ("Bitcoin", _change(assets["bitcoin"]), True, 0.50, 1),
    ]
    for label, value, positive_when_up, threshold, weight in rules:
        point, reason = _score_component(label, value, positive_when_up, threshold, weight)
        score += point
        if point:
            reasons.append(reason)

    curve_bias = curve.get("operational_bias", "Neutro")
    if curve_bias == "Risk-off forte":
        score -= 3
        reasons.append("curva americana em Risk-off forte")
    elif curve_bias == "Risk-off moderado":
        score -= 2
        reasons.append("curva americana em Risk-off moderado")
    elif curve_bias == "Risk-on forte":
        score += 3
        reasons.append("curva americana em Risk-on forte")
    elif curve_bias == "Risk-on moderado":
        score += 2
        reasons.append("curva americana em Risk-on moderado")

    if score >= 5:
        regime = "Risk-on forte"
        sentiment_hint = "COMPRA"
        confidence = "Alta"
    elif score >= 2:
        regime = "Risk-on moderado"
        sentiment_hint = "COMPRA"
        confidence = "Media"
    elif score <= -5:
        regime = "Risk-off forte"
        sentiment_hint = "VENDA"
        confidence = "Alta"
    elif score <= -2:
        regime = "Risk-off moderado"
        sentiment_hint = "VENDA"
        confidence = "Media"
    else:
        regime = "Neutro/seletivo"
        sentiment_hint = "NEUTRO"
        confidence = "Baixa"

    important_calendar = []
    if isinstance(calendar_data, dict):
        events = calendar_data.get("events") or calendar_data.get("value") or []
    else:
        events = calendar_data if isinstance(calendar_data, list) else []
    for event in events[:12]:
        if not isinstance(event, dict):
            continue
        impact = str(event.get("impact", "")).upper()
        if impact in {"HIGH", "MEDIUM"}:
            important_calendar.append(
                f"{event.get('time', '---')} {event.get('currency', '---')} {impact}: "
                f"{event.get('event', '---')} | atual {event.get('actual', '---')} | "
                f"proj {event.get('forecast', '---')} | ant {event.get('previous', '---')}"
            )

    snapshot_lines = [
        _asset_line("S&P 500", assets["sp500"]),
        _asset_line("Nasdaq", assets["nasdaq"]),
        _asset_line("VIX", assets["vix"]),
        _asset_line("DXY", assets["dxy"]),
        _asset_line("US10Y", assets["us10y"]),
        _asset_line("US30Y", assets["us30y"]),
        _asset_line("EEM", assets["eem"]),
        _asset_line("EWZ", assets["ewz"]),
        _asset_line("USDBRL", assets["usbrl"]),
        _asset_line("6L", assets["real_cme"]),
        _asset_line("Brent", assets["brent"]),
        _asset_line("Ouro", assets["gold"]),
        _asset_line("Bitcoin", assets["bitcoin"]),
        _asset_line("IBOV", assets["ibov"]),
    ]

    return {
        "score": score,
        "regime": regime,
        "confidence": confidence,
        "sentiment_hint": sentiment_hint,
        "reasons": reasons[:8],
        "curve": {
            "regime": curve.get("regime", "Neutro"),
            "confidence": curve.get("confidence", "Baixo"),
            "bias": curve.get("operational_bias", "Neutro"),
            "reading": curve.get("macro_reading", ""),
        },
        "snapshot": snapshot_lines,
        "calendar_focus": important_calendar[:6],
        "local_data_available": bool(local_data),
    }


def _extract_sentiment(full_text, fallback="NEUTRO"):
    upper = full_text.upper()
    if "REGIME: RISK-ON" in upper or "REGIME: RISK ON" in upper:
        return "COMPRA"
    if "REGIME: RISK-OFF" in upper or "REGIME: RISK OFF" in upper:
        return "VENDA"
    if "REGIME: NEUTRO" in upper or "REGIME: NEUTRO/SELETIVO" in upper:
        return "NEUTRO"
    if "VEREDITO: COMPRA" in upper:
        return "COMPRA"
    if "VEREDITO: VENDA" in upper:
        return "VENDA"
    if "VEREDITO: NEUTRO" in upper:
        return "NEUTRO"
    return fallback


def _clean_verdict(full_text):
    cleaned = full_text
    for verdict in [
        "VEREDITO: COMPRA", "VEREDITO: VENDA", "VEREDITO: NEUTRO",
        "REGIME: RISK-ON", "REGIME: RISK ON", "REGIME: RISK-OFF", "REGIME: RISK OFF",
        "REGIME: NEUTRO", "REGIME: NEUTRO/SELETIVO",
    ]:
        cleaned = cleaned.replace(verdict, "")
        cleaned = cleaned.replace(verdict.lower(), "")
        cleaned = cleaned.replace(verdict.title(), "")
    return cleaned.strip()


def _local_fallback_text(context):
    reasons = "; ".join(context.get("reasons") or ["sinais mistos"])
    calendar = context.get("calendar_focus") or ["Sem evento HIGH/MEDIUM carregado no calendario."]
    curve = context.get("curve", {})
    return f"""REGIME MACRO
{context['regime']} | confianca {context['confidence']} | score {context['score']}. Drivers: {reasons}.

CURVA, JUROS E DOLAR
{curve.get('regime', 'Neutro')} | {curve.get('bias', 'Neutro')}. {curve.get('reading', '')}

INTERMERCADOS
Juros e DXY sao o primeiro filtro; VIX confirma apetite a risco; EEM/EWZ/USDBRL mostram transmissao para emergentes e Brasil.

CALENDARIO
{chr(10).join('- ' + item for item in calendar[:3])}

IMPACTO PROVAVEL
Regime macro usado como filtro de risco. Entrada operacional depende do setup tecnico, liquidez e confirmacao do preco.

RISCO
Se DXY, VIX, curva americana e emergentes divergirem, tratar o ambiente como seletivo.
"""


def generate_macro_insight():
    try:
        local_data = _load_json("dados_mercado.json", {})
        global_data = _load_json("mercados_globais.json", {})
        calendar_data = _load_json("calendario_economico.json", [])
        macro_context = build_macro_regime_context(local_data, global_data, calendar_data)

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            clean_text = _local_fallback_text(macro_context)
            sentiment = macro_context["sentiment_hint"]
            provider = "Local/macro_regime_engine"
        else:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("AI_ANALYST_GEMINI_MODEL", "gemini-flash-latest"))
            prompt = f"""
Voce e um Analista Macro Global Profissional, com mentalidade de trader institucional.

Use o painel macro estruturado abaixo como fonte principal. Os dados brutos sao apenas apoio.
Seu trabalho e transformar o contexto em uma leitura curta de regime macro para o Terminal de Trading.

HIERARQUIA OBRIGATORIA:
1. Curva americana e yields
2. DXY e liquidez global
3. VIX e apetite a risco
4. S&P 500, Nasdaq e Dow
5. Emergentes: EEM, EWZ, USDBRL e 6L
6. Commodities: petroleo, ouro e cripto
7. Calendario economico

PAINEL MACRO ESTRUTURADO:
{json.dumps(macro_context, ensure_ascii=False, indent=2)}

DADOS BRUTOS DE APOIO:
MERCADO LOCAL: {json.dumps(local_data, ensure_ascii=False)}
MERCADOS GLOBAIS: {json.dumps(global_data, ensure_ascii=False)}
CALENDARIO: {json.dumps(calendar_data, ensure_ascii=False)}

FORMATO:
REGIME
Uma linha com Risk-on, Risk-off ou Neutro/seletivo e o motivo principal.

DRIVERS
3 bullets curtos conectando dado observado -> leitura macro -> impacto provavel.

INTERMERCADOS
- Juros/DXY:
- VIX/Indices EUA:
- Emergentes/Brasil:
- Commodities:

CALENDARIO
Classifique os eventos relevantes como inflacao, crescimento, emprego, politica monetaria ou neutro. Explique o risco macro em 1 ou 2 linhas.

IMPACTO PROVAVEL
Explique em uma linha o efeito esperado em juros, DXY, petroleo, indices EUA e Brasil.

RISCO
Uma linha com o principal ponto que pode invalidar a leitura.

REGRAS:
- Nao seja generico.
- Nao invente dados ausentes.
- Nao trate a curva como gatilho isolado.
- Nao liste ativos isoladamente; explique a cadeia juros -> dolar -> risco -> emergentes -> Brasil.
- Nao gere recomendacao direta de compra/venda. E uma leitura de regime macro, nao call de trade.
- A ultima linha deve ser exatamente: REGIME: RISK-ON, REGIME: RISK-OFF ou REGIME: NEUTRO.
"""
            response = model.generate_content(prompt)
            full_text = getattr(response, "text", "") or ""
            sentiment = _extract_sentiment(full_text, macro_context["sentiment_hint"])
            clean_text = _clean_verdict(full_text)
            provider = f"Gemini/{os.getenv('AI_ANALYST_GEMINI_MODEL', 'gemini-flash-latest')} + macro_regime_engine"

        updated_at = datetime.now().strftime("%H:%M:%S")
        payload = {
            "insight": clean_text,
            "sentiment": sentiment,
            "updated_at": updated_at,
            "provider": provider,
            "macro_regime": macro_context.get("regime"),
            "confidence": macro_context.get("confidence"),
            "macro_score": macro_context.get("score"),
            "curve_regime": macro_context.get("curve", {}).get("regime"),
            "curve_bias": macro_context.get("curve", {}).get("bias"),
            "drivers": macro_context.get("reasons", []),
        }
        with open("ai_insight.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return clean_text

    except Exception as e:
        print(f"Erro na IA: {e}")
        return f"Erro ao gerar analise: {e}"


if __name__ == "__main__":
    generate_macro_insight()
