# Diretriz: Geração Automatizada do Morning Call

## Objetivo
Gerar o relatório "Trading Strategy Morning Brief" (ou Morning Call Manus Capital) de forma totalmente automatizada, coletando dados de cotações, calendário econômico e notícias de fontes confiáveis.

## Frequência
Diariamente, antes da abertura do mercado (aprox. 08:30 BRT).

## Fontes de Dados
1.  **Cotações (TradingView/YFinance)**:
    *   CFDs: IBOV, USDBRL, VIX, DAPK2035, DI1F2035, US2000, US10Y, US30Y.
    *   Pre-Market: EEM, EWZ, PBR, BBD, ITUB, VALE, BDORY.
    *   Commodities: Petróleo (WTI), Minério de Ferro, Ouro, Prata.
    *   EUA: Nasdaq (USATEC), S&P 500 (USA500).
    *   Criptos: BTC, ETH.
2.  **Calendário Econômico (Investing.com)**:
    *   Coletar: Horário, Evento, Relevância (Impacto) e valores (Atual/Previsto/Anterior).
3.  **Notícias (Multifontes)**:
    *   Fontes: Reuters, Investing, Bloomberg, Valor Econômico, CNN.
    *   Foco: Headlines macro, geopolítica e balanços corporativos.

## Ferramentas (Scripts de Execução)
*   `execution/fetch_quotes.py`: Coleta cotações via yfinance (Camada 3).
*   `execution/fetch_calendar.py`: Scrapes Investing.com para o calendário do dia (Camada 3).
*   `execution/fetch_news.py`: Coleta notícias via RSS/Scraping (Camada 3).
*   `execution/generate_morning_brief.py`: Gera o PDF (Camada 3).

## Fluxo de Trabalho (Orquestração - Camada 2)
1.  Executar a coleta de dados de cotações.
2.  Executar a coleta do calendário econômico.
3.  Executar a coleta de notícias.
4.  Processar os dados coletados (limpeza e formatação).
5.  Injetar os dados no script de geração de PDF.
6.  Gerar e abrir o PDF final.

## Tratamento de Erros
*   Se uma fonte de dados falhar, usar dados estáticos de "fallback" ou buscar via ferramenta de busca web.
*   Em caso de rate limit em APIs, aplicar backoff exponencial.

---
*Ultima atualização: 23/04/2026*
