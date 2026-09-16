"""Coleta contratos de DI futuro BR com fallback local.

Fonte principal: ferramenta publica de DI Futuro do InfoMoney.
Fallback: CSV local exportado pelo usuario e ultimo cache valido.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


BR_TZ = ZoneInfo("America/Sao_Paulo")
ROOT_DIR = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT_DIR / ".tmp"
CACHE_PATH = TMP_DIR / "di_futuro_br.json"
USER_CSV_PATH = Path("C:/Users/Mini PC/Downloads/contratos_di_futuro.csv")

INFOMONEY_DI_URL = "https://www.infomoney.com.br/ferramentas/juros-futuros-di/"
INFOMONEY_AJAX_URL = "https://www.infomoney.com.br/wp-admin/admin-ajax.php"
WATCHED_DI_CONTRACTS = ("DI1F27", "DI1F28", "DI1F29", "DI1F31", "DI1F32", "DI1F40")
LONG_TENOR_FALLBACKS = {"DI1F40": "DI1F39"}


def _now_iso() -> str:
    return datetime.now(BR_TZ).isoformat()


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return num if math.isfinite(num) else None
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    text = text.replace("%", "").replace("\xa0", " ").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        num = float(text)
        return num if math.isfinite(num) else None
    except Exception:
        return None


def _mark_as_fallback_contract(quote: dict[str, Any], requested_symbol: str) -> dict[str, Any]:
    marked = dict(quote)
    marked["fallback_for"] = requested_symbol
    marked["name"] = f"{marked.get('symbol')} (DI Futuro, fallback {requested_symbol})"
    return marked


def _merge_missing_quotes(base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not extra:
        return base
    merged = list(base)
    present = {str(item.get("symbol")) for item in merged if item.get("symbol")}
    for item in extra:
        symbol = str(item.get("symbol") or "")
        if symbol and symbol not in present:
            merged.append(item)
            present.add(symbol)
    return merged


def _parse_fallback_ts_from_raw(raw_ts: Any) -> tuple[str | None, float | None]:
    try:
        if raw_ts:
            dt = datetime.fromtimestamp(float(raw_ts), BR_TZ)
            age = (datetime.now(BR_TZ) - dt).total_seconds()
            return dt.isoformat(), float(round(age, 1))
    except Exception:
        pass
    return None, None


def _parse_br_datetime(value: Any) -> tuple[str | None, float | None]:
    if isinstance(value, dict):
        display = value.get("display")
        if display:
            value = display
        else:
            return _parse_fallback_ts_from_raw(value.get("timestamp"))

    if not value:
        return None, None

    text = str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=BR_TZ)
            age = (datetime.now(BR_TZ) - dt).total_seconds()
            return dt.isoformat(), float(round(age, 1))
        except Exception:
            continue
    return None, None


def _parse_maturity(value: Any) -> tuple[str | None, int | None]:
    if isinstance(value, dict):
        display = value.get("display")
        raw_ts = value.get("timestamp")
        try:
            return display, int(float(raw_ts)) if raw_ts else None
        except Exception:
            return display, None
    return str(value).strip() if value else None, None


def _build_quote(
    code: str,
    maturity: Any,
    rate: Any,
    change: Any,
    last_trade: Any,
    volume: Any,
    source: str,
) -> dict[str, Any] | None:
    price = _finite_float(rate)
    if price is None:
        return None

    variation = _finite_float(change)
    maturity_display, maturity_ts = _parse_maturity(maturity)
    source_timestamp, age_seconds = _parse_br_datetime(last_trade)
    updated_at = _now_iso()

    return {
        "name": f"{code} (DI Futuro)",
        "symbol": code,
        "source_symbol": code,
        "source": source,
        "source_timestamp": source_timestamp or updated_at,
        "age_seconds": age_seconds,
        "price": float(round(price, 3)),
        "high": float(round(price, 3)),
        "low": float(round(price, 3)),
        "change": float(round(variation or 0.0, 2)),
        "change_5m": None,
        "prev_close": None,
        "rate": float(round(price, 3)),
        "contract": code,
        "maturity": maturity_display,
        "maturity_timestamp": maturity_ts,
        "last_trade": last_trade.get("display") if isinstance(last_trade, dict) else last_trade,
        "volume": _finite_float(volume),
        "category": "DI Futuro BR",
        "updated_at": updated_at,
    }


def _extract_infomoney_nonce(html: str) -> str | None:
    patterns = [
        r'"di_futuro_cotacoes_nonce"\s*:\s*"([^"]+)"',
        r"di_futuro_cotacoes_nonce['\"]?\s*[:=]\s*['\"]([^'\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def fetch_di_futuro_infomoney(timeout: int = 12) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": INFOMONEY_DI_URL,
    }
    session = requests.Session()
    page = session.get(INFOMONEY_DI_URL, headers=headers, timeout=timeout)
    page.raise_for_status()
    nonce = _extract_infomoney_nonce(page.text)
    if not nonce:
        raise RuntimeError("Nonce de DI Futuro nao encontrado no InfoMoney.")

    response = session.post(
        INFOMONEY_AJAX_URL,
        data={"action": "tool_contratos_di_futuro", "di_futuro_cotacoes_nonce": nonce},
        headers={**headers, "Accept": "application/json, text/javascript, */*; q=0.01"},
        timeout=timeout,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("Resposta inesperada do InfoMoney para DI Futuro.")

    quotes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        quote = _build_quote(row[0], row[1], row[2], row[3], row[4], row[5], "InfoMoney DI")
        if quote:
            quotes.append(quote)
    return quotes


def load_di_futuro_csv(path: Path | None = None) -> list[dict[str, Any]]:
    csv_path = path or USER_CSV_PATH
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        quotes = []
        for row in reader:
            code = row.get("Codigo") or row.get("Código") or row.get("code") or row.get("symbol")
            if not code:
                continue
            quote = _build_quote(
                code.strip(),
                row.get("Vencimento") or row.get("maturity"),
                row.get("Taxa de juros") or row.get("Taxa") or row.get("rate"),
                row.get("Variacao") or row.get("Variação") or row.get("change"),
                row.get("Data/Hora do Ult. negocio")
                or row.get("Data/Hora do Últ. negócio")
                or row.get("Ultimo negocio")
                or row.get("last_trade"),
                row.get("Volume negociado") or row.get("Volume") or row.get("volume"),
                "CSV DI Futuro",
            )
            if quote:
                quotes.append(quote)
        return quotes


def _load_cached_payload() -> dict[str, Any] | None:
    try:
        if CACHE_PATH.exists():
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _save_cached_payload(payload: dict[str, Any]) -> None:
    try:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] Nao foi possivel salvar cache DI Futuro: {exc}")


def filter_principal_di(quotes: list[dict[str, Any]], watched: tuple[str, ...] = WATCHED_DI_CONTRACTS) -> list[dict[str, Any]]:
    by_symbol = {str(item.get("symbol")): item for item in quotes if item.get("symbol")}
    selected: list[dict[str, Any]] = []
    for symbol in watched:
        if symbol in by_symbol:
            selected.append(by_symbol[symbol])
            continue
        fallback_symbol = LONG_TENOR_FALLBACKS.get(symbol)
        if fallback_symbol and fallback_symbol in by_symbol:
            selected.append(_mark_as_fallback_contract(by_symbol[fallback_symbol], symbol))
    return selected


def build_di_futuro_payload() -> dict[str, Any]:
    errors: list[str] = []
    quotes: list[dict[str, Any]] = []
    source = "InfoMoney DI"

    try:
        quotes = fetch_di_futuro_infomoney()
    except Exception as exc:
        errors.append(f"InfoMoney: {exc}")

    if quotes:
        try:
            csv_quotes = load_di_futuro_csv()
            quotes = _merge_missing_quotes(quotes, csv_quotes)
            missing = [symbol for symbol in WATCHED_DI_CONTRACTS if symbol not in {str(q.get("symbol")) for q in quotes}]
            if csv_quotes and missing:
                errors.append(f"Contratos ausentes nas fontes locais/API: {', '.join(missing)}")
        except Exception as exc:
            errors.append(f"CSV complementar: {exc}")

    if not quotes:
        try:
            quotes = load_di_futuro_csv()
            if quotes:
                source = "CSV DI Futuro"
        except Exception as exc:
            errors.append(f"CSV: {exc}")

    if not quotes:
        cached = _load_cached_payload()
        if cached:
            cached.setdefault("errors", []).extend(errors)
            cached["source"] = f"{cached.get('source', 'cache')} + cache"
            return cached

    payload = {
        "schema_version": "di_futuro_br_v1",
        "updated_at": _now_iso(),
        "source": source,
        "contracts": quotes,
        "principais": filter_principal_di(quotes),
        "errors": errors,
    }
    if quotes:
        _save_cached_payload(payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_di_futuro_payload(), ensure_ascii=False, indent=2))
