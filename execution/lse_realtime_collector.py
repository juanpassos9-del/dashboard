"""Coletor leve da London Strategic Edge para overlay quase-tempo-real.

Uso:
    python execution/lse_realtime_collector.py --once
    python execution/lse_realtime_collector.py --loop --interval 5

O script grava `lse_realtime_quotes` em app_state/Supabase e um cache local em
`.tmp/lse_realtime_quotes.json`. Ele falha de forma segura se a chave, pacote ou
simbolos London nao estiverem disponiveis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TMP_DIR = PROJECT_DIR / ".tmp"
TMP_DIR.mkdir(exist_ok=True)

if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.append(str(PROJECT_DIR))

from app_state_sync import get_service_client, sync_app_state_value
from lse_client import fetch_lse_ohlcv


BR_TZ = ZoneInfo("America/Sao_Paulo")
CACHE_PATH = TMP_DIR / "lse_realtime_quotes.json"

DEFAULT_SYMBOLS = [
    "^BVSP",
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^RUT",
    "^VIX",
    "DX-Y.NYB",
    "BRL=X",
    "EURUSD=X",
    "GBPUSD=X",
    "JPY=X",
    "AUDUSD=X",
    "CAD=X",
    "CHF=X",
    "BZ=F",
    "CL=F",
    "NG=F",
    "GC=F",
    "SI=F",
    "HG=F",
    "EEM",
    "EMB",
    "EWZ",
    "ILF",
    "SPY",
    "XOP",
    "XLE",
    "XLK",
    "XLP",
    "XLB",
    "XLI",
    "XLV",
    "XLRE",
    "XBI",
    "XLY",
    "XLC",
    "PBR",
    "VALE",
    "ITUB",
    "BBD",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
]


def _round_price(value):
    value = float(value)
    return float(round(value, 2) if abs(value) > 10 else round(value, 4))


def _age_seconds(ts) -> float | None:
    if ts is None:
        return None
    try:
        timestamp = pd.Timestamp(ts)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone.utc)
        else:
            timestamp = timestamp.tz_convert(timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - timestamp.to_pydatetime()).total_seconds())
    except Exception:
        return None


def _change_5m(df: pd.DataFrame, last_price: float) -> float | None:
    try:
        clean = df.dropna(subset=["Close"])
        if clean.empty:
            return None
        target = clean.index[-1] - pd.Timedelta(minutes=5)
        prior = clean[clean.index <= target]
        if prior.empty:
            return None
        ref = float(prior["Close"].iloc[-1])
        if ref <= 0:
            return None
        return round(((last_price - ref) / ref) * 100, 2)
    except Exception:
        return None


def _prev_close(df: pd.DataFrame) -> float | None:
    try:
        clean = df.dropna(subset=["Close"]).copy()
        if clean.empty:
            return None
        local_index = clean.index.tz_convert(BR_TZ) if clean.index.tz is not None else clean.index.tz_localize(timezone.utc).tz_convert(BR_TZ)
        clean = clean.copy()
        clean["_date"] = local_index.date
        latest_date = clean["_date"].iloc[-1]
        prior = clean[clean["_date"] < latest_date]
        if prior.empty:
            return None
        return _round_price(float(prior["Close"].iloc[-1]))
    except Exception:
        return None


def build_snapshot(symbols: list[str], interval: str = "1m", limit: int = 390) -> dict:
    quotes = {}
    errors = {}
    started = datetime.now(timezone.utc)

    for symbol in symbols:
        try:
            df = fetch_lse_ohlcv(symbol, interval=interval, limit=limit)
            if df.empty:
                errors[symbol] = "sem dados"
                continue
            clean = df.dropna(subset=["Close"])
            if clean.empty:
                errors[symbol] = "sem close"
                continue
            last_price = float(clean["Close"].iloc[-1])
            source_time = clean.index[-1]
            quotes[symbol.upper()] = {
                "symbol": symbol.upper(),
                "source": "London Strategic Edge",
                "source_symbol": df.attrs.get("lse_symbol") or symbol,
                "source_timestamp": pd.Timestamp(source_time).isoformat(),
                "age_seconds": round(_age_seconds(source_time) or 0.0, 1),
                "price": _round_price(last_price),
                "prev_close": _prev_close(clean),
                "change_5m": _change_5m(clean, last_price),
            }
        except Exception as exc:
            errors[symbol] = str(exc)[:180]

    return {
        "source": "London Strategic Edge",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_at_br": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "interval": interval,
        "quotes": quotes,
        "errors": errors,
        "metadata": {
            "symbols_requested": len(symbols),
            "symbols_ok": len(quotes),
            "mode": "polling",
        },
    }


def sync_snapshot(snapshot: dict) -> None:
    CACHE_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    client = get_service_client()
    sync_app_state_value("lse_realtime_quotes", snapshot, client)


def is_market_window(now_br: datetime | None = None) -> bool:
    now_br = now_br or datetime.now(BR_TZ)
    if now_br.weekday() >= 5:
        return False
    return dtime(9, 0) <= now_br.time() <= dtime(17, 0)


def parse_symbols(raw: str) -> list[str]:
    if not raw:
        return DEFAULT_SYMBOLS
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    # GitHub/Streamlit envs sometimes keep a one-symbol test value around.
    # For the production 24/7 collector, fall back to the curated universe.
    if len(symbols) < 5:
        return DEFAULT_SYMBOLS
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta quotes London Strategic Edge e sincroniza no Supabase.")
    parser.add_argument("--once", action="store_true", help="Executa uma coleta e encerra.")
    parser.add_argument("--loop", action="store_true", help="Executa em loop.")
    parser.add_argument("--interval", type=int, default=5, help="Intervalo do loop em segundos.")
    parser.add_argument("--lse-interval", default="1m", help="Timeframe de candles London.")
    parser.add_argument("--limit", type=int, default=390, help="Quantidade de candles por ativo.")
    parser.add_argument("--symbols", default=os.getenv("LSE_REALTIME_SYMBOLS", ""), help="Lista separada por virgula.")
    parser.add_argument("--ignore-market-window", action="store_true", help="Roda fora da janela 9h-17h BR.")
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    if not args.once and not args.loop:
        args.once = True

    while True:
        if args.ignore_market_window or is_market_window():
            snapshot = build_snapshot(symbols, interval=args.lse_interval, limit=args.limit)
            sync_snapshot(snapshot)
            print(f"[+] LSE realtime: {len(snapshot['quotes'])}/{len(symbols)} simbolos em {snapshot['elapsed_seconds']}s")
        else:
            print("[i] Fora da janela 9h-17h BR. Aguardando.")

        if args.once:
            return 0
        time.sleep(max(2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
