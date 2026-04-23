import io
import os
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage, Flowable
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Paleta de cores oficial
NAVY       = '#151D2E'
NAVY_MID   = '#1E2A40'
NAVY_LIGHT = '#253047'
SILVER     = '#B0B8C8'
SILVER_LT  = '#D4DAE6'
WHITE      = '#FFFFFF'
GREEN      = '#2ECC8F'
RED        = '#E05252'
GOLD       = '#C9A84C'
ORANGE     = '#F5A623'
DEEP_RED   = '#8B0000'

def hex2col(hex_str):
    return colors.HexColor(hex_str)

def vc(v):
    s = str(v)
    return hex2col(GREEN) if s.startswith('+') else hex2col(RED) if s.startswith('-') else hex2col(SILVER)

def make_sparkline(prices, w_mm=30, h_mm=9):
    """Gera um sparkline e retorna um Image do ReportLab"""
    fig, ax = plt.subplots(figsize=(w_mm/25.4, h_mm/25.4))
    fig.patch.set_facecolor(NAVY_LIGHT)
    ax.set_facecolor(NAVY_LIGHT)
    
    if prices[-1] >= prices[0]:
        color = GREEN
    else:
        color = RED
        
    ax.plot(prices, color=color, linewidth=1.5)
    ax.fill_between(range(len(prices)), prices, min(prices) - (max(prices)-min(prices))*0.1, color=color, alpha=0.2)
    ax.plot(len(prices)-1, prices[-1], marker='o', color=color, markersize=3)
    
    ax.set_axis_off()
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=300, facecolor=fig.get_facecolor(), bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    
    return RLImage(buf, width=w_mm*mm, height=h_mm*mm)

class MorningBriefCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self.accent_color = kwargs.pop('accent_color', GOLD)
        self.title_day = kwargs.pop('title_day', "Dia X do Conflito")
        self.date_str = kwargs.pop('date_str', datetime.datetime.now().strftime("%d/%m/%Y"))
        self.highlights = kwargs.pop('highlights', "Destaques não informados")
        super().__init__(*args, **kwargs)
        
    def _draw_header(self):
        # Faixa superior de acento
        self.setFillColor(hex2col(self.accent_color))
        self.rect(0, A4[1] - 2*mm, A4[0], 2*mm, stroke=0, fill=1)
        
        # Fundo do header
        self.setFillColor(hex2col(NAVY_MID))
        self.rect(0, A4[1] - 30*mm, A4[0], 28*mm, stroke=0, fill=1)
        
        # Faixa inferior de acento
        self.setFillColor(hex2col(self.accent_color))
        self.rect(0, A4[1] - 32*mm, A4[0], 2*mm, stroke=0, fill=1)
        
        # Logo (opcional)
        logo_path = "/home/claude/logo.png"
        if os.path.exists(logo_path):
            self.drawImage(logo_path, 10*mm, A4[1] - 25*mm, width=40*mm, height=15*mm, preserveAspectRatio=True, mask='auto')
        else:
            self.setFont("Helvetica-Bold", 16)
            self.setFillColor(hex2col(GOLD))
            self.drawString(10*mm, A4[1] - 15*mm, "MorningCallTTS")
            self.setFont("Helvetica", 8)
            self.setFillColor(hex2col(SILVER))
            self.drawString(10*mm, A4[1] - 20*mm, "MORNING BRIEF PRÉ-MERCADO")

        # Textos do Header - Direita
        self.setFont("Helvetica-Bold", 12)
        self.setFillColor(hex2col(WHITE))
        self.drawRightString(A4[0] - 10*mm, A4[1] - 15*mm, f"{self.title_day} | {self.date_str}")
        
        self.setFont("Helvetica", 9)
        self.setFillColor(hex2col(SILVER_LT))
        self.drawRightString(A4[0] - 10*mm, A4[1] - 22*mm, self.highlights)
        
        self.setFont("Helvetica", 7)
        self.setFillColor(hex2col(SILVER))
        self.drawRightString(A4[0] - 10*mm, A4[1] - 27*mm, f"Emitido em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    def _draw_footer(self):
        # Fundo do footer
        self.setFillColor(hex2col(NAVY_MID))
        self.rect(0, 0, A4[0], 15*mm, stroke=0, fill=1)
        
        # Faixa inferior GOLD
        self.setFillColor(hex2col(GOLD))
        self.rect(0, 0, A4[0], 0.5*mm, stroke=0, fill=1)
        
        # Texto footer
        self.setFont("Helvetica", 8)
        self.setFillColor(hex2col(SILVER))
        self.drawString(10*mm, 6*mm, "Trading Strategy © 2026. Distribuição Restrita.")
        self.drawRightString(A4[0] - 10*mm, 6*mm, f"Página {self.getPageNumber()}")

    def showPage(self):
        self._draw_header()
        self._draw_footer()
        super().showPage()

class BannerCard(Flowable):
    def __init__(self, title, text, border_color=ORANGE, bg_color=NAVY_MID, text_color=WHITE, width=190*mm):
        Flowable.__init__(self)
        self.title = title
        self.text = text
        self.border_color = hex2col(border_color)
        self.bg_color = hex2col(bg_color)
        self.text_color = hex2col(text_color)
        self.width = width
        
        styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle('BannerTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=self.border_color)
        self.text_style = ParagraphStyle('BannerText', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=self.text_color, leading=11)
        
        self.p_title = Paragraph(self.title, self.title_style)
        self.p_text = Paragraph(self.text, self.text_style)
        
    def wrap(self, availWidth, availHeight):
        self.w_title, self.h_title = self.p_title.wrap(self.width - 10*mm, availHeight)
        self.w_text, self.h_text = self.p_text.wrap(self.width - 10*mm, availHeight)
        self.height = self.h_title + self.h_text + 15*mm
        return self.width, self.height

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self.bg_color)
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(1)
        
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=1)
        
        self.p_title.drawOn(self.canv, 5*mm, self.height - self.h_title - 5*mm)
        self.p_text.drawOn(self.canv, 5*mm, 5*mm)
        
        self.canv.restoreState()

