"""Coleta contratos continuos de commodities equivalentes aos widgets TradingView."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import requests


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/global/scan"
COMMODITY_FUTURES = {
    "BZ=F": "NYMEX:BZ1!",
    "CL=F": "NYMEX:CL1!",
    "NG=F": "NYMEX:NG1!",
    "HG=F": "COMEX:HG1!",
    "GC=F": "COMEX:GC1!",
    "SI=F": "COMEX:SI1!",
    "PL=F": "NYMEX:PL1!",
    "PA=F": "NYMEX:PA1!",
}

_COLUMNS = ("close", "change", "change_abs", "high", "low", "open", "update_mode")
_CACHE: dict[str, dict[str, Any]] | None = None


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _market_delay_seconds(update_mode: Any) -> int:
    text = str(update_mode or "")
    if text.startswith("delayed_streaming_"):
        try:
            return int(text.rsplit("_", 1)[1])
        except (TypeError, ValueError):
            pass
    return 0


def fetch_tradingview_commodity_futures(timeout: int = 8, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Busca todos os contratos em lote para evitar chamadas repetidas."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    payload = {
        "symbols": {"tickers": list(COMMODITY_FUTURES.values()), "query": {"types": []}},
        "columns": list(_COLUMNS),
    }
    response = requests.post(TRADINGVIEW_SCAN_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    retrieved_at = datetime.now(timezone.utc)
    quotes: dict[str, dict[str, Any]] = {}

    for row in response.json().get("data", []):
        symbol = str(row.get("s") or "")
        values = row.get("d") or []
        if symbol not in COMMODITY_FUTURES.values() or len(values) != len(_COLUMNS):
            continue
        fields = dict(zip(_COLUMNS, values))
        price = _finite_float(fields.get("close"))
        change_abs = _finite_float(fields.get("change_abs"))
        if price is None or price <= 0:
            continue
        previous_settlement = price - change_abs if change_abs is not None else None
        update_mode = fields.get("update_mode")
        quotes[symbol] = {
            "price": price,
            "high": _finite_float(fields.get("high")) or price,
            "low": _finite_float(fields.get("low")) or price,
            "open": _finite_float(fields.get("open")),
            "prev_close": previous_settlement,
            "previous_settlement": previous_settlement,
            "change": _finite_float(fields.get("change")),
            "change_settlement": _finite_float(fields.get("change")),
            "change_abs": change_abs,
            "change_5m": None,
            "source": "TradingView Commodity Futures",
            "source_symbol": symbol,
            "source_timestamp": retrieved_at.isoformat(),
            "timestamp_type": "retrieved_at",
            "age_seconds": 0.0,
            "market_delay_seconds": _market_delay_seconds(update_mode),
            "update_mode": update_mode,
            "contract_type": "continuous_front",
        }

    if not quotes:
        raise RuntimeError("TradingView nao retornou contratos continuos de commodities.")
    _CACHE = quotes
    return quotes


def fetch_tradingview_commodity_candidate(name: str, ticker_symbol: str) -> dict[str, Any] | None:
    tradingview_symbol = COMMODITY_FUTURES.get(ticker_symbol)
    if not tradingview_symbol:
        return None
    quote = fetch_tradingview_commodity_futures().get(tradingview_symbol)
    if not quote:
        return None
    candidate = {"name": name, "symbol": ticker_symbol, **quote}
    for key in ("price", "high", "low", "open", "prev_close", "previous_settlement", "change_abs"):
        if candidate.get(key) is not None:
            candidate[key] = round(float(candidate[key]), 4)
    for key in ("change", "change_settlement"):
        if candidate.get(key) is not None:
            candidate[key] = round(float(candidate[key]), 3)
    return candidate


if __name__ == "__main__":
    for item in fetch_tradingview_commodity_futures(refresh=True).values():
        print(item)
