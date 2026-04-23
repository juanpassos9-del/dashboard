import requests
import json
from datetime import datetime

def fetch_economic_calendar():
    # Usando a API do TradingEconomics ou similar que seja mais rápida nos actuals
    # Por segurança, vamos usar um endpoint que costuma ter os dados em real-time
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    try:
        response = requests.get(url)
        all_events = response.json()
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_events = []
        
        for event in all_events:
            # Pegando a data local
            event_date = event['date'].split('T')[0]
            
            if event_date == today:
                impact = event['impact'].upper()
                if impact == "HIGH": icon = "🔴"
                elif impact == "MEDIUM": icon = "🟡"
                else: icon = "⚪"
                
                # Tenta capturar o Actual com fallback para outros nomes de campos se houver
                actual = event.get('actual', '')
                forecast = event.get('forecast', '')
                previous = event.get('previous', '')
                
                today_events.append({
                    "time": event['date'].split('T')[1][:5],
                    "currency": event['country'],
                    "event": event['title'],
                    "impact": impact,
                    "icon": icon,
                    "previous": previous,
                    "forecast": forecast,
                    "actual": actual
                })
        
        today_events = sorted(today_events, key=lambda x: x['time'])
        
        with open("calendario_economico.json", "w", encoding="utf-8") as f:
            json.dump(today_events, f, ensure_ascii=False)
            
        return today_events
        
    except Exception as e:
        print(f"Erro ao buscar calendário: {e}")
        return []

if __name__ == "__main__":
    fetch_economic_calendar()
