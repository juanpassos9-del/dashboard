"""Official historical macro series for the Brazilian monitor."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import requests


SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
SIDRA_SERIES = (
    {
        "key": "ipca",
        "name": "IPCA mensal",
        "topic": "Inflação",
        "unit": "% m/m",
        "source": "IBGE SIDRA · tabela 1737, variável 63",
        "table": 1737,
        "variable": 63,
    },
    {
        "key": "retail",
        "name": "Volume de vendas no varejo (ajustado sazonalmente)",
        "topic": "Consumo",
        "unit": "% m/m",
        "source": "IBGE SIDRA · tabela 8880, variável 11708, volume do varejo",
        "table": 8880,
        "variable": 11708,
        "classification": "11046[56734]",
    },
    {
        "key": "unemployment",
        "name": "Taxa de desocupação · trimestre móvel",
        "topic": "Mercado de trabalho",
        "unit": "% da força de trabalho",
        "source": "IBGE SIDRA · tabela 6381, variável 4099",
        "table": 6381,
        "variable": 4099,
    },
)


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", "."))
        return parsed if value not in (None, "..", "...") else None
    except (TypeError, ValueError):
        return None


def _period_label(period: str) -> str:
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}-{period[4:]}"
    return period


def _fetch_sidra_series(spec: dict[str, Any], periods: int, timeout: int) -> list[dict[str, Any]]:
    url = f"{SIDRA_BASE}/{spec['table']}/periodos/-{periods}/variaveis/{spec['variable']}"
    params = {"localidades": "N1[all]"}
    if spec.get("classification"):
        params["classificacao"] = spec["classification"]
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "TradingStrategyDashboard/1.0"})
    response.raise_for_status()
    payload = response.json()
    try:
        observations = payload[0]["resultados"][0]["series"][0]["serie"]
    except (IndexError, KeyError, TypeError):
        return []
    rows = []
    for period, raw_value in observations.items():
        value = _to_float(raw_value)
        if value is not None:
            rows.append({"period": period, "date": _period_label(period), "value": value})
    return sorted(rows, key=lambda row: row["period"])


def _fetch_bcb_ibc_br(periods: int, timeout: int) -> list[dict[str, Any]]:
    today = date.today()
    start = today - timedelta(days=periods * 32)
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.24363/dados"
    response = requests.get(
        url,
        params={"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"), "dataFinal": today.strftime("%d/%m/%Y")},
        timeout=timeout,
        headers={"User-Agent": "TradingStrategyDashboard/1.0"},
    )
    response.raise_for_status()
    rows = []
    for item in response.json():
        try:
            value = _to_float(item.get("valor"))
            observed = datetime.strptime(str(item.get("data")), "%d/%m/%Y").date()
        except (TypeError, ValueError):
            continue
        if value is not None:
            rows.append({"period": observed.isoformat(), "date": observed.strftime("%Y-%m-%d"), "value": value})
    return rows


def fetch_monitor_br_history(periods: int = 120, timeout: int = 20) -> dict[str, Any]:
    """Fetch historical realized values, keeping successful sources if one fails."""
    period_count = max(12, min(int(periods), 240))
    series: list[dict[str, Any]] = []
    errors: list[str] = []
    sources = [*SIDRA_SERIES, {
        "key": "ibc_br",
        "name": "IBC-Br dessazonalizado",
        "topic": "Atividade",
        "unit": "índice",
        "source": "Banco Central · SGS 24363",
    }]
    for spec in sources:
        try:
            observations = (
                _fetch_bcb_ibc_br(period_count, timeout)
                if spec["key"] == "ibc_br"
                else _fetch_sidra_series(spec, period_count, timeout)
            )
            if not observations:
                raise ValueError("nenhuma observação disponível")
            series.append({**{key: value for key, value in spec.items() if key not in {"table", "variable", "classification"}}, "observations": observations})
        except Exception as exc:
            errors.append(f"{spec['name']}: {type(exc).__name__}: {exc}")
    return {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested_periods": period_count,
        "series": series,
        "errors": errors,
    }
