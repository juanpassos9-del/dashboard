import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from execution.fetch_news import fetch_all_news

try:
    import google.generativeai as genai
except Exception:
    genai = None

load_dotenv()

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
DAILY_REPORT_FILE = "market_report_daily.json"
LATEST_REPORT_FILE = "market_report.json"

REPORT_SLOTS = {
    "manha": {
        "label": "Manha",
        "window": "07:00-11:59",
        "focus": "abertura, overnight global, agenda economica e vies inicial para Brasil",
    },
    "tarde": {
        "label": "Tarde",
        "window": "13:00-17:59",
        "focus": "ajustes intradiarios, fluxo de NY, commodities e reprecificacao de juros/moedas",
    },
    "noite": {
        "label": "Noite",
        "window": "19:00-23:59",
        "focus": "fechamento, leitura dos drivers do dia e riscos para a proxima sessao",
    },
}


def _now_local():
    return datetime.now(LOCAL_TZ)


def get_report_slot(now=None, force=False):
    """Retorna o slot devido. Fora das janelas, nao gera automaticamente."""
    now = now or _now_local()
    hour = now.hour
    if 7 <= hour < 12:
        return "manha"
    if 13 <= hour < 18:
        return "tarde"
    if 19 <= hour <= 23:
        return "noite"
    if force:
        if hour < 12:
            return "manha"
        if hour < 18:
            return "tarde"
        return "noite"
    return None


def _empty_daily_state(date_str):
    return {
        "date": date_str,
        "timezone": "America/Sao_Paulo",
        "reports": [],
        "updated_at": None,
    }


