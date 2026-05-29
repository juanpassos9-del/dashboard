import yfinance as yf
import pandas as pd
import json
import os
import time
from datetime import datetime


def fetch_global_data(save_file=True):
    # Estrutura de categorias e nomes amigáveis
    categories_config = {
        "📊 ÍNDICES": {
            "IBOV": "^BVSP",
            "S&P 500": "^GSPC",
            "NASDAQ": "^IXIC",
            "VIX": "^VIX"
        },
        "💱 MOEDAS / FOREX": {
            "DXY (Dólar Index)": "DX-Y.NYB",
            "USDBRL (Comercial)": "BRL=X",
            "6L (Real CME)": "6L=F"
        },
        "🇺🇸 TREASURIES (YIELDS)": {
            "US 10Y (Yield)": "^TNX",
            "US 30Y (Yield)": "^TYX",
            "US 02Y (Yield)": "^IRX"
        },
        "🌏 EMERGENTES & BRASIL": {
            "EEM (Emerging Markets)": "EEM",
            "EWZ (Brazil ETF)": "EWZ",
            "PETR4 (ADR)": "PBR",
            "VALE (ADR)": "VALE",
            "ITUB (ADR)": "ITUB"
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
            "GOLD": "GC=F",
            "SILVER": "SI=F",
            "BITCOIN": "BTC-USD",
            "ETHEREUM": "ETH-USD"
        }
    }
    
    # 1. Coleta todos os tickers únicos
    all_tickers = []
    for cat in categories_config.values():
        all_tickers.extend(cat.values())
    all_tickers = list(set(all_tickers))
    
    print(f"[*] Buscando dados para {len(all_tickers)} ativos via yfinance...")
    
    # 2. Busca em lote (batch) com retentativa
    data = None
    for attempt in range(3):
        try:
            data = yf.download(all_tickers, period="5d", interval="1m", prepost=True, group_by='ticker', progress=False, timeout=20)
            if not data.empty:
                break
        except Exception as e:
            print(f"[!] Tentativa {attempt+1} falhou: {e}")
            time.sleep(2)

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
                if ticker_symbol not in data.columns.levels[0] if isinstance(data.columns, pd.MultiIndex) else [ticker_symbol]:
                    continue
                    
                ticker_df = data[ticker_symbol]
                clean_df = ticker_df.dropna(subset=['Close'])
                if clean_df.empty:
                    continue
                
                last_price = clean_df['Close'].iloc[-1]
                
                daily_df = ticker_df.resample('D').last().dropna(subset=['Close'])
                if len(daily_df) >= 2:
                    prev_close = daily_df['Close'].iloc[-2]
                else:
                    prev_close = last_price
                
                change = ((last_price - prev_close) / prev_close) * 100
                
                cat_results.append({
                    "name": name,
                    "symbol": ticker_symbol,
                    "price": round(last_price, 2) if last_price > 10 else round(last_price, 4),
                    "change": round(change, 2)
                })
                valid_data_count += 1
            except Exception as e:
                print(f"[!] Erro ao processar {name} ({ticker_symbol}): {e}")
        
        results["categories"][cat_name] = cat_results
            
    # Só salva se tivermos dados mínimos (ex: pelo menos 5 ativos válidos)
    if valid_data_count > 5:
        if save_file:
            with open("mercados_globais.json", "w") as f:
                json.dump(results, f)
        print(f"[+] Sucesso: {valid_data_count} ativos atualizados.")
        return results
    else:
        print("[!] Erro: Poucos dados válidos recebidos. Abortando salvamento para proteger dados antigos.")
        return None


if __name__ == "__main__":
    fetch_global_data()
