import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import tomllib
except Exception:
    tomllib = None


LSE_SECRET_NAMES = (
    "LSE_API_KEY",
    "LONDON_STRATEGIC_EDGE_API_KEY",
    "LONDON_STRATEGIC_EDGE_KEY",
    "LSE_KEY",
)

LSE_SYMBOL_MAP = {
    "^BVSP": ("IBOV", "IBOVESPA", "^BVSP"),
    "^GSPC": ("SPY", "SPX", "US500", "S&P 500"),
    "^IXIC": ("QQQ", "NDX", "NASDAQ"),
    "^DJI": ("DIA", "DJI"),
    "^RUT": ("IWM", "RUSSELL"),
    "^VIX": ("VIX",),
    "DX-Y.NYB": ("DXY", "UUP"),
    "BRL=X": ("USD/BRL", "USDBRL", "BRLUSD"),
    "EURUSD=X": ("EUR/USD", "EURUSD"),
    "GBPUSD=X": ("GBP/USD", "GBPUSD"),
    "JPY=X": ("USD/JPY", "USDJPY"),
    "AUDUSD=X": ("AUD/USD", "AUDUSD"),
    "CAD=X": ("USD/CAD", "USDCAD"),
    "CHF=X": ("USD/CHF", "USDCHF"),
    "BZ=F": ("BRENT", "BNO"),
    "CL=F": ("WTI", "USO"),
    "NG=F": ("NATGAS", "UNG"),
    "GC=F": ("XAUUSD", "GOLD", "GLD"),
    "SI=F": ("XAGUSD", "SILVER", "SLV"),
    "HG=F": ("COPPER", "CPER"),
    "EEM": ("EEM",),
    "EMB": ("EMB",),
    "EWZ": ("EWZ",),
    "ILF": ("ILF",),
    "SPY": ("SPY",),
    "XOP": ("XOP",),
    "XLE": ("XLE",),
    "XLK": ("XLK",),
    "XLP": ("XLP",),
    "XLB": ("XLB",),
    "XLI": ("XLI",),
    "XLV": ("XLV",),
    "XLRE": ("XLRE",),
    "XBI": ("XBI",),
    "XLY": ("XLY",),
    "XLC": ("XLC",),
    "PBR": ("PBR",),
    "VALE": ("VALE",),
    "ITUB": ("ITUB",),
    "BBD": ("BBD",),
    "BTC-USD": ("BTCUSDT", "BTCUSD", "BTC"),
    "ETH-USD": ("ETHUSDT", "ETHUSD", "ETH"),
    "SOL-USD": ("SOLUSDT", "SOLUSD", "SOL"),
}


def get_lse_api_key() -> str:
    for name in LSE_SECRET_NAMES:
        value = os.getenv(name)
        if value:
            return str(value)

    try:
        import streamlit as st

        for name in LSE_SECRET_NAMES:
            value = st.secrets.get(name, "")
            if value:
                return str(value)
    except Exception:
        pass

    secrets_path = Path(".streamlit") / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        if tomllib is not None:
            with secrets_path.open("rb") as fp:
                secrets = tomllib.load(fp)
        else:
            secrets = {}
            for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return ""

    for name in LSE_SECRET_NAMES:
        value = secrets.get(name)
        if value:
            return str(value)
    return ""


def _normalise_candles(payload) -> pd.DataFrame:
    if payload is None:
        return pd.DataFrame()
    if isinstance(payload, pd.DataFrame):
        df = payload.copy()
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("candles") or payload.get("results") or payload.get("items") or []
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(payload)
    if df.empty:
        return pd.DataFrame()

    lower_map = {str(col).lower(): col for col in df.columns}
    time_col = next((lower_map[key] for key in ("time", "timestamp", "datetime", "date") if key in lower_map), None)
    if not time_col:
        return pd.DataFrame()

    out = pd.DataFrame(index=pd.to_datetime(df[time_col], errors="coerce", utc=True))
    for source, target in (
        ("open", "Open"),
        ("high", "High"),
        ("low", "Low"),
        ("close", "Close"),
        ("volume", "Volume"),
    ):
        col = lower_map.get(source)
        out[target] = pd.to_numeric(df[col], errors="coerce") if col else 0.0

    return out.dropna(subset=["High", "Low", "Close"]).sort_index()


def _call_candles(client, symbol: str, interval: str, limit: int):
    call_shapes = (
        {"symbol": symbol, "timeframe": interval, "limit": limit},
        {"ticker": symbol, "timeframe": interval, "limit": limit},
        {"symbol": symbol, "interval": interval, "limit": limit},
        {"ticker": symbol, "interval": interval, "limit": limit},
    )
    for kwargs in call_shapes:
        try:
            return client.candles(**kwargs)
        except TypeError:
            continue
    return None


def fetch_lse_ohlcv(symbol: str, interval: str = "1m", limit: int = 390) -> pd.DataFrame:
    api_key = get_lse_api_key()
    if not api_key:
        return pd.DataFrame()
    try:
        from lse import LSE
    except Exception:
        return pd.DataFrame()

    aliases = LSE_SYMBOL_MAP.get(symbol, (symbol,))
    for alias in aliases:
        try:
            client = LSE(api_key=api_key)
            payload = _call_candles(client, alias, interval, limit)
            df = _normalise_candles(payload)
            if not df.empty:
                df.attrs["lse_symbol"] = alias
                return df
        except Exception:
            continue
    return pd.DataFrame()


def fetch_lse_quote(symbol: str) -> dict | None:
    df = fetch_lse_ohlcv(symbol, interval="1m", limit=390)
    if df.empty:
        return None
    last = df.dropna(subset=["Close"]).iloc[-1]
    source_time = df.dropna(subset=["Close"]).index[-1]
    if source_time.tzinfo is None:
        source_time = source_time.tz_localize(timezone.utc)
    age = max(0.0, (datetime.now(timezone.utc) - source_time.to_pydatetime().astimezone(timezone.utc)).total_seconds())
    return {
        "df": df,
        "source": "London Strategic Edge",
        "source_symbol": df.attrs.get("lse_symbol") or symbol,
        "source_timestamp": source_time.isoformat(),
        "age_seconds": float(round(age, 1)),
        "price": float(last["Close"]),
    }
