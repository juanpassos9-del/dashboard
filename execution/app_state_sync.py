"""Safe app_state synchronization helpers for server-side jobs."""

from __future__ import annotations

import os
try:
    import tomllib
except Exception:
    tomllib = None
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import create_client

APP_STATE_ALLOWED_KEYS = {
    "ai_insight",
    "ai_insight_history",
    "boletim_focus",
    "calendario_economico",
    "dados_mercado",
    "financial_juice_news",
    "fluxo_estrangeiro_b3",
    "manual_trades",
    "market_report",
    "market_report_daily",
    "mercados_globais",
    "lse_realtime_quotes",
    "lse_diagnostics",
    "ewz_plotly_ohlcv",
    "risk_manual_trades",
}


def get_service_client():
    url = _get_config_value("SUPABASE_URL", "SUPABASE")
    service_key = _get_config_value("SUPABASE_SERVICE_ROLE", "SUPABASE_KEY", "SUPABASE_SERVICE")
    if not url or not service_key:
        raise RuntimeError("SUPABASE/SUPABASE_SERVICE ausentes para escrita segura em app_state.")
    return create_client(url, service_key)


def _get_config_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value

    secrets_path = Path(".streamlit") / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        if tomllib is not None:
            with secrets_path.open("rb") as fp:
                secrets = tomllib.load(fp)
        else:
            secrets = {}
            for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return ""

    for name in names:
        value = secrets.get(name)
        if value:
            return str(value)
    return ""


def sync_app_state_value(key: str, value: Any, client=None) -> None:
    if key not in APP_STATE_ALLOWED_KEYS:
        raise ValueError(f"Chave app_state nao permitida: {key}")
    client = client or get_service_client()
    client.table("app_state").upsert({
        "key": key,
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
