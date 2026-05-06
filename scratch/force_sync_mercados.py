import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def force_sync():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE")
    supabase = create_client(url, key)
    
    if os.path.exists("mercados_globais.json"):
        with open("mercados_globais.json", "r") as f:
            data = json.load(f)
            supabase.table("app_state").upsert({
                "key": "mercados_globais",
                "value": data,
                "updated_at": "now()"
            }).execute()
            print("[+] Sincronização forçada com sucesso!")

if __name__ == "__main__":
    force_sync()
