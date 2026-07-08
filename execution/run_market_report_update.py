import json
import os
import sys

from dotenv import load_dotenv
from app_state_sync import get_service_client, sync_app_state_value

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market_report import generate_market_report

load_dotenv()


def sync_to_supabase(key, value):
    supabase = get_service_client()
    sync_app_state_value(key, value, supabase)
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
