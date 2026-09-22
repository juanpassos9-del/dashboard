"""Coleta contratos continuos de commodities equivalentes aos widgets TradingView."""

from __future__ import annotations

import json
import math
import random
import string
import time
from datetime import datetime, timezone
from typing import Any

import requests


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/global/scan"
COMMODITY_FUTURES = {
    "BZ=F": "TVC:UKOIL",
    "CL=F": "TVC:USOIL",
    "NG=F": "NYMEX:NG1!",
    "HG=F": "COMEX:HG1!",
    "GC=F": "COMEX:GC1!",
    "SI=F": "COMEX:SI1!",
    "PL=F": "NYMEX:PL1!",
    "PA=F": "NYMEX:PA1!",
}
OIL_FALLBACKS = {
    "BZ=F": "NYMEX:BZ1!",
    "CL=F": "NYMEX:CL1!",
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


def _tv_frame(method: str, params: list[Any]) -> str:
    body = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _iter_tv_messages(raw: str):
    cursor = 0
    while raw.startswith("~m~", cursor):
        length_end = raw.find("~m~", cursor + 3)
        if length_end < 0:
            return
        try:
            body_length = int(raw[cursor + 3:length_end])
        except ValueError:
            return
        body_start = length_end + 3
        body = raw[body_start:body_start + body_length]
        cursor = body_start + body_length
        try:
            yield json.loads(body)
        except json.JSONDecodeError:
            continue


def _fetch_tvc_oil_quotes(timeout: int = 8) -> dict[str, dict[str, Any]]:
    """Le UKOIL/USOIL no mesmo canal websocket usado pelos graficos TradingView."""
    try:
        import websocket
    except Exception:
        return {}

    symbols = tuple(OIL_FALLBACKS.keys())
    tv_symbols = [COMMODITY_FUTURES[symbol] for symbol in symbols]
    session = "qs_" + "".join(random.choices(string.ascii_lowercase, k=12))
    fields = (
        "lp",
        "ch",
        "chp",
        "open_price",
        "high_price",
        "low_price",
        "prev_close_price",
        "update_mode",
        "short_name",
    )
    ws = None
    quotes: dict[str, dict[str, Any]] = {}
    try:
        ws = websocket.create_connection(
            "wss://data.tradingview.com/socket.io/websocket?from=symbols/USOIL/?exchange=TVC",
            origin="https://www.tradingview.com",
            timeout=timeout,
        )
        ws.send(_tv_frame("set_auth_token", ["unauthorized_user_token"]))
        ws.send(_tv_frame("quote_create_session", [session]))
        ws.send(_tv_frame("quote_set_fields", [session, *fields]))
        for symbol in tv_symbols:
            ws.send(_tv_frame("quote_add_symbols", [session, symbol]))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(quotes) < len(tv_symbols):
            raw = ws.recv()
            for message in _iter_tv_messages(str(raw)):
                if message.get("m") != "qsd":
                    continue
                payload = (message.get("p") or [None, {}])[1]
                symbol = str(payload.get("n") or "")
                values = payload.get("v") or {}
                price = _finite_float(values.get("lp"))
                if symbol not in tv_symbols or price is None or price <= 0:
                    continue
                previous_close = _finite_float(values.get("prev_close_price"))
                update_mode = values.get("update_mode")
                retrieved_at = datetime.now(timezone.utc)
                quotes[symbol] = {
                    "price": price,
                    "high": _finite_float(values.get("high_price")) or price,
                    "low": _finite_float(values.get("low_price")) or price,
                    "open": _finite_float(values.get("open_price")),
                    "prev_close": previous_close,
                    "previous_close": previous_close,
                    "change": _finite_float(values.get("chp")),
                    "change_session": _finite_float(values.get("chp")),
                    "change_abs": _finite_float(values.get("ch")),
                    "change_5m": None,
                    "source": "TradingView TVC Energy",
                    "source_symbol": symbol,
                    "source_timestamp": retrieved_at.isoformat(),
                    "timestamp_type": "retrieved_at",
                    "age_seconds": 0.0,
                    "market_delay_seconds": _market_delay_seconds(update_mode),
                    "update_mode": update_mode,
                    "instrument_type": "derived_cfd",
                    "reference_type": "previous_close",
                }
    except Exception as exc:
        print(f"[!] TradingView TVC Energy websocket falhou: {exc}")
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
    return quotes


def fetch_tradingview_commodity_futures(timeout: int = 8, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Busca todos os contratos em lote para evitar chamadas repetidas."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    payload = {
        "symbols": {
            "tickers": list(COMMODITY_FUTURES.values()) + list(OIL_FALLBACKS.values()),
            "query": {"types": []},
        },
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

    quotes.update(_fetch_tvc_oil_quotes(timeout=timeout))

    if not quotes:
        raise RuntimeError("TradingView nao retornou contratos continuos de commodities.")
    _CACHE = quotes
    return quotes


def fetch_tradingview_commodity_candidate(name: str, ticker_symbol: str) -> dict[str, Any] | None:
    tradingview_symbol = COMMODITY_FUTURES.get(ticker_symbol)
    if not tradingview_symbol:
        return None
    available_quotes = fetch_tradingview_commodity_futures()
    quote = available_quotes.get(tradingview_symbol)
    if not quote and ticker_symbol in OIL_FALLBACKS:
        fallback_symbol = OIL_FALLBACKS[ticker_symbol]
        fallback_quote = available_quotes.get(fallback_symbol)
        if fallback_quote:
            quote = {
                **fallback_quote,
                "preferred_source_symbol": tradingview_symbol,
                "fallback_reason": "TVC websocket indisponivel",
            }
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
