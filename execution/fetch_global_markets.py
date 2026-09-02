import yfinance as yf
import pandas as pd
import json
import os
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    from execution.lse_client import fetch_lse_quote
except Exception:
    try:
        from lse_client import fetch_lse_quote
    except Exception:
        fetch_lse_quote = None

try:
    import tomllib
except Exception:
    tomllib = None


BR_TZ = ZoneInfo("America/Sao_Paulo")
NY_TZ = ZoneInfo("America/New_York")


TWELVE_SYMBOL_MAP = {
    "^GSPC": "SPY",
    "^IXIC": "QQQ",
    "^DJI": "DIA",
    "^RUT": "IWM",
    "^VIX": "VIX",
    "DX-Y.NYB": "UUP",
    "BRL=X": "USD/BRL",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "JPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "CAD=X": "USD/CAD",
    "CHF=X": "USD/CHF",
    "BZ=F": "BNO",
    "CL=F": "USO",
    "NG=F": "UNG",
    "GC=F": "GLD",
    "SI=F": "SLV",
    "HG=F": "CPER",
    "EEM": "EEM",
    "EMB": "EMB",
    "EWZ": "EWZ",
    "ILF": "ILF",
    "SPY": "SPY",
    "XOP": "XOP",
    "XLE": "XLE",
    "XLK": "XLK",
    "XLP": "XLP",
    "XLB": "XLB",
    "XLI": "XLI",
    "XLV": "XLV",
    "XLRE": "XLRE",
    "XBI": "XBI",
    "XLY": "XLY",
    "XLC": "XLC",
    "PBR": "PBR",
    "VALE": "VALE",
    "ITUB": "ITUB",
    "BBD": "BBD",
    "BTC-USD": "BTC/USD",
    "ETH-USD": "ETH/USD",
    "SOL-USD": "SOL/USD",
}


ALPHA_SYMBOL_MAP = {
    "^GSPC": "SPY",
    "^IXIC": "QQQ",
    "^DJI": "DIA",
    "^RUT": "IWM",
    "DX-Y.NYB": "UUP",
    "BZ=F": "BNO",
    "CL=F": "USO",
    "NG=F": "UNG",
    "GC=F": "GLD",
    "SI=F": "SLV",
    "HG=F": "CPER",
    "EEM": "EEM",
    "EMB": "EMB",
    "EWZ": "EWZ",
    "ILF": "ILF",
    "SPY": "SPY",
    "XOP": "XOP",
    "XLE": "XLE",
    "XLK": "XLK",
    "XLP": "XLP",
    "XLB": "XLB",
    "XLI": "XLI",
    "XLV": "XLV",
    "XLRE": "XLRE",
    "XBI": "XBI",
    "XLY": "XLY",
    "XLC": "XLC",
    "PBR": "PBR",
    "VALE": "VALE",
    "ITUB": "ITUB",
    "BBD": "BBD",
}


BRAPI_SYMBOL_MAP = {
    "^BVSP": "IBOV",
}


