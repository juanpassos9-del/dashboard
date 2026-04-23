"""
app.py — Dashboard de Mercado Intermercado
Streamlit dashboard com cotações, correlações, notícias e calendário econômico.
Execute com: streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Adiciona diretório raiz ao path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execution.fetch_quotes import fetch_all_quotes, ASSETS
from execution.calc_correlations import get_full_correlation_analysis
from execution.fetch_news import fetch_all_news, categorize_news
from execution.fetch_calendar import fetch_economic_calendar

# ============================================================
# Configuração da Página
# ============================================================

st.set_page_config(
    page_title="Dashboard Intermercados",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# CSS Customizado — Visual Premium Dark Mode
# ============================================================

st.markdown("""
<style>
    /* === Imports === */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* === Root & Body === */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #0d1117 50%, #0a0a0f 100%);
        font-family: 'Inter', sans-serif;
    }

    /* === Header === */
    .main-header {
        text-align: center;
        padding: 1.5rem 0 1rem;
        border-bottom: 1px solid rgba(99, 102, 241, 0.15);
        margin-bottom: 1.5rem;
    }
    .main-header h1 {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #818cf8, #6366f1, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header .subtitle {
        color: #6b7280;
        font-size: 0.85rem;
        margin-top: 0.3rem;
        font-weight: 400;
    }

    /* === Section Title === */
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e5e7eb;
        margin: 1.5rem 0 0.75rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(99, 102, 241, 0.3);
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* === Category Title === */
    .category-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 0.5rem;
        padding-left: 0.25rem;
    }

    /* === Quote Card === */
    .quote-card {
        background: linear-gradient(145deg, rgba(17, 24, 39, 0.9), rgba(17, 24, 39, 0.6));
        border: 1px solid rgba(55, 65, 81, 0.5);
        border-radius: 12px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
    }
    .quote-card:hover {
        border-color: rgba(99, 102, 241, 0.5);
        transform: translateY(-1px);
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.1);
    }
    .quote-name {
        font-size: 0.75rem;
        color: #9ca3af;
        font-weight: 500;
        margin-bottom: 0.2rem;
    }
    .quote-price {
        font-size: 1.2rem;
        font-weight: 700;
        color: #f3f4f6;
        margin-bottom: 0.15rem;
    }
    .quote-change-up {
        font-size: 0.8rem;
        font-weight: 600;
        color: #34d399;
    }
    .quote-change-down {
        font-size: 0.8rem;
        font-weight: 600;
        color: #f87171;
    }

    /* === News Card === */
    .news-card {
        background: rgba(17, 24, 39, 0.7);
        border: 1px solid rgba(55, 65, 81, 0.4);
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.6rem;
        transition: border-color 0.2s;
    }
    .news-card:hover {
        border-color: rgba(99, 102, 241, 0.4);
    }
    .news-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #e5e7eb;
        margin-bottom: 0.25rem;
        line-height: 1.4;
    }
    .news-meta {
        font-size: 0.7rem;
        color: #6b7280;
    }
    .news-summary {
        font-size: 0.75rem;
        color: #9ca3af;
        margin-top: 0.3rem;
        line-height: 1.4;
    }

    /* === Insight Card === */
    .insight-card {
        background: rgba(17, 24, 39, 0.8);
        border-left: 3px solid #6366f1;
        border-radius: 0 10px 10px 0;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
    }
    .insight-pair {
        font-size: 0.85rem;
        font-weight: 700;
        color: #e5e7eb;
    }
    .insight-corr {
        font-size: 0.75rem;
        font-weight: 600;
        color: #a78bfa;
        margin-left: 0.5rem;
    }
    .insight-text {
        font-size: 0.78rem;
        color: #9ca3af;
        margin-top: 0.3rem;
        line-height: 1.4;
    }

    /* === Calendar Table === */
    .calendar-high {
        background: rgba(248, 113, 113, 0.1) !important;
        border-left: 3px solid #f87171;
    }
    .calendar-medium {
        background: rgba(251, 191, 36, 0.1) !important;
        border-left: 3px solid #fbbf24;
    }

    /* === Status Bar === */
    .status-bar {
        text-align: center;
        padding: 0.5rem;
        font-size: 0.7rem;
        color: #4b5563;
        border-top: 1px solid rgba(55, 65, 81, 0.3);
        margin-top: 2rem;
    }
    .status-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #34d399;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }

    /* === Hide Streamlit defaults === */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}

    /* === Tabs === */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: rgba(17, 24, 39, 0.5);
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #9ca3af;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 0.5rem 1.2rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(99, 102, 241, 0.2);
        color: #a78bfa;
    }

    /* === Divider override === */
    hr {
        border-color: rgba(55, 65, 81, 0.3) !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================

st.markdown(f"""
<div class="main-header">
    <h1>📊 Dashboard Intermercados</h1>
    <div class="subtitle">Cotações • Correlações • Notícias • Calendário Econômico</div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# Cache & Data Loading
# ============================================================

@st.cache_data(ttl=60)
def load_quotes():
    return fetch_all_quotes()

@st.cache_data(ttl=300)
def load_correlations():
    return get_full_correlation_analysis(period_days=30)

@st.cache_data(ttl=600)
def load_news():
    return fetch_all_news(max_results=15)

@st.cache_data(ttl=900)
def load_calendar():
    return fetch_economic_calendar()


# ============================================================
# Funções de Renderização
# ============================================================

def render_quote_card(name, data):
    """Renderiza um card de cotação."""
    if data["price"] is None:
        price_str = "N/A"
        change_str = ""
        change_class = "quote-change-up"
    else:
        price_str = f"{data['price']:,.4f}" if data['price'] < 10 else f"{data['price']:,.2f}"
        sign = "+" if data["change_pct"] >= 0 else ""
        arrow = "▲" if data["change_pct"] >= 0 else "▼"
        change_str = f"{arrow} {sign}{data['change_pct']:.2f}%"
        change_class = "quote-change-up" if data["change_pct"] >= 0 else "quote-change-down"

    st.markdown(f"""
    <div class="quote-card">
        <div class="quote-name">{name}</div>
        <div class="quote-price">{price_str}</div>
        <div class="{change_class}">{change_str}</div>
    </div>
    """, unsafe_allow_html=True)


def render_correlation_heatmap(corr_matrix):
    """Renderiza heatmap de correlação com Plotly."""
    if corr_matrix.empty:
        st.warning("Dados insuficientes para calcular correlações.")
        return

    labels = corr_matrix.columns.tolist()
    z_values = corr_matrix.values

    fig = go.Figure(data=go.Heatmap(
        z=z_values,
        x=labels,
        y=labels,
        colorscale=[
            [0.0, "#1e3a5f"],
            [0.25, "#3b82f6"],
            [0.5, "#1f2937"],
            [0.75, "#ef4444"],
            [1.0, "#7f1d1d"],
        ],
        zmin=-1,
        zmax=1,
        text=np.round(z_values, 2),
        texttemplate="%{text}",
        textfont={"size": 9, "color": "#e5e7eb"},
        hovertemplate="<b>%{x}</b> × <b>%{y}</b><br>Correlação: %{z:.2f}<extra></extra>",
        colorbar=dict(
            title="Corr.",
            titlefont=dict(color="#9ca3af", size=11),
            tickfont=dict(color="#6b7280", size=10),
            thickness=15,
            len=0.8,
        ),
    ))

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb", family="Inter"),
        height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(
            tickangle=-45,
            tickfont=dict(size=10, color="#9ca3af"),
            side="bottom",
        ),
        yaxis=dict(
            tickfont=dict(size=10, color="#9ca3af"),
            autorange="reversed",
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Layout Principal
# ============================================================

# --- TAB NAVIGATION ---
tab_quotes, tab_corr, tab_news, tab_cal = st.tabs([
    "📊 Cotações",
    "🔗 Correlações",
    "📰 Notícias",
    "📅 Calendário",
])

# ========================
# TAB 1: COTAÇÕES
# ========================
with tab_quotes:
    with st.spinner("Carregando cotações..."):
        quotes = load_quotes()

    for category, assets in quotes.items():
        st.markdown(f'<div class="category-title">{category}</div>', unsafe_allow_html=True)

        cols = st.columns(len(assets))
        for i, (name, data) in enumerate(assets.items()):
            with cols[i]:
                render_quote_card(name, data)

    # Botão refresh
    col1, col2, col3 = st.columns([4, 2, 4])
    with col2:
        if st.button("🔄 Atualizar Cotações", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# ========================
# TAB 2: CORRELAÇÕES
# ========================
with tab_corr:
    st.markdown('<div class="section-title">🔗 Matriz de Correlação (30 dias)</div>', unsafe_allow_html=True)

    with st.spinner("Calculando correlações..."):
        corr_matrix, interpretations = load_correlations()

    col_heatmap, col_insights = st.columns([3, 2])

    with col_heatmap:
        render_correlation_heatmap(corr_matrix)

    with col_insights:
        st.markdown('<div class="section-title">💡 Interpretações</div>', unsafe_allow_html=True)

        if interpretations:
            for insight in interpretations:
                st.markdown(f"""
                <div class="insight-card">
                    <div>
                        <span class="insight-pair">{insight['pair']}</span>
                        <span class="insight-corr">{insight['strength']} ({insight['correlation']:.2f})</span>
                    </div>
                    <div class="insight-text">{insight['interpretation']}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Sem dados suficientes para interpretar correlações.")


# ========================
# TAB 3: NOTÍCIAS
# ========================
with tab_news:
    st.markdown('<div class="section-title">📰 Mini Relatório Diário</div>', unsafe_allow_html=True)

    with st.spinner("Buscando notícias..."):
        news = load_news()

    if news:
        categorized = categorize_news(news)

        for cat_name, cat_news in categorized.items():
            st.markdown(f'<div class="category-title">{cat_name}</div>', unsafe_allow_html=True)
            for item in cat_news[:3]:  # Max 3 por categoria
                st.markdown(f"""
                <div class="news-card">
                    <div class="news-title">{item['title']}</div>
                    <div class="news-meta">🕐 {item['published_str']} • {item['source']}</div>
                    <div class="news-summary">{item['summary']}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("📰 Nenhuma notícia relevante encontrada no momento.")


# ========================
# TAB 4: CALENDÁRIO ECONÔMICO
# ========================
with tab_cal:
    st.markdown('<div class="section-title">📅 Calendário Econômico — Hoje</div>', unsafe_allow_html=True)

    with st.spinner("Buscando calendário..."):
        calendar_df = load_calendar()

    if not calendar_df.empty:
        # Estiliza a tabela
        def highlight_impact(row):
            if "Alto" in str(row.get("Impacto", "")):
                return ["background: rgba(248, 113, 113, 0.08); color: #f3f4f6"] * len(row)
            elif "Médio" in str(row.get("Impacto", "")):
                return ["background: rgba(251, 191, 36, 0.06); color: #f3f4f6"] * len(row)
            return ["color: #9ca3af"] * len(row)

        styled_df = calendar_df.style.apply(highlight_impact, axis=1).set_properties(**{
            "font-size": "0.85rem",
            "font-family": "Inter, sans-serif",
            "border-bottom": "1px solid rgba(55, 65, 81, 0.3)",
            "padding": "0.5rem",
        })

        st.dataframe(
            calendar_df,
            use_container_width=True,
            hide_index=True,
            height=400,
        )
    else:
        st.info("📅 Sem eventos econômicos para hoje.")


# ============================================================
# Status Bar (Footer)
# ============================================================

st.markdown(f"""
<div class="status-bar">
    <span class="status-dot"></span>
    Última atualização: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")} (Brasília)
    &nbsp;•&nbsp; Dados: Yahoo Finance (delay ~15min)
    &nbsp;•&nbsp; Auto-refresh: 60s
</div>
""", unsafe_allow_html=True)

# Auto-refresh a cada 60 segundos
st.markdown("""
<script>
    setTimeout(function() {
        window.location.reload();
    }, 60000);
</script>
""", unsafe_allow_html=True)
