"""Dados diários oficiais de preços e taxas dos títulos do Tesouro Direto."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests


TESOURO_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)
CACHE_PATH = Path(__file__).resolve().parents[1] / ".tmp" / "renda_fixa_br.json"


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
