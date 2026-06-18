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
- **Autenticacao:** O dashboard deve bloquear o acesso antes da sidebar quando nao houver usuario autenticado em `st.session_state`. Usar Supabase Auth para cadastro/login com email e senha; cadastro pede apenas email, senha e celular. Salvar celular em `user_metadata` e, quando a tabela `profiles` existir, fazer `upsert` com `user_id`, `email`, `phone`, `role`, `is_active` e `updated_at`. O primeiro usuario cadastrado recebe `role='admin'`; todos os proximos recebem `role='member'`. Se ja existir conta antes da regra e ainda nao houver admin em `profiles`, o proximo usuario autenticado deve ser promovido para `admin`. Limitar novos cadastros a 1000 usuarios quando a contagem em `profiles` ou Auth Admin estiver disponivel. Nunca salvar senha em tabela propria. O schema recomendado da tabela fica em `supabase_profiles.sql`.
- **Market Report intradiario:** Gerar no maximo 3 leituras por dia (`manha`, `tarde`, `noite`) e salvar em `market_report_daily.json`/`app_state.market_report_daily`. `market_report` continua apontando para o ultimo report para compatibilidade, mas a tela deve ler o historico do dia para preservar as analises ate virar a data local de Sao Paulo.
- **Market Report automatico:** Usar o workflow dedicado `.github/workflows/market_report.yml` para gerar/sincronizar automaticamente as leituras as 07:05, 13:05 e 19:05 de Sao Paulo. O workflow chama `execution/run_market_report_update.py`, que sincroniza `market_report` e `market_report_daily` no Supabase.
- **Market Report IA resiliente:** A geracao do Market Report deve tentar Gemini primeiro e OpenAI como fallback quando houver quota/modelo indisponivel. Antes de gerar, a tela deve preparar `mercados_globais.json` e `dados_mercado.json` a partir de Supabase/cache para o fallback local nao ficar com `---`. Se nenhuma chave externa (`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) existir no ambiente online, gerar um report local deterministico profissional com dados/noticias disponiveis e provider `Local/sem chave IA`, em vez de deixar a tela sem analise. O corpo do report deve renderizar Markdown real, nao texto escapado com `###`/`**` visiveis. A tela nao deve bloquear a geracao apenas porque o Supabase esta indisponivel; nesse caso, gerar e mostrar a analise na sessao, avisando que nao foi salva no historico online.
- **Calendario no Market Report:** A analise do Market Report deve incluir o calendario economico do dia, priorizando eventos `HIGH` e `MEDIUM` em horario de Brasilia. Na geracao do report, buscar primeiro o calendario ao vivo do Investing.com para obter Atual/Projecao/Anterior; se o Investing falhar no Streamlit Cloud, usar `app_state.calendario_economico` do Supabase antes do arquivo local `calendario_economico.json`. Quando o Market Report baixar o calendario ao vivo, sincronizar tambem `calendario_economico` no Supabase. Para cada evento relevante, destacar atual/projecao/anterior e uma interpretacao breve dos cenarios possiveis: acima da projecao, abaixo da projecao, hawkish/dovish ou impacto em juros, DXY, petroleo e indices.
- **Feed de noticias ao vivo:** Para baixa latencia sem travar o Streamlit Cloud, buscar Financial Juice RSS direto no Streamlit/bridge com `fast_mode=True`, `translate=False`, cache de tela em torno de 30s e `min_network_interval=30`. No dashboard, exibir manchetes/resumos originais em ingles e nao preencher `title_pt`/`summary_pt` no caminho critico. O Supabase deve ser usado como cache/backup, nao como unica fonte quando ja existir dado antigo.
- **Fontes externas do feed no Streamlit Cloud:** Nao chamar GDELT/Reuters diretamente no carregamento do Streamlit, porque essas fontes podem responder `429` e prender o app no spinner. O caminho critico do feed deve usar Supabase/cache + Financial Juice RSS direto; fontes extras ficam para rotinas externas ou cache ja persistido.
- **Historico do feed:** O feed de noticias nunca deve ficar vazio enquanto busca novos dados. Se a fonte ao vivo ainda estiver carregando ou falhar, exibir as ultimas 10 noticias do cache local/Supabase/session_state e atualizar a lista assim que chegarem manchetes novas.
- **Indicadores Globais:** A aba Terminal Global deve manter uma cesta ampla de ativos acompanhados via `execution/fetch_global_markets.py`, incluindo indices globais, principais pares de FX, treasuries, emergentes/Brasil, ETFs setoriais, commodities e cripto. Antes de subir alteracoes nessa cesta, testar `fetch_global_data(save_file=False)` para confirmar que o Yahoo Finance retorna dados suficientes sem sobrescrever cache antigo.
- **Layout dos Indicadores Globais:** Renderizar os indicadores como heatmap compacto de cards, com categorias laterais, preco em destaque, variacao percentual por cor e campos H/L quando disponiveis. Evitar voltar para tabela simples nessa secao do Terminal Global.
- **Graficos proprios:** A pagina `Graficos Avancados` pode complementar os widgets TradingView com um componente proprio em `lightweight_chart_component.py`, embutido via `st.components.v1.html`, usando Lightweight Charts v5 (`chart.addSeries(...)`), dados Binance REST/WebSocket para cripto e proxies yfinance pre-carregados para mercado americano/macro. Os tempos padrao devem ser `30s`, `1m`, `5m`, `h1`, `1d`, `1w` e `1month`. Para yfinance, usar 1m como base intraday, agregar localmente 5m/h1 e usar serie diaria para 1d/1w/1month; avisar que 30s usa a base de 1m por falta de granularidade. Manter os widgets TradingView existentes como fallback ate o modulo proprio estar completamente validado.
- **Fontes gratuitas no Lightweight:** O componente proprio de graficos nao deve usar Finnhub como fonte de candles; reservar a API Finnhub para outras solucoes futuras. Nos graficos, usar Binance para cripto, yfinance para proxies de mercado e `FRED_API_KEY` para series macro FRED. As chaves devem ser lidas apenas no backend Streamlit (`st.secrets` ou variaveis de ambiente), nunca expostas no JS. Se FRED for selecionado em timeframe intraday, ajustar automaticamente para `1d`, porque FRED entrega series macro diarias.
- **Painel operacional Lightweight:** O componente proprio deve manter crosshair com leitura OHLC/volume/variação/distancia da VWAP, linhas de abertura/maxima/minima/fechamento anterior/preco atual, VWAP diaria/semanal/mensal, bandas percentuais e por desvio, medias SMA/EMA configuraveis, volume relativo, Volume Profile da sessao com POC, VAH e VAL destacados, HV252 calculada com retornos logaritmicos de candles diarios e bandas intradiarias 1/1.5/2 sigma projetadas a partir do fechamento anterior, markers de sinais operacionais, alertas laterais, acoes de zoom/export/reload e preferencias em `localStorage`. Nao renderizar oscilador inferior para preservar area util do candle e reduzir custo de renderizacao.
- **REFS no Lightweight:** A camada `Refs` deve marcar maxima/minima do dia atual, dia anterior, semana anterior e mes anterior, com labels curtos no eixo (`DIA MAX`, `DIA ANT MAX`, `SEM ANT MAX`, `MES ANT MAX` etc.), cores diferentes por grupo e estilos de linha distintos para leitura rapida. Nao plotar abertura do dia nem fechamento anterior nessa camada.
- **Motor de sinais Lightweight:** Os markers do grafico proprio devem ser gerados por motor deterministico local, sem LLM e sem execucao de ordens. O motor ativo atual opera apenas sinais de reversao por regioes de volatilidade (`VOL_BUY`/`VOL_SELL`), aplica score minimo, cooldown, filtros configuraveis e retorna motivo curto com regiao, fonte, sigma e padrao de candle. A camada `Sinais` controla a exibicao dos markers, e o crosshair deve mostrar a explicacao do sinal quando houver marker no candle.
- **Filtros REV Lightweight obsoletos:** A regra antiga `REV_BUY`/`REV_SELL` por confluencia direta de VWAP/HV/GARCH foi substituida pelo motor de regioes de volatilidade. Nao usar RSI/IFR nem a logica antiga como criterio operacional.
- **Volume Profile e sinais:** `POC`, `VAH` e `VAL` devem permanecer apenas como leitura visual do Volume Profile. O motor de sinais REV/TREND nao deve usar `POC`, `VAH` ou `VAL` para regime, proximidade, stop ou alvo; usar referencias de dia, VWAP, swings recentes e bandas HV252 no lugar.
- **Motor de sinais por regioes de volatilidade:** O motor ativo deve usar exclusivamente regioes criadas a partir das `Bandas Vol` GARCH/HV252. Compra so pode ocorrer em regiao inferior com multiplicador minimo configuravel, candle tocando/varrendo a regiao, padrao de rejeicao comprador, volume ok quando habilitado, cooldown e score minimo. Venda so pode ocorrer em regiao superior com as mesmas confirmacoes espelhadas. Padroes validos: pin bar, engolfo, falso rompimento, fechamento de volta para dentro e impulso reversivo. A logica antiga de REV por VWAP/HV/GARCH direto fica obsoleta e nao deve ser usada como motor operacional.
- **Estrategia unica temporaria:** Enquanto a estrategia estiver em simplificacao, o grafico proprio deve operar somente o motor de reversao (`REV_BUY` e `REV_SELL`). `TREND_BUY` e `TREND_SELL` devem permanecer desativados, escondidos do painel e fora da lista de candidatos, mesmo que existam preferencias antigas no `localStorage`.
- **Grafico unico Lightweight:** A pagina `Graficos Avancados` deve renderizar apenas um componente Lightweight operacional enquanto houver somente uma estrategia ativa. Quando a estrategia TREND voltar, reavaliar se faz sentido separar novamente em dois graficos.
- **Ativos Lightweight Brasil/FX:** O grafico proprio em `Graficos Avancados` deve incluir ativos Brasil via `yfinance` (`.SA`, ETFs e `^BVSP`), `EURUSD` via `EURUSD=X` e referencias BCB gratuitas via SGS apenas para cambio BRL. Ativos BCB sao diarios e devem forcar timeframes `1d`, `1w` ou `1month`, sem WebSocket. Nao exibir Selic, CDI ou IPCA no seletor do Lightweight.
- **Ativos FRED Lightweight:** No seletor do grafico proprio, manter FRED apenas para `US10Y FRED` e `US30Y FRED`. Nao exibir `Fed Funds`, `CPI FRED` ou `Unemp FRED`.
- **Desvios da VWAP:** O toggle `Desvios` do grafico proprio deve usar multiplicadores de desvio padrao `1`, `2` e `3`, mantendo as bandas percentuais da VWAP em toggle separado.
- **Bandas percentuais VWAP:** O grafico proprio deve ter toggles independentes para bandas percentuais da VWAP diaria (`Bandas D`) e da VWAP semanal (`Bandas W`), usando 0.5%, 1%, 1.5% e 2% com paletas bem diferentes por horizonte. Nao desenhar bandas percentuais da VWAP mensal.
- **Bandas semanais por volatilidade:** O grafico proprio deve ter um toggle separado `Bandas W Vol` para bandas adaptativas da VWAP semanal. Calcular o desvio padrao da distancia `close - VWAP semanal` dentro da semana e plotar VWAP semanal +/- 1, 2 e 3 desvios. Essa camada deve ser independente das bandas percentuais semanais.
- **Coloracao de candles por volume:** Os candles do grafico proprio devem destacar participacao por RVOL sem alterar o motor de sinais: RVOL normal usa verde/vermelho discretos, RVOL >= 1.2 reforca a cor direcional, RVOL >= 1.5 usa cores fortes, e RVOL >= 2 usa destaque ambar para volume extremo.
- **Weis Wave Volume:** O grafico proprio deve ter uma camada visual `Weis Vol` que acumula volume por pernadas de alta/baixa usando uma reversao percentual minima. Plotar histograma inferior com volume acumulado da onda atual, verde para alta e vermelho para baixa, e mostrar no painel lateral a direcao, volume da onda atual e comparacao com a ultima onda da mesma direcao. Essa camada deve ser visual primeiro e nao alterar o motor REV sem validacao posterior.
- **TTS GARCH(1,1) + HV252 - Modelo Hull:** O grafico proprio deve ter uma camada `GARCH` baseada em GARCH(1,1) sem dependencias externas, com `omega=0.000001`, `alpha=0.08`, `beta=0.90` e validacao `alpha + beta < 1`. Por padrao, calcular o GARCH em base diaria usando `dailyCandles` e apenas projetar as bandas no grafico intraday; modo intraday pode existir apenas para comparacao. Plotar zonas horizontais lognormais/Hull em torno da referencia por 0, 0.5, 1, 1.5, 2, 2.5 e 3 sigma usando `referencia * exp(sigma * multiplicador)`, mostrar no painel volatilidade atual, timeframe do GARCH, preco de referencia, modo de referencia e distancia em sigma por log-retorno. A referencia deve poder usar fechamento anterior, abertura da sessao, VWAP, ultimo fechamento ou ajuste manual. Quando `Filtro GARCH` estiver ligado, o motor REV deve permitir compra apenas abaixo de `-minSigmaForSignal` e venda apenas acima de `+minSigmaForSignal`, com padrao `1.5`.
- **Bandas de Volatilidade:** O grafico proprio deve ter um indicador visual chamado `Bandas Vol`, separado do motor de sinais, que plota em uma unica camada a referencia central, bandas GARCH lognormais 0.5/1/1.5/2/3 sigma e bandas HV252 1/2/3 sigma. Essa camada substitui a plotagem visual separada de `GARCH` e `HV 252` para evitar duplicacao de linhas; o checkbox `Filtro GARCH` no painel de sinais continua controlando apenas a validacao do motor REV.
- **Traducao manual do feed:** O feed deve carregar em ingles por padrao. Se o usuario clicar em `Traduzir noticias`, traduzir apenas os cards visiveis no Streamlit, mantendo a busca de rede em `translate=False` para nao atrasar o carregamento inicial.
- **Traducao completa sob demanda:** Ao clicar em `Traduzir noticias`, traduzir todo o feed filtrado para portugues do Brasil usando `translate_text_google` e cache em `st.session_state`, nao apenas substituicoes heuristicas. O botao deve continuar sem afetar o carregamento inicial em ingles.
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
- **IA Macro TTS curta e intermercado:** No Terminal Global, a IA Macro TTS deve responder de forma curta e direta. A leitura deve combinar calendario Investing com `get_global_markets_data()` para avaliar correlacao intermercados, regime dominante, politica monetaria, inflacao, juros, DXY, petroleo e indices americanos. O texto deve evitar explicacoes longas e apresentar apenas surpresa/projecao, vies Risk-on/Risk-off, choque macro e principais efeitos.
- **Layout calendario Terminal Global:** Manter a area de analise IA Macro TTS lado a lado com o widget oficial do calendario Investing em desktop. A coluna esquerda deve concentrar proximos eventos, IA e historico; a direita deve exibir o iframe do Investing com altura suficiente para leitura.
- **Painel lateral de correlacao Terminal Global:** O Terminal Global deve dividir o corpo em conteudo principal e uma lateral direita compacta, renderizada apenas em `pagina_terminal_global()`. A lateral deve conter o painel de correlacao macro em TradingView com `USA500`, `TVC:GOLD`, `TVC:UKOIL`, `OTCB:US10Y`, `OTCB:US30Y` e `CAPITALCOM:DXY`, com GOLD logo abaixo do S&P 500, seletor de intervalo e comportamento sticky no desktop. Em telas menores, ocultar essa lateral para nao sobrepor graficos ou widgets.
- **Graficos Terminal Global:** A aba Terminal Global deve exibir quatro graficos TradingView em duas linhas, dois lado a lado em cada linha, todos com seletores independentes de ativo/intervalo, volume oculto, painel lateral de desenho habilitado e VWAP diaria/semanal/mensal.
- **Ativos dos graficos globais:** Os seletores do Terminal Global devem incluir `USATEC` (`ACTIVTRADES:USATEC`), `ETHUSDT` (`BINANCE:ETHUSDT`), `US10Y OTCB` (`OTCB:US10Y`) e `US30Y OTCB` (`OTCB:US30Y`).
- **Defaults dos graficos globais:** Os quatro graficos do Terminal Global devem abrir em `5 minutos`: grafico 1 `USA500`, grafico 2 `UKOIL`, grafico 3 `BRA50` e grafico 4 `BTCUSDT`.
- **Classificacao visual de noticias:** O Terminal Bloomberg deve classificar manchetes por impacto (`URGENTE`, `ALTO IMPACTO`, `IMPACTO MEDIO`, `BAIXO IMPACTO`), ordenar o feed priorizando maior impacto antes da recencia e destacar visualmente as noticias urgentes/alto impacto com cor, borda e badge.
- **NEWS compacta na sidebar:** A barra lateral deve ter uma aba `NEWS` ao lado de `MERCADOS` e `CALENDARIO`, usando o mesmo feed do Terminal Bloomberg via `load_bloomberg_news_feed`. Mostrar no maximo 10 manchetes compactas, em ingles por padrao, com horario, fonte, link e badge de impacto; nao criar novas rotas de rede alem do cache/Supabase/Financial Juice ja usados pelo feed principal. A secao deve ter botoes compactos `Atualizar`, `Traduzir`/`Ver EN`, `-` e `+`; atualizar limpa o cache do feed, traduzir converte somente as manchetes visiveis da sidebar para PT-BR, e `-`/`+` controlam apenas o zoom/fonte do feed NEWS.
- **Logo na sidebar:** A barra lateral deve exibir a logo `assets/trading_strategy_logo.png` acima da navegacao principal. Nao referenciar caminhos locais fora do repo, como `Downloads`, porque o Streamlit Cloud nao consegue acessar esses arquivos.
- **Relogio na sidebar:** A barra lateral deve exibir um relogio compacto logo abaixo da navegacao principal, com horario de Brasilia atualizado por segundo via componente HTML/JS, fonte grande e marcadores de abertura `09:00 Abertura BR`, `10:00 Abertura acoes BR` e `10:30 Abertura NY`, destacando proximo evento, evento em andamento e eventos ja passados.
- **Pagina inicial:** No primeiro acesso, o dashboard deve abrir no `Terminal Global` como pagina padrao da navegacao lateral.
- **Impacto do calendario Investing:** O impacto do evento economico deve seguir a escala oficial de touros do Investing (`bull1`, `bull2`, `bull3`). Um touro = baixo impacto, dois touros = impacto medio, tres touros = alto impacto. A IA deve ponderar a surpresa por essa escala: quanto mais touros, maior o efeito macro.
- **Horario do calendario Investing:** Usar `timeZone=12` nas chamadas e no widget do Investing para exibir os eventos no horario de Brasilia/Sao Paulo. `timeZone=8` deixava o widget em GMT-4 e atrasava a agenda em uma hora.
- **Performance Streamlit:** Fragmentos RTD que leem a mesma chave do Supabase devem compartilhar cache curto (`ttl=2`) em vez de consultar o banco a cada rerender. Fallbacks de `mercados_globais`, `calendario_economico` e `financial_juice_news` devem usar cache de 30s para evitar latencia e rate limit quando a fonte ao vivo falhar.
- **Boot do Streamlit Cloud:** No carregamento inicial, `get_global_markets_data()` e `get_calendar_data()` devem ler Supabase/cache primeiro. Nao chamar yfinance nem endpoint backend do Investing antes de renderizar a UI, pois qualquer timeout externo pode deixar o app preso no spinner.
