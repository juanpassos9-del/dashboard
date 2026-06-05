import json
import os
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


def generate_market_report(slot=None, force=False):
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("[!] Erro: configure GOOGLE_API_KEY/GEMINI_API_KEY ou OPENAI_API_KEY.")
        return None

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

REPORTS JA REGISTRADOS HOJE:
{previous_reports}

INSTRUCOES:
1. Conecte noticias aos movimentos de preco.
2. Seja direto, profissional e com linguagem de mesa.
3. Nao repita mecanicamente reports anteriores; atualize a leitura do dia.
4. Divida em 3 secoes curtas:
   - DRIVERS DO MOMENTO
   - GLOBAL VS BRASIL
   - RISCOS RADAR
5. Termine com uma linha "Viés tatico:".

Use Markdown compacto. Evite texto longo.
"""

        print("[*] Gerando Market Report via IA...")
        report_text, provider, ai_errors = _generate_ai_report_text(prompt)
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
