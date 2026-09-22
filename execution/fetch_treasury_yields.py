"""Coleta yields spot dos Treasuries usados pelos widgets TradingView.

O scanner entrega o mesmo instrumento OTC exibido no dashboard. FRED continua
sendo o fallback oficial diario no coletor principal quando esta fonte falhar.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import requests


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/global/scan"
TREASURY_SYMBOLS = {
    "FRED:DGS2": "OTCB:US02Y",
    "^FVX": "OTCB:US05Y",
    "^TNX": "OTCB:US10Y",
    "^TYX": "OTCB:US30Y",
    "^IRX": "OTCB:US03MY",
}

_COLUMNS = ("close", "change", "change_abs", "high", "low", "open", "update_mode")
_CACHE: dict[str, dict[str, Any]] | None = None


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def fetch_tradingview_treasury_yields(timeout: int = 8, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Retorna os cinco vencimentos spot em uma unica chamada."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    payload = {
        "symbols": {"tickers": list(TREASURY_SYMBOLS.values()), "query": {"types": []}},
        "columns": list(_COLUMNS),
    }
    response = requests.post(TRADINGVIEW_SCAN_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    rows = response.json().get("data", [])
    retrieved_at = datetime.now(timezone.utc)
    quotes: dict[str, dict[str, Any]] = {}

    for row in rows:
        symbol = str(row.get("s") or "")
        values = row.get("d") or []
        if symbol not in TREASURY_SYMBOLS.values() or len(values) != len(_COLUMNS):
            continue
        fields = dict(zip(_COLUMNS, values))
        price = _finite_float(fields.get("close"))
        change_abs = _finite_float(fields.get("change_abs"))
        if price is None or not 0 < price < 25:
            continue
        previous = price - change_abs if change_abs is not None else None
        quotes[symbol] = {
            "price": price,
            "high": _finite_float(fields.get("high")) or price,
            "low": _finite_float(fields.get("low")) or price,
            "open": _finite_float(fields.get("open")),
            "prev_close": previous,
            "change": _finite_float(fields.get("change")),
            "change_bps": change_abs * 100.0 if change_abs is not None else None,
            "source": "TradingView OTC Yields",
            "source_symbol": symbol,
            "source_timestamp": retrieved_at.isoformat(),
            "timestamp_type": "retrieved_at",
            "age_seconds": 0.0,
            "update_mode": fields.get("update_mode"),
        }

    if not quotes:
        raise RuntimeError("TradingView nao retornou yields spot dos Treasuries.")
    _CACHE = quotes
    return quotes


def fetch_tradingview_treasury_candidate(name: str, ticker_symbol: str) -> dict[str, Any] | None:
    tradingview_symbol = TREASURY_SYMBOLS.get(ticker_symbol)
    if not tradingview_symbol:
        return None
    quote = fetch_tradingview_treasury_yields().get(tradingview_symbol)
    if not quote:
        return None
    return {
        "name": name,
        "symbol": ticker_symbol,
        **quote,
        "price": round(float(quote["price"]), 4),
        "high": round(float(quote["high"]), 4),
        "low": round(float(quote["low"]), 4),
        "prev_close": round(float(quote["prev_close"]), 4) if quote.get("prev_close") is not None else None,
        "change": round(float(quote["change"]), 3) if quote.get("change") is not None else None,
        "change_bps": round(float(quote["change_bps"]), 2) if quote.get("change_bps") is not None else None,
        "change_5m": None,
    }


if __name__ == "__main__":
    for item in fetch_tradingview_treasury_yields(refresh=True).values():
        print(item)
