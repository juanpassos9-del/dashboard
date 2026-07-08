"""Safe app_state synchronization helpers for server-side jobs."""

from __future__ import annotations

import os
from datetime import datetime, timezone
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
    "risk_manual_trades",
}


def get_service_client():
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE")
    if not url or not service_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_SERVICE_ROLE ausentes para escrita segura em app_state.")
    return create_client(url, service_key)


def sync_app_state_value(key: str, value: Any, client=None) -> None:
    if key not in APP_STATE_ALLOWED_KEYS:
        raise ValueError(f"Chave app_state nao permitida: {key}")
    client = client or get_service_client()
    client.table("app_state").upsert({
        "key": key,
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
