import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from supabase import create_client


DEFAULT_EXCEL_PATH = r"C:\Users\Mini PC\Documents\ANALISE JUROS\Curva_DI_RTD_Monitor_PrecoTempo.xlsx"
APP_STATE_KEY = "regime_juros"


def read_regime_juros_excel(path: str = DEFAULT_EXCEL_PATH) -> dict:
    excel_path = Path(path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel nao encontrado: {excel_path}")

    wb = load_workbook(excel_path, data_only=True, read_only=True)
    ws = wb["Indice Atual"]
    return {
        "taxa_sintetica": ws["E2"].value,
        "variacao_bps": ws["H2"].value,
        "regime_estrutural": ws["K2"].value,
        "updated_at": datetime.fromtimestamp(
            excel_path.stat().st_mtime,
            ZoneInfo("America/Sao_Paulo"),
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "source": "supabase",
    }


def sync_to_supabase(payload: dict) -> None:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE", "") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY no ambiente.")

    client = create_client(url, key)
    client.table("app_state").upsert(
        {
            "key": APP_STATE_KEY,
            "value": payload,
            "updated_at": datetime.utcnow().isoformat(),
        },
        on_conflict="key",
    ).execute()


def main() -> None:
    excel_path = os.environ.get("REGIME_JUROS_EXCEL_PATH", DEFAULT_EXCEL_PATH)
    payload = read_regime_juros_excel(excel_path)
    sync_to_supabase(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
