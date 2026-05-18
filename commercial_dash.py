import streamlit as st
import streamlit.components.v1 as components

import os
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client


# ── Configuração da Página ──────────────────────────────────────────────────
st.set_page_config(page_title="Terminal TTS | Inteligência", layout="wide")

# ── Supabase ────────────────────────────────────────────────────────────────
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
        key = st.secrets.get("SUPABASE_SERVICE_ROLE", os.environ.get("SUPABASE_SERVICE_ROLE", ""))
        if not key:
            key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
        if not url or not key:
            st.error("🔑 Credenciais do Supabase não encontradas. Verifique os segredos.")
            return None
        return create_client(url, key)
    except Exception as e:
        st.error(f"🌐 Falha na conexão com o Banco de Dados: {e}")
        return None

supabase = init_supabase()

def fetch_app_state(key: str):
    """Busca dados no Supabase com tratamento de erro e redundância."""
    if not supabase: return None
    try:
        response = supabase.table("app_state").select("value").eq("key", key).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["value"]
    except Exception as e:
        print(f"[ERROR] Fetch {key}: {e}")
    return None

def fetch_app_state_with_time(key: str):
    """Busca dados no Supabase e retorna uma tupla (valor, data_atualizacao_formatada_local, dt_utc)."""
    if not supabase: return None, "Sem conexão", None
    try:
        response = supabase.table("app_state").select("value, updated_at").eq("key", key).execute()
        if response.data and len(response.data) > 0:
            val = response.data[0]["value"]
            upd_raw = response.data[0].get("updated_at")
            if upd_raw:
                try:
                    s = upd_raw.replace("Z", "+00:00")
                    dt_utc = datetime.fromisoformat(s)
                    tz_br = timezone(timedelta(hours=-3))
                    dt_local = dt_utc.astimezone(tz_br)
                    return val, dt_local.strftime("%d/%m/%Y %H:%M:%S"), dt_utc
                except Exception as ex:
                    print(f"Erro formatar data {upd_raw}: {ex}")
                    return val, str(upd_raw), None
            return val, "---", None
    except Exception as e:
        print(f"[ERROR] Fetch {key} with time: {e}")
    return None, "Erro", None

def save_credentials(creds):
    if not supabase: return
    try:
        supabase.table("app_state").upsert({
            "key": "user_credentials",
            "value": creds,
            "updated_at": "now()"
        }).execute()
    except Exception as e:
        print(f"[ERROR] Save Creds: {e}")

def sanitize_text(text):
    """Proteção básica contra injeção de scripts."""
    if text is None: return ""
    if not isinstance(text, str): return str(text)
    return text.replace("<script", "&lt;script").replace("javascript:", "")

