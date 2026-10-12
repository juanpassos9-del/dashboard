"""Dados diários oficiais de preços e taxas dos títulos do Tesouro Direto."""

from __future__ import annotations

import csv
import io
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


TESOURO_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)
CACHE_PATH = Path(__file__).resolve().parents[1] / ".tmp" / "renda_fixa_br.json"
DI_CONTRACT_RE = re.compile(r"^DI1[A-Z]\d{2}$")
MONTH_LABELS_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_tesouro_csv(content: bytes | str) -> dict[str, Any]:
    """Normalize the official semicolon-separated CSV into daily records."""
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
    else:
        text = content.lstrip("\ufeff")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = []
    for raw in reader:
        try:
            base_date = datetime.strptime(raw["Data Base"].strip(), "%d/%m/%Y").date()
            maturity = datetime.strptime(raw["Data Vencimento"].strip(), "%d/%m/%Y").date()
        except (KeyError, TypeError, ValueError):
            continue
        title = str(raw.get("Tipo Titulo") or "").strip()
        if not title:
            continue
        rows.append({
            "title": title,
            "maturity": maturity.isoformat(),
            "date": base_date.isoformat(),
            "buy_rate": _number(raw.get("Taxa Compra Manha")),
            "sell_rate": _number(raw.get("Taxa Venda Manha")),
            "buy_price": _number(raw.get("PU Compra Manha")),
            "sell_price": _number(raw.get("PU Venda Manha")),
            "base_price": _number(raw.get("PU Base Manha")),
        })
    if not rows:
        raise ValueError("O CSV oficial não contém linhas válidas de preços e taxas.")
    rows.sort(key=lambda row: (row["date"], row["title"], row["maturity"]))
    return {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "Tesouro Transparente · Taxas dos Títulos Ofertados pelo Tesouro Direto",
        "license": "ODbL",
        "latest_date": max(row["date"] for row in rows),
        "rows": rows,
    }


def fetch_tesouro_data(timeout: int = 45) -> dict[str, Any]:
    response = requests.get(
        TESOURO_CSV_URL,
        timeout=timeout,
        headers={"User-Agent": "TradingStrategyDashboard/1.0", "Accept": "text/csv,*/*"},
    )
    response.raise_for_status()
    return parse_tesouro_csv(response.content)


def save_tesouro_cache(payload: dict[str, Any], path: Path = CACHE_PATH) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_tesouro_cache(path: Path = CACHE_PATH) -> dict[str, Any] | None:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and isinstance(payload.get("rows"), list) else None


def latest_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows") or []
    latest_date = payload.get("latest_date") or max((row.get("date", "") for row in rows), default="")
    return [row for row in rows if row.get("date") == latest_date]


def pu_history_coverage(payload: dict[str, Any], minimum_observations: int = 31) -> dict[str, int]:
    """Summarize usable history for securities currently quoted by the source."""
    latest = latest_rows(payload)
    current_keys = {
        (str(row.get("title") or ""), str(row.get("maturity") or ""))
        for row in latest
    }
    counts: dict[tuple[str, str], int] = {}
    for row in payload.get("rows", []):
        key = (str(row.get("title") or ""), str(row.get("maturity") or ""))
        price = row.get("base_price") if row.get("base_price") is not None else row.get("buy_price")
        try:
            valid_price = float(price) > 0
        except (TypeError, ValueError):
            valid_price = False
        if key in current_keys and valid_price:
            counts[key] = counts.get(key, 0) + 1
    return {
        "current_securities": len(current_keys),
        "covered_securities": sum(counts.get(key, 0) >= minimum_observations for key in current_keys),
        "minimum_observations": minimum_observations,
    }


def title_history(payload: dict[str, Any], title: str, maturity: str) -> list[dict[str, Any]]:
    return [
        row for row in payload.get("rows", [])
        if row.get("title") == title and row.get("maturity") == maturity
    ]


