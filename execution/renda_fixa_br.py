"""Dados diários oficiais de preços e taxas dos títulos do Tesouro Direto."""

from __future__ import annotations

import csv
import io
import re
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
