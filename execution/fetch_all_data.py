import os
import sys
import datetime
import pandas as pd
from fetch_quotes import fetch_all_quotes
from fetch_calendar import fetch_economic_calendar
from fetch_news import fetch_all_news, categorize_news
from generate_morning_brief import generate_report, make_sparkline, Paragraph, hex2col, RED, GREEN, SILVER

def run_automation():
    print("[1/4] Buscando cotações...")
    quotes = fetch_all_quotes()
    
    print("[2/4] Buscando calendário econômico...")
    calendar_df = fetch_economic_calendar()
    
    print("[3/4] Buscando notícias...")
    news_list = fetch_all_news(max_results=20)
    news_cats = categorize_news(news_list)
    
    # --- Formatação dos Ativos ---
    assets_formatted = {}
    for cat, items in quotes.items():
        table_rows = [["Ativo", "Preço", "Var %", "Sparkline", "Contexto / Análise Técnica"]]
        for name, data in items.items():
            if data["price"]:
                color = GREEN if data["change_pct"] >= 0 else RED
                # Simula sparkline (idealmente viria de dados históricos reais)
                # Para fins deste script, usamos dados sintéticos baseados na variação
                spark_data = [data["price"] * (1 - data["change_pct"]/100)] * 5 + [data["price"]] * 5
                
                table_rows.append([
                    name,
                    f"{data['price']:.2f}",
                    Paragraph(f"<font color='{color}'>{data['change_pct']:+.2f}%</font>"),
                    make_sparkline(spark_data),
                    "Monitoramento em tempo real."
                ])
        assets_formatted[cat] = table_rows

    # --- Formatação da Agenda ---
    agenda_formatted = [["Hora (BR)", "Evento", "País", "Impacto", "Atual / Prev"]]
    for _, row in calendar_df.iterrows():
        agenda_formatted.append([
            row["Horário"],
            row["Evento"][:40] + "..." if len(row["Evento"]) > 40 else row["Evento"],
            row["País"],
            row["Impacto"],
            f"{row['Atual']} / {row['Previsão']}"
        ])
    
    # --- Geração de Textos (Headlines e Panorama) ---
    top_news = news_list[:3]
    headlines = " | ".join([n["title"] for n in top_news])
    panorama = "O mercado opera com foco no fluxo de notícias global. "
    if "🛢️ Commodities" in news_cats:
        panorama += "Tensões no setor de energia mantêm commodities em alerta. "
    if "🏦 Pol. Monetária" in news_cats:
        panorama += "Expectativas sobre juros e falas de membros do Fed dominam o sentimento. "
    
    # --- Análise de Correlação ---
    corr_points = []
    cfd = quotes.get("CFD", {})
    eua = quotes.get("EUA", {})
    comm = quotes.get("COMMODITIES", {})
    
    vix_change = cfd.get("VIX", {}).get("change_pct", 0)
    dxy_change = cfd.get("DXY", {}).get("change_pct", 0) # Assumindo que DXY esteja em Moedas ou CFD
    us10y_change = cfd.get("US10Y", {}).get("change_pct", 0)
    sp500_change = eua.get("USA500", {}).get("change_pct", 0)
    nasdaq_change = eua.get("USATEC", {}).get("change_pct", 0)
    
    if vix_change and vix_change > 2 and sp500_change and sp500_change < 0:
        corr_points.append("O aumento do VIX confirma um regime de 'Risk-Off', com investidores buscando proteção frente à queda nos índices.")
    if us10y_change and us10y_change > 0.5 and nasdaq_change and nasdaq_change < 0:
        corr_points.append("A alta nas Yields de 10 anos pressiona o setor de tecnologia (Nasdaq), refletindo o ajuste de valuation por taxas de desconto maiores.")
    if dxy_change and dxy_change > 0.1 and comm.get("XAUUSD (Ouro)", {}).get("change_pct", 0) < 0:
        corr_points.append("O fortalecimento do DXY atua como vento contrário para o Ouro e demais commodities metálicas.")
    
    correlation_text = " ".join(corr_points) if corr_points else "Dinâmica de mercado mista, com ativos operando sem correlações claras nas últimas horas. Foco no fluxo pontual."

    # --- Notícias e Impactos por Ativo ---
    news_impacts = {}
    for cat_name, items in news_cats.items():
        if items:
            # Pega as 2 notícias mais recentes por categoria
            impact_texts = [f"{n['title']} ({n['source']})" for n in items[:2]]
            news_impacts[cat_name] = " | ".join(impact_texts)
    
    # Se não houver notícias em algumas categorias, preenche com placeholder informativo
    required_cats = ["📊 Inflação", "🏦 Juros / Treasuries", "🛢️ Petróleo", "✨ Ouro / Prata", "₿ Bitcoin / Ethereum", "🌍 Emergentes"]
    for rc in required_cats:
        if rc not in news_impacts:
            news_impacts[rc] = "Sem destaques significativos nas últimas horas. Monitoramento de fluxo ativo."

    radar_brasil = [
        {"label": "IBOVESPA", "text": "Acompanhando o humor global e o fluxo de capital estrangeiro."},
        {"label": "DÓLAR", "text": "Volatilidade em função do diferencial de juros e risco país."},
    ]
    
    # Pega mais notícias para o radar se houver
    if "🌍 Emergentes" in news_cats:
        for n in news_cats["🌍 Emergentes"][:2]:
            radar_brasil.append({"label": "NOTÍCIA BR", "text": n["title"]})

    print("[4/4] Gerando PDF...")
    output_name = f"MorningCallTTS_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
    
    generate_report(
        date_str=datetime.datetime.now().strftime("%d de %B de %Y"),
        output_filename=output_name,
        accent_color='#F5A623', # ORANGE
        title_day="MorningCallTTS",
        highlights=headlines,
        focus_text="Geopolítica, Macro Global e Brasil",
        panorama_text=panorama,
        assets_data=assets_formatted,
        agenda_data=agenda_formatted,
        correlation_text=correlation_text,
        news_impacts=news_impacts,
        radar_brasil_data=radar_brasil,
        strategy_text="Manter cautela operacional nas aberturas. Atenção aos horários da agenda econômica para evitar volatilidade excessiva."
    )
    
    print(f"\n[SUCESSO] Relatório gerado: {output_name}")
    return output_name

if __name__ == "__main__":
    # Garante que o diretório .tmp existe
    os.makedirs(".tmp", exist_ok=True)
    run_automation()
