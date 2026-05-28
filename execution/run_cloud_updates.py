import os
import sys
import time
import json
from dotenv import load_dotenv

# Adiciona o diretório deste script ao path para importação limpa
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client

# Carrega chaves
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("[!] Chaves do Supabase não encontradas no ambiente.")
    exit(1)

supabase = create_client(supabase_url, supabase_key)

def sync_to_supabase(key, value):
    try:
        data = {
            "key": key,
            "value": value,
            "updated_at": "now()"
        }
        supabase.table("app_state").upsert(data).execute()
        print(f"[*] Sincronizado com sucesso: {key}")
    except Exception as e:
        print(f"[!] Erro ao sincronizar {key}: {e}")

print("=== INICIANDO ATUALIZAÇÕES EM NUVEM ===")

# 1. Mercados Globais
try:
    print("\n[1/4] Atualizando Mercados Globais...")
    from fetch_global_markets import fetch_global_data
    fetch_global_data()
    # Tenta achar o arquivo na raiz ou na pasta de execução
    paths = ["mercados_globais.json", "execution/mercados_globais.json"]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r") as f:
                sync_to_supabase("mercados_globais", json.load(f))
            break
except Exception as e:
    print(f"[!] Erro em Mercados Globais: {e}")

# 2. IA Analista
try:
    print("\n[2/4] Atualizando IA Analista...")
    from ai_analyst import generate_macro_insight
    generate_macro_insight()
    paths = ["ai_insight.json", "execution/ai_insight.json"]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                new_insight = json.load(f)
                sync_to_supabase("ai_insight", new_insight)
                
                # Atualiza Histórico
                try:
                    res = supabase.table("app_state").select("value").eq("key", "ai_insight_history").execute()
                    history = res.data[0]["value"] if res.data else []
                    if not isinstance(history, list): history = []
                    
                    history.append({
                        "sentiment": new_insight.get("sentiment", "NEUTRO"),
                        "updated_at": new_insight.get("updated_at", ""),
                        "id": int(time.time())
                    })
                    history = history[-5:]
                    sync_to_supabase("ai_insight_history", history)
                except Exception as he:
                    print(f"[!] Erro ao atualizar histórico da IA: {he}")
            break
except Exception as e:
    print(f"[!] Erro em IA Analista: {e}")

# 3. Market Report
try:
    print("\n[3/4] Atualizando Market Report...")
    from market_report import generate_market_report
    generate_market_report()
    paths = ["market_report.json", "execution/market_report.json"]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                sync_to_supabase("market_report", json.load(f))
            break
    daily_paths = ["market_report_daily.json", "execution/market_report_daily.json"]
    for p in daily_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                sync_to_supabase("market_report_daily", json.load(f))
            break
except Exception as e:
    print(f"[!] Erro em Market Report: {e}")

# 4. Calendário Econômico
try:
    print("\n[4/5] Atualizando Calendário Econômico...")
    from fetch_calendar import fetch_economic_calendar
    fetch_economic_calendar()
    paths = ["calendario_economico.json", "execution/calendario_economico.json"]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                sync_to_supabase("calendario_economico", json.load(f))
            break
except Exception as e:
    print(f"[!] Erro em Calendário Econômico: {e}")

# 5. Fluxo Estrangeiro B3
try:
    print("\n[5/6] Atualizando Fluxo Estrangeiro B3...")
    from fetch_foreign_flow import fetch_foreign_flow, save_flow_data
    records = fetch_foreign_flow()
    if records:
        flow_data = save_flow_data(records)
        sync_to_supabase("fluxo_estrangeiro_b3", flow_data)
except Exception as e:
    print(f"[!] Erro em Fluxo Estrangeiro B3: {e}")

# 6. Boletim Focus
try:
    print("\n[6/6] Atualizando Boletim Focus (BCB)...")
    from fetch_focus import fetch_focus_bcb, save_focus_data
    focus_data = fetch_focus_bcb()
    if focus_data:
        data_to_save = save_focus_data(focus_data)
        sync_to_supabase("boletim_focus", data_to_save)
except Exception as e:
    print(f"[!] Erro no Boletim Focus: {e}")

print("\n=== ATUALIZAÇÕES COMPLETADAS COM SUCESSO ===")
