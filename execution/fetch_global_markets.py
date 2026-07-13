import yfinance as yf
import pandas as pd
import json
import os
import time
from datetime import datetime


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
        all_tickers.extend(cat.values())
    all_tickers = list(set(all_tickers))
    
    print(f"[*] Buscando dados para {len(all_tickers)} ativos via yfinance...")
    
    # 2. Busca em mini-lotes com retentativa para reduzir rate limit no Streamlit Cloud
    data = _download_market_batches(all_tickers, batch_size=5)

    if data is None or data.empty:
        print("[!] Erro crítico: Não foi possível baixar dados do Yahoo Finance.")
        return None

    results = {
        "metadata": {
            "last_updated": datetime.now().strftime("%H:%M:%S"),
            "full_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "categories": {}
    }
    
    # 3. Processa os dados para cada categoria
    valid_data_count = 0
    for cat_name, symbols_map in categories_config.items():
        cat_results = []
        for name, ticker_symbol in symbols_map.items():
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker_symbol not in set(data.columns.get_level_values(0)):
                        continue
                    ticker_df = data[ticker_symbol]
                elif ticker_symbol in data.columns:
                    ticker_df = data
                else:
                    continue

                clean_df = ticker_df.dropna(subset=['Close'])
                if clean_df.empty:
                    continue
                
                session_df = _latest_session_frame(ticker_df)
                last_price = float(clean_df['Close'].iloc[-1])
                high_price = float(session_df['High'].max()) if 'High' in session_df.columns and not session_df.empty else last_price
                low_price = float(session_df['Low'].min()) if 'Low' in session_df.columns and not session_df.empty else last_price

                latest_session_date = clean_df.index[-1].date()
                prev_close = _previous_session_close(ticker_df, latest_session_date)
                if not prev_close or prev_close <= 0:
                    prev_close = last_price

                change = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0.0
                change_5m = _change_5m(ticker_df, last_price)
                
                cat_results.append({
                    "name": name,
                    "symbol": ticker_symbol,
                    "price": float(round(last_price, 2) if last_price > 10 else round(last_price, 4)),
                    "high": float(round(high_price, 2) if high_price > 10 else round(high_price, 4)),
                    "low": float(round(low_price, 2) if low_price > 10 else round(low_price, 4)),
                    "change": float(round(change, 2)),
                    "change_5m": float(round(change_5m, 2)) if change_5m is not None else None,
                    "prev_close": float(round(prev_close, 2) if prev_close > 10 else round(prev_close, 4)),
                })
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