def clean_val(val):
    """Limpa strings com formatações variadas de milhar/decimal para float robusto."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s = s.replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            s = s.replace(".", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0



# ── Estilo Global ───────────────────────────────────────────────────────────
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&family=Inter:wght@400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Roboto Mono', monospace; background-color: #050505; color: #E0E0E0; }
    
    /* Price Cards */
    .main-card { background: #111111; border-left: 5px solid #FF9800; padding: 20px; border-radius: 5px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); margin-bottom: 20px; }
    .price-large { font-size: 3.2rem; font-weight: bold; color: #FFFFFF; line-height: 1; }
    .label-small { font-size: 0.75rem; color: #888; text-transform: uppercase; margin-bottom: 5px; }
    
    /* Semáforo */
    .status-box { padding: 12px; border-radius: 4px; text-align: center; font-weight: bold; background: #1A1A1A; border: 1px solid #333; font-size: 0.85rem; }
    
    /* Escada Moderna */
    .ladder-container { background: #0A0A0A; border: 1px solid #222; border-radius: 4px; overflow: hidden; margin-top: 15px; font-size: 0.85rem; }
    .ladder-row { display: grid; grid-template-columns: 1fr 1.5fr 1fr 1.5fr; padding: 6px 12px; border-bottom: 1px solid #1a1a1a; align-items: center; }
    .ladder-row:last-child { border-bottom: none; }
    .ladder-header { background: #151515; color: #666; font-weight: bold; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 1px; }
    .level-col { font-weight: bold; }
    .price-col { font-family: 'Roboto Mono', monospace; color: #FFF; text-align: right; font-weight: bold; }
    .delta-col { font-size: 0.75rem; text-align: right; }
    .ajuste-row { background: #1A1A1A !important; border: 1px solid #FF980088; color: #FFF; }
    .pos-row { background: #1F0A0A; color: #FF4B4B; }
    .neg-row { background: #0A1F13; color: #00FFA3; }
    .highlight-row { background: #FFC107 !important; color: #000 !important; font-weight: bold; }
    .highlight-row .price-col, .highlight-row .level-col, .highlight-row .delta-col { color: #000 !important; }
    
    /* IA Banner */
    .ia-banner { background: #111; border: 1px solid #333; border-left: 8px solid #444; padding: 20px; border-radius: 8px; margin: 20px 0; }
    </style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# FRAGMENTS
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment(run_every=60)
def painel_tickers_topo():
    """Mini cards de cotações globais no topo do terminal."""
    global_data = fetch_app_state("mercados_globais")
    if not global_data: return

    # Suporte para formato com ou sem chave 'categories'
    categories = global_data.get("categories", global_data)
    
    # Mapeamento dos ativos solicitados pelo usuário
    targets = {
        "EWZ": "EWZ (Brazil ETF)",
        "EEM": "EEM (Emerging Markets)",
        "6L": "6L (Real CME)",
        "PBR": "PETR4 (ADR)",
        "VALE": "VALE (ADR)",
        "BRENT": "BRENT OIL"
    }
    
    found_assets = {}
    if isinstance(categories, dict):
        for cat_assets in categories.values():
            if not isinstance(cat_assets, list): continue
            for asset in cat_assets:
                for key, target_name in targets.items():
                    if asset.get('name') == target_name:
                        found_assets[key] = asset

    # Renderização em colunas
    cols = st.columns(len(targets))
    for i, key in enumerate(targets.keys()):
        with cols[i]:
            asset = found_assets.get(key)
            if asset:
                change = asset.get('change', 0)
                color = "#00FFA3" if change >= 0 else "#FF4B4B"
                price = asset.get('price', 0)
                # Formatação compacta para o topo
                price_fmt = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.markdown(f"""
                    <div style="background: #111; border: 1px solid #222; border-top: 2px solid {color}; padding: 8px; border-radius: 4px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
                        <div style="font-size: 0.6rem; color: #888; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">{key}</div>
                        <div style="font-size: 1.1rem; font-weight: bold; color: #FFF; margin: 2px 0;">{price_fmt}</div>
                        <div style="font-size: 0.75rem; color: {color}; font-weight: bold;">{change:+.2f}%</div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div style="background: #0A0A0A; border: 1px solid #222; padding: 8px; border-radius: 4px; text-align: center; color: #444;">
                        <div style="font-size: 0.6rem;">{key}</div>
                        <div style="font-size: 1.1rem;">---</div>
                    </div>
                """, unsafe_allow_html=True)

@st.fragment(run_every=1)
def painel_topo_rtd():
    """Parte superior em tempo real (1s): Preços, Métricas e Semáforo."""
    dados = fetch_app_state("dados_mercado")
    if not dados or (isinstance(dados, list) and len(dados) == 0):
        st.info("⏳ Aguardando dados do Terminal Bridge...")
        return

    data = dados[0] if isinstance(dados, list) else dados

    def safe_fmt(v):
        try: return f"{float(v):.2f}" if v is not None else "---"
        except: return str(v)


    # 1. Cabeçalho
    bridge_time = data.get('updated_at', '')[-8:] or "---"
    st.markdown(f"### 📡 {data['symbol']} | <span style='color:#888;'>{bridge_time}</span>", unsafe_allow_html=True)

    # 2. Preços
    c1, c2, c3 = st.columns([2, 1, 1])
    change_val = data['change_percent']
    change_str = f"{change_val:.2%}" if isinstance(change_val, float) else str(change_val)
    color_hex  = '#00FFA3' if (isinstance(change_val, float) and change_val >= 0) else '#FF4B4B'

    with c1:
        last_price_val = clean_val(data.get('last_price', 0))
        st.markdown(f"""
            <div class="main-card">
                <div class="label-small">Último Preço</div>
                <div class="price-large">{last_price_val:,.2f}</div>
                <div style="color:{color_hex}; font-weight:bold; margin-top:5px;">{change_str}</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.metric("VWAP",   safe_fmt(data['vwap']))
        st.metric("Ajuste", safe_fmt(data['adjustment']))
    with c3:
        saldo_agr = data.get('saldo_agressao')
        if saldo_agr is not None:
            try:
                saldo_num = clean_val(saldo_agr)
                color = "#00FFA3" if saldo_num > 0 else ("#FF4B4B" if saldo_num < 0 else "#E0E0E0")
                # Formata com sinal (+/-) e separadores de milhar no padrão brasileiro
                saldo_fmt = f"{saldo_num:+,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except:
                color = "#E0E0E0"
                saldo_fmt = str(saldo_agr)
            st.markdown(f"<div class='label-small'>Saldo Agressão</div><div style='color:{color}; font-size:1.1rem; font-weight:bold;'>{saldo_fmt}</div>", unsafe_allow_html=True)
            
    # --- INTERPRETAÇÃO DE DIVERGÊNCIA DE DELTA ---
    last_price_val = data.get('last_price')
    vwap_val = data.get('vwap')
    saldo_agr = data.get('saldo_agressao')
    
    if last_price_val is not None and vwap_val is not None and saldo_agr is not None:
        try:
            np_price = clean_val(last_price_val)
            np_vwap = clean_val(vwap_val)
            
            # Ajuste de magnitude robusto
            if np_price > 0 and np_vwap > 0:
                ratio = np_price / np_vwap
                if ratio > 500:
                    np_vwap *= 1000
                elif ratio < 0.002:
                    np_price *= 1000
            
            saldo_num = clean_val(saldo_agr)
            
            if np_price > np_vwap and saldo_num < 0:
                st.markdown("""
                    <div style="background: rgba(255, 75, 75, 0.1); border: 2px solid #FF4B4B; padding: 15px; border-radius: 8px; text-align: center; margin-top: 15px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(255,75,75,0.2);">
                        <span style="color: #FF4B4B; font-weight: bold; font-size: 1.2rem; letter-spacing: 1px;">⚠️ DIVERGÊNCIA DE DELTA (VENDA)</span><br>
                        <span style="color: #DDD; font-size: 0.85rem;">Preço atual acima da VWAP com Saldo Acumulado Vendedor. Alerta de absorção na venda ou exaustão de compra!</span>
                    </div>
                """, unsafe_allow_html=True)
            elif np_price < np_vwap and saldo_num > 0:
                st.markdown("""
                    <div style="background: rgba(0, 255, 163, 0.1); border: 2px solid #00FFA3; padding: 15px; border-radius: 8px; text-align: center; margin-top: 15px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,255,163,0.2);">
                        <span style="color: #00FFA3; font-weight: bold; font-size: 1.2rem; letter-spacing: 1px;">🚀 DIVERGÊNCIA DE DELTA (COMPRA)</span><br>
                        <span style="color: #DDD; font-size: 0.85rem;">Preço atual abaixo da VWAP com Saldo Acumulado Comprador. Alerta de absorção na compra ou exaustão de venda!</span>
                    </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            pass

    # 3. Semáforo
    st.markdown("#### 🚥 SEMÁFORO DIRECIONAL")
    if "semaforo" in data:
        sem = data["semaforo"]
        def sig_style(text):
            t = str(text).upper() if text else ""
            if any(x in t for x in ["VENDA","VENDER","VENDIDO"]): return "background-color:#400000;color:#FF4B4B;border:1px solid #FF4B4B;"
            if any(x in t for x in ["COMPRA","COMPRAR","COMPRADO"]): return "background-color:#002611;color:#00FFA3;border:1px solid #00FFA3;"
            return "background-color:#1A1A1A;color:#E0E0E0;border:1px solid #333;"

        s1, s2, s3 = st.columns(3)
        with s1: st.markdown(f"<div class='status-box' style='{sig_style(sem.get('direcao'))}'>DIREÇÃO DO DIA<br>{sem.get('direcao','---')}</div>", unsafe_allow_html=True)
        with s2: st.markdown(f"<div class='status-box' style='{sig_style(sem.get('correlacao_rtd'))}'>CORRELAÇÕES RTD<br>{sem.get('correlacao_rtd','---')}</div>", unsafe_allow_html=True)
        with s3: st.markdown(f"<div class='status-box' style='{sig_style(sem.get('correlacao_interna'))}'>CORRELAÇÃO INTERNA<br>{sem.get('correlacao_interna','---')}</div>", unsafe_allow_html=True)

    # 4. Histograma de Variação % do Dia (Movido para baixo do Semáforo a pedido do usuário)
    if data.get("correlacoes") or data.get("acoes_peso"):
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("#### 📊 HISTOGRAMA DE VARIAÇÃO % DO DIA")
        try:
            bar_data = []
            
            # Filtra e adiciona ativos macro das correlações
            if data.get("correlacoes"):
                for row in data["correlacoes"]:
                    fator = row[0]
                    if "CORR" in str(fator).upper():
                        continue
                    var_val = clean_val(row[2])
                    bar_data.append({"Ativo": fator, "Variação %": var_val})
            
            # Adiciona ações de maior peso
            if data.get("acoes_peso"):
                for row in data["acoes_peso"]:
                    fator = row[0]
                    var_val = clean_val(row[3])
                    bar_data.append({"Ativo": fator, "Variação %": var_val})
            
            df_bar = pd.DataFrame(bar_data)
            
            if not df_bar.empty:
                # Garante arredondamento de 2 casas decimais no dataframe para evitar floats longos
                df_bar['Variação %'] = df_bar['Variação %'].round(2)
                
                import plotly.express as px
                df_bar['Cor'] = df_bar['Variação %'].apply(lambda x: '#00FFA3' if x >= 0 else '#FF4B4B')
                
                fig = px.bar(
                    df_bar,
                    x='Variação %',
                    y='Ativo',
                    orientation='h',
                    text='Variação %',
                    color='Cor',
                    color_discrete_map="identity"
                )
                
                num_items = len(df_bar)
                chart_height = max(180, num_items * 28 + 20)
                
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_family='"Roboto Mono", monospace',
                    font_color='#E0E0E0',
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=chart_height,
                    xaxis=dict(
                        showgrid=True, 
                        gridcolor='#1a1a1a', 
                        zeroline=True, 
                        zerolinecolor='#444',
                        title=None,
                        ticksuffix="%"
                    ),
                    yaxis=dict(
                        title=None,
                        autorange="reversed"
                    ),
                    showlegend=False
                )
                
                fig.update_traces(
                    texttemplate='%{text:+.2f}%',
                    textposition='inside',
                    insidetextanchor='middle',
                    marker_line_color='#050505',
                    marker_line_width=1,
                    opacity=0.85
                )
                
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        except Exception as e:
            st.error(f"Erro ao gerar histograma de variação: {e}")

@st.fragment(run_every=60)
def secao_ia_fragment():
    """Seção de IA isolada para evitar atualizações constantes (60s)."""
    st.markdown("---")
    
    # Histórico da IA (Tendência)
    history_data = fetch_app_state("ai_insight_history")
    if history_data:
        st.markdown("<div style='font-size: 0.7rem; color: #666; margin-bottom: 8px; font-weight: bold; letter-spacing: 1px;'>⏳ HISTÓRICO DE DIREÇÃO (ÚLTIMAS 5)</div>", unsafe_allow_html=True)
        cols_h = st.columns(5)
        for i in range(5):
            with cols_h[i]:
                if i < len(history_data):
                    h = history_data[i]
                    h_sent = h.get('sentiment', 'NEUTRO')
                    h_time = h.get('updated_at', '')
                    if h_sent == "COMPRA":   h_color, h_bg = "#00FFA3", "#002611"
                    elif h_sent == "VENDA":  h_color, h_bg = "#FF4B4B", "#400000"
                    else:                  h_color, h_bg = "#E0E0E0", "#111"
                    
                    st.markdown(f"""
                        <div style="background:{h_bg}; border: 1px solid {h_color}44; border-radius: 4px; padding: 4px; text-align: center; height: 45px; display: flex; flex-direction: column; justify-content: center;">
                            <div style="font-size: 0.6rem; color: #888;">{h_time}</div>
                            <div style="font-size: 0.7rem; font-weight: bold; color: {h_color};">{h_sent}</div>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown('<div style="background:#050505; border: 1px dashed #222; border-radius: 4px; height: 45px;"></div>', unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom:15px;'></div>", unsafe_allow_html=True)

    ai_data = fetch_app_state("ai_insight")
    if ai_data:
        sent = ai_data.get('sentiment', 'NEUTRO')
        ibg, itext = ("#002611", "#00FFA3") if sent == "COMPRA" else (("#400000", "#FF4B4B") if sent == "VENDA" else ("#111", "#E0E0E0"))
        
        st.markdown(f"""
            <div style="background:{ibg}; border: 1px solid {itext}44; padding: 20px; border-radius: 8px; border-left: 8px solid {itext}; margin-bottom: 25px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <b style="color:{itext}; font-size: 1rem;">🤖 ANALISTA IA: {sent}</b>
                    <span style="color: #666; font-size: 0.75rem;">{ai_data.get('updated_at', '')}</span>
                </div>
                <div style="color: #E0E0E0; font-size: 0.95rem; line-height: 1.5;">{sanitize_text(ai_data.get('insight', '')).replace(chr(10), '<br>')}</div>
            </div>
        """, unsafe_allow_html=True)

@st.fragment(run_every=300)
def secao_market_report_fragment():
    """Seção de Relatório de Mercado (Market Report) baseada em notícias."""
    report_data = fetch_app_state("market_report")
    if report_data:
        st.markdown("---")
        st.markdown(f"""
            <div style="background: #0A0A0A; border: 1px solid #1a1a1a; border-top: 4px solid #FF9800; padding: 25px; border-radius: 8px; margin: 20px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3 style="margin: 0; color: #FF9800; font-family: 'Inter', sans-serif;">📰 MARKET REPORT</h3>
                    <span style="color: #555; font-size: 0.75rem; font-family: 'Roboto Mono', monospace;">ÚLTIMA ATUALIZAÇÃO: {report_data.get('updated_at', '---')}</span>
                </div>
                <div style="color: #CCC; font-size: 0.9rem; line-height: 1.6; font-family: 'Inter', sans-serif;">
                    {sanitize_text(report_data.get('report', '')).replace(chr(10), '<br>')}
                </div>
            </div>
        """, unsafe_allow_html=True)


@st.fragment(run_every=1)
def painel_inferior_rtd():
    """Parte inferior em tempo real (1s): Correlações e Escada."""
    dados = fetch_app_state("dados_mercado")
    if not dados or (isinstance(dados, list) and len(dados) == 0):
        return

    data = dados[0] if isinstance(dados, list) else dados



    # 5. Escada de Níveis

    if data.get("escada"):
        st.markdown("""<div style="background:#FF9800; color:#000; padding:5px 15px; font-weight:bold; border-radius:4px 4px 0; font-size:0.8rem; display:flex; justify-content:space-between;">
            <span>ESCADA DE NÍVEIS</span>
            <span>0,5% EM 0,5%</span>
        </div>""", unsafe_allow_html=True)
        
        html = '<div class="ladder-container" style="margin-top:0; border-top:none;">'
        html += '<div class="ladder-row ladder-header" style="grid-template-columns: 0.8fr 1fr 1.2fr 1.2fr 1fr;"><div>NÍVEL</div><div style="text-align:right;">Δ %</div><div style="text-align:right;">PREÇO</div><div style="text-align:right;">Δ P/ ÚLTIMO</div><div style="text-align:right;">MARCADOR</div></div>'
        
        last_price = clean_val(data.get('last_price', 0))
        precos_niveis = [float(row[2]) for row in data["escada"]]
        preco_mais_proximo = min(precos_niveis, key=lambda x: abs(x - last_price))

        for row in data["escada"]:
            nivel, var_pct, preco, dist = row
            preco_val = float(preco)
            is_highlight = abs(preco_val - preco_mais_proximo) < 0.1
            is_ajuste = "AJUSTE" in str(nivel).upper()
            row_class = "highlight-row" if is_highlight else ("ajuste-row" if is_ajuste else ("pos-row" if any(x in str(nivel) for x in ["+","1","2","3","4","5"]) else "neg-row"))
            marcador = "◀ PREÇO" if is_highlight else ""
            p_fmt = f"{preco_val:,.0f}".replace(",", ".")
            d_fmt = f"{float(dist):+,.0f}".replace(",", ".")
            v_fmt = f"{float(var_pct):+.1f}%".replace(".", ",")
            
            html += f'<div class="ladder-row {row_class}" style="grid-template-columns: 0.8fr 1fr 1.2fr 1.2fr 1fr;">'
            html += f'<div class="level-col">{nivel}</div>'
            html += f'<div class="delta-col" style="text-align:right;">{v_fmt}</div>'
            html += f'<div class="price-col" style="text-align:right;">{p_fmt}</div>'
            html += f'<div class="delta-col" style="text-align:right;">{d_fmt}</div>'
            html += f'<div style="text-align:right; font-size:0.7rem;">{marcador}</div>'
            html += '</div>'
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

@st.fragment(run_every=60)
def painel_topo_global():
    """Cards de destaque para o mercado global."""
    global_data = fetch_app_state("mercados_globais")
    if not global_data: return
    
    categories = global_data.get("categories", global_data)
    
    # Encontrar ativos específicos para os cards
    cards_assets = {
        "S&P 500": None,
        "DXY (Dólar Index)": None,
        "US 10Y (Yield)": None,
        "BRENT OIL": None
    }
    
    for cat in categories.values():
        for asset in cat:
            if asset['name'] in cards_assets:
                cards_assets[asset['name']] = asset

    st.markdown("#### 🌎 INDICADORES GLOBAIS")
    cols = st.columns(4)
    for i, (name, asset) in enumerate(cards_assets.items()):
        with cols[i]:
            if asset:
                change = asset.get('change', 0)
                color = "#00FFA3" if change >= 0 else "#FF4B4B"
                price = asset.get('price', 0)
                price_fmt = f"{price:.4f}" if price < 10 else f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                st.markdown(f"""
                    <div class="main-card" style="padding: 15px; margin-bottom: 10px; border-left-color: {color};">
                        <div class="label-small">{name}</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: #FFF;">{price_fmt}</div>
                        <div style="color: {color}; font-size: 0.85rem; font-weight: bold;">{change:+.2f}%</div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='main-card' style='padding:15px;'>{name}<br>---</div>", unsafe_allow_html=True)

@st.fragment(run_every=60)
def painel_corpo_global():
    """Tabelas detalhadas de mercados globais."""
    global_data = fetch_app_state("mercados_globais")
    if not global_data: return
    
    categories = global_data.get("categories", global_data)
    
    st.markdown("---")
    # Organizar em colunas de 2 para economizar espaço
    cat_names = list(categories.keys())
    for i in range(0, len(cat_names), 2):
        c1, c2 = st.columns(2)
        with c1:
            cat = cat_names[i]
            st.markdown(f"##### {cat}")
            assets = categories[cat]
            df = pd.DataFrame(assets)[['name', 'price', 'change']]
            df.columns = ['Ativo', 'Preço', 'Var %']
            def color_change(val):
                try: 
                    v = float(val)
                    color = '#00FFA3' if v >= 0 else '#FF4B4B'
                    return f'color: {color}; font-weight: bold'
                except: return ''
            st.dataframe(df.style.applymap(color_change, subset=['Var %']), hide_index=True, use_container_width=True)
        
        if i + 1 < len(cat_names):
            with c2:
                cat = cat_names[i+1]
                st.markdown(f"##### {cat}")
                assets = categories[cat]
                df = pd.DataFrame(assets)[['name', 'price', 'change']]
                df.columns = ['Ativo', 'Preço', 'Var %']
                st.dataframe(df.style.applymap(color_change, subset=['Var %']), hide_index=True, use_container_width=True)

def pagina_terminal_global():
    """Página de Terminal Global."""
    painel_topo_global()
    
    st.markdown("---")
    
    global_chart_assets = {
        "S&P 500": {"tv": "USA500", "yf": "^GSPC"},
        "NASDAQ": {"tv": "CME_MINI:NQ1!", "yf": "^IXIC"},
        "BRENT OIL": {"tv": "TVC:UKOIL", "yf": "BZ=F"},
        "WTI OIL": {"tv": "TVC:USOIL", "yf": "CL=F"},
        "GOLD": {"tv": "TVC:GOLD", "yf": "GC=F"},
        "BITCOIN": {"tv": "BINANCE:BTCUSDT", "yf": "BTC-USD"},
        "DXY (Dólar Index)": {"tv": "TVC:DXY", "yf": "DX-Y.NYB"},
        "US 10Y (Yield)": {"tv": "TVC:US10Y", "yf": "^TNX"},
        "EWZ (Brazil ETF)": {"tv": "AMEX:EWZ", "yf": "EWZ"},
        "EEM (Emerging Markets)": {"tv": "AMEX:EEM", "yf": "EEM"},
    }
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.markdown("#### 📈 Gráfico Global")
        col_sel, col_int = st.columns([2, 1])
        with col_sel:
            sym = st.selectbox("Ativo", list(global_chart_assets.keys()), index=0, key="global_sym")
        with col_int:
            interval = st.selectbox("Intervalo", ["1", "5", "15", "60", "D", "W"], index=4, key="global_int")
            
        tv_html = f"""
        <div class="tradingview-widget-container" style="height: 480px; width: 100%;">
          <div id="tv_global" style="height: 100%; width: 100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "autosize": true,
            "symbol": "{global_chart_assets[sym]['tv']}",
            "interval": "{interval}",
            "timezone": "America/Sao_Paulo",
            "theme": "dark",
            "style": "1",
            "locale": "br",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_top_toolbar": false,
            "save_image": true,
            "hide_volume": false,
            "container_id": "tv_global"
          }});
          </script>
        </div>
        """
        components.html(tv_html, height=500)

    with c2:
        st.markdown("#### 🤖 Analista Técnico IA")
        st.info(f"Análise baseada no histórico diário (OHLC) de {sym}.")
        if st.button("Gerar Análise Técnica (IA)", use_container_width=True):
            with st.spinner("Lendo o gráfico via IA..."):
                import sys
                exec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'execution'))
                if exec_path not in sys.path:
                    sys.path.append(exec_path)
                from tech_analyst import get_technical_analysis
                
                yf_ticker = global_chart_assets[sym]['yf']
                insight = get_technical_analysis(sym, yf_ticker)
                
                st.session_state[f'tech_insight_{sym}'] = insight
                
        if f'tech_insight_{sym}' in st.session_state:
            insight_text = st.session_state[f'tech_insight_{sym}']
            if "Erro" in insight_text or "429" in insight_text:
                border_color = "#FF4B4B"
                if "quota" in insight_text.lower() or "429" in insight_text:
                    insight_text = "⚠️ Limite de requisições da IA (Quota Exceeded) atingido. Tente novamente em alguns minutos."
            else:
                border_color = "#00FFA3"
                
            st.markdown(f"""
                <div style="background: #111; border: 1px solid #333; padding: 15px; border-radius: 8px; border-left: 5px solid {border_color}; font-size: 0.85rem; color: #E0E0E0; max-height: 380px; overflow-y: auto;">
                    {insight_text.replace(chr(10), '<br>')}
                </div>
            """, unsafe_allow_html=True)
            
    secao_market_report_fragment()
    painel_corpo_global()

@st.fragment(run_every=60)
def sidebar_mercados():
    global_data = fetch_app_state("mercados_globais")
    if not global_data: 
        st.info("Carregando mercados...")
        return
    
    # Suporte tanto para o formato antigo quanto para o novo
    if "categories" in global_data:
        categories = global_data["categories"]
        metadata = global_data.get("metadata", {})
        last_upd = metadata.get("last_updated", "---")
    else:
        categories = global_data
        last_upd = "---"

    st.markdown(f"<div style='text-align:right; font-size:0.65rem; color:#666; margin-bottom:10px;'>ATUALIZADO ÀS: {last_upd}</div>", unsafe_allow_html=True)

    for cat_name, assets in categories.items():
        st.markdown(f"<div style='font-size:0.75rem; font-weight:bold; color:#FF9800; margin-bottom:5px;'>{cat_name}</div>", unsafe_allow_html=True)
        for item in assets:
            if not isinstance(item, dict): continue
            change_val = item.get('change', 0)
            if not isinstance(change_val, (int, float)):
                try: change_val = float(change_val)
                except (ValueError, TypeError): change_val = 0.0

            color = "#00FFA3" if change_val >= 0 else "#FF4B4B"
            
            price_val = item.get('price', 0)
            if not isinstance(price_val, (int, float)):
                try: price_val = float(price_val)
                except (ValueError, TypeError): price_val = 0.0

            # Formatação de preço: 4 casas se for pequeno (moedas), 2 se for grande
            price_fmt = f"{price_val:.4f}" if price_val < 10 else f"{price_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            st.markdown(f"""
                <div style='display:flex; justify-content:space-between; border-bottom:1px solid #1a1a1a; padding:4px 0; align-items:center;'>
                    <span style='font-size:0.75rem; color:#AAA; max-width:60%;'>{item.get('name', '---')}</span>
                    <div style='text-align:right;'>
                        <div style='font-size:0.8rem; font-weight:bold;'>{price_fmt}</div>
                        <div style='color:{color}; font-weight:bold; font-size:0.65rem;'>{change_val:+.2f}%</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom:15px;'></div>", unsafe_allow_html=True)


