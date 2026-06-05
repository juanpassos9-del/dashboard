import json
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market_report import generate_market_report

load_dotenv()


def sync_to_supabase(key, value):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY ausentes.")

    supabase = create_client(supabase_url, supabase_key)
    supabase.table("app_state").upsert({
        "key": key,
        "value": value,
        "updated_at": "now()",
    }).execute()
    print(f"[*] Sincronizado: {key}")


def sync_json_file(key, paths):
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                sync_to_supabase(key, json.load(f))
            return True
    print(f"[!] Arquivo nao encontrado para {key}: {paths}")
    return False


def main():
    force = os.getenv("MARKET_REPORT_FORCE", "").lower() in {"1", "true", "yes", "sim"}
    report = generate_market_report(force=force)
    if not report:
        print("[*] Nenhum Market Report novo nesta janela.")
        return

    sync_json_file("market_report", ["market_report.json", "execution/market_report.json"])
    sync_json_file("market_report_daily", ["market_report_daily.json", "execution/market_report_daily.json"])
    sync_json_file("calendario_economico", ["calendario_economico.json", "execution/calendario_economico.json"])


if __name__ == "__main__":
    main()
