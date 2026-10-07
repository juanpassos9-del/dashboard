"""Official historical macro series for the Brazilian monitor."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import time

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

IPCA_GROUPS = (
    ("7170", "Alimentação e bebidas"),
    ("7445", "Habitação"),
    ("7486", "Artigos de residência"),
    ("7558", "Vestuário"),
    ("7625", "Transportes"),
    ("7660", "Saúde e cuidados pessoais"),
    ("7712", "Despesas pessoais"),
    ("7766", "Educação"),
    ("7786", "Comunicação"),
)
BCB_CREDIT_SERIES = (
    {"key": "credit_balance", "name": "Saldo da carteira de crédito", "topic": "Crédito", "unit": "R$ mi", "source": "Banco Central · SGS 20539", "id": 20539},
    {"key": "credit_concessions", "name": "Concessões de crédito", "topic": "Crédito", "unit": "R$ mi", "source": "Banco Central · SGS 20631", "id": 20631},
    {"key": "credit_interest", "name": "Taxa média de juros do crédito", "topic": "Crédito", "unit": "% a.a.", "source": "Banco Central · SGS 20714", "id": 20714},
    {"key": "credit_delinquency", "name": "Inadimplência do crédito (90+ dias)", "topic": "Crédito", "unit": "%", "source": "Banco Central · SGS 21082", "id": 21082},
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
    return _fetch_bcb_sgs_range(24363, periods, timeout)


def _fetch_bcb_sgs_range(series_id: int, periods: int, timeout: int) -> list[dict[str, Any]]:
    today = date.today()
    start = today - timedelta(days=periods * 32)
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
    response = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                params={"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"), "dataFinal": today.strftime("%d/%m/%Y")},
                timeout=timeout,
                headers={"User-Agent": "TradingStrategyDashboard/1.0"},
            )
            if response.status_code < 500 or attempt == 2:
                response.raise_for_status()
                break
        except requests.RequestException:
            if attempt == 2:
                raise
        time.sleep(0.4 * (attempt + 1))
    if response is None:
        raise RuntimeError("BCB SGS não retornou resposta")
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


def _fetch_ipca_group(group_id: str, group_name: str, periods: int, timeout: int) -> dict[str, Any]:
    url = f"{SIDRA_BASE}/7060/periodos/-{periods}/variaveis/63|66"
    response = requests.get(
        url,
        params={"localidades": "N1[all]", "classificacao": f"315[{group_id}]"},
        timeout=timeout,
        headers={"User-Agent": "TradingStrategyDashboard/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    observations: dict[str, dict[str, float]] = {}
    for variable in payload if isinstance(payload, list) else []:
        variable_id = str(variable.get("id"))
        try:
            values = variable["resultados"][0]["series"][0]["serie"]
        except (IndexError, KeyError, TypeError):
            continue
        for period, raw_value in values.items():
            value = _to_float(raw_value)
            if value is not None:
                observations.setdefault(period, {})[variable_id] = value
    rows = []
    for period, values in sorted(observations.items()):
        if "63" in values:
            row = {"period": period, "date": _period_label(period), "value": values["63"]}
            if "66" in values:
                row["weight"] = values["66"]
                row["contribution_pp_approx"] = round(values["63"] * values["66"] / 100, 5)
            rows.append(row)
    return {
        "key": f"ipca_group_{group_id}",
        "name": group_name,
        "topic": "Inflação",
        "unit": "% m/m",
        "source": f"IBGE SIDRA · tabela 7060, variáveis 63 e 66, grupo {group_id}",
        "observations": rows,
    }


def _fetch_bcb_credit_series(spec: dict[str, Any], periods: int, timeout: int) -> dict[str, Any]:
    rows = _fetch_bcb_sgs_range(int(spec["id"]), periods, timeout)
    if not rows:
        raise ValueError("nenhuma observação disponível")
    return {key: value for key, value in spec.items() if key != "id"} | {"observations": rows}


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
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fetch_ipca_group, group_id, group_name, period_count, timeout): group_name
            for group_id, group_name in IPCA_GROUPS
        }
        futures.update({
            pool.submit(_fetch_bcb_credit_series, spec, period_count, timeout): spec["name"]
            for spec in BCB_CREDIT_SERIES
        })
        for future in as_completed(futures):
            try:
                result = future.result()
                if result.get("observations"):
                    series.append(result)
                else:
                    errors.append(f"{futures[future]}: nenhuma observação disponível")
            except Exception as exc:
                errors.append(f"{futures[future]}: {type(exc).__name__}: {exc}")
    ordered_keys = [
        *(spec["key"] for spec in SIDRA_SERIES),
        "ibc_br",
        *(f"ipca_group_{group_id}" for group_id, _ in IPCA_GROUPS),
        *(spec["key"] for spec in BCB_CREDIT_SERIES),
    ]
    sort_order = {key: index for index, key in enumerate(ordered_keys)}
    series.sort(key=lambda item: sort_order.get(item.get("key"), len(sort_order)))
    return {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested_periods": period_count,
        "series": series,
        "errors": errors,
    }
