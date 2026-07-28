"""Diagnostico leve de cobertura da London Strategic Edge.

O plano free pode liberar apenas parte dos endpoints. Este script testa
permissoes/cobertura sem travar o dashboard e salva um resumo seguro em
`app_state.lse_diagnostics`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TMP_DIR = PROJECT_DIR / ".tmp"
TMP_DIR.mkdir(exist_ok=True)

if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.append(str(PROJECT_DIR))

from app_state_sync import sync_app_state_value
from lse_client import get_lse_api_key


CACHE_PATH = TMP_DIR / "lse_diagnostics.json"
DEFAULT_TEST_SYMBOLS = ["SPY", "EWZ", "BTCUSDT", "EURUSD", "BRENT", "XAUUSD"]


def _safe_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text.replace(get_lse_api_key(), "[redacted]")[:180]


def _count_payload(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("results") or payload.get("items") or payload.get("candles")
        if isinstance(rows, list):
            return len(rows)
        return len(payload)
    if isinstance(payload, list):
        return len(payload)
    try:
        return len(payload)
    except Exception:
        return 0


def _endpoint_result(name: str, fn) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        payload = fn()
        rows = _count_payload(payload)
        return {
            "name": name,
            "status": "ok" if rows else "empty",
            "rows": rows,
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "error",
            "rows": 0,
            "message": _safe_error(exc),
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        }


def build_lse_diagnostics(test_symbols: list[str] | None = None) -> dict[str, Any]:
    api_key = get_lse_api_key()
    now = datetime.now(timezone.utc)
    if not api_key:
        return {
            "source": "London Strategic Edge",
            "status": "disabled",
            "updated_at": now.isoformat(),
            "message": "LSE_API_KEY ausente.",
            "endpoints": [],
            "symbols": [],
        }

    try:
        from lse import LSE
    except Exception as exc:
        return {
            "source": "London Strategic Edge",
            "status": "disabled",
            "updated_at": now.isoformat(),
            "message": f"Pacote lse-data indisponivel: {_safe_error(exc)}",
            "endpoints": [],
            "symbols": [],
        }

    client = LSE(api_key=api_key)
    endpoints = []
    symbols_result = []

    endpoints.append(_endpoint_result("tier", lambda: [{"tier": str(getattr(client, "tier", ""))}]))
    endpoints.append(_endpoint_result("symbols", lambda: getattr(client, "symbols", [])))
    endpoints.append(_endpoint_result("catalog", lambda: client.catalog()))
    endpoints.append(_endpoint_result("economic_calendar", lambda: client.economic_calendar(limit=5)))
    endpoints.append(_endpoint_result("bond_yields", lambda: client.bond_yields(limit=5)))

    for symbol in test_symbols or DEFAULT_TEST_SYMBOLS:
        result = _endpoint_result(f"candles:{symbol}", lambda s=symbol: client.candles(symbol=s, timeframe="1m", limit=3))
        result["symbol"] = symbol
        symbols_result.append(result)

    ok_count = sum(1 for item in endpoints + symbols_result if item.get("status") == "ok")
    error_count = sum(1 for item in endpoints + symbols_result if item.get("status") == "error")
    empty_count = sum(1 for item in endpoints + symbols_result if item.get("status") == "empty")
    status = "ok" if ok_count else ("error" if error_count else "stale")

    return {
        "source": "London Strategic Edge",
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message": f"{ok_count} testes ok, {empty_count} vazios, {error_count} erros.",
        "endpoints": endpoints,
        "symbols": symbols_result,
        "summary": {
            "ok": ok_count,
            "empty": empty_count,
            "error": error_count,
            "total": len(endpoints) + len(symbols_result),
        },
    }


def parse_symbols(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostica endpoints London Strategic Edge disponiveis.")
    parser.add_argument("--symbols", default="", help="Lista curta separada por virgula para testar candles.")
    parser.add_argument("--no-sync", action="store_true", help="Apenas salva cache local.")
    args = parser.parse_args()

    payload = build_lse_diagnostics(parse_symbols(args.symbols) or None)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_sync:
        sync_app_state_value("lse_diagnostics", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