@st.fragment(run_every=3600)
def sidebar_calendario():
    calendar_data = fetch_app_state("calendario_economico")
    if not calendar_data: 
        st.info("Carregando calendário...")
        return
    
    # 1. Seletor de Dia (Filtro Semanal)
    try:
        dates = sorted(list(set([e.get('date', '') for e in calendar_data if e.get('date')])))
        if not dates:
            st.warning("Nenhuma data disponível no calendário.")
            return
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        default_idx = dates.index(today_str) if today_str in dates else 0
        selected_date = st.selectbox("📅 Selecione o Dia", dates, index=default_idx)
    except Exception as e:
        st.error(f"Erro ao processar datas do calendário: {e}")
        return

    
    st.markdown("---")
    
    # 2. Filtragem e Exibição
    filtered_events = [e for e in calendar_data if e['date'] == selected_date]
    
    if not filtered_events:
        st.write("Nenhum evento importante para este dia.")
        return

    for event in filtered_events:
        impact_color = "#FF4B4B" if event['impact'] == "HIGH" else ("#FF9800" if event['impact'] == "MEDIUM" else "#888")
        
        actual = event.get('actual', '---')
        forecast = event.get('forecast', '---')
        
        # Design do Evento
        st.markdown(f"""
            <div style='border-bottom:1px solid #222; padding:10px 0;'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span style='font-size:0.7rem; color:#888;'>{event['time']} | {event['currency']}</span>
                    <span style='font-size:0.65rem; background:#1a1a1a; padding:2px 6px; border-radius:10px; color:{impact_color}; border:1px solid {impact_color}44;'>{event['impact']}</span>
                </div>
                <div style='font-size:0.85rem; font-weight:bold; margin:4px 0;'>{event['icon']} {event['event']}</div>
                <div style='display:flex; gap:15px; margin-top:5px;'>
                    <div style='font-size:0.7rem;'>
                        <span style='color:#666;'>PREV:</span> <b style='color:#DDD;'>{forecast}</b>
                    </div>
                    <div style='font-size:0.7rem;'>
                        <span style='color:#666;'>ATUAL:</span> <b style='color:#FFF;'>{actual}</b>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

@st.fragment(run_every=300)
def secao_fluxo_estrangeiro_fragment():
    """Seção que exibe o Fluxo do Investidor Estrangeiro na B3."""
    fluxo_data = fetch_app_state("fluxo_estrangeiro_b3")
    if not fluxo_data or "records" not in fluxo_data:
        return

    st.markdown("---")
    st.markdown("#### 🌍 FLUXO ESTRANGEIRO NA B3")
    st.markdown(f"<span style='color: #666; font-size: 0.75rem; font-family: \"Roboto Mono\", monospace;'>ÚLTIMA ATUALIZAÇÃO: {fluxo_data.get('updated_at', '---')[:10]}</span>", unsafe_allow_html=True)
    
    records = fluxo_data["records"][:30] # Últimos 30 dias
    if not records:
        return
        
    df = pd.DataFrame(records)
    df = df.sort_values("date") # Ordem cronológica para o gráfico
    
    import plotly.graph_objects as go
    
    # Cores baseadas no valor (positivo = verde, negativo = vermelho)
    colors = ['#00FFA3' if val >= 0 else '#FF4B4B' for val in df['foreigners']]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['foreigners'],
        marker_color=colors,
        text=df['foreigners'].apply(lambda x: f"R$ {x/1000:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")),
        textposition='outside',
        textfont=dict(color='#E0E0E0', size=9)
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='"Roboto Mono", monospace',
        font_color='#E0E0E0',
        margin=dict(l=10, r=10, t=30, b=10),
        height=350,
        xaxis=dict(showgrid=False, title=None, tickangle=-45),
        yaxis=dict(showgrid=True, gridcolor='#1a1a1a', zeroline=True, zerolinecolor='#444', title="R$ Milhares"),
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

@st.fragment(run_every=300)
def secao_boletim_focus_fragment():
    """Seção que exibe as expectativas do Boletim Focus no formato histórico."""
    focus_data = fetch_app_state("boletim_focus")
    if not focus_data or "years" not in focus_data:
        return
        
    st.markdown("---")
    st.markdown("#### 🇧🇷 BOLETIM FOCUS (BCB)")
    st.markdown(f"<span style='color: #666; font-size: 0.75rem; font-family: \"Roboto Mono\", monospace;'>DATA BASE: {focus_data.get('publish_date', '---')}</span>", unsafe_allow_html=True)
    
    years = sorted(list(focus_data["years"].keys()))
    if not years:
        return
        
    # CSS para a tabela do Focus
    st.markdown("""
    <style>
    .focus-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.75rem;
        font-family: "Roboto Mono", monospace;
    }
    .focus-table th {
        text-align: right;
        color: #888;
        padding: 4px;
        border-bottom: 1px solid #333;
        font-weight: normal;
    }
    .focus-table th:first-child {
        text-align: left;
    }
    .focus-table td {
        text-align: right;
        color: #FFF;
        padding: 4px;
        border-bottom: 1px solid #222;
    }
    .focus-table td:first-child {
        text-align: left;
        color: #AAA;
    }
    </style>
    """, unsafe_allow_html=True)
    
    cols = st.columns(len(years))
    
    for i, year in enumerate(years):
        with cols[i]:
            data_year = focus_data["years"][year]
            st.markdown(f"<div style='text-align:center; padding:5px; background-color:#1a1a1a; border-radius:5px; margin-bottom:5px;'><b style='color:#00FFA3;'>{year}</b></div>", unsafe_allow_html=True)
            
            html = "<table class='focus-table'><tr><th>Indicador</th><th>Há 4 sem</th><th>Há 1 sem</th><th>Hoje</th><th></th></tr>"
            
            indicadores = [
                ("IPCA", data_year.get("IPCA", {})),
                ("PIB", data_year.get("PIB", {})),
                ("Câmbio", data_year.get("Cambio", {})),
                ("Selic", data_year.get("Selic", {}))
            ]
            
            for nome, vals in indicadores:
                if not vals or not isinstance(vals, dict):
                    html += f"<tr><td>{nome}</td><td>---</td><td>---</td><td>---</td><td></td></tr>"
                    continue
                    
                v4 = vals.get("4_sem")
                v1 = vals.get("1_sem")
                v0 = vals.get("hoje")
                
                # Formatters
                def f_val(x):
                    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if x is not None else "---"
                
                v4_str = f_val(v4)
                v1_str = f_val(v1)
                v0_str = f_val(v0)
                
                # Setas de tendência
                seta = ""
                if v0 is not None and v1 is not None:
                    if v0 > v1: seta = "<span style='color:#FF4B4B'>▲</span>" # Subiu (Vermelho se IPCA/Selic, mas mantendo simples)
                    elif v0 < v1: seta = "<span style='color:#00FFA3'>▼</span>" # Caiu
                    else: seta = "<span style='color:#888'>=</span>"
                
                html += f"<tr><td>{nome}</td><td>{v4_str}</td><td>{v1_str}</td><td><b>{v0_str}</b></td><td>{seta}</td></tr>"
                
            html += "</table>"
            st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINAS DO DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def pagina_terminal():
    """Renderiza o terminal principal de trading."""
    painel_tickers_topo()   # Indicadores Globais no Topo
    painel_topo_rtd()       # Tempo Real (1s)
    secao_ia_fragment()     # Estático/Lento (60s)
    painel_inferior_rtd()   # Tempo Real (1s) - Escada de Níveis
    secao_boletim_focus_fragment() # Estático/Lento (300s)
    secao_fluxo_estrangeiro_fragment() # Fluxo B3 (300s)

def pagina_market_report():
    """Página dedicada ao Market Report Institucional."""
    painel_tickers_topo()
    secao_market_report_fragment()

def pagina_graficos():
    """Página com integração TradingView Advanced Chart."""
    st.markdown("### 📊 Gráficos Avançados TradingView")
    
    assets = {
        "MINI ÍNDICE (WIN)": "BRA50",
        "MINI DÓLAR (WDO)": "BMFBOVESPA:WDO1!",
        "IBOVESPA": "BMFBOVESPA:IBOV",
        "S&P 500 (Futuro)": "USA500",
        "NASDAQ (Futuro)": "CME_MINI:NQ1!",
        "VIX": "CBOE:VIX",
        "DXY (Dólar Index)": "TVC:DXY",
        "USDBRL": "FX_IDC:USDBRL",
        "6L (Real CME)": "CME:6L1!",
        "US 10Y (Yield)": "TVC:US10Y",
        "US 30Y (Yield)": "TVC:US30Y",
        "US 02Y (Yield)": "TVC:US02Y",
        "EEM (Emerging Markets)": "AMEX:EEM",
        "EWZ (Brazil ETF)": "AMEX:EWZ",
        "PETR4": "BMFBOVESPA:PETR4",
        "VALE3": "BMFBOVESPA:VALE3",
        "ITUB4": "BMFBOVESPA:ITUB4",
        "SPY (S&P 500 ETF)": "AMEX:SPY",
        "XOP (Oil & Gas)": "AMEX:XOP",
        "XLE (Energy)": "AMEX:XLE",
        "XLK (Tech)": "AMEX:XLK",
        "XLP (Staples)": "AMEX:XLP",
        "XLB (Materials)": "AMEX:XLB",
        "XLI (Industrials)": "AMEX:XLI",
        "XLV (Health)": "AMEX:XLV",
        "XLRE (Real Estate)": "AMEX:XLRE",
        "XBI (Biotech)": "AMEX:XBI",
        "XLY (Consumer)": "AMEX:XLY",
        "XLC (Comm)": "AMEX:XLC",
        "BRENT OIL": "TVC:UKOIL",
        "WTI OIL": "TVC:USOIL",
        "GOLD": "TVC:GOLD",
        "SILVER": "TVC:SILVER",
        "BITCOIN": "BINANCE:BTCUSDT",
        "ETHEREUM": "BINANCE:ETHUSDT"
    }

    c_topo1, c_topo2, c_topo3 = st.columns([1, 1, 2])
    with c_topo3:
        chart_height = st.slider("Ajustar Altura dos Gráficos", min_value=300, max_value=1200, value=550, step=50)

    st.markdown("---")
    st.markdown("#### 📈 Gráfico 1")
    c1a, c1b = st.columns([2, 1])
    with c1a:
        sym1 = st.selectbox("Ativo 1", list(assets.keys()), index=0, key="sym1")
    with c1b:
        int1 = st.selectbox("Intervalo 1", ["1", "5", "15", "60", "D", "W"], index=1, key="int1")
        
    tv_html1 = f"""
    <div class="tradingview-widget-container" style="height: {chart_height}px; width: 100%;">
      <div id="tv_chart_1" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{assets[sym1]}",
        "interval": "{int1}",
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "save_image": true,
        "hide_volume": true,
        "container_id": "tv_chart_1"
      }});
      </script>
    </div>
    """
    components.html(tv_html1, height=chart_height + 20)

    st.markdown("---")
    st.markdown("#### 📉 Gráfico 2")
    c2a, c2b = st.columns([2, 1])
    with c2a:
        sym2 = st.selectbox("Ativo 2", list(assets.keys()), index=3, key="sym2")
    with c2b:
        int2 = st.selectbox("Intervalo 2", ["1", "5", "15", "60", "D", "W"], index=1, key="int2")
        
    tv_html2 = f"""
    <div class="tradingview-widget-container" style="height: {chart_height}px; width: 100%;">
      <div id="tv_chart_2" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{assets[sym2]}",
        "interval": "{int2}",
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "save_image": true,
        "hide_volume": true,
        "container_id": "tv_chart_2"
      }});
      </script>
    </div>
    """
    components.html(tv_html2, height=chart_height + 20)

def pagina_correlacao():
    """Página dedicada ao estudo de correlação unificada com visibilidade aprimorada."""
    st.markdown("### ⚖️ Painel de Correlação Macro")
    
    # Controles Gerais
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        interval = st.selectbox("Intervalo", ["5", "15", "60", "D", "W"], index=3)
    with c2:
        theme = st.selectbox("Tema", ["dark", "light"], index=0)
    with c3:
        c_height = st.slider("Altura do Gráfico", 400, 1200, 800, 50)

    # Legenda customizada com cores sugeridas para o usuário ajustar no widget
    st.info("💡 Dica: No gráfico abaixo, você pode clicar em cada ativo na legenda (canto superior esquerdo) para ajustar a cor e a espessura da linha para melhor visibilidade.")

    # Widget TradingView com ferramentas de customização habilitadas
    tv_html = f"""
    <div class="tradingview-widget-container" style="height: {c_height}px; width: 100%;">
      <div id="tradingview_unified_v2" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "USA500",
        "interval": "{interval}",

        "timezone": "America/Sao_Paulo",
        "theme": "{theme}",
        "style": "2",
        "locale": "br",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_side_toolbar": true,
        "allow_symbol_change": true,

        "save_image": true,
        "details": false,
        "hotlist": false,
        "calendar": false,
        "hide_volume": true,
        "container_id": "tradingview_unified_v2",
        "overrides": {{
            "mainSeriesProperties.lineStyle.color": "#FF00FF",
            "mainSeriesProperties.lineStyle.linewidth": 3
        }},
        "studies": [
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "TVC:GOLD" }}, "plots": {{ "Plot": {{ "color": "#FFFF00" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "TVC:UKOIL" }}, "plots": {{ "Plot": {{ "color": "#006400" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "US10Y" }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "OTCB:US30Y" }}, "plots": {{ "Plot": {{ "color": "#00BFFF" }} }} }}
        ]



      }}
      );
      </script>
    </div>
    """
    components.html(tv_html, height=c_height + 20)


def render_tv_corr(container_id, main_sym, comp_sym, interval, height):
    """(Mantido para compatibilidade se necessário futuramente)"""
    pass

def pagina_painel_controle():
    import time
    import json
    st.markdown("### ⚙️ Central de Controle e Sincronização")
    st.write("Monitore o status das fontes de dados do seu terminal e force atualizações na nuvem de forma manual.")

    # 1. Busca dados do Supabase
    val_rtd, time_rtd, dt_rtd = fetch_app_state_with_time("dados_mercado")
    val_globais, time_globais, dt_globais = fetch_app_state_with_time("mercados_globais")
    val_ia, time_ia, dt_ia = fetch_app_state_with_time("ai_insight")
    val_report, time_report, dt_report = fetch_app_state_with_time("market_report")
    val_cal, time_cal, dt_cal = fetch_app_state_with_time("calendario_economico")
    val_fluxo, time_fluxo, dt_fluxo = fetch_app_state_with_time("fluxo_estrangeiro_b3")
    val_focus, time_focus, dt_focus = fetch_app_state_with_time("boletim_focus")

    # Calcula se os dados estão atualizados (B3 RTD - 30 segundos de tolerância)
    is_rtd_ok = False
    if dt_rtd:
        try:
            diff = (datetime.now(timezone.utc) - dt_rtd).total_seconds()
            if abs(diff) < 30:
                is_rtd_ok = True
        except Exception:
            pass

    # Status e cor dos badges
    def get_badge(status_ok, text_ok="🟢 ATUALIZADO", text_err="🔴 DESATUALIZADO / OFFLINE"):
        if status_ok:
            return f"<span style='color: #00FFA3; font-weight: bold;'>{text_ok}</span>"
        else:
            return f"<span style='color: #FF4B4B; font-weight: bold;'>{text_err}</span>"

    status_rtd = get_badge(is_rtd_ok, "🟢 EM OPERAÇÃO (TEMPO REAL)", "🔴 BRIDGE INDISPONÍVEL / OFFLINE")
    status_globais = get_badge(time_globais != "---" and "Erro" not in time_globais, "🟢 ATIVO", "🔴 INDISPONÍVEL")
    status_ia = get_badge(time_ia != "---" and "Erro" not in time_ia, "🟢 ATIVO", "🔴 INDISPONÍVEL")
    status_report = get_badge(time_report != "---" and "Erro" not in time_report, "🟢 ATIVO", "🔴 INDISPONÍVEL")
    status_cal = get_badge(time_cal != "---" and "Erro" not in time_cal, "🟢 ATIVO", "🔴 INDISPONÍVEL")
    status_fluxo = get_badge(time_fluxo != "---" and "Erro" not in time_fluxo, "🟢 ATIVO", "🔴 INDISPONÍVEL")
    status_focus = get_badge(time_focus != "---" and "Erro" not in time_focus, "🟢 ATIVO", "🔴 INDISPONÍVEL")

    # Exibe Grid de Status
    st.markdown("""
        <style>
        .status-table { width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 25px; }
        .status-table th, .status-table td { padding: 12px; text-align: left; border-bottom: 1px solid #222; }
        .status-table th { background-color: #111; color: #FF9800; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
        .status-table td { font-size: 0.85rem; }
        </style>
    """, unsafe_allow_html=True)

    html = f"""
    <table class="status-table">
        <tr>
            <th>Fonte de Dados</th>
            <th>Status do Feed</th>
            <th>Última Sincronização (Brasília)</th>
            <th>Tipo</th>
        </tr>
        <tr>
            <td><b>ProfitChart B3 (RTD Local)</b></td>
            <td>{status_rtd}</td>
            <td>{time_rtd}</td>
            <td>Local COM (WIN/WDO)</td>
        </tr>
        <tr>
            <td><b>Mercados Globais (Yahoo Finance)</b></td>
            <td>{status_globais}</td>
            <td>{time_globais}</td>
            <td>Nuvem API (S&P 500, Moedas, Commodities)</td>
        </tr>
        <tr>
            <td><b>IA Analista (Gemini)</b></td>
            <td>{status_ia}</td>
            <td>{time_ia}</td>
            <td>Nuvem LLM</td>
        </tr>
        <tr>
            <td><b>Market Report (Gemini + RSS)</b></td>
            <td>{status_report}</td>
            <td>{time_report}</td>
            <td>Nuvem LLM / RSS Notícias</td>
        </tr>
        <tr>
            <td><b>Calendário Econômico (ForexFactory)</b></td>
            <td>{status_cal}</td>
            <td>{time_cal}</td>
            <td>Nuvem Scraping</td>
        </tr>
        <tr>
            <td><b>Fluxo Estrangeiro (B3 / DDM)</b></td>
            <td>{status_fluxo}</td>
            <td>{time_fluxo}</td>
            <td>Nuvem Scraping</td>
        </tr>
        <tr>
            <td><b>Boletim Focus (BCB)</b></td>
            <td>{status_focus}</td>
            <td>{time_focus}</td>
            <td>API Pública</td>
        </tr>
    </table>
    """
    st.markdown(html, unsafe_allow_html=True)

    st.warning("""
        ⚠️ **Nota sobre o ProfitChart B3 (RTD Local):** As cotações do Mini Índice (WIN), Mini Dólar (WDO) e a Escada de Níveis requerem que a sua plataforma ProfitChart esteja aberta localmente com o script `dashboard_bridge.py` em execução no seu computador. Essa conexão COM local não pode ser atualizada em nuvem sem a bridge física ativa.
    """)

    st.markdown("### 🔄 Sincronização Manual na Nuvem")
    st.write("Se o seu computador estiver desligado (sem a bridge rodando) ou você queira forçar a atualização imediata dos mercados globais, IA e notícias, use os botões abaixo:")

    c1, c2, c3 = st.columns(3)

    def run_update_task(name, func, key, success_msg):
        with st.spinner(f"Atualizando {name}..."):
            try:
                result = func()
                paths_map = {
                    "mercados_globais": ["mercados_globais.json", "execution/mercados_globais.json"],
                    "ai_insight": ["ai_insight.json", "execution/ai_insight.json"],
                    "market_report": ["market_report.json", "execution/market_report.json"],
                    "calendario_economico": ["calendario_economico.json", "execution/calendario_economico.json"],
                    "fluxo_estrangeiro_b3": ["fluxo_estrangeiro.json", "execution/fluxo_estrangeiro.json"],
                    "boletim_focus": ["focus_bcb.json", "execution/focus_bcb.json"]
                }
                
                if key == "mercados_globais":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r") as f:
                                data = json.load(f)
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": data,
                                    "updated_at": "now()"
                                }).execute()
                            break
                            
                elif key == "ai_insight":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                new_insight = json.load(f)
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": new_insight,
                                    "updated_at": "now()"
                                }).execute()
                                
                                try:
                                    res = supabase.table("app_state").select("value").eq("key", "ai_insight_history").execute()
                                    history = res.data[0]["value"] if res.data else []
                                    if not isinstance(history, list): history = []
                                    
                                    history.append({
                                        "sentiment": new_insight.get("sentiment", "NEUTRO"),
                                        "updated_at": new_insight.get("updated_at", ""),
                                        "id": int(time.time())
                                    })
                                    history = history[-5:]
                                    supabase.table("app_state").upsert({
                                        "key": "ai_insight_history",
                                        "value": history,
                                        "updated_at": "now()"
                                    }).execute()
                                except Exception as he:
                                    print(f"Erro histórico: {he}")
                            break
                            
                elif key == "market_report":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": json.load(f),
                                    "updated_at": "now()"
                                }).execute()
                            break
                            
                elif key == "calendario_economico":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": json.load(f),
                                    "updated_at": "now()"
                                }).execute()
                            break
                            
                elif key == "fluxo_estrangeiro_b3":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": json.load(f),
                                    "updated_at": "now()"
                                }).execute()
                            break
                            
                elif key == "boletim_focus":
                    for p in paths_map[key]:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": key,
                                    "value": json.load(f),
                                    "updated_at": "now()"
                                }).execute()
                            break
                            
                st.success(success_msg)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar {name}: {e}")

    with c1:
        if st.button("📊 Atualizar Mercados Globais", use_container_width=True, help="Baixa cotações do Yahoo Finance em lote e sincroniza com o banco de dados."):
            import sys
            exec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'execution'))
            if exec_path not in sys.path: sys.path.append(exec_path)
            from fetch_global_markets import fetch_global_data
            run_update_task("Mercados Globais", fetch_global_data, "mercados_globais", "✅ Mercados Globais atualizados com sucesso!")

    with c2:
        if st.button("🤖 Atualizar IA & Market Report", use_container_width=True, help="Executa a análise macro da IA com Gemini e o Market Report de notícias diário."):
            import sys
            exec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'execution'))
            if exec_path not in sys.path: sys.path.append(exec_path)
            from ai_analyst import generate_macro_insight
            from market_report import generate_market_report
            
            with st.spinner("Atualizando IA Analista..."):
                try:
                    generate_macro_insight()
                    paths = ["ai_insight.json", "execution/ai_insight.json"]
                    for p in paths:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                new_insight = json.load(f)
                                supabase.table("app_state").upsert({
                                    "key": "ai_insight",
                                    "value": new_insight,
                                    "updated_at": "now()"
                                }).execute()
                                
                                try:
                                    res = supabase.table("app_state").select("value").eq("key", "ai_insight_history").execute()
                                    history = res.data[0]["value"] if res.data else []
                                    if not isinstance(history, list): history = []
                                    
                                    history.append({
                                        "sentiment": new_insight.get("sentiment", "NEUTRO"),
                                        "updated_at": new_insight.get("updated_at", ""),
                                        "id": int(time.time())
                                    })
                                    history = history[-5:]
                                    supabase.table("app_state").upsert({
                                        "key": "ai_insight_history",
                                        "value": history,
                                        "updated_at": "now()"
                                    }).execute()
                                except Exception as he:
                                    print(f"Erro histórico: {he}")
                            break
                    st.success("✅ Análise da IA atualizada!")
                except Exception as e:
                    st.error(f"Erro na IA Analista: {e}")
                    
            with st.spinner("Atualizando Market Report..."):
                try:
                    generate_market_report()
                    paths = ["market_report.json", "execution/market_report.json"]
                    for p in paths:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": "market_report",
                                    "value": json.load(f),
                                    "updated_at": "now()"
                                }).execute()
                            break
                    st.success("✅ Market Report atualizado!")
                except Exception as e:
                    st.error(f"Erro no Market Report: {e}")
            st.rerun()

    with c3:
        if st.button("📅 Atualizar Dados (Calendário, Fluxo, Focus)", use_container_width=True, help="Busca o calendário, fluxo B3 e Focus."):
            import sys
            exec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'execution'))
            if exec_path not in sys.path: sys.path.append(exec_path)
            
            from fetch_calendar import fetch_economic_calendar
            run_update_task("Calendário Econômico", fetch_economic_calendar, "calendario_economico", "✅ Calendário Econômico atualizado!")
            
            from fetch_foreign_flow import fetch_foreign_flow, save_flow_data
            def fetch_and_save_flow():
                records = fetch_foreign_flow()
                if records: save_flow_data(records, "fluxo_estrangeiro.json")
            run_update_task("Fluxo Estrangeiro", fetch_and_save_flow, "fluxo_estrangeiro_b3", "✅ Fluxo Estrangeiro atualizado!")
            
            from fetch_focus import fetch_focus_bcb, save_focus_data
            def fetch_and_save_focus():
                data = fetch_focus_bcb()
                if data: save_focus_data(data, "focus_bcb.json")
            run_update_task("Boletim Focus", fetch_and_save_focus, "boletim_focus", "✅ Boletim Focus atualizado!")

    st.markdown("---")
    st.markdown("### ☁️ Configurando Automação 24/7 Gratuita no GitHub")
    st.write("""
        Para que o seu site **nunca fique desatualizado** (mesmo com o seu computador desligado), configuramos um fluxo de trabalho automatizado (GitHub Actions) no seu repositório.
        
        Esse fluxo roda silenciosamente na nuvem a **cada hora**, buscando cotações globais, notícias e gerando relatórios de IA automaticamente.
        
        **Para ativá-lo, você só precisa cadastrar suas credenciais nas configurações do seu repositório no GitHub:**
        
        1. Acesse o seu repositório no **GitHub**.
        2. Vá em **Settings** (Configurações) > **Secrets and variables** > **Actions**.
        3. Clique em **New repository secret** (Novo segredo) e adicione as seguintes chaves:
           - Nome: `SUPABASE_URL` | Valor: *Sua URL do Supabase*
           - Nome: `SUPABASE_KEY` | Valor: *Sua service_role key do Supabase*
           - Nome: `GEMINI_API_KEY` | Valor: *Sua API Key do Google Gemini*
        
        Pronto! Com isso cadastrado, o GitHub atualizará o seu site automaticamente 24 horas por dia, 7 dias por semana, sem que você precise deixar nenhum código rodando no seu computador!
    """)

# Navegação na Barra Lateral
with st.sidebar:
    st.markdown("### 🧭 Navegação")
    page = st.radio("Ir para:", ["📉 Terminal de Trading", "🌎 Terminal Global", "📰 Market Report", "📊 Gráficos Avançados", "⚖️ Painel de Correlação", "⚙️ Painel de Controle"], label_visibility="collapsed")
    
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["🌍 MERCADOS", "📅 CALENDÁRIO"])
    with tab1: sidebar_mercados()
    with tab2: sidebar_calendario()

# Roteamento de Páginas
if page == "📉 Terminal de Trading":
    pagina_terminal()
elif page == "🌎 Terminal Global":
    pagina_terminal_global()
elif page == "📰 Market Report":
    pagina_market_report()
elif page == "📊 Gráficos Avançados":
    pagina_graficos()
elif page == "⚖️ Painel de Correlação":
    pagina_correlacao()
elif page == "⚙️ Painel de Controle":
    pagina_painel_controle()