def historical_delta(
    history: list[dict[str, Any]],
    current: dict[str, Any],
    field: str,
    *,
    days: int = 1,
    tolerance_days: int = 5,
    relative: bool = False,
) -> tuple[float | None, str | None]:
    """Compare with the closest available observation near a past reference date."""
    try:
        current_date = datetime.strptime(str(current["date"]), "%Y-%m-%d").date()
        current_value = current.get(field)
        if current_value is None:
            return None, None
        target_date = current_date - timedelta(days=days)
        candidates = []
        for row in history:
            value = row.get(field)
            try:
                row_date = datetime.strptime(str(row["date"]), "%Y-%m-%d").date()
                numeric = float(value)
            except (KeyError, TypeError, ValueError):
                continue
            distance = (target_date - row_date).days
            if 0 <= distance <= tolerance_days and row_date < current_date:
                candidates.append((distance, row_date, numeric))
        if not candidates:
            return None, None
        _, reference_date, reference_value = min(candidates, key=lambda item: item[0])
        if relative:
            if reference_value == 0:
                return None, None
            delta = (float(current_value) / reference_value - 1) * 100
        else:
            delta = float(current_value) - reference_value
        return delta, reference_date.isoformat()
    except (KeyError, TypeError, ValueError):
        return None, None


def _title_family(title: str) -> str:
    normalized = title.upper()
    if "SELIC" in normalized:
        return "Tesouro Selic"
    if "IPCA" in normalized and "JUROS SEMESTRAIS" in normalized:
        return "IPCA+ com juros semestrais"
    if "PREFIXADO" in normalized and "JUROS SEMESTRAIS" in normalized:
        return "Prefixado com juros semestrais"
    if "IPCA" in normalized:
        return "Tesouro IPCA+"
    if "PREFIXADO" in normalized:
        return "Tesouro Prefixado"
    if "EDUCA" in normalized:
        return "Tesouro Educa+"
    if "RENDA+" in normalized or "RENDA +" in normalized:
        return "Tesouro RendA+"
    return "Outros títulos"


def _session_change(
    history: list[dict[str, Any]],
    current: dict[str, Any],
    field: str,
    sessions: int,
    *,
    relative: bool = False,
) -> float | None:
    valid = []
    for row in sorted(history, key=lambda item: str(item.get("date") or "")):
        try:
            value = float(row.get(field))
            row_date = str(row.get("date") or "")
        except (TypeError, ValueError):
            continue
        if value > 0 and row_date <= str(current.get("date") or ""):
            valid.append((row_date, value))
    if len(valid) <= sessions:
        return None
    current_date, current_value = valid[-1]
    if current_date != str(current.get("date") or ""):
        return None
    reference_value = valid[-1 - sessions][1]
    if relative:
        return (current_value / reference_value - 1) * 100 if reference_value else None
    return current_value - reference_value


