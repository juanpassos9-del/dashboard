import json
import os
import sys
import time

from dotenv import load_dotenv
from supabase import create_client

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_analyst import generate_macro_insight

load_dotenv()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY ausentes.")
    return create_client(supabase_url, supabase_key)


def sync_to_supabase(client, key, value):
    client.table("app_state").upsert({
        "key": key,
        "value": value,
        "updated_at": "now()",
    }).execute()
    print(f"[*] Sincronizado: {key}")


def fetch_app_state(client, key, default=None):
    try:
        response = client.table("app_state").select("value").eq("key", key).execute()
        if response.data:
            return response.data[0].get("value", default)
    except Exception as exc:
        print(f"[WARN] Falha ao buscar {key}: {exc}")
    return default


def prime_local_context(client):
    """Prepara os arquivos que o motor da IA le sem disparar coletas pesadas."""
    key_to_path = {
        "mercados_globais": "mercados_globais.json",
        "dados_mercado": "dados_mercado.json",
        "calendario_economico": "calendario_economico.json",
    }
    for key, path in key_to_path.items():
        value = fetch_app_state(client, key)
        if value:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
            print(f"[*] Contexto local preparado: {path}")


def sync_ai_history(client, new_insight):
    history = fetch_app_state(client, "ai_insight_history", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "sentiment": new_insight.get("sentiment", "NEUTRO"),
        "updated_at": new_insight.get("updated_at", ""),
        "insight": new_insight.get("insight", ""),
        "macro_regime": new_insight.get("macro_regime", ""),
        "confidence": new_insight.get("confidence", ""),
        "macro_score": new_insight.get("macro_score", 0),
        "curve_regime": new_insight.get("curve_regime", ""),
        "curve_bias": new_insight.get("curve_bias", ""),
        "id": int(time.time()),
    })
    sync_to_supabase(client, "ai_insight_history", history[-5:])


def main():
    client = get_supabase_client()
    prime_local_context(client)
    generate_macro_insight()

    for path in ["ai_insight.json", "execution/ai_insight.json"]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                new_insight = json.load(f)
            sync_to_supabase(client, "ai_insight", new_insight)
            sync_ai_history(client, new_insight)
            return
    raise RuntimeError("ai_insight.json nao foi gerado.")


if __name__ == "__main__":
    main()
