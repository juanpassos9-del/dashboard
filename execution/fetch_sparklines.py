"""
fetch_sparklines.py — Busca dados intraday para mini gráficos sparkline.
Parte da Camada 3 (Execução) do sistema.
"""

import yfinance as yf
import pandas as pd
import time
import warnings

warnings.filterwarnings("ignore")

SPARK_TICKERS = {
    "CL=F": "Petróleo", "GC=F": "Ouro", "^VIX": "VIX",
    "DX-Y.NYB": "DXY", "^GSPC": "S&P 500", "^RUT": "Russell 2000",
    "EWZ": "EWZ", "EEM": "EEM", "^TNX": "US10Y", "^TYX": "US30Y",
    "PBR": "PBR", "VALE": "VALE",
}

BATCH_SIZE = 6
BATCH_DELAY = 3.0


def fetch_sparkline_data(period="5d", interval="1h"):
    """
    Busca dados de preço para sparklines.
    Retorna dict {ticker: list_of_close_prices}.
    """
    tickers = list(SPARK_TICKERS.keys())
    results = {}

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        try:
            data = yf.download(
                batch,
                period=period,
                interval=interval,
                progress=False,
                threads=False,
            )
            if not data.empty:
                for t in batch:
                    try:
                        if len(batch) == 1:
                            close = data["Close"].dropna().tolist()
                        else:
                            if t in data.columns.get_level_values(0):
                                close = data[t]["Close"].dropna().tolist()
                            else:
                                close = data["Close"][t].dropna().tolist() if t in data["Close"].columns else []
                        if close and len(close) >= 3:
                            results[t] = [round(float(v), 4) for v in close]
                    except Exception:
                        pass
        except Exception as e:
            print(f"[WARN] Sparkline batch falhou: {e}")

        if i + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_DELAY)

    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("Buscando sparklines...")
    data = fetch_sparkline_data()
    for ticker, prices in data.items():
        name = SPARK_TICKERS.get(ticker, ticker)
        print(f"  {name}: {len(prices)} pontos | {prices[-1]:.2f}")