def build_fixed_income_intelligence(
    payload: dict[str, Any],
    di_contracts: list[dict[str, Any]] | None = None,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Create a deterministic market read from Treasury history and the DI curve."""
    current = latest_rows(payload)
    latest_date = str(payload.get("latest_date") or "")
    histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in payload.get("rows", []):
        key = (str(row.get("title") or ""), str(row.get("maturity") or ""))
        histories.setdefault(key, []).append(row)

    grouped: dict[str, dict[str, list[float]]] = {}
    all_pu_changes: list[float] = []
    all_rate_changes: list[float] = []
    for row in current:
        key = (str(row.get("title") or ""), str(row.get("maturity") or ""))
        history = histories.get(key, [])
        family = _title_family(key[0])
        bucket = grouped.setdefault(family, {"pu": [], "rate": []})
        price_field = "base_price" if row.get("base_price") is not None else "buy_price"
        pu_change = _session_change(history, row, price_field, 5, relative=True)
        rate_change = _session_change(history, row, "buy_rate", 5)
        if pu_change is not None:
            bucket["pu"].append(pu_change)
            all_pu_changes.append(pu_change)
        if rate_change is not None:
            bucket["rate"].append(rate_change)
            all_rate_changes.append(rate_change)

    family_rows = []
    for family, values in grouped.items():
        family_rows.append({
            "family": family,
            "securities": len({(row.get("title"), row.get("maturity")) for row in current if _title_family(str(row.get("title") or "")) == family}),
            "pu_change_5d": statistics.median(values["pu"]) if values["pu"] else None,
            "rate_change_5d": statistics.median(values["rate"]) if values["rate"] else None,
            "observations": min(len(values["pu"]), len(values["rate"])) if values["pu"] and values["rate"] else max(len(values["pu"]), len(values["rate"])),
        })
    family_rows.sort(key=lambda item: item["family"])

    median_pu = statistics.median(all_pu_changes) if all_pu_changes else None
    median_rate = statistics.median(all_rate_changes) if all_rate_changes else None
    if median_pu is not None and median_rate is not None and median_pu >= 0.15 and median_rate <= -0.05:
        summary = "Os preços dos títulos avançaram enquanto as taxas recuaram em cinco pregões: movimento compatível com valorização por marcação a mercado."
    elif median_pu is not None and median_rate is not None and median_pu <= -0.15 and median_rate >= 0.05:
        summary = "Os preços recuaram enquanto as taxas subiram em cinco pregões: movimento compatível com pressão de marcação a mercado sobre os títulos."
    elif median_pu is not None and median_rate is not None:
        summary = "Os movimentos agregados de preços e taxas estão mistos ou modestos; a leitura exige atenção às diferenças entre vencimentos e tipos de título."
    else:
        summary = "Histórico insuficiente para uma leitura comparável de cinco pregões; atualize os dados diários do Tesouro."

    nominal = [row for row in current if "PREFIXADO" in str(row.get("title", "")).upper() and "JUROS SEMESTRAIS" not in str(row.get("title", "")).upper() and row.get("buy_rate") is not None]
    real = [row for row in current if "IPCA" in str(row.get("title", "")).upper() and "JUROS SEMESTRAIS" not in str(row.get("title", "")).upper() and row.get("buy_rate") is not None]
    breakevens = []
    for ipca_row in real:
        try:
            ipca_maturity = date.fromisoformat(str(ipca_row["maturity"]))
            real_rate = float(ipca_row["buy_rate"])
        except (KeyError, TypeError, ValueError):
            continue
        matches = []
        for nominal_row in nominal:
            try:
                nominal_maturity = date.fromisoformat(str(nominal_row["maturity"]))
                nominal_rate = float(nominal_row["buy_rate"])
            except (KeyError, TypeError, ValueError):
                continue
            distance = abs((nominal_maturity - ipca_maturity).days)
            if distance <= 366 and real_rate > -100:
                matches.append((distance, nominal_rate, real_rate))
        if matches:
            _, nominal_rate, real_rate = min(matches, key=lambda item: item[0])
            breakevens.append(((1 + nominal_rate / 100) / (1 + real_rate / 100) - 1) * 100)
    implied_inflation = statistics.median(breakevens) if breakevens else None

    curve = build_di_curve_rows(di_contracts or [], as_of=as_of or date.today())
    curve_slope = curve[-1]["rate"] - curve[0]["rate"] if len(curve) >= 2 else None
    if curve_slope is None:
        curve_read = "indisponível"
    elif curve_slope > 0.15:
        curve_read = "ascendente"
    elif curve_slope < -0.15:
        curve_read = "invertida"
    else:
        curve_read = "quase plana"

    return {
        "as_of": latest_date,
        "summary": summary,
        "median_pu_change_5d": median_pu,
        "median_rate_change_5d": median_rate,
        "pu_observations": len(all_pu_changes),
        "rate_observations": len(all_rate_changes),
        "families": family_rows,
        "implied_inflation": implied_inflation,
        "inflation_pairs": len(breakevens),
        "di_slope": curve_slope,
        "di_curve_read": curve_read,
        "di_contracts": len(curve),
    }


def build_di_curve_rows(contracts: list[dict[str, Any]], as_of: date | None = None) -> list[dict[str, Any]]:
    """Prepare valid, unexpired DI contracts in maturity order for plotting."""
    as_of = as_of or datetime.now(timezone.utc).date()
    by_symbol: dict[str, dict[str, Any]] = {}
    for item in contracts:
        symbol = str(item.get("symbol") or "").upper()
        if not DI_CONTRACT_RE.fullmatch(symbol):
            continue
        try:
            rate = float(item.get("rate", item.get("price")))
            maturity_ts = item.get("maturity_timestamp")
            if maturity_ts:
                maturity = datetime.fromtimestamp(float(maturity_ts), timezone.utc).date()
            else:
                maturity = datetime.strptime(str(item["maturity"]), "%d/%m/%Y").date()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if maturity < as_of:
            continue
        previous = by_symbol.get(symbol)
        if previous and str(previous.get("source_timestamp") or "") >= str(item.get("source_timestamp") or ""):
            continue
        by_symbol[symbol] = {
            "symbol": symbol,
            "maturity": maturity.isoformat(),
            "label": f"{MONTH_LABELS_PT[maturity.month - 1]}/{maturity.strftime('%y')}",
            "rate": rate,
            "last_trade": str(item.get("last_trade") or item.get("source_timestamp") or "—"),
            "source": str(item.get("source") or "DI Futuro"),
        }
    return sorted(by_symbol.values(), key=lambda item: (item["maturity"], item["symbol"]))


def detect_pu_spikes(
    payload: dict[str, Any],
    *,
    horizons: tuple[int, ...] = (1, 5, 20),
    minimum_observations: int = 31,
) -> list[dict[str, Any]]:
    """Find unusual positive PU moves against each bond's own historical volatility."""
    floors = {1: 0.5, 5: 1.5, 20: 3.0}
    latest_date_in_payload = str(payload.get("latest_date") or max((str(row.get("date") or "") for row in payload.get("rows", [])), default=""))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in payload.get("rows", []):
        grouped.setdefault((str(row.get("title") or ""), str(row.get("maturity") or "")), []).append(row)

    alerts = []
    for (title, maturity), history in grouped.items():
        history.sort(key=lambda row: str(row.get("date") or ""))
        if not history or str(history[-1].get("date") or "") != latest_date_in_payload:
            continue
        if len(history) < minimum_observations:
            continue
        price_field = "base_price" if any(row.get("base_price") is not None for row in history) else "buy_price"
        valid = []
        for row in history:
            try:
                value = float(row.get(price_field))
                row_date = datetime.strptime(str(row.get("date")), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
            if value > 0:
                valid.append((row_date, value))
        if len(valid) < minimum_observations:
            continue

        latest_date, latest_price = valid[-1]
        for horizon in horizons:
            if horizon not in floors or len(valid) < max(minimum_observations, horizon + 11):
                continue
            baseline_returns = []
            for end in range(horizon, len(valid) - 1):
                start_value = valid[end - horizon][1]
                end_value = valid[end][1]
                if start_value > 0:
                    baseline_returns.append(abs((end_value / start_value - 1) * 100))
            if len(baseline_returns) < 10:
                continue
            center = statistics.median(baseline_returns)
            mad = statistics.median(abs(value - center) for value in baseline_returns)
            threshold = max(floors[horizon], center + 3 * 1.4826 * mad)

            reference_date, reference_price = valid[-1 - horizon]
            change = (latest_price / reference_price - 1) * 100
            if change < threshold:
                continue
            alerts.append({
                "title": title,
                "maturity": maturity,
                "date": latest_date.isoformat(),
                "reference_date": reference_date.isoformat(),
                "horizon_sessions": horizon,
                "horizon_label": "1 pregão" if horizon == 1 else f"{horizon} pregões",
                "price_field": price_field,
                "current_price": latest_price,
                "reference_price": reference_price,
                "change_percent": change,
                "threshold_percent": threshold,
                "multiple": change / threshold if threshold else None,
            })
    return sorted(alerts, key=lambda item: (item["multiple"] or 0, item["change_percent"]), reverse=True)