def _get_config_value(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return str(value)

    try:
        import streamlit as st

        for name in names:
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

    for name in names:
        value = secrets.get(name)
        if value:
            return str(value)
    return ""


def _to_utc_timestamp(value, assume_tz=timezone.utc):
    if value is None or value == "":
        return None
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize(assume_tz)
        else:
            ts = ts.tz_convert(timezone.utc)
        return ts.to_pydatetime().astimezone(timezone.utc)
    except Exception:
        return None


def _age_seconds(source_time):
    if not source_time:
        return None
    try:
        return max(0.0, (datetime.now(timezone.utc) - source_time.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _finite_float(value):
    try:
        num = float(value)
        if math.isfinite(num):
            return num
    except Exception:
        pass
    return None


def _round_price(value):
    value = float(value)
    return float(round(value, 2) if abs(value) > 10 else round(value, 4))


def _candidate_from_frame(name, ticker_symbol, ticker_df, source="Yahoo Finance", source_symbol=None):
    try:
        clean_df = ticker_df.dropna(subset=["Close"]).copy()
        if clean_df.empty:
            return None

        session_df = _latest_session_frame(ticker_df)
        last_price = float(clean_df["Close"].iloc[-1])
        high_price = float(session_df["High"].max()) if "High" in session_df.columns and not session_df.empty else last_price
        low_price = float(session_df["Low"].min()) if "Low" in session_df.columns and not session_df.empty else last_price

        latest_session_date = clean_df.index[-1].date()
        prev_close = _previous_session_close(ticker_df, latest_session_date)
        if not prev_close or prev_close <= 0:
            prev_close = last_price

        change = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0.0
        change_5m = _change_5m(ticker_df, last_price)
        source_time = _to_utc_timestamp(clean_df.index[-1], assume_tz=timezone.utc)
        age = _age_seconds(source_time)

        return {
            "name": name,
            "symbol": ticker_symbol,
            "source_symbol": source_symbol or ticker_symbol,
            "source": source,
            "source_timestamp": source_time.isoformat() if source_time else None,
            "age_seconds": float(round(age, 1)) if age is not None else None,
            "price": _round_price(last_price),
            "high": _round_price(high_price),
            "low": _round_price(low_price),
            "change": float(round(change, 2)),
            "change_5m": float(round(change_5m, 2)) if change_5m is not None else None,
            "prev_close": _round_price(prev_close),
        }
    except Exception as e:
        print(f"[!] Erro ao montar candidato {name} ({ticker_symbol}) via {source}: {e}")
        return None


def _parse_intraday_values(values, assume_tz=NY_TZ):
    rows = []
    if not isinstance(values, list):
        return pd.DataFrame()
    for row in values:
        try:
            ts = pd.Timestamp(row.get("datetime"))
            if ts.tzinfo is None:
                ts = ts.tz_localize(assume_tz)
            rows.append({
                "time": ts,
                "Open": float(row["open"]),
                "High": float(row["high"]),
                "Low": float(row["low"]),
                "Close": float(row["close"]),
                "Volume": float(row.get("volume", 0) or 0),
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("time").sort_index()


def _fetch_twelve_candidate(name, ticker_symbol):
    api_key = _get_config_value("TWELVE_DATA_API_KEY")
    mapped_symbol = TWELVE_SYMBOL_MAP.get(ticker_symbol)
    if not api_key or not mapped_symbol:
        return None

    params = {
        "symbol": mapped_symbol,
        "interval": "1min",
        "outputsize": 390,
        "apikey": api_key,
        "timezone": "America/New_York",
    }
    try:
        response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=6)
        payload = response.json()
        if payload.get("status") == "error":
            return None
        df = _parse_intraday_values(payload.get("values"), assume_tz=NY_TZ)
        if df.empty:
            return None
        return _candidate_from_frame(name, ticker_symbol, df, source="Twelve Data", source_symbol=mapped_symbol)
    except Exception as e:
        print(f"[!] Twelve Data falhou para {ticker_symbol}: {e}")
        return None


def _fetch_alpha_candidate(name, ticker_symbol):
    api_key = _get_config_value("ALPHA_VANTAGE_API_KEY")
    mapped_symbol = ALPHA_SYMBOL_MAP.get(ticker_symbol)
    if not api_key or not mapped_symbol:
        return None

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": mapped_symbol,
        "interval": "1min",
        "outputsize": "compact",
        "apikey": api_key,
    }
    try:
        response = requests.get("https://www.alphavantage.co/query", params=params, timeout=6)
        payload = response.json()
        series = payload.get("Time Series (1min)")
        if not isinstance(series, dict):
            return None
        values = []
        for raw_ts, row in series.items():
            values.append({
                "datetime": raw_ts,
                "open": row.get("1. open"),
                "high": row.get("2. high"),
                "low": row.get("3. low"),
                "close": row.get("4. close"),
                "volume": row.get("5. volume"),
            })
        df = _parse_intraday_values(values, assume_tz=NY_TZ)
        if df.empty:
            return None
        return _candidate_from_frame(name, ticker_symbol, df, source="Alpha Vantage", source_symbol=mapped_symbol)
    except Exception as e:
        print(f"[!] Alpha Vantage falhou para {ticker_symbol}: {e}")
        return None


def _fetch_brapi_candidate(name, ticker_symbol):
    token = _get_config_value("BRAPI_TOKEN", "BRAPI_API_KEY")
    mapped_symbol = BRAPI_SYMBOL_MAP.get(ticker_symbol)
    if not mapped_symbol:
        return None
    params = {"range": "1d", "interval": "1m", "fundamental": "false", "modules": ""}
    if token:
        params["token"] = token
    try:
        response = requests.get(f"https://brapi.dev/api/quote/{mapped_symbol}", params=params, timeout=5)
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            return None
        quote = results[0]
        price = _finite_float(quote.get("regularMarketPrice"))
        prev_close = _finite_float(quote.get("regularMarketPreviousClose"))
        change = _finite_float(quote.get("regularMarketChangePercent"))
        timestamp = quote.get("regularMarketTime")
        source_time = datetime.fromtimestamp(float(timestamp), timezone.utc) if timestamp else None
        if price is None:
            return None
        if prev_close is None or prev_close <= 0:
            prev_close = price
        if change is None:
            change = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
        age = _age_seconds(source_time)
        return {
            "name": name,
            "symbol": ticker_symbol,
            "source_symbol": mapped_symbol,
            "source": "Brapi",
            "source_timestamp": source_time.isoformat() if source_time else None,
            "age_seconds": float(round(age, 1)) if age is not None else None,
            "price": _round_price(price),
            "high": _round_price(_finite_float(quote.get("regularMarketDayHigh")) or price),
            "low": _round_price(_finite_float(quote.get("regularMarketDayLow")) or price),
            "change": float(round(change, 2)),
            "change_5m": None,
            "prev_close": _round_price(prev_close),
        }
    except Exception as e:
        print(f"[!] Brapi falhou para {ticker_symbol}: {e}")
        return None


def _fetch_lse_candidate(name, ticker_symbol):
    if fetch_lse_quote is None:
        return None
    try:
        payload = fetch_lse_quote(ticker_symbol)
        if not payload or payload.get("df") is None or payload["df"].empty:
            return None
        return _candidate_from_frame(
            name,
            ticker_symbol,
            payload["df"],
            source="London Strategic Edge",
            source_symbol=payload.get("source_symbol") or ticker_symbol,
        )
    except Exception as e:
        print(f"[!] London Strategic Edge falhou para {ticker_symbol}: {e}")
        return None


def _fetch_fred_yield_candidate(name, ticker_symbol):
    if not str(ticker_symbol).startswith("FRED:"):
        return None
    api_key = _get_config_value("FRED_API_KEY", "FRED_KEY")
    if not api_key:
        return _fetch_us02y_yahoo_candidate(name, ticker_symbol)
    series_id = str(ticker_symbol).split(":", 1)[1]
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,
    }
    try:
        response = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=6)
        response.raise_for_status()
        observations = response.json().get("observations", [])
        values = []
        for obs in observations:
            value = _finite_float(obs.get("value"))
            if value is not None:
                values.append({"date": obs.get("date"), "value": value})
        if len(values) < 2:
            return None
        latest, previous = values[0], values[1]
        price = float(latest["value"])
        prev = float(previous["value"])
        change_pct = ((price - prev) / prev) * 100 if prev else 0.0
        change_bps = (price - prev) * 100.0
        source_time = _to_utc_timestamp(latest.get("date"), assume_tz=timezone.utc)
        age = _age_seconds(source_time)
        return {
            "name": name,
            "symbol": ticker_symbol,
            "source_symbol": series_id,
            "source": "FRED",
            "source_timestamp": source_time.isoformat() if source_time else None,
            "age_seconds": float(round(age, 1)) if age is not None else None,
            "price": _round_price(price),
            "high": _round_price(max(price, prev)),
            "low": _round_price(min(price, prev)),
            "change": float(round(change_pct, 2)),
            "change_bps": float(round(change_bps, 2)),
            "change_5m": None,
            "prev_close": _round_price(prev),
        }
    except Exception as e:
        print(f"[!] FRED falhou para {series_id}: {e}")
        return _fetch_us02y_yahoo_candidate(name, ticker_symbol)


def _fetch_us02y_yahoo_candidate(name, ticker_symbol):
    if ticker_symbol != "FRED:DGS2":
        return None
    try:
        data = yf.download(
            "2YY=F",
            period="10d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=8,
        )
        if data is None or data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            if "2YY=F" in set(data.columns.get_level_values(0)):
                data = data["2YY=F"]
            elif "2YY=F" in set(data.columns.get_level_values(1)):
                data = data.xs("2YY=F", axis=1, level=1)
        candidate = _candidate_from_frame(name, ticker_symbol, data, source="Yahoo Finance", source_symbol="2YY=F")
        if not candidate:
            return None
        try:
            price = _finite_float(candidate.get("price"))
            prev = _finite_float(candidate.get("prev_close"))
            if price is not None and prev is not None:
                candidate["change_bps"] = float(round((price - prev) * 100.0, 2))
        except Exception:
            pass
        candidate["change_5m"] = None
        return candidate
    except Exception as e:
        print(f"[!] Yahoo fallback US02Y falhou: {e}")
        return None


def _quote_candidates(name, ticker_symbol, yfinance_df=None):
    candidates = []
    fred_candidate = _fetch_fred_yield_candidate(name, ticker_symbol)
    if fred_candidate:
        return [fred_candidate]

    if yfinance_df is not None and not yfinance_df.empty:
        candidate = _candidate_from_frame(name, ticker_symbol, yfinance_df, source="Yahoo Finance")
        if candidate:
            candidates.append(candidate)

    best_age = None
    if candidates:
        best_age = candidates[0].get("age_seconds")
    if best_age is not None and best_age <= 120:
        return candidates

    # Brapi, London e Twelve tendem a ser bons fallbacks para o painel.
    # Alpha entra por ultimo porque o plano gratuito e mais limitado.
    for fetcher in (_fetch_brapi_candidate, _fetch_lse_candidate, _fetch_twelve_candidate, _fetch_alpha_candidate):
        candidate = fetcher(name, ticker_symbol)
        if candidate:
            candidates.append(candidate)
            if candidate.get("age_seconds") is not None and candidate["age_seconds"] <= 120:
                break
    return candidates


def _select_best_candidate(candidates):
    valid = [item for item in candidates if _finite_float(item.get("price")) is not None]
    if not valid:
        return None

    def score(item):
        age = item.get("age_seconds")
        if age is None:
            age = 10**9
        source_bonus = {"Brapi": -10, "London Strategic Edge": -8, "Twelve Data": -5, "Yahoo Finance": 0, "Alpha Vantage": 20}.get(item.get("source"), 0)
        return (float(age) + source_bonus, item.get("source") != "Yahoo Finance")

    return sorted(valid, key=score)[0]


def _download_market_batches(tickers, batch_size=5):
    data_parts = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        print(f"[*] Baixando lote {i // batch_size + 1}: {', '.join(batch)}")
        batch_data = None
        for attempt in range(3):
            try:
                batch_data = yf.download(
                    batch,
                    period="5d",
                    interval="1m",
                    prepost=True,
                    group_by="ticker",
                    progress=False,
                    timeout=20,
                    threads=False,
                )
                if batch_data is not None and not batch_data.empty:
                    data_parts.append(batch_data)
                    break
            except Exception as e:
                print(f"[!] Lote {i // batch_size + 1} tentativa {attempt + 1} falhou: {e}")
                time.sleep(5)
        if batch_data is None or batch_data.empty:
            print(f"[!] Lote sem dados: {', '.join(batch)}")
        time.sleep(3)

    if not data_parts:
        return None
    return pd.concat(data_parts, axis=1)


def _latest_session_frame(ticker_df):
    """Retorna os candles da ultima data disponivel, evitando high/low de 5 dias."""
    clean_df = ticker_df.dropna(subset=["Close"]).copy()
    if clean_df.empty:
        return clean_df
    try:
        latest_date = clean_df.index[-1].date()
        session_df = clean_df[clean_df.index.date == latest_date]
        return session_df if not session_df.empty else clean_df.tail(1)
    except Exception:
        return clean_df.tail(1)


def _previous_session_close(ticker_df, latest_session_date):
    """Fechamento da sessao anterior ao ultimo candle, usado para variacao diaria."""
    clean_df = ticker_df.dropna(subset=["Close"]).copy()
    if clean_df.empty:
        return None
    try:
        previous_sessions = clean_df[clean_df.index.date < latest_session_date]
        if not previous_sessions.empty:
            return float(previous_sessions["Close"].iloc[-1])
    except Exception:
        pass

    try:
        daily_df = clean_df.resample("D").last().dropna(subset=["Close"])
        if len(daily_df) >= 2:
            return float(daily_df["Close"].iloc[-2])
    except Exception:
        pass
    return None


def _change_5m(ticker_df, last_price):
    clean_df = ticker_df.dropna(subset=["Close"]).copy()
    if clean_df.empty or len(clean_df) < 2:
        return None
    try:
        last_ts = clean_df.index[-1]
        target_ts = last_ts - pd.Timedelta(minutes=5)
        prior_df = clean_df[clean_df.index <= target_ts]
        if prior_df.empty:
            prior_price = float(clean_df["Close"].iloc[-2])
        else:
            prior_price = float(prior_df["Close"].iloc[-1])
        if prior_price <= 0:
            return None
        return ((float(last_price) - prior_price) / prior_price) * 100
    except Exception:
        return None


def fetch_global_data(save_file=True):
    # Estrutura de categorias e nomes amigáveis
    categories_config = {
        "📊 ÍNDICES": {
            "IBOV": "^BVSP",
            "S&P 500": "^GSPC",
            "NASDAQ": "^IXIC",
            "DOW JONES": "^DJI",
            "RUSSELL 2000": "^RUT",
            "NIKKEI 225": "^N225",
            "EURO STOXX 50": "^STOXX50E",
            "DAX": "^GDAXI",
            "FTSE 100": "^FTSE",
            "VIX": "^VIX"
        },
        "💱 MOEDAS / FOREX": {
            "DXY (Dólar Index)": "DX-Y.NYB",
            "USDBRL (Comercial)": "BRL=X",
            "6L (Real CME)": "6L=F",
            "EURUSD": "EURUSD=X",
            "GBPUSD": "GBPUSD=X",
            "USDJPY": "JPY=X",
            "AUDUSD": "AUDUSD=X",
            "USDCAD": "CAD=X",
            "USDCHF": "CHF=X"
        },
        "🇺🇸 TREASURIES (YIELDS)": {
            "US 02Y (Yield)": "FRED:DGS2",
            "US 10Y (Yield)": "^TNX",
            "US 30Y (Yield)": "^TYX",
            "US 05Y (Yield)": "^FVX",
            "US 03M (Yield)": "^IRX"
        },
        "🌏 EMERGENTES & BRASIL": {
            "EEM (Emerging Markets)": "EEM",
            "EMB (EM Bonds)": "EMB",
            "EWZ (Brazil ETF)": "EWZ",
            "ILF (Latin America)": "ILF",
            "PETR4 (ADR)": "PBR",
            "VALE (ADR)": "VALE",
            "ITUB (ADR)": "ITUB",
            "BBD (ADR)": "BBD"
        },
        "🇺🇸 ETFs SETORIAIS": {
            "SPY (S&P 500)": "SPY",
            "XOP (Oil & Gas)": "XOP",
            "XLE (Energy)": "XLE",
            "XLK (Tech)": "XLK",
            "XLP (Staples)": "XLP",
            "XLB (Materials)": "XLB",
            "XLI (Industrials)": "XLI",
            "XLV (Health)": "XLV",
            "XLRE (Real Estate)": "XLRE",
            "XBI (Biotech)": "XBI",
            "XLY (Consumer)": "XLY",
            "XLC (Comm)": "XLC"
        },
        "🛢️ COMMODITIES & CRIPTO": {
            "BRENT OIL": "BZ=F",
            "WTI OIL": "CL=F",
            "NATURAL GAS": "NG=F",
            "COPPER": "HG=F",
            "GOLD": "GC=F",
            "SILVER": "SI=F",
            "PLATINUM": "PL=F",
            "PALLADIUM": "PA=F",
            "BITCOIN": "BTC-USD",
            "ETHEREUM": "ETH-USD",
            "SOLANA": "SOL-USD"
        }
    }
    
    # 1. Coleta todos os tickers únicos
    all_tickers = []
    for cat in categories_config.values():
        all_tickers.extend([ticker for ticker in cat.values() if not str(ticker).startswith("FRED:")])
    all_tickers = list(set(all_tickers))
    
    print(f"[*] Buscando dados para {len(all_tickers)} ativos via yfinance...")
    
    # 2. Busca em mini-lotes com retentativa para reduzir rate limit no Streamlit Cloud
    data = _download_market_batches(all_tickers, batch_size=5)

    if data is None or data.empty:
        print("[!] Yahoo Finance retornou vazio. Tentando fallbacks por ativo.")
        data = None

    results = {
        "metadata": {
            "last_updated": datetime.now().strftime("%H:%M:%S"),
            "full_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "quote_router": "freshest_source",
            "sources": {},
        },
        "categories": {}
    }
    
    # 3. Processa os dados para cada categoria
    valid_data_count = 0
    for cat_name, symbols_map in categories_config.items():
        cat_results = []
        for name, ticker_symbol in symbols_map.items():
            try:
                if data is None:
                    ticker_df = None
                elif isinstance(data.columns, pd.MultiIndex):
                    if ticker_symbol not in set(data.columns.get_level_values(0)):
                        ticker_df = None
                    else:
                        ticker_df = data[ticker_symbol]
                elif ticker_symbol in data.columns:
                    ticker_df = data
                else:
                    ticker_df = None

                candidates = _quote_candidates(name, ticker_symbol, ticker_df)
                selected = _select_best_candidate(candidates)
                if not selected:
                    continue

                source = str(selected.get("source") or "unknown")
                results["metadata"]["sources"][source] = results["metadata"]["sources"].get(source, 0) + 1
                cat_results.append(selected)
                valid_data_count += 1
            except Exception as e:
                print(f"[!] Erro ao processar {name} ({ticker_symbol}): {e}")
        
        results["categories"][cat_name] = cat_results
            
    # Só salva se tivermos dados mínimos (ex: pelo menos 5 ativos válidos)
    if valid_data_count > 5:
        if save_file:
            with open("mercados_globais.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False)
        print(f"[+] Sucesso: {valid_data_count} ativos atualizados.")
        return results
    else:
        print("[!] Erro: Poucos dados válidos recebidos. Abortando salvamento para proteger dados antigos.")
        return None


if __name__ == "__main__":
    fetch_global_data()
