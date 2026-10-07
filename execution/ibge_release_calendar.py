"""Official IBGE release dates for major Brazilian macro indicators."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import requests


API_URL = "https://servicodados.ibge.gov.br/api/v3/calendario/{research_id}"
IBGE_RESEARCHES = {
    9256: "Índice Nacional de Preços ao Consumidor Amplo (IPCA)",
    9260: "Índice Nacional de Preços ao Consumidor Amplo 15 (IPCA-15)",
    9258: "Índice Nacional de Preços ao Consumidor (INPC)",
    9227: "Pesquisa Mensal de Comércio (PMC)",
    9229: "Pesquisa Mensal de Serviços (PMS)",
    9294: "Pesquisa Industrial Mensal - Produção Física (PIM-PF Brasil)",
    9171: "PNAD Contínua - divulgação mensal",
    9173: "PNAD Contínua - divulgação trimestral",
    9300: "Sistema de Contas Nacionais Trimestrais (PIB)",
}


def fetch_ibge_release_calendar(
    today: date | None = None,
    retention_days: int = 365 * 3,
    future_days: int = 365,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetches official past and future release dates for selected IBGE surveys."""
    today = today or date.today()
    start = today - timedelta(days=retention_days)
    end = today + timedelta(days=future_days)
    releases: dict[int, dict[str, Any]] = {}
    for research_id, label in IBGE_RESEARCHES.items():
        response = requests.get(
            API_URL.format(research_id=research_id),
            params={"qtd": 500},
            timeout=timeout,
            headers={"User-Agent": "TradingStrategyDashboard/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            try:
                release_dt = datetime.strptime(item["data_divulgacao"], "%d/%m/%Y %H:%M:%S")
            except (KeyError, TypeError, ValueError):
                continue
            if not start <= release_dt.date() <= end:
                continue
            ref_year = item.get("ano_referencia_inicio")
            ref_month = item.get("mes_referencia_inicio")
            reference = f"{int(ref_year):04d}-{int(ref_month):02d}" if ref_year and ref_month else str(ref_year or "")
            product = str(item.get("nome_produto") or label).strip()
            title = str(item.get("titulo") or product).strip()
            releases[int(item.get("id") or 0)] = {
                "date": release_dt.strftime("%Y-%m-%d"),
                "time": release_dt.strftime("%H:%M"),
                "currency": "BRL",
                "event": title,
                "impact": "HIGH",
                "actual": "---",
                "forecast": "---",
                "previous": "---",
                "reference_period": reference,
                "official_release": True,
                "source": "IBGE · API oficial de Calendário de Divulgações",
                "source_url": f"https://servicodados.ibge.gov.br/api/v3/calendario/{research_id}",
                "release_id": item.get("id"),
                "research_id": research_id,
                "research": label,
            }
    return sorted(releases.values(), key=lambda item: (item["date"], item["time"]))
