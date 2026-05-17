import yfinance as yf
import pandas as pd

def test_pre_market(symbol):
    print(f"[*] Testando {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # Tenta pegar o último preço do dia atual incluindo pré-mercado
    hist = ticker.history(period="1d", interval="1m", prepost=True)
    
    if not hist.empty:
        last_price = hist['Close'].iloc[-1]
        last_time = hist.index[-1]
        print(f"    - Último Preço (Hist 1m prepost=True): {last_price} as {last_time}")
    else:
        print("    - Nenhum dado de 1m hoje.")

    # Também checa o ticker.info (mais lento mas às vezes tem o campo específico)
    # pre_price = ticker.info.get('preMarketPrice')
    # print(f"    - PreMarketPrice (info): {pre_price}")

if __name__ == "__main__":
    test_pre_market("PBR")  # Petrobras ADR
    test_pre_market("EWZ")  # Brazil ETF
    test_pre_market("EEM")  # Emerging Markets ETF