def create_table_style():
    return TableStyle([
        ('BACKGROUND', (0,0), (-1,0), hex2col(GOLD)),
        ('TEXTCOLOR', (0,0), (-1,0), hex2col(NAVY)),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), hex2col(NAVY_MID)),
        ('TEXTCOLOR', (0,1), (-1,-1), hex2col(WHITE)),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, hex2col('#2A3A55')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [hex2col(NAVY_MID), hex2col(NAVY_LIGHT)]),
    ])

def generate_report(date_str, output_filename, accent_color, title_day, highlights, focus_text, panorama_text, assets_data, agenda_data, correlation_text, news_impacts, radar_brasil_data, strategy_text):
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        rightMargin=10*mm,
        leftMargin=10*mm,
        topMargin=35*mm,
        bottomMargin=20*mm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('SectionTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, textColor=hex2col(GOLD), spaceAfter=10, spaceBefore=15)
    normal_style = ParagraphStyle('NormalText', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=hex2col(SILVER_LT), leading=12)
    
    elements = []
    
    # 1. Headline do Dia (Banner Principal)
    elements.append(BannerCard(
        title="HEADLINE DO DIA", 
        text=highlights,
        border_color=accent_color,
        bg_color=NAVY_MID
    ))
    elements.append(Spacer(1, 5*mm))

    # 2. Panorama Global e Sentimento
    elements.append(Paragraph("PANORAMA GLOBAL E SENTIMENTO", title_style))
    elements.append(Paragraph(panorama_text, normal_style))
    elements.append(Spacer(1, 10*mm))
    
    # 3. Ativos e Commodities (Abertura/Pré-Mercado)
    elements.append(Paragraph("ATIVOS E COMMODITIES (ABERTURA/PRÉ-MERCADO)", title_style))
    for table_title, data in assets_data.items():
        if len(data) > 1:
            t = Table(data, colWidths=[35*mm, 20*mm, 20*mm, 35*mm, 80*mm])
            t.setStyle(create_table_style())
            elements.append(t)
            elements.append(Spacer(1, 5*mm))
    
    elements.append(Spacer(1, 5*mm))
    
    # 4. Agenda Econômica e Eventos Chave
    elements.append(Paragraph("AGENDA ECONÔMICA E EVENTOS CHAVE", title_style))
    agenda_table = Table(agenda_data, colWidths=[20*mm, 45*mm, 25*mm, 25*mm, 75*mm])
    agenda_table.setStyle(create_table_style())
    elements.append(agenda_table)
    elements.append(Spacer(1, 10*mm))
    
    # 5. Análise de Correlação Intermercado
    elements.append(Paragraph("ANÁLISE DE CORRELAÇÃO INTERMERCADO", title_style))
    elements.append(BannerCard(
        title="DINÂMICA MACROECONÔMICA", 
        text=correlation_text,
        border_color=ORANGE,
        bg_color=NAVY_MID
    ))
    elements.append(Spacer(1, 10*mm))
    
    # 6. Notícias e Impactos por Ativo
    elements.append(Paragraph("NOTÍCIAS E IMPACTOS POR ATIVO", title_style))
    impact_text_full = ""
    for category, content in news_impacts.items():
        impact_text_full += f"<b>{category}:</b> {content}<br/>"
    
    elements.append(BannerCard(
        title="RESUMO DE IMPACTOS", 
        text=impact_text_full,
        border_color=GOLD,
        bg_color=NAVY_MID
    ))
    elements.append(Spacer(1, 10*mm))
    
    # 7. Radar de Ações e Brasil
    elements.append(Paragraph("RADAR DE AÇÕES E BRASIL", title_style))
    radar_text_full = ""
    for item in radar_brasil_data:
        radar_text_full += f"<b>{item['label']}:</b> {item['text']}<br/>"
    
    elements.append(BannerCard(
        title="MONITORAMENTO LOCAL", 
        text=radar_text_full,
        border_color=GOLD,
        bg_color=NAVY_MID
    ))
    elements.append(Spacer(1, 5*mm))
    
    # 6. Conclusão e Estratégia do Dia
    elements.append(Paragraph("CONCLUSÃO E ESTRATÉGIA DO DIA", title_style))
    elements.append(BannerCard(
        title="RECOMENDAÇÃO ESTRATÉGICA", 
        text=strategy_text,
        border_color=GOLD,
        bg_color=NAVY_MID
    ))
        
    # Build PDF
    def canvas_maker(*args, **kwargs):
        return MorningBriefCanvas(
            *args, 
            accent_color=accent_color, 
            title_day=title_day, 
            date_str=date_str, 
            highlights=f"FOCO: {focus_text}", 
            **kwargs
        )
        
    doc.build(elements, canvasmaker=canvas_maker)

if __name__ == "__main__":
    # Dados de exemplo adaptados ao modelo Manus
    date_str = "23 de abril de 2026"
    output_filename = f"TS_MorningBrief_{datetime.datetime.now().strftime('%d%b%Y').upper()}.pdf"
    
    spark_up = [10, 11, 12, 11.5, 12.5, 13, 14, 13.5, 14.5, 15]
    spark_down = [15, 14.5, 13.5, 14, 13, 12.5, 11.5, 12, 11, 10]
    
    highlights = "Mercados operam em cautela à espera de dados de emprego nos EUA e resultados das Big Techs; tensão no Oriente Médio segue no radar."
    focus_text = "Seguro-Desemprego nos EUA, Balanços de Big Techs e Geopolítica"
    panorama_text = "A quinta-feira inicia-se com os investidores em modo de espera. Após o rali de ontem em Wall Street, os futuros operam em leve queda em um movimento de realização técnica. O foco central do dia divide-se entre a economia real (seguro-desemprego) e o setor corporativo (Microsoft e Alphabet)."
    
    assets_data = {
        "Mercados Internacionais": [
            ["Ativo", "Preço", "Var %", "Sparkline", "Contexto / Análise Técnica"],
            ["S&P 500 Fut", "7.133", Paragraph(f"<font color='{RED}'>-0.52%</font>"), make_sparkline(spark_down), "Realização técnica; suporte em 7.100."],
            ["Nasdaq Fut", "26.839", Paragraph(f"<font color='{RED}'>-0.20%</font>"), make_sparkline(spark_down), "Sustentação pela expectativa de IA."],
            ["Bitcoin", "75.164", Paragraph(f"<font color='{RED}'>-0.50%</font>"), make_sparkline(spark_down), "Consolidação acima dos US$ 75k."],
        ],
        "Commodities": [
            ["Ativo", "Preço", "Var %", "Sparkline", "Contexto / Análise Técnica"],
            ["Petróleo Brent", "93.50", Paragraph(f"<font color='{SILVER}'>0.00%</font>"), make_sparkline(spark_up), "Estresse geopolítico precificado."],
            ["Ouro", "2.450", Paragraph(f"<font color='{GREEN}'>+0.15%</font>"), make_sparkline(spark_up), "Busca por proteção e segurança."],
        ]
    }
    
    agenda_data = [
        ["Hora (BR)", "Evento", "Local", "Relevância", "Impacto Esperado"],
        ["09:30", "Seguro-Desemprego", "EUA", "ALTA", "Termômetro do Fed."],
        ["10:45", "PMI Flash S&P", "EUA", "MÉDIA", "Atividade econômica."],
        ["17:00*", "Balanços: Big Techs", "EUA", "MÁXIMA", "Microsoft e Alphabet."],
    ]
    
    radar_brasil_data = [
        {"label": "IBOVESPA", "text": "Resistência nos 200.000 pontos segue como o grande desafio psicológico e técnico."},
        {"label": "TECNOLOGIA", "text": "Expectativa elevada para os resultados de Microsoft e Alphabet; foco em monetização de IA."},
        {"label": "COMMODITIES", "text": "Petrobras e Vale devem operar em estabilidade refletindo a lateralização externa."},
    ]
    
    strategy_text = "Reduzir exposição antes das 17h para evitar a volatilidade dos balanços. Monitorar suporte do Ibovespa em 195k. Se o emprego nos EUA vier forte, o dólar ganha tração."
    
    print(f"Gerando relatório adaptado {output_filename}...")
    generate_report(
        date_str=date_str,
        output_filename=output_filename,
        accent_color=ORANGE,
        title_day="MANUS CAPITAL | MORNING CALL",
        highlights=highlights,
        focus_text=focus_text,
        panorama_text=panorama_text,
        assets_data=assets_data,
        agenda_data=agenda_data,
        radar_brasil_data=radar_brasil_data,
        strategy_text=strategy_text
    )
    print("Relatório adaptado com sucesso!")
