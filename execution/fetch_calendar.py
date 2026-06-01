import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup


IMPACT_LABELS = {
    "HIGH": "Alto",
    "MEDIUM": "Medio",
    "LOW": "Baixo",
}


def _events_to_dataframe(events):
    """Converte o JSON semanal em DataFrame compativel com os dashboards legados."""
    rows = []
    for event in events:
        rows.append({
            "Data": event.get("date", ""),
            "Horário": event.get("time", ""),
            "País": event.get("currency", "???"),
            "Evento": event.get("event", "Evento"),
            "Impacto": IMPACT_LABELS.get(event.get("impact", ""), event.get("impact", "")),
            "Atual": event.get("actual", "---"),
            "Previsão": event.get("forecast", "---"),
            "Anterior": event.get("previous", "---"),
        })
    return pd.DataFrame(rows)


def _impact_from_investing_title(title):
    title = (title or "").lower()
    if "high" in title:
        return "HIGH"
    if "moderate" in title or "medium" in title:
        return "MEDIUM"
    if "low" in title:
        return "LOW"
    return "LOW"


def _impact_icon(impact):
    if impact == "HIGH":
        return "🔴"
    if impact == "MEDIUM":
        return "🟡"
    return "⚪"


def _investing_request(base_url, language="pt-BR"):
    url = f"{base_url}/economic-calendar/Service/getCalendarFilteredData"
    session = requests.Session()
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{language},pt;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    session.get(f"{base_url}/economic-calendar/", timeout=12)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": f"{language},pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": base_url,
        "Referer": f"{base_url}/economic-calendar/",
    }
    payload = {
        "country[]": ["5", "4", "17", "72", "35", "25", "6", "12", "37", "26", "10", "14", "48"],
        "importance[]": ["1", "2", "3"],
        "timeZone": "8",
        "timeFilter": "timeOnly",
        "currentTab": "today",
        "limit_from": "0",
    }

    response = session.post(url, headers=headers, data=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def _fetch_investing_calendar():
    """Busca calendario no Investing.com, que inclui Atual/Projecao/Anterior."""
    last_error = None
    payload_json = None
    for base_url, language in [
        ("https://br.investing.com", "pt-BR"),
        ("https://www.investing.com", "en-US"),
    ]:
        try:
            payload_json = _investing_request(base_url, language)
            break
        except Exception as e:
            last_error = e
    if payload_json is None:
        raise last_error or RuntimeError("Investing.com indisponivel.")

    soup = BeautifulSoup(payload_json.get("data", ""), "html.parser")

    events = []
    for row in soup.select("tr.js-event-item"):
        cols = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cols) < 7:
            continue

        event_datetime = row.get("data-event-datetime", "")
        date_part = event_datetime[:10].replace("/", "-") if event_datetime else ""
        time_part = cols[0] or (event_datetime[11:16] if len(event_datetime) >= 16 else "")
        impact_cell = row.select_one("td.sentiment")
        impact = _impact_from_investing_title(impact_cell.get("title", "") if impact_cell else "")

        events.append({
            "date": date_part,
            "time": time_part,
            "currency": cols[1].strip() or "???",
            "event": cols[3].strip() or "Evento",
            "impact": impact,
            "icon": _impact_icon(impact),
            "actual": cols[4].strip() or "---",
            "forecast": cols[5].strip() or "---",
            "previous": cols[6].strip() or "---",
            "source": "Investing.com",
        })

    events.sort(key=lambda x: (x["date"], x["time"]))
    return events


def _fetch_faireconomy_calendar():
    """Fallback ForexFactory/Faireconomy; geralmente nao inclui Atual."""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    response = requests.get(url, timeout=10)
    all_events_raw = response.json()

    processed_events = []
    for event in all_events_raw:
        impact = event.get("impact", "").upper()
        event_dt = datetime.fromisoformat(event["date"]).astimezone(ZoneInfo("America/Sao_Paulo"))
        date_part = event_dt.strftime("%Y-%m-%d")
        time_part = event_dt.strftime("%H:%M")

        processed_events.append({
            "date": date_part,
            "time": time_part,
            "currency": event.get("country", "???"),
            "event": event.get("title", "Evento"),
            "impact": impact,
            "icon": _impact_icon(impact),
            "previous": event.get("previous", "---"),
            "forecast": event.get("forecast", "---"),
            "actual": event.get("actual", "---"),
            "source": "ForexFactory/Faireconomy",
        })

    processed_events.sort(key=lambda x: (x["date"], x["time"]))
    return processed_events


def fetch_economic_calendar(save_file=True):
    try:
        processed_events = _fetch_investing_calendar()
        if not processed_events:
            raise ValueError("Investing.com retornou calendario vazio.")
    except Exception as e:
        print(f"Erro ao buscar calendario Investing.com: {e}")
        try:
            processed_events = _fetch_faireconomy_calendar()
        except Exception as fallback_error:
            print(f"Erro ao buscar calendario semanal: {fallback_error}")
            return _events_to_dataframe([])

    if save_file:
        try:
            with open("calendario_economico.json", "w", encoding="utf-8") as f:
                json.dump(processed_events, f, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar calendario: {e}")

    return _events_to_dataframe(processed_events)


if __name__ == "__main__":
    fetch_economic_calendar()
