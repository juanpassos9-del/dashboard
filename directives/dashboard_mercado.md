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
- **Market Report intradiario:** Gerar no maximo 3 leituras por dia (`manha`, `tarde`, `noite`) e salvar em `market_report_daily.json`/`app_state.market_report_daily`. `market_report` continua apontando para o ultimo report para compatibilidade, mas a tela deve ler o historico do dia para preservar as analises ate virar a data local de Sao Paulo.
- **Market Report automatico:** Usar o workflow dedicado `.github/workflows/market_report.yml` para gerar/sincronizar automaticamente as leituras as 07:05, 13:05 e 19:05 de Sao Paulo. O workflow chama `execution/run_market_report_update.py`, que sincroniza `market_report` e `market_report_daily` no Supabase.
- **Feed de noticias ao vivo:** Para baixa latencia, buscar Financial Juice RSS direto no Streamlit/bridge com `fast_mode=True` e `min_network_interval=5`. Nao bloquear manchetes novas em traducao IA; exibir primeiro com traducao heuristica/cache e deixar normalizacoes mais pesadas fora do caminho critico. O Supabase deve ser usado como cache/backup, nao como unica fonte quando ja existir dado antigo.
- **yfinance rate limit:** Downloads em batch de 20+ tickers causam `YFRateLimitError`. Solução: mini-lotes de 5 tickers, delay 3s entre lotes, `threads=False`, retry individual com backoff 5s.
- **Windows cp1252:** Console do Windows não suporta emojis Unicode (▲▼🔴🟡🟢). Usar caracteres ASCII no console, emojis só no Streamlit (UTF-8).
- **DI Futuro B3:** Contratos DI1F26/DI1F27 não estão disponíveis no yfinance. Precisa de scraping direto da B3 ou API especializada.
- **Investing.com:** Scraping do calendário econômico pode falhar (403/CloudFlare). Fallback estático por dia da semana implementado.
- **Cotações globais no Streamlit Cloud:** O painel deve buscar `mercados_globais` direto via `execution/fetch_global_markets.py` com cache curto no app e usar Supabase apenas como fallback. Nao depender exclusivamente do `dashboard_bridge.py`, porque ele roda localmente e, se estiver offline, deixa os dados congelados no horario do ultimo sync.
- **Calendario economico com Atual:** O endpoint Faireconomy/ForexFactory (`ff_calendar_thisweek.json`) normalmente nao entrega o campo `actual`; tentar Investing.com primeiro com cache curto e timeout controlado para `Atual/Projecao/Anterior`, mantendo Supabase/Faireconomy como fallback quando houver bloqueio/rate limit. Nunca deixar falha do Investing derrubar a renderizacao.
- **IA Macro TTS do calendario:** A interpretacao do calendario deve ser deterministica e local durante a renderizacao. Nao chamar LLM/API externa no Streamlit para esse card. Usar `execution/macro_calendar_ai.py` para normalizar evento, detectar `actual`, calcular surpresa, classificar choque macro e gerar Score Risk/viés operacional.
- **Investing Brasil para calendario ao vivo:** Para o Terminal Global, usar `br.investing.com/economic-calendar/Service/getCalendarFilteredData` com `Session`, GET inicial em `/economic-calendar/`, cookies e `timeZone=8` antes do fallback `www.investing.com`. Essa rota entrega os campos `Atual/Projecao/Anterior` iguais ao widget visual, enquanto o iframe oficial continua servindo apenas como conferencia visual e nao deve ser tratado como fonte legivel pelo backend.
- **Numeros BR no calendario:** Valores do Investing Brasil podem vir com virgula decimal (`55,1`, `0,4%`). O parser da IA deve converter virgula decimal corretamente antes de calcular surpresa; quando nao houver consenso, usar o valor anterior como benchmark secundario e marcar a surpresa como `vs anterior`.
- **Score Macro TTS:** O score Risk-on/Risk-off deve combinar surpresa do dado, categoria do indicador, regime dominante e confirmacao intermercado. Inflação/salarios acima pesam risk-off; inflação abaixo pesa risk-on. Atividade/emprego fortes pesam risk-on em regime neutro/recessivo, mas podem pesar hawkish/risk-off em regime de inflação dominante. A confirmação deve olhar US10Y, DXY, VIX, S&P, Nasdaq, EWZ, USD/BRL, Bitcoin e energia, mantendo o score final entre -100 e +100.
- **Modo Investing-only no Terminal Global:** Quando o usuário pedir análises exclusivamente com dados do Investing, chamar `interpret_event(event, None)` e filtrar histórico para `source == "Investing.com"`. Nesse modo, nao usar `get_global_markets_data()`, Supabase/Faireconomy ou qualquer confirmação intermercado na IA; o texto deve deixar claro que o score vem apenas da surpresa do calendário Investing.
- **Leitura de projeção:** Se o evento Investing ainda nao tiver `Atual`, mas tiver `Projecao` e `Anterior`, a IA deve gerar status `Projecao analisada`, comparando `Projecao vs Anterior`. Essa leitura é pre-evento, deve ter peso menor que um dado divulgado e deixar claro que a entrada operacional depende da confirmação do campo `Atual`.
- **Visual da IA sem placar:** Na tela do Terminal Global, nao exibir numero/placar do score da IA. Mostrar de forma textual se houve surpresa, qual foi o choque macro e qual efeito esperado (`Risk-on`, `Risk-off` ou `Neutro`). O score pode existir internamente apenas para classificar o efeito.
- **Foco macro da IA do calendario:** A leitura da IA do calendario nao deve citar WIN nem gerar vies operacional para mini indice. Focar o impacto em juros, inflacao, DXY, petroleo e indices americanos (S&P 500, Nasdaq e Dow Jones).
- **Classificacao visual de noticias:** O Terminal Bloomberg deve classificar manchetes por impacto (`URGENTE`, `ALTO IMPACTO`, `IMPACTO MEDIO`, `BAIXO IMPACTO`), ordenar o feed priorizando maior impacto antes da recencia e destacar visualmente as noticias urgentes/alto impacto com cor, borda e badge.
