import yfinance as yf
import json
import os

def fetch_global_data():
    categories = {
        "📊 ÍNDICES": {
            "IBOV": "^BVSP",
            "S&P 500": "^GSPC",
            "NASDAQ": "^IXIC",
            "DXY": "DX-Y.NYB",
            "VIX": "^VIX"
        },
        "🇺🇸 TREASURIES (YIELDS)": {
            "US 10Y (Yield)": "^TNX",
            "US 30Y (Yield)": "^TYX",
            "US 02Y (Yield)": "^IRX"
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
        "🇧🇷 ADRs BRASIL": {
            "EWZ (Brazil ETF)": "EWZ",
            "PETR4 (ADR)": "PBR",
            "VALE (ADR)": "VALE",
            "ITUB (ADR)": "ITUB"
        },
        "🛢️ COMMODITIES & CRIPTO": {
            "BRENT OIL": "BZ=F",
            "GOLD": "GC=F",
            "BITCOIN": "BTC-USD",
            "ETHEREUM": "ETH-USD"
        }
    }
    
    results = {}
    
    for cat_name, symbols in categories.items():
        cat_results = []
        for name, ticker_symbol in symbols.items():
            try:
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.history(period="5d")
                
                if len(info) >= 2:
                    last_price = info['Close'].iloc[-1]
                    prev_price = info['Close'].iloc[-2]
                    change = ((last_price - prev_price) / prev_price) * 100
                    
                    cat_results.append({
                        "name": name,
                        "symbol": ticker_symbol,
                        "price": round(last_price, 2),
                        "change": round(change, 2)
                    })
            except Exception as e:
                print(f"[!] Erro ao buscar {name}: {e}")
        
        results[cat_name] = cat_results
            
    with open("mercados_globais.json", "w") as f:
        json.dump(results, f)

if __name__ == "__main__":
    fetch_global_data()
