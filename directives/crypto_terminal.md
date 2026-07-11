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

O resultado deve mostrar score, confianca, drivers positivos, drivers negativos, alertas e dados ausentes.
