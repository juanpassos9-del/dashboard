import requests
import json
import pandas as pd


IMPACT_LABELS = {
    "HIGH": "Alto",
    "MEDIUM": "Médio",
    "LOW": "Baixo",
}


def _events_to_dataframe(events):
    """Converte o JSON semanal em DataFrame compatível com os dashboards legados."""
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

def fetch_economic_calendar():
    # Este endpoint da ForexFactory (via faireconomy) fornece a semana inteira
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    try:
        response = requests.get(url, timeout=10)
        all_events_raw = response.json()
        
        processed_events = []
        
        for event in all_events_raw:
            impact = event.get('impact', '').upper()
            if impact == "HIGH": icon = "🔴"
            elif impact == "MEDIUM": icon = "🟡"
            else: icon = "⚪"
            
            # Formatação de data e hora
            # Ex: "2026-05-05T15:30:00-04:00"
            date_part = event['date'].split('T')[0]
            time_part = event['date'].split('T')[1][:5]
            
            processed_events.append({
                "date": date_part,
                "time": time_part,
                "currency": event.get('country', '???'),
                "event": event.get('title', 'Evento'),
                "impact": impact,
                "icon": icon,
                "previous": event.get('previous', '---'),
                "forecast": event.get('forecast', '---'),
                "actual": event.get('actual', '---')
            })
        
        # Ordena por data e depois por hora
        processed_events.sort(key=lambda x: (x['date'], x['time']))
        
        with open("calendario_economico.json", "w", encoding="utf-8") as f:
            json.dump(processed_events, f, ensure_ascii=False)
            
        return _events_to_dataframe(processed_events)
        
    except Exception as e:
        print(f"Erro ao buscar calendário semanal: {e}")
        return _events_to_dataframe([])

if __name__ == "__main__":
    fetch_economic_calendar()
