"""
fetch_quotes.py — Busca cotações de mercado via yfinance.

Parte da Camada 3 (Execução) do sistema.
Retorna DataFrame com preço atual, variação %, e metadata dos ativos monitorados.

Aprendizado: yfinance tem rate limit agressivo. Solução: download em mini-lotes
de 5 tickers com delay de 2s entre lotes + retry com backoff.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings

warnings.filterwarnings("ignore")

# ============================================================
# Mapeamento de ativos: TradingView → yfinance
# ============================================================

ASSETS = {
    "CFD": {
        "IBOV": "^BVSP",
        "USDBRL": "BRL=X",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
        "DAPK2035": "DAPK2035.SA",
        "DI1F2035": "DI1F35.SA",
        "MOVE": "^MOVE", # Placeholder or search
        "US10Y": "^TNX",
        "US30Y": "^TYX",
    },
    "PRE MARKET": {
        "EEM": "EEM",
        "EWZ": "EWZ",
        "PBR": "PBR",
        "BBD": "BBD",
        "ITUB": "ITUB",
        "VALE": "VALE",
        "BDORY": "BDORY",
        "BR20": "BR20", # Placeholder
    },
    "COMMODITIES": {
        "FEF2! (Minerio)": "TIO=F",
        "CL1! (WTI)": "CL=F",
        "XAUUSD (Ouro)": "GC=F",
        "XAGUSD (Prata)": "SI=F",
    },
    "EUA": {
        "USATEC (Nasdaq)": "^IXIC",
        "USA500 (S&P)": "^GSPC",
    },
    "CRIPTOS": {
        "BTCUSDT": "BTC-USD",
        "ETHUSDT": "ETH-USD",
    },
}

# Configurações de rate limit
BATCH_SIZE = 5          # Tickers por lote
BATCH_DELAY = 3.0       # Segundos entre lotes
RETRY_ATTEMPTS = 2      # Tentativas por ticker individual
RETRY_DELAY = 5.0       # Segundos entre retries


def get_all_tickers():
    """Retorna dicionário flat {display_name: ticker}."""
    tickers = {}
    for category, assets in ASSETS.items():
        for name, ticker in assets.items():
            tickers[name] = ticker
    return tickers


def get_ticker_to_name():
    """Retorna mapeamento reverso {ticker: display_name}."""
    mapping = {}
    for category, assets in ASSETS.items():
        for name, ticker in assets.items():
            mapping[ticker] = name
    return mapping


def _download_batch(tickers_list):
    """
    Faz download de um lote pequeno de tickers.
    Retorna dict {ticker: {price, change, change_pct}} 
    """
    results = {}

    try:
        data = yf.download(
            tickers_list,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=False,  # threads=False para evitar rate limit
        )

        if data.empty:
            return results

        for ticker in tickers_list:
            try:
                if len(tickers_list) == 1:
                    close = data["Close"].dropna()
                else:
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    close = data[ticker]["Close"].dropna()

                if len(close) < 1:
                    continue

                current_price = float(close.iloc[-1])
                if len(close) >= 2:
                    prev_price = float(close.iloc[-2])
                    change = current_price - prev_price
                    change_pct = (change / prev_price) * 100
                else:
                    change = 0.0
                    change_pct = 0.0

                results[ticker] = {
                    "price": round(current_price, 4),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                }
            except Exception:
                continue

    except Exception as e:
        print(f"[WARN] Batch download falhou: {e}")

    return results


def _fetch_single_with_retry(ticker_symbol):
    """Busca cotação individual com retry."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="5d", interval="1d")

            if hist.empty or len(hist) < 1:
                return None

            current_price = float(hist["Close"].iloc[-1])
            if len(hist) >= 2:
                prev_price = float(hist["Close"].iloc[-2])
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
            else:
                change = 0.0
                change_pct = 0.0

            return {
                "price": round(current_price, 4),
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
            }
        except Exception as e:
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"[WARN] Falha definitiva {ticker_symbol}: {e}")
    return None


def fetch_all_quotes():
    """
    Busca todas as cotações em mini-lotes para evitar rate limit.
    Retorna dict estruturado por categoria.
    """
    # 1. Coleta todos os tickers
    all_tickers = []
    for category, assets in ASSETS.items():
        for name, ticker in assets.items():
            all_tickers.append(ticker)

    # 2. Download em mini-lotes
    all_data = {}
    for i in range(0, len(all_tickers), BATCH_SIZE):
        batch = all_tickers[i:i + BATCH_SIZE]
        batch_label = ", ".join(batch)
        print(f"[INFO] Buscando lote {i // BATCH_SIZE + 1}: {batch_label}")

        batch_results = _download_batch(batch)
        all_data.update(batch_results)

        # Delay entre lotes (exceto no último)
        if i + BATCH_SIZE < len(all_tickers):
            time.sleep(BATCH_DELAY)

    # 3. Tenta buscar individualmente os que falharam
    missing = [t for t in all_tickers if t not in all_data]
    if missing:
        print(f"[INFO] Buscando {len(missing)} tickers faltantes individualmente...")
        time.sleep(BATCH_DELAY)
        for ticker in missing:
            quote = _fetch_single_with_retry(ticker)
            if quote:
                all_data[ticker] = quote
            time.sleep(1.0)

    # 4. Estrutura resultado por categoria
    results = {}
    for category, assets in ASSETS.items():
        results[category] = {}
        for name, ticker in assets.items():
            if ticker in all_data:
                results[category][name] = {**all_data[ticker], "ticker": ticker}
            else:
                results[category][name] = {
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "ticker": ticker,
                }

    return results


def get_quotes_summary(results):
    """Retorna resumo das cotações para log."""
    lines = []
    for category, assets in results.items():
        lines.append(f"\n=== {category} ===")

        for name, data in assets.items():
            if data["price"] is not None:
                arrow = "+" if data["change_pct"] >= 0 else "-"
                lines.append(f"  {name}: {data['price']:.4f} {arrow} {data['change_pct']:+.2f}%")
            else:
                lines.append(f"  {name}: N/A")
    return "\n".join(lines)


# ============================================================
# Teste standalone
# ============================================================
if __name__ == "__main__":
    print("Buscando cotações...\n")
    quotes = fetch_all_quotes()
    print(get_quotes_summary(quotes))
    print(f"\nÚltima atualização: {datetime.now().strftime('%H:%M:%S')}")
