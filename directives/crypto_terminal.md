# TTS Crypto Terminal - Diretiva

## Objetivo
Adicionar ao dashboard atual uma pagina `Crypto Terminal` com leitura operacional do mercado cripto usando APIs gratuitas, cache local e motor deterministico de regime. O modulo deve complementar o dashboard Streamlit existente, sem migrar para outra stack nesta fase.

## Fontes da Fase 1

| Fonte | Dados | Chave | Frequencia | Cache | Fallback |
|---|---|---:|---:|---:|---|
| Binance Public API | ticker 24h, klines, funding, open interest | Nao | intraday | 30s-5min | ultimo `.tmp/crypto_binance.json` |
| CoinGecko Public API | market cap, dominance aproximada, rankings | Nao | agregado | 10min | ultimo `.tmp/crypto_coingecko.json` |
| Alternative.me | Fear & Greed atual/historico | Nao | diario | 60min | ultimo `.tmp/crypto_fear_greed.json` |
| DefiLlama | TVL, stablecoins, protocolos/chains | Nao | agregado | 15min | ultimo `.tmp/crypto_defillama.json` |
| BGeometrics | Snapshot on-chain BTC, MVRV e MVRV Z-Score | Sim (`BGEOMETRICS_API_KEY`) | diario/ciclo | 6h | ultimo `.tmp/crypto_bgeometrics.json` |

## Regras
- Nao usar dados simulados sem rotulo `DEMO`.
- Nunca expor chave de API no frontend.
- Nunca pedir seed phrase, chave privada ou assinatura de transacao.
- Todo provider deve retornar `source`, `status`, `updated_at`, `latency_ms`, `data`, `warnings`.
- Se a API falhar, usar ultimo cache valido e marcar status `stale`.
- Registrar saude das fontes via `execution/source_health.py`.
- UTC internamente; interface em portugues do Brasil.

## Fase 1 Entregavel
- Providers em `execution/crypto_*.py`.
- Motor `execution/crypto_regime.py`.
- Pagina `Crypto Terminal` no Streamlit.
- Overview com majors, regime, scores, alertas visuais e saude das fontes.
- Sem alertas Telegram, Wallet Watch, ETF Flows ou execucao de ordens nesta fase.

## Fase 2 Entregavel
- Motor `execution/crypto_signals.py` com ranking operacional local.
- Ranking de lideres de risco e ativos mais defensivos/fracos.
- Alertas deterministas de funding esticado, proximidade de maxima/minima de 24h e volatilidade realizada.
- Mini graficos intraday dos principais pares usando candles Binance e Lightweight Charts.
- O ranking usa apenas dados publicos/cacheados ja carregados na Fase 1.
- Se Binance vier vazia no ambiente online, ranking e mini graficos usam CoinGecko com sparkline como fallback rotulado.
- Continua sem execucao de ordens, sem carteira conectada e sem chaves privadas.

## Fase 3 Entregavel
- Regime por subclasse: Majors, L1/L2, DeFi/Infra, Memes/Beta, Pagamentos, Altcoins e Stablecoins quando houver dados.
- Mapa de rotacao com classe lider, classe mais fraca, score medio, variacao 24h, tendencia e volatilidade realizada.
- Leitura IA local curta e deterministica para interpretar se o fluxo esta em Majors, Altcoins ou defensivo.
- Rankings operacionais passam a exibir a subclasse do ativo para facilitar leitura de beta e concentracao de risco.

## Fase 4 Entregavel
- Provider `execution/crypto_bgeometrics.py` para snapshot on-chain do Bitcoin via BGeometrics.
- Card `Bitcoin On-chain` no Crypto Terminal com MVRV, MVRV Z-Score, data da leitura e zona de ciclo.
- Grafico historico do MVRV Z-Score, com linhas de referencia 0, 2, 4 e 7 para leitura de acumulacao/aquecimento/euforia.
- O historico tenta primeiro a API BGeometrics e, se houver limite/erro, usa o grafico publico da BGeometrics como fallback cacheado.
- Motor de regime usa MVRV Z-Score como sinal de ciclo:
  - abaixo de 0: acumulacao;
  - 0 a 2: saudavel;
  - 2 a 4: neutro/aquecendo;
  - 4 a 7: risco de ciclo;
  - acima de 7: euforia.
- A chave nunca deve ser commitada. Usar `.env` local ou secret `BGEOMETRICS_API_KEY` no ambiente online.
- Por limite de plano gratuito, manter cache de 6 horas e usar cache stale se a API falhar.

## Fase 5 Entregavel
- Expandir o snapshot BGeometrics no Crypto Terminal sem aumentar chamadas externas.
- Exibir painel `Regime on-chain BTC` com leitura deterministica de ciclo.
- Exibir heatmap on-chain com MVRV Z-Score, MVRV, Mayer Multiple, Puell Multiple, AVIV, Fear & Greed, enderecos ativos e hashrate.
- O motor de regime deve usar Mayer, Puell e AVIV como confirmadores de valuation/ciclo, mantendo MVRV Z-Score como sinal principal.
- Métricas adicionais da BGeometrics como CDD, SOPR, NVT, Reserve Risk e RHODL podem ser normalizadas no provider, mas so devem aparecer na interface quando houver dado confiavel no snapshot/cache.
- Manter cache longo e nao criar novas chamadas historicas sem necessidade, para respeitar o plano gratuito.

## Motor de Regime
Classificar em:
- `Risk-on forte`
- `Risk-on moderado`
- `Neutro`
- `Risk-off moderado`
- `Risk-off forte`
- `Desalavancagem`
- `Capitulacao`
- `Euforia`

Variaveis iniciais:
- tendencia BTC e ETH
- ETH/BTC
- breadth das moedas acompanhadas
- volume spot
- funding BTC/ETH
- open interest BTC/ETH
- Fear & Greed
- TVL DeFi
- market cap/stablecoin dominance quando disponivel
- MVRV / MVRV Z-Score do Bitcoin via BGeometrics quando configurado

O resultado deve mostrar score, confianca, drivers positivos, drivers negativos, alertas e dados ausentes.
