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
    try:
        price_txt = f"{float(price):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        price_txt = str(price)
    try:
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


def _generate_local_report_text(slot_meta, date_str, local_data, global_data, news, previous_reports, calendar_events):
    spx = _find_asset(global_data, "s&p 500", "^gspc", "spy")
    nasdaq = _find_asset(global_data, "nasdaq", "^ixic")
    dxy = _find_asset(global_data, "dxy", "dx-y")
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

- **Regime:** {risk_label}. A leitura combina indices americanos, volatilidade, DXY e juros longos.
- **Tema dominante do radar:** {dominant_theme}. O mercado tende a precificar primeiro o impacto em Fed/juros, depois reflexo em DXY, commodities e indices.
- **Indices/volatilidade:** {_asset_line(spx, nasdaq, vix)}
- **Juros, moedas e commodities:** {_asset_line(us10y, dxy, usbrl, brent, gold)}

### Global vs Brasil

- **Juros EUA:** queda em US10Y favorece duration, Nasdaq e ativos de risco; alta nos yields aumenta risco de compressao de multiplos.
- **DXY/BRL:** DXY fraco e USDBRL cedendo aliviam emergentes; DXY forte muda o foco para protecao cambial e reduz apetite por Brasil.
- **Commodities:** petroleo e ouro ajudam a separar choque inflacionario de busca por protecao. Petroleo em alta com yields subindo tende a ser mais risk-off.
- **Brasil:** viés depende da combinacao EWZ/IBOV, USDBRL e commodities. Sem confirmacao nesses tres eixos, evitar leitura direcional agressiva.

### Calendario economico e cenarios

{chr(10).join(_calendar_scenario_lines(calendar_events))}

### Riscos radar

{chr(10).join(news_lines)}

**Viés tatico:** {risk_label}. Confirmar pelo comportamento conjunto de DXY, US10Y, petroleo, S&P 500 e Nasdaq.
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
        calendar_data = _load_json_file("calendario_economico.json", [])

        print(f"[*] Coletando noticias para o relatorio {slot}...")
        news = fetch_all_news(max_results=18, max_age_hours=12)
        news_context = "\n".join(
            [f"- [{n['source']}] {n['title']}: {n['summary']}" for n in news]
        )
        calendar_events = _select_calendar_events(calendar_data, date_str)
        if not calendar_events:
            try:
                from execution.fetch_calendar import _fetch_investing_calendar

                live_calendar = _fetch_investing_calendar()
                live_events = _select_calendar_events(live_calendar, date_str)
                if live_events:
                    calendar_data = live_calendar
                    calendar_events = live_events
            except Exception as e:
                print(f"[WARN] Calendario ao vivo indisponivel para Market Report: {e}")
        calendar_context = "\n".join(_calendar_context_lines(calendar_events))

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

        ai_errors = []
        has_external_ai_key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
        if has_external_ai_key:
            print("[*] Gerando Market Report via IA...")
            report_text, provider, ai_errors = _generate_ai_report_text(prompt)
        else:
            print("[*] Gerando Market Report local sem chave de IA externa...")
            report_text = _generate_local_report_text(slot_meta, date_str, local_data, global_data, news, previous_reports, calendar_events)
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
