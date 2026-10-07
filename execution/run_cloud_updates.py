import os
import sys
import time
import json
from dotenv import load_dotenv

# Adiciona o diretório deste script ao path para importação limpa
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app_state_sync import get_service_client, sync_app_state_value

# Carrega chaves
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL") or os.getenv("SUPABASE")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE")

if not supabase_url or not supabase_key:
    print("[!] Chaves do Supabase não encontradas no ambiente.")
    exit(1)

supabase = get_service_client()

def sync_to_supabase(key, value):
    try:
        sync_app_state_value(key, value, supabase)
        print(f"[*] Sincronizado com sucesso: {key}")
    except Exception as e:
        print(f"[!] Erro ao sincronizar {key}: {e}")

print("=== INICIANDO ATUALIZAÇÕES EM NUVEM ===")

# 1. IA Analista
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
                        "insight": new_insight.get("insight", ""),
                        "macro_regime": new_insight.get("macro_regime", ""),
                        "confidence": new_insight.get("confidence", ""),
                        "macro_score": new_insight.get("macro_score", 0),
                        "curve_regime": new_insight.get("curve_regime", ""),
                        "curve_bias": new_insight.get("curve_bias", ""),
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
    from economic_calendar_history import merge_calendar_history
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now_br = datetime.now(ZoneInfo("America/Sao_Paulo"))
    fetch_economic_calendar()
    paths = ["calendario_economico.json", "execution/calendario_economico.json"]
    current_events = []
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                current_events = json.load(f)
                sync_to_supabase("calendario_economico", current_events)
            break

    history_row = supabase.table("app_state").select("value").eq("key", "calendario_economico_historico").execute()
    history = history_row.data[0]["value"] if history_row.data else None
    incoming_batches = [current_events] if isinstance(current_events, list) else []
    ibge_calendar_status = history.get("ibge_calendar_status", "not_attempted") if isinstance(history, dict) else "not_attempted"
    ibge_calendar_updated_at = history.get("ibge_calendar_updated_at") if isinstance(history, dict) else None
    refresh_ibge_calendar = not ibge_calendar_updated_at
    if ibge_calendar_updated_at:
        try:
            last_ibge_refresh = datetime.fromisoformat(str(ibge_calendar_updated_at))
            if last_ibge_refresh.tzinfo is None:
                last_ibge_refresh = last_ibge_refresh.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
            refresh_ibge_calendar = now_br - last_ibge_refresh >= timedelta(hours=24)
        except ValueError:
            refresh_ibge_calendar = True
    if refresh_ibge_calendar:
        try:
            from ibge_release_calendar import fetch_ibge_release_calendar
            ibge_releases = fetch_ibge_release_calendar(today=now_br.date())
            incoming_batches.append(ibge_releases)
            ibge_calendar_status = f"ok:{len(ibge_releases)}"
            ibge_calendar_updated_at = now_br.isoformat(timespec="seconds")
        except Exception as ibge_error:
            ibge_calendar_status = f"unavailable:{type(ibge_error).__name__}"
            ibge_calendar_updated_at = now_br.isoformat(timespec="seconds")
            print(f"[!] Calendário oficial IBGE indisponível: {ibge_error}")
    backfill_status = None
    retry_after = None
    try:
        retry_after = datetime.fromisoformat(str(history.get("backfill_retry_after"))) if isinstance(history, dict) else None
        if retry_after and retry_after.tzinfo is None:
            retry_after = retry_after.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    except ValueError:
        retry_after = None
    prior_status = str(history.get("backfill_status", "")) if isinstance(history, dict) else ""
    should_backfill = not isinstance(history, dict) or prior_status in {"", "not_attempted"} or (
        prior_status.startswith(("unavailable", "empty_response")) and (retry_after is None or retry_after <= now_br)
    )
    if should_backfill:
        try:
            from fetch_calendar import fetch_investing_calendar_range
            today = now_br.date()
            start = today - timedelta(days=90)
            backfill_rows = fetch_investing_calendar_range(start.isoformat(), today.isoformat())
            if backfill_rows:
                incoming_batches.append(backfill_rows)
                backfill_status = f"completed:{start.isoformat()}:{today.isoformat()}"
            else:
                backfill_status = "empty_response"
        except Exception as backfill_error:
            backfill_status = f"unavailable:{type(backfill_error).__name__}"
            print(f"[!] Backfill histórico do calendário indisponível: {backfill_error}")

    history_payload = merge_calendar_history(history, incoming_batches, backfill_status=backfill_status)
    history_payload["ibge_calendar_status"] = ibge_calendar_status
    if ibge_calendar_updated_at:
        history_payload["ibge_calendar_updated_at"] = ibge_calendar_updated_at
    if backfill_status and backfill_status.startswith(("unavailable", "empty_response")):
        history_payload["backfill_retry_after"] = (now_br + timedelta(days=1)).isoformat(timespec="seconds")
    elif backfill_status and backfill_status.startswith("completed"):
        history_payload["backfill_retry_after"] = None
    sync_to_supabase("calendario_economico_historico", history_payload)
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