def load_daily_reports(date_str=None):
    date_str = date_str or _now_local().strftime("%Y-%m-%d")
    if not os.path.exists(DAILY_REPORT_FILE):
        return _empty_daily_state(date_str)
    try:
        with open(DAILY_REPORT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != date_str:
            return _empty_daily_state(date_str)
        if not isinstance(data.get("reports"), list):
            data["reports"] = []
        return data
    except Exception:
        return _empty_daily_state(date_str)


def save_daily_reports(data):
    with open(DAILY_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _upsert_slot_report(daily_data, report):
    reports = [r for r in daily_data.get("reports", []) if r.get("slot") != report.get("slot")]
    reports.append(report)
    slot_order = {"manha": 1, "tarde": 2, "noite": 3}
    reports.sort(key=lambda item: slot_order.get(item.get("slot"), 99))
    daily_data["reports"] = reports
    daily_data["updated_at"] = report["updated_at"]
    return daily_data


def _load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data[0]
        return data
    except Exception:
        return default


def _load_app_state_value(key, default):
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("SUPABASE")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE")
    if not supabase_url or not supabase_key:
        return default
    try:
        from supabase import create_client

        client = create_client(supabase_url, supabase_key)
        response = client.table("app_state").select("value").eq("key", key).execute()
        if response.data:
            value = response.data[0].get("value")
            return value if value is not None else default
    except Exception as e:
        print(f"[WARN] Supabase indisponivel para {key}: {e}")
    return default


def _extract_ai_text(response):
    text = getattr(response, "text", "") or ""
    text = text.strip()
    if text:
        return text
    try:
        parts = response.candidates[0].content.parts
        text = "\n".join(getattr(part, "text", "") for part in parts).strip()
    except Exception:
        text = ""
    return text


def _generate_with_gemini(prompt, errors):
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        errors.append("Gemini sem GOOGLE_API_KEY/GEMINI_API_KEY.")
        return None, None
    if genai is None:
        errors.append("Pacote google-generativeai indisponivel.")
        return None, None

    genai.configure(api_key=api_key)
    model_names = [
        os.getenv("MARKET_REPORT_GEMINI_MODEL", "").strip(),
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]
    for model_name in [name for name in model_names if name]:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = _extract_ai_text(response)
            if text:
                return text, f"Gemini/{model_name}"
            errors.append(f"{model_name}: resposta vazia.")
        except Exception as e:
            errors.append(f"{model_name}: {e}")
    return None, None


def _generate_with_openai(prompt, errors):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        errors.append("OpenAI sem OPENAI_API_KEY.")
        return None, None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("MARKET_REPORT_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Voce e um estrategista-chefe de mesa institucional. "
                        "Responda em portugues do Brasil, com leitura macro objetiva."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        text = (completion.choices[0].message.content or "").strip()
        if text:
            return text, f"OpenAI/{os.getenv('MARKET_REPORT_OPENAI_MODEL', 'gpt-4o-mini')}"
        errors.append("OpenAI: resposta vazia.")
    except Exception as e:
        errors.append(f"OpenAI: {e}")
    return None, None


def _generate_ai_report_text(prompt):
    errors = []
    text, provider = _generate_with_gemini(prompt, errors)
    if text:
        return text, provider, errors
    text, provider = _generate_with_openai(prompt, errors)
    if text:
        return text, provider, errors
    raise RuntimeError("Falha nas IAs do Market Report: " + " | ".join(errors))


def _flatten_assets(global_data):
    categories = global_data.get("categories", global_data) if isinstance(global_data, dict) else {}
    assets = []
    if isinstance(categories, dict):
        for items in categories.values():
            if isinstance(items, list):
                assets.extend([item for item in items if isinstance(item, dict)])
    return assets


def _find_asset(global_data, *names):
    names_norm = [name.lower() for name in names]
    for item in _flatten_assets(global_data):
        item_name = str(item.get("name", "")).lower()
        item_symbol = str(item.get("symbol", "")).lower()
        if any(name in item_name or name in item_symbol for name in names_norm):
            return item
    return {}


def _fmt_asset(item):
    if not item:
        return "---"
    name = item.get("name", "Ativo")
    price = item.get("price", "---")
    change = item.get("change", 0)
    change_bps = item.get("change_bps")
    try:
        price_txt = f"{float(price):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        price_txt = str(price)
    try:
        if change_bps is not None:
            change_txt = f"{float(change_bps):+.1f} bps"
        else:
            change_txt = f"{float(change):+.2f}%"
    except Exception:
        change_txt = str(change)
    return f"{name}: {price_txt} ({change_txt})"


def _change(item):
    try:
        return float(item.get("change", 0))
    except Exception:
        return 0.0


def _has_asset(item):
    return isinstance(item, dict) and bool(item.get("name") or item.get("symbol"))


def _asset_line(*items):
    present = [_fmt_asset(item) for item in items if _has_asset(item)]
    return " | ".join(present) if present else "Dados de mercado indisponiveis no cache."


def _score_from_asset(item, positive_when_up=True):
    if not _has_asset(item):
        return 0
    change = _change(item)
    if abs(change) < 0.01:
        return 0
    if positive_when_up:
        return 1 if change > 0 else -1
    return 1 if change < 0 else -1


def _asset_snapshot(global_data):
    return {
        "spx": _find_asset(global_data, "s&p 500", "sp 500", "^gspc", "spy", "usa500"),
        "nasdaq": _find_asset(global_data, "nasdaq", "^ixic", "nas100", "usatec"),
        "dow": _find_asset(global_data, "dow", "djia", "^dji"),
        "russell": _find_asset(global_data, "russell", "rty", "iwm"),
        "vix": _find_asset(global_data, "vix", "^vix", "vxx"),
        "dxy": _find_asset(global_data, "dxy", "dolar index", "dollar index", "dx-y"),
        "us02y": _find_asset(global_data, "us02y", "us 02y", "us 2y", "2 year", "dgs2", "2yy=f"),
        "us10y": _find_asset(global_data, "us10y", "us 10y", "10 year", "^tnx"),
        "us30y": _find_asset(global_data, "us30y", "us 30y", "30 year", "^tyx"),
        "brent": _find_asset(global_data, "brent", "bz=f", "ukoil"),
        "wti": _find_asset(global_data, "wti", "cl=f", "crude oil"),
        "gold": _find_asset(global_data, "gold", "ouro", "xau", "gc=f"),
        "ibov": _find_asset(global_data, "ibov", "bovespa", "^bvsp"),
        "ewz": _find_asset(global_data, "ewz"),
        "usbrl": _find_asset(global_data, "usdbrl", "brl=x", "usdb"),
    }


def _direction_word(item, positive_when_up=True):
    if not _has_asset(item):
        return "sem dado"
    change = _change(item)
    if abs(change) < 0.05:
        return "estavel"
    if positive_when_up:
        return "alta" if change > 0 else "queda"
    return "queda favoravel" if change < 0 else "alta desfavoravel"


def _market_regime(snapshot):
    score = 0
    components = []
    checks = [
        ("S&P 500", snapshot.get("spx"), True),
        ("Nasdaq", snapshot.get("nasdaq"), True),
        ("Dow", snapshot.get("dow"), True),
        ("VIX", snapshot.get("vix"), False),
        ("DXY", snapshot.get("dxy"), False),
        ("US02Y", snapshot.get("us02y"), False),
        ("US10Y", snapshot.get("us10y"), False),
        ("US30Y", snapshot.get("us30y"), False),
    ]
    for label, item, positive_when_up in checks:
        if not _has_asset(item):
            continue
        point = _score_from_asset(item, positive_when_up=positive_when_up)
        score += point
        if point:
            components.append(f"{label} {_direction_word(item, positive_when_up)}")

    if score >= 3:
        label = "Risk-on"
        tone = "apetite a risco dominante, desde que juros e DXY nao acelerem contra o movimento."
    elif score <= -3:
        label = "Risk-off"
        tone = "defensivo, com pressao de juros/dolar/volatilidade ou perda de tracao dos indices."
    else:
        label = "Neutro/seletivo"
        tone = "sinais mistos; operar com confirmacao entre juros, DXY, petroleo e indices."
    return {"score": score, "label": label, "tone": tone, "components": components[:6]}


def _market_context_lines(snapshot, regime):
    groups = [
        ("Indices EUA", [snapshot.get("spx"), snapshot.get("nasdaq"), snapshot.get("dow"), snapshot.get("russell"), snapshot.get("vix")]),
        ("Juros e dolar", [snapshot.get("us02y"), snapshot.get("us10y"), snapshot.get("us30y"), snapshot.get("dxy"), snapshot.get("usbrl")]),
        ("Commodities", [snapshot.get("brent"), snapshot.get("wti"), snapshot.get("gold")]),
        ("Brasil/EM", [snapshot.get("ibov"), snapshot.get("ewz")]),
    ]
    lines = [f"- Regime calculado: {regime['label']} (score {regime['score']}). {regime['tone']}"]
    if regime["components"]:
        lines.append("- Sinais dominantes: " + "; ".join(regime["components"]) + ".")
    for label, items in groups:
        lines.append(f"- {label}: {_asset_line(*items)}")
    return lines


def _market_implications(snapshot, regime):
    dxy = _change(snapshot.get("dxy"))
    us02y = _change(snapshot.get("us02y"))
    us10y = _change(snapshot.get("us10y"))
    us30y = _change(snapshot.get("us30y"))
    vix = _change(snapshot.get("vix"))
    nasdaq = _change(snapshot.get("nasdaq"))
    brent = _change(snapshot.get("brent"))
    usbrl = _change(snapshot.get("usbrl"))

    implications = []
    if us02y > 0.05:
        implications.append("US02Y em alta indica front-end mais hawkish; Fed e dolar seguem como filtro principal para risco.")
    elif us02y < -0.05:
        implications.append("US02Y cedendo sugere alivio no front-end da curva e melhora a leitura de liquidez.")

    if us10y > 0.05 or us30y > 0.05:
        implications.append("Juros longos em alta reduzem conforto para duration e pressionam Nasdaq/multiplos.")
    elif us10y < -0.05 or us30y < -0.05:
        implications.append("Juros longos cedendo aliviam duration e favorecem tecnologia/ativos de risco.")
    else:
        implications.append("Juros longos sem direcao forte deixam o foco em DXY, petroleo e agenda.")

    if dxy > 0.05:
        implications.append("DXY firme encarece emergentes e pode limitar fluxo para Brasil.")
    elif dxy < -0.05:
        implications.append("DXY fraco melhora liquidez para emergentes e reduz pressao em USDBRL.")

    if brent > 0.4:
        implications.append("Petroleo em alta adiciona risco inflacionario; se vier com yields altos, leitura fica menos construtiva.")
    elif brent < -0.4:
        implications.append("Petroleo em queda alivia inflacao esperada, mas pode sinalizar preocupacao com crescimento.")

    if vix > 0.5 and nasdaq < 0:
        implications.append("VIX subindo com Nasdaq negativo reforca protecao e menor apetite a risco.")
    if usbrl > 0.2:
        implications.append("USDBRL em alta exige cautela com Brasil, mesmo que indices externos tentem recuperar.")

    implications.append(f"Leitura final do painel: {regime['label']}.")
    return implications


def _dominant_news_theme(news):
    text = " ".join(f"{item.get('title', '')} {item.get('summary', '')}" for item in news).lower()
    themes = [
        ("Payroll/Fed", ["payroll", "jobs", "fed", "fomc", "powell", "juros", "rate"]),
        ("Inflacao", ["inflation", "cpi", "pce", "ppi", "inflacao", "inflação"]),
        ("Geopolitica", ["israel", "iran", "russia", "china", "war", "sanction", "guerra"]),
        ("Commodities", ["oil", "brent", "wti", "gold", "commodity", "petroleo", "petróleo", "ouro"]),
        ("Tecnologia/IA", ["ai", "chips", "nvidia", "technology", "tech", "semiconductor"]),
    ]
    hits = []
    for label, keywords in themes:
        score = sum(text.count(keyword) for keyword in keywords)
        if score:
            hits.append((score, label))
    hits.sort(reverse=True)
    return hits[0][1] if hits else "macro global"


def _event_value(event, key):
    value = str(event.get(key, "") or "").strip()
    return value if value and value not in ["-", "---"] else "---"


def _parse_event_number(value):
    value = _event_value({"v": value}, "v")
    if value == "---":
        return None
    match = re.search(r"-?\d+(?:[,.]\d+)?", value.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except Exception:
        return None


def _surprise_phrase(event, lower_is_better=False):
    actual_num = _parse_event_number(event.get("actual"))
    forecast_num = _parse_event_number(event.get("forecast"))
    if actual_num is None or forecast_num is None:
        return ""
    diff = actual_num - forecast_num
    tolerance = max(abs(forecast_num) * 0.01, 0.0001)
    if abs(diff) <= tolerance:
        return "Atual em linha com a projecao."
    if lower_is_better:
        return "Atual abaixo da projecao: leitura mais favoravel ao risco/juros." if diff < 0 else "Atual acima da projecao: leitura menos favoravel ao risco/juros."
    return "Atual acima da projecao." if diff > 0 else "Atual abaixo da projecao."


def _event_scenario(event):
    name = str(event.get("event", "")).lower()
    currency = event.get("currency", "---")
    base = (
        f"Projecao {_event_value(event, 'forecast')}; "
        f"anterior {_event_value(event, 'previous')}; "
        f"atual {_event_value(event, 'actual')}."
    )
    inflation_keys = ["cpi", "pce", "ppi", "inflation", "price", "prices", "precos", "preços", "inflacao", "inflação", "indice de precos", "indice de preços"]
    wage_keys = ["wage", "wages", "earnings", "salario", "salário", "ganho medio", "ganho médio", "remuneracao", "remuneração"]
    unemployment_keys = ["unemployment", "jobless", "claims", "desemprego", "seguro desemprego", "pedidos de seguro"]
    jobs_keys = ["payroll", "employment", "emprego", "adp", "nonfarm", "jolts", "vagas"]
    growth_keys = ["gdp", "pib", "pmi", "ism", "retail", "sales", "vendas", "consumer confidence", "confidence", "confianca", "confiança", "industrial production", "producao industrial", "produção industrial", "durable goods", "bens duraveis"]
    central_bank_keys = ["rate", "fomc", "fed", "ecb", "boe", "boj", "speaks", "statement", "minutes", "discurso", "fala", "ata", "decisao", "decisão", "juros", "banco central"]
    oil_keys = ["oil", "crude", "inventories", "gasoline", "storage", "petroleo", "petróleo", "estoques", "eia"]

    if any(k in name for k in inflation_keys):
        surprise = _surprise_phrase(event, lower_is_better=True)
        return f"{base} {surprise} Acima: pressiona juros reais, DXY e expectativas de aperto; pesa em Nasdaq/S&P. Abaixo: reforca desinflacao, alivia yields e favorece duration/indices."
    if any(k in name for k in wage_keys):
        surprise = _surprise_phrase(event, lower_is_better=True)
        return f"{base} {surprise} Acima: pressao salarial/hawkish, US10Y e DXY tendem a subir; abaixo: alivia inflacao de servicos e favorece duration/indices."
    if any(k in name for k in unemployment_keys):
        surprise = _surprise_phrase(event, lower_is_better=False)
        return f"{base} {surprise} Acima: mercado de trabalho mais frouxo, yields podem ceder, mas aumenta risco de desaceleracao. Abaixo: trabalho apertado, DXY/US10Y podem subir e indices perdem conforto."
    if any(k in name for k in jobs_keys):
        surprise = _surprise_phrase(event)
        return f"{base} {surprise} Forte: sustenta crescimento/risk-on inicial, mas pode elevar US10Y se reduzir cortes. Fraco: favorece queda de yields, porem pesa em ciclicos se indicar desaceleracao."
    if any(k in name for k in growth_keys):
        surprise = _surprise_phrase(event)
        return f"{base} {surprise} Acima: melhora leitura de atividade e favorece risco, salvo se reacender juros. Abaixo: reduz yields, mas pode pressionar indices por medo de desaceleracao."
    if any(k in name for k in central_bank_keys):
        return f"{base} Tom hawkish: juros e {currency} para cima, indices sob pressao. Tom dovish: yields cedem e risco melhora."
    if any(k in name for k in oil_keys):
        return f"{base} Estoques menores: suporte ao petroleo e risco inflacionario. Estoques maiores: pesa no petroleo e alivia inflacao."
    return f"{base} Acima tende a fortalecer moeda/atividade local; abaixo tende a aliviar juros, mas pode pesar em risco se confirmar perda de crescimento."


def _event_category(event):
    name = str(event.get("event", "")).lower()
    buckets = [
        ("inflacao", ["cpi", "pce", "ppi", "inflation", "price", "prices", "precos", "inflacao"]),
        ("salarios", ["wage", "wages", "earnings", "salario", "ganho medio", "remuneracao"]),
        ("emprego", ["payroll", "employment", "emprego", "adp", "nonfarm", "jolts", "vagas", "jobless", "claims", "unemployment", "desemprego"]),
        ("atividade", ["gdp", "pib", "pmi", "ism", "retail", "sales", "vendas", "confidence", "confianca", "industrial production", "producao industrial", "durable goods"]),
        ("banco central", ["rate", "fomc", "fed", "ecb", "boe", "boj", "speaks", "statement", "minutes", "discurso", "fala", "ata", "decisao", "juros", "banco central"]),
        ("petroleo", ["oil", "crude", "inventories", "gasoline", "storage", "petroleo", "estoques", "eia"]),
    ]
    for category, keys in buckets:
        if any(key in name for key in keys):
            return category
    return "macro"


def _event_surprise_label(event, lower_is_better=False):
    actual_num = _parse_event_number(event.get("actual"))
    forecast_num = _parse_event_number(event.get("forecast"))
    previous_num = _parse_event_number(event.get("previous"))
    if actual_num is None:
        if forecast_num is not None and previous_num is not None:
            diff = forecast_num - previous_num
            tolerance = max(abs(previous_num) * 0.01, 0.0001)
            if abs(diff) <= tolerance:
                return "projecao em linha com anterior"
            if lower_is_better:
                return "projecao abaixo do anterior" if diff < 0 else "projecao acima do anterior"
            return "projecao acima do anterior" if diff > 0 else "projecao abaixo do anterior"
        return "aguardando atual"
    if forecast_num is None:
        if previous_num is None:
            return "divulgado sem base comparativa"
        diff = actual_num - previous_num
        tolerance = max(abs(previous_num) * 0.01, 0.0001)
        if abs(diff) <= tolerance:
            return "em linha com anterior"
        if lower_is_better:
            return "abaixo do anterior" if diff < 0 else "acima do anterior"
        return "acima do anterior" if diff > 0 else "abaixo do anterior"
    diff = actual_num - forecast_num
    tolerance = max(abs(forecast_num) * 0.01, 0.0001)
    if abs(diff) <= tolerance:
        return "em linha com projecao"
    if lower_is_better:
        return "abaixo da projecao" if diff < 0 else "acima da projecao"
    return "acima da projecao" if diff > 0 else "abaixo da projecao"


def _event_scenario(event):
    category = _event_category(event)
    currency = event.get("currency", "---")
    lower_is_better = category in {"inflacao", "salarios", "petroleo"}
    surprise = _event_surprise_label(event, lower_is_better=lower_is_better)
    base = (
        f"Atual {_event_value(event, 'actual')} | "
        f"Projecao {_event_value(event, 'forecast')} | "
        f"Anterior {_event_value(event, 'previous')} | "
        f"Leitura: {surprise}."
    )

    if category == "inflacao":
        return f"{base} Acima: hawkish, juros/DXY para cima e pressao em Nasdaq/S&P. Abaixo: dovish, alivia yields e favorece duration/indices."
    if category == "salarios":
        return f"{base} Salarios fortes elevam risco de inflacao de servicos e Fed mais duro; salarios fracos aliviam juros longos."
    if category == "emprego":
        return f"{base} Forte sustenta crescimento, mas pode reduzir aposta de corte; fraco derruba yields, porem aumenta medo de desaceleracao."
    if category == "atividade":
        return f"{base} Acima favorece crescimento e risco; abaixo pesa em ciclicos, salvo se queda de yields dominar."
    if category == "banco central":
        return f"{base} Tom hawkish tende a fortalecer {currency}, DXY/yields e pesar em indices; tom dovish faz o inverso."
    if category == "petroleo":
        return f"{base} Estoques menores sustentam petroleo e inflacao; estoques maiores aliviam energia e expectativas inflacionarias."
    return f"{base} Surpresa positiva favorece moeda/atividade local; surpresa negativa tende a reduzir juros, mas pode pesar em risco."


def _select_calendar_events(calendar_data, date_str, limit=7):
    if isinstance(calendar_data, dict):
        calendar_data = calendar_data.get("events") or calendar_data.get("value") or []
    if not isinstance(calendar_data, list):
        return []
    currencies = {"USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "NZD", "CHF", "BRL"}
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "HOLIDAY": 9}
    events = [
        event for event in calendar_data
        if event.get("date") == date_str
        and event.get("currency") in currencies
        and str(event.get("impact", "")).upper() != "HOLIDAY"
    ]
    events.sort(key=lambda event: (impact_rank.get(str(event.get("impact", "")).upper(), 5), event.get("time", "99:99")))
    priority = [event for event in events if str(event.get("impact", "")).upper() in {"HIGH", "MEDIUM"}]
    selected = priority[:limit]
    if len(selected) < min(limit, 4):
        selected.extend([event for event in events if event not in selected][: limit - len(selected)])
    return selected[:limit]


def _calendar_context_lines(calendar_events):
    if not calendar_events:
        return ["- Sem eventos economicos relevantes carregados para hoje no calendario."]
    lines = []
    for event in calendar_events:
        bulls = event.get("bull_count")
        bulls_txt = f" | {bulls} touro(s)" if bulls else ""
        lines.append(
            f"- {event.get('time', '---')} | {event.get('currency', '---')} | "
            f"{str(event.get('impact', '---')).upper()}{bulls_txt} | {event.get('event', '---')} | "
            f"Atual: {_event_value(event, 'actual')} | Projecao: {_event_value(event, 'forecast')} | "
            f"Anterior: {_event_value(event, 'previous')}"
        )
    return lines


def _calendar_scenario_lines(calendar_events, limit=5):
    if not calendar_events:
        return ["- Sem agenda relevante carregada para hoje; priorizar price action, juros, DXY e noticias."]
    return [
        f"- **{event.get('time', '---')} {event.get('currency', '---')} - {event.get('event', '---')}:** {_event_scenario(event)}"
        for event in calendar_events[:limit]
    ]


def _load_calendar_events_for_report(date_str):
    """Prioriza Investing ao vivo; usa Supabase/arquivo local como backup no Streamlit Cloud."""
    cached_calendar = _load_json_file("calendario_economico.json", [])
    supabase_calendar = _load_app_state_value("calendario_economico", [])
    live_error = None

    try:
        from execution.fetch_calendar import _fetch_investing_calendar

        print("[*] Coletando calendario economico Investing.com para o Market Report...")
        live_calendar = _fetch_investing_calendar()
        live_events = _select_calendar_events(live_calendar, date_str)
        if live_events:
            try:
                with open("calendario_economico.json", "w", encoding="utf-8") as f:
                    json.dump(live_calendar, f, ensure_ascii=False)
            except Exception as e:
                print(f"[WARN] Nao foi possivel atualizar calendario_economico.json: {e}")
            return live_events, "Investing.com ao vivo"
        live_error = "Investing.com retornou calendario sem eventos relevantes para hoje."
    except Exception as e:
        live_error = str(e)

    supabase_events = _select_calendar_events(supabase_calendar, date_str)
    if supabase_events:
        if live_error:
            print(f"[WARN] Calendario Investing indisponivel; usando Supabase: {live_error}")
        return supabase_events, "Supabase calendario_economico"

    cached_events = _select_calendar_events(cached_calendar, date_str)
    if cached_events:
        if live_error:
            print(f"[WARN] Calendario Investing indisponivel; usando cache: {live_error}")
        return cached_events, "Cache calendario_economico"

    if live_error:
        print(f"[WARN] Calendario Investing indisponivel e cache vazio: {live_error}")
    return [], "Indisponivel"


def _generate_local_report_text(slot_meta, date_str, local_data, global_data, news, previous_reports, calendar_events, calendar_source):
    spx = _find_asset(global_data, "s&p 500", "^gspc", "spy")
    nasdaq = _find_asset(global_data, "nasdaq", "^ixic")
    dxy = _find_asset(global_data, "dxy", "dx-y")
    us02y = _find_asset(global_data, "us 02y", "us 2y", "us02y", "dgs2", "2yy=f")
    us10y = _find_asset(global_data, "us 10y", "^tnx")
    brent = _find_asset(global_data, "brent", "bz=f")
    gold = _find_asset(global_data, "gold", "gc=f")
    vix = _find_asset(global_data, "vix", "^vix")
    usbrl = _find_asset(global_data, "usdbrl", "brl=x")

    risk_score = 0
    risk_score += _score_from_asset(spx)
    risk_score += _score_from_asset(nasdaq)
    risk_score += _score_from_asset(vix, positive_when_up=False)
    risk_score += _score_from_asset(dxy, positive_when_up=False)
    risk_score += _score_from_asset(us02y, positive_when_up=False)
    risk_score += _score_from_asset(us10y, positive_when_up=False)
    risk_label = "Risk-on moderado" if risk_score >= 2 else ("Risk-off moderado" if risk_score <= -2 else "Neutro/seletivo")
    dominant_theme = _dominant_news_theme(news)

    news_lines = []
    for item in news[:5]:
        source = item.get("source", "Fonte")
        title = item.get("title", "")
        if title:
            news_lines.append(f"- [{source}] {title}")
    if not news_lines:
        news_lines.append("- Sem manchetes novas relevantes no feed RSS no momento.")

    return f"""### Drivers do momento

- **Regime:** {risk_label}. A leitura combina indices americanos, volatilidade, DXY, US02Y e juros longos.
- **Tema dominante do radar:** {dominant_theme}. O mercado tende a precificar primeiro o impacto em Fed/juros, depois reflexo em DXY, commodities e indices.
- **Indices/volatilidade:** {_asset_line(spx, nasdaq, vix)}
- **Juros, moedas e commodities:** {_asset_line(us02y, us10y, dxy, usbrl, brent, gold)}

### Global vs Brasil

- **Juros EUA:** US02Y mede o front-end/Fed; queda em US10Y favorece duration, Nasdaq e ativos de risco; alta nos yields aumenta risco de compressao de multiplos.
- **DXY/BRL:** DXY fraco e USDBRL cedendo aliviam emergentes; DXY forte muda o foco para protecao cambial e reduz apetite por Brasil.
- **Commodities:** petroleo e ouro ajudam a separar choque inflacionario de busca por protecao. Petroleo em alta com yields subindo tende a ser mais risk-off.
- **Brasil:** viés depende da combinacao EWZ/IBOV, USDBRL e commodities. Sem confirmacao nesses tres eixos, evitar leitura direcional agressiva.

### Calendario economico e cenarios

- **Fonte:** {calendar_source}.
{chr(10).join(_calendar_scenario_lines(calendar_events))}

### Riscos radar

{chr(10).join(news_lines)}

**Viés tatico:** {risk_label}. Confirmar pelo comportamento conjunto de DXY, US02Y/US10Y, petroleo, S&P 500 e Nasdaq.
"""


def _generate_local_report_text(slot_meta, date_str, local_data, global_data, news, previous_reports, calendar_events, calendar_source):
    snapshot = _asset_snapshot(global_data)
    regime = _market_regime(snapshot)
    dominant_theme = _dominant_news_theme(news)
    context_lines = _market_context_lines(snapshot, regime)
    implication_lines = _market_implications(snapshot, regime)

    news_lines = []
    for item in news[:5]:
        source = item.get("source", "Fonte")
        title = item.get("title", "")
        summary = item.get("summary", "")
        if title:
            suffix = f" - {summary}" if summary else ""
            news_lines.append(f"- [{source}] {title}{suffix}")
    if not news_lines:
        news_lines.append("- Sem manchetes novas relevantes no feed RSS no momento.")

    return f"""### Drivers do momento

- **Regime:** {regime['label']} ({regime['score']}). {regime['tone']}
- **Tema dominante:** {dominant_theme}. O mercado deve precificar primeiro juros/Fed, depois DXY, commodities e indices.
{chr(10).join(context_lines[1:])}

### Global vs Brasil

{chr(10).join(f"- {line}" for line in implication_lines)}
- **Brasil:** avaliar IBOV/EWZ, USDBRL e commodities em conjunto. Sem confirmacao nesses tres eixos, evitar leitura direcional agressiva.

### Calendario economico e cenarios

- **Fonte:** {calendar_source}.
{chr(10).join(_calendar_scenario_lines(calendar_events))}

### Riscos radar

{chr(10).join(news_lines)}

**Vies tatico:** {regime['label']}. Confirmar pelo comportamento conjunto de DXY, US02Y/US10Y/US30Y, petroleo, S&P 500, Nasdaq e Dow Jones.
"""


def generate_market_report(slot=None, force=False):
    now = _now_local()
    date_str = now.strftime("%Y-%m-%d")
    slot = slot or get_report_slot(now, force=force)
    daily_data = load_daily_reports(date_str)

    if not slot:
        print("[*] Fora das janelas de Market Report. Mantendo historico do dia.")
        if daily_data.get("reports"):
            latest = daily_data["reports"][-1]
            with open(LATEST_REPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(latest, f, ensure_ascii=False, indent=2)
            return latest
        return None

    if not force:
        existing = next((r for r in daily_data.get("reports", []) if r.get("slot") == slot), None)
        if existing:
            print(f"[*] Market Report {slot} ja existe para {date_str}. Mantendo registro.")
            with open(LATEST_REPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            return existing

    try:
        local_data = _load_json_file("dados_mercado.json", {})
        global_data = _load_json_file("mercados_globais.json", {})

        print(f"[*] Coletando noticias para o relatorio {slot}...")
        news = fetch_all_news(max_results=18, max_age_hours=12)
        news_context = "\n".join(
            [f"- [{n['source']}] {n['title']}: {n['summary']}" for n in news]
        )
        calendar_events, calendar_source = _load_calendar_events_for_report(date_str)
        calendar_context = "\n".join(_calendar_context_lines(calendar_events))
        market_snapshot = _asset_snapshot(global_data)
        market_regime = _market_regime(market_snapshot)
        market_context = "\n".join(_market_context_lines(market_snapshot, market_regime))
        market_implications = "\n".join(f"- {line}" for line in _market_implications(market_snapshot, market_regime))
        try:
            from execution.yield_curve_regime import analyze_yield_curve_regime

            curve_context = analyze_yield_curve_regime(global_data)
        except Exception as curve_error:
            curve_context = {"regime": "Neutro", "operational_bias": "Neutro", "macro_reading": f"Curva indisponivel: {curve_error}"}

        slot_meta = REPORT_SLOTS[slot]
        previous_reports = "\n\n".join(
            [
                f"{REPORT_SLOTS.get(r.get('slot'), {}).get('label', r.get('slot'))} ({r.get('updated_at')}):\n{r.get('report', '')}"
                for r in daily_data.get("reports", [])
                if r.get("slot") != slot
            ]
        ) or "Sem reports anteriores hoje."

        prompt = f"""
Voce e um Estrategista-Chefe de uma Mesa de Operacoes Institucional.
Crie o MARKET REPORT {slot_meta['label'].upper()} de {date_str}.

FOCO DO SLOT:
{slot_meta['focus']}

CONTEXTO DE MERCADO:
- LOCAL (WIN/WDO): {json.dumps(local_data, ensure_ascii=False)}
- GLOBAL: {json.dumps(global_data, ensure_ascii=False)}

PRINCIPAIS NOTICIAS DO MOMENTO:
{news_context}

CALENDARIO ECONOMICO DE HOJE (HORARIO DE BRASILIA):
Fonte: {calendar_source}
{calendar_context}

REPORTS JA REGISTRADOS HOJE:
{previous_reports}

INSTRUCOES:
1. Conecte noticias aos movimentos de preco.
2. Seja direto, profissional e com linguagem de mesa.
3. Nao repita mecanicamente reports anteriores; atualize a leitura do dia.
4. Divida em 4 secoes curtas:
   - DRIVERS DO MOMENTO
   - GLOBAL VS BRASIL
   - CALENDARIO ECONOMICO E CENARIOS
   - RISCOS RADAR
5. Na secao de calendario, destaque os principais eventos do dia, informe Atual/Projecao/Anterior quando houver e descreva cenarios breves: acima da projecao, abaixo da projecao, hawkish/dovish e impactos em juros, DXY, petroleo, S&P 500, Nasdaq e Dow Jones.
6. Termine com uma linha "Viés tatico:".

Use Markdown compacto. Evite texto longo.
"""

        prompt = f"""
Voce e um Estrategista-Chefe de uma Mesa de Operacoes Institucional.
Crie o MARKET REPORT {slot_meta['label'].upper()} de {date_str} em portugues do Brasil.

FOCO DO SLOT:
{slot_meta['focus']}

PAINEL MACRO JA PROCESSADO:
{market_context}

IMPLICACOES INTERMERCADOS:
{market_implications}

DADOS BRUTOS DE APOIO:
- LOCAL: {json.dumps(local_data, ensure_ascii=False)}
- GLOBAL: {json.dumps(global_data, ensure_ascii=False)}

PRINCIPAIS NOTICIAS DO MOMENTO:
{news_context}

CALENDARIO ECONOMICO DE HOJE (HORARIO DE BRASILIA):
Fonte: {calendar_source}
{calendar_context}

REPORTS JA REGISTRADOS HOJE:
{previous_reports}

INSTRUCOES:
1. Conecte noticias, calendario e movimentos de preco em uma leitura unica de mesa.
2. Seja direto, profissional e operacional; evite frases genericas.
3. Nao repita mecanicamente reports anteriores; atualize a leitura do dia e destaque mudancas de regime.
4. Divida em 4 secoes curtas:
   - DRIVERS DO MOMENTO
   - GLOBAL VS BRASIL
   - CALENDARIO ECONOMICO E CENARIOS
   - RISCOS RADAR
5. Na secao de calendario, destaque os principais eventos do dia, informe Atual/Projecao/Anterior quando houver e descreva cenarios breves: acima da projecao, abaixo da projecao, hawkish/dovish e impactos em juros, DXY, petroleo, S&P 500, Nasdaq e Dow Jones.
6. Classifique o vies como Risk-on, Risk-off ou Neutro/seletivo. Nao cite WIN nem recomendacao de day trade.
7. Termine com uma linha "Vies tatico:".

Use Markdown compacto. Evite texto longo.
"""

        prompt = f"""
Voce e o Estrategista-Chefe de uma mesa institucional macro global.
Crie o MARKET REPORT {slot_meta['label'].upper()} de {date_str} em portugues do Brasil.

Use somente os dados fornecidos. Nao invente precos, noticias, eventos ou leituras ausentes.
Para cada conclusao importante, use o padrao mental: dado observado -> leitura macro -> impacto provavel.

FOCO DO SLOT:
{slot_meta['focus']}

HIERARQUIA OBRIGATORIA:
1. Curva de juros americana e yields
2. DXY / dolar global
3. VIX / apetite a risco
4. S&P 500, Nasdaq e Dow
5. Commodities: petroleo, ouro e cripto quando relevante
6. Emergentes/Brasil: EWZ, IBOV, USDBRL
7. Calendario economico e noticias

PAINEL MACRO JA PROCESSADO:
{market_context}

IMPLICACOES INTERMERCADOS:
{market_implications}

REGIME DA CURVA AMERICANA:
{json.dumps(curve_context, ensure_ascii=False)}

DADOS BRUTOS DE APOIO:
- LOCAL: {json.dumps(local_data, ensure_ascii=False)}
- GLOBAL: {json.dumps(global_data, ensure_ascii=False)}

PRINCIPAIS NOTICIAS DO MOMENTO:
{news_context}

CALENDARIO ECONOMICO DE HOJE (HORARIO DE BRASILIA):
Fonte: {calendar_source}
{calendar_context}

REPORTS JA REGISTRADOS HOJE:
{previous_reports}

INSTRUCOES:
1. Nao analise ativos isolados; sempre relacione juros, DXY, VIX, indices, commodities e Brasil.
2. Se os sinais estiverem contraditorios, diga que o regime e misto e explique o conflito.
3. Nao repita mecanicamente reports anteriores; atualize a leitura e destaque mudancas de regime.
4. Seja curto, direto, profissional e sem frases genericas.
5. Nao cite WIN e nao de recomendacao de day trade.

FORMATO OBRIGATORIO:

### Drivers do momento
- 3 a 5 bullets.
- Explique o principal regime: Risk-on, Risk-off ou Neutro/seletivo.
- Destaque se ha alinhamento ou desalinhamento entre curva/juros, DXY, VIX e indices.

### Global vs Brasil
- Explique como o cenario global afeta EWZ, IBOV e USDBRL.
- Diga se Brasil tende a performar melhor, pior ou em linha com mercados globais.
- Cite commodities apenas se forem relevantes para Brasil.

### Calendario economico e cenarios
- Liste os principais eventos HIGH/MEDIUM.
- Para cada evento importante, informe Atual, Projecao e Anterior.
- Interprete acima/abaixo/em linha e impacto em juros, DXY, S&P 500, Nasdaq, Dow, petroleo/ouro quando fizer sentido.

### Riscos radar
- Liste riscos vindos das noticias.
- Separe risco de inflacao, crescimento, geopolitica e politica monetaria quando aplicavel.

### Vies tatico
- Uma linha final.
- Classifique como: Risk-on forte, Risk-on moderado, Neutro/seletivo, Risk-off moderado ou Risk-off forte.
- Diga o que confirmaria ou invalidaria esse vies.
"""

        ai_errors = []
        has_external_ai_key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
        if has_external_ai_key:
            print("[*] Gerando Market Report via IA...")
            report_text, provider, ai_errors = _generate_ai_report_text(prompt)
        else:
            print("[*] Gerando Market Report local sem chave de IA externa...")
            report_text = _generate_local_report_text(slot_meta, date_str, local_data, global_data, news, previous_reports, calendar_events, calendar_source)
            provider = "Local/sem chave IA"
            ai_errors = ["Nenhuma chave GOOGLE_API_KEY/GEMINI_API_KEY/OPENAI_API_KEY encontrada."]
        updated_at = now.strftime("%Y-%m-%d %H:%M:%S")
        report = {
            "date": date_str,
            "slot": slot,
            "slot_label": slot_meta["label"],
            "slot_window": slot_meta["window"],
            "report": report_text,
            "provider": provider,
            "calendar_source": calendar_source,
            "fallback_errors": ai_errors,
            "updated_at": updated_at,
        }

        daily_data = _upsert_slot_report(daily_data, report)
        save_daily_reports(daily_data)

        with open(LATEST_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"[+] Market Report {slot} gerado com sucesso.")
        return report

    except Exception as e:
        print(f"[!] Erro ao gerar Market Report: {e}")
        return None


if __name__ == "__main__":
    generate_market_report()
