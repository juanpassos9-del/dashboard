# Dashboard de Mercado Intermercado — Diretiva

## Objetivo
Dashboard em Python (Streamlit) que exibe cotações quasi-tempo-real de ativos de múltiplas classes, correlações intermercados com interpretação automática, notícias relevantes e calendário econômico do dia.

## Fontes de Dados

| Tipo | Fonte | Lib |
|---|---|---|
| Cotações | Yahoo Finance | `yfinance` |
| Notícias | RSS Feeds (CNBC, Reuters, MarketWatch) | `feedparser` |
| Calendário Econômico | Investing.com | `requests` + `beautifulsoup4` |

## Ativos Monitorados

### Commodities
- `CL=F` — Petróleo WTI
- `GC=F` — Ouro
- `^VIX` — VIX

### Moedas
- `6J=F` — Iene Japonês Fut.
- `6L=F` — Real Brasileiro Fut.
- `6M=F` — Peso Mexicano Fut.
- `6E=F` — Euro Fut.
- `DX-Y.NYB` — Índice Dólar (DXY)

### Global
- `^GSPC` — S&P 500
- `^RUT` — Russell 2000
- `EWZ` — ETF Brasil
- `EEM` — ETF Emergentes

### Treasuries
- `ZN=F` — T-Note 10Y Fut.
- `^TNX` — Yield 10 Anos
- `^TYX` — Yield 30 Anos

### ADR Brasil
- `PBR` — Petrobras
- `VALE` — Vale
- `BBD` — Bradesco
- `ITUB` — Itaú
- `BDORY` — Banco do Brasil

## Fluxo de Execução

1. `execution/fetch_quotes.py` busca cotações via yfinance
2. `execution/calc_correlations.py` calcula correlações de 30 dias
3. `execution/fetch_news.py` busca notícias via RSS
4. `execution/fetch_calendar.py` busca calendário econômico
5. `app.py` orquestra tudo via Streamlit, atualiza a cada 60s

## Edge Cases
- **Rate limiting yfinance:** cache de 60s para evitar bloqueio
- **Ativo indisponível:** exibir "N/A" sem quebrar o dashboard
- **Fora do horário de mercado:** exibir último preço de fechamento
- **RSS sem resultados:** exibir mensagem "Sem notícias recentes"
- **Calendário vazio:** exibir "Sem eventos hoje"

## Aprendizados
- **yfinance rate limit:** Downloads em batch de 20+ tickers causam `YFRateLimitError`. Solução: mini-lotes de 5 tickers, delay 3s entre lotes, `threads=False`, retry individual com backoff 5s.
- **Windows cp1252:** Console do Windows não suporta emojis Unicode (▲▼🔴🟡🟢). Usar caracteres ASCII no console, emojis só no Streamlit (UTF-8).
- **DI Futuro B3:** Contratos DI1F26/DI1F27 não estão disponíveis no yfinance. Precisa de scraping direto da B3 ou API especializada.
- **Investing.com:** Scraping do calendário econômico pode falhar (403/CloudFlare). Fallback estático por dia da semana implementado.
