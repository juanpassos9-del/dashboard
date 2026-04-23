import streamlit as st
import streamlit_authenticator as stauth
import json
import os
import pandas as pd
from datetime import datetime
import time
from streamlit_autorefresh import st_autorefresh
from supabase import create_client, Client

# Configurações Estéticas (Bloomberg/TTS Style)
st.set_page_config(page_title="Terminal TTS | Inteligência", layout="wide")

# Inicializa Supabase
@st.cache_resource
def init_supabase() -> Client:
    # No Streamlit Cloud, as variáveis vêm do st.secrets
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
    key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
    return create_client(url, key)

supabase = init_supabase()

def fetch_app_state(key: str):
    """Busca o JSON armazenado no Supabase."""
    try:
        response = supabase.table("app_state").select("value").eq("key", key).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["value"]
    except Exception as e:
        pass
    return None

def apply_terminal_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap');
        html, body, [class*="css"] { font-family: 'Roboto Mono', monospace; background-color: #050505; color: #E0E0E0; }
        .main-card { background: #111111; border-left: 5px solid #FF9800; padding: 25px; border-radius: 5px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); margin-bottom: 20px; }
        .price-large { font-size: 3.5rem; font-weight: bold; color: #FFFFFF; }
        .label-small { font-size: 0.8rem; color: #888888; text-transform: uppercase; }
        .status-box { padding: 10px; border-radius: 4px; text-align: center; font-weight: bold; background: #1A1A1A; border: 1px solid #333; }
        .venda { color: #FF4B4B; border-color: #FF4B4B; }
        .compra { color: #00FFA3; border-color: #00FFA3; }
        </style>
    """, unsafe_allow_html=True)

apply_terminal_style()
def save_credentials(creds):
    """Salva a estrutura de usuários atualizada na nuvem."""
    try:
        data = {
            "key": "user_credentials",
            "value": creds,
            "updated_at": "now()"
        }
        supabase.table("app_state").upsert(data).execute()
    except Exception as e:
        pass

# Configuração Dinâmica de Usuários
saved_creds = fetch_app_state("user_credentials")

if saved_creds is None:
    # Primeira vez rodando na nuvem: Cria usuário Master
    credentials = {
        'usernames': {
            'admin': {
                'email': 'admin@test.com', 
                'name': 'Trader TTS', 
                'password': '123'
            }
        }
    }
    stauth.Hasher.hash_passwords(credentials)
    save_credentials(credentials)
else:
    credentials = saved_creds

authenticator = stauth.Authenticate(credentials, 'tts_terminal_cookie', 'auth_key_123', cookie_expiry_days=30)

# Layout: Se não estiver logado, exibe as abas Login/Registro
if not st.session_state.get("authentication_status"):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔒 Entrar", "📝 Novo Cadastro"])
        
        with tab_login:
            authenticator.login(location='main')
            
        with tab_register:
            try:
                # O registro atualiza a variável credentials na memória
                register_result = authenticator.register_user(clear_on_submit=True)
                if register_result and register_result[0]: # email_of_registered_user
                    st.success("Usuário registrado com sucesso! Volte na aba Entrar para logar.")
                    save_credentials(credentials)
            except Exception as e:
                st.error(f"Erro no cadastro: {e}")

# 3. Lógica Principal
if st.session_state["authentication_status"]:
    # Auto-refresh de 1 segundo (1000ms)
    st_autorefresh(interval=1000, key="data_refresh")
    
    authenticator.logout('Encerrar Sessão', 'sidebar')
    name = st.session_state["name"]
    
    # Barra Lateral - Informações Globais
    with st.sidebar:
        tab1, tab2 = st.tabs(["🌍 MERCADOS", "📅 CALENDÁRIO"])
        
        with tab1:
            global_categories = fetch_app_state("mercados_globais")
            if global_categories:
                for cat_name, assets in global_categories.items():
                    st.markdown(f"#### {cat_name}")
                    for item in assets:
                        color = "#00FFA3" if item['change'] >= 0 else "#FF4B4B"
                        st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #222; padding: 4px 0;">
                                <span style="font-size: 0.75rem; color: #AAA;">{item['name']}</span>
                                <span style="font-size: 0.8rem; font-weight: bold;">{item['price']}</span>
                                <span style="color: {color}; font-weight: bold; font-size: 0.8rem;">{item['change']}%</span>
                            </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
            else:
                st.info("Carregando mercados da nuvem...")

        with tab2:
            calendar_data = fetch_app_state("calendario_economico")
            if calendar_data:
                if not calendar_data:
                    st.write("Sem eventos relevantes hoje.")
                
                def parse_val(val):
                    try:
                        return float(val.replace('%', '').replace('K', '').replace('M', '').replace('B', '').strip())
                    except:
                        return None

                for event in calendar_data:
                    actual_raw = event.get('actual', '')
                    forecast_raw = event.get('forecast', '')
                    
                    # Lógica de seta
                    arrow = ""
                    actual_v = parse_val(actual_raw)
                    forecast_v = parse_val(forecast_raw)
                    
                    if actual_v is not None and forecast_v is not None:
                        if actual_v > forecast_v: arrow = "<span style='color:#00FFA3;'>▲</span>"
                        elif actual_v < forecast_v: arrow = "<span style='color:#FF4B4B;'>▼</span>"

                    st.markdown(f"""
                        <div style="border-bottom: 1px solid #333; padding: 8px 0;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-size: 0.7rem; color: #888;">{event['time']} | {event['currency']}</span>
                                <span style="font-size: 0.75rem; font-weight: bold;">{arrow} {actual_raw}</span>
                            </div>
                            <span style="font-size: 0.85rem; font-weight: bold;">{event['icon']} {event['event']}</span>
                            <div style="display: flex; gap: 10px; margin-top: 4px;">
                                <span style="font-size: 0.65rem; color: #666;">Proj: {forecast_raw if forecast_raw else '---'}</span>
                                <span style="font-size: 0.65rem; color: #666;">Ant: {event.get('previous', '---')}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Carregando calendário da nuvem...")

    dados_mercado_raw = fetch_app_state("dados_mercado")
    if dados_mercado_raw:
        try:
            data = dados_mercado_raw[0] if isinstance(dados_mercado_raw, list) else dados_mercado_raw
            
            def safe_format(value):
                try:
                    if value is None: return "---"
                    return f"{float(value):.3f}"
                except:
                    return str(value)

            st.markdown(f"### 📡 {data['symbol']} | {datetime.now().strftime('%H:%M:%S')}")
            c1, c2, c3 = st.columns([2, 1, 1])
        
            # Formatação de cores e strings
            change_val = data['change_percent']
            if isinstance(change_val, float):
                change_str = f"{change_val:.2%}"
            else:
                change_str = str(change_val)
            
            color_hex = '#00FFA3' if (isinstance(change_val, float) and change_val >= 0) else '#FF4B4B'

            with c1:
                st.markdown(f"""
                    <div class="main-card">
                        <div class="label-small">Último Preço</div>
                        <div class="price-large">{safe_format(data['last_price'])}</div>
                        <div style="color: {color_hex}">{change_str}</div>
                    </div>
                """, unsafe_allow_html=True)
                
            with c2:
                st.metric("VWAP", safe_format(data['vwap']))
                st.metric("Ajuste", safe_format(data['adjustment']))
                
            with c3:
                st.markdown(f"<div class='label-small'>Viés VWAP</div>", unsafe_allow_html=True)
                st.info(data['bias'])
                st.markdown(f"<div class='label-small'>Status Mercado</div>", unsafe_allow_html=True)
                st.warning(data['status'])

            # 2. Semáforo Direcional
            st.markdown("---")
            st.markdown("#### 🚥 SEMÁFORO DIRECIONAL")
            
            if "semaforo" in data:
                sem = data["semaforo"]
                
                def get_signal_color(text):
                    t = str(text).upper() if text else ""
                    if "VENDA" in t or "VENDER" in t or "VENDIDO" in t: 
                        return "background-color: #400000; color: #FF4B4B; border: 1px solid #FF4B4B;"
                    if "COMPRA" in t or "COMPRAR" in t or "COMPRADO" in t: 
                        return "background-color: #002611; color: #00FFA3; border: 1px solid #00FFA3;"
                    return "background-color: #1A1A1A; color: #E0E0E0; border: 1px solid #333;"

                # Layout em 3 banners
                s1, s2, s3 = st.columns(3)
                with s1: st.markdown(f"<div class='status-box' style='{get_signal_color(sem.get('direcao'))}'>DIREÇÃO DO DIA<br>{sem.get('direcao', '---')}</div>", unsafe_allow_html=True)
                with s2: st.markdown(f"<div class='status-box' style='{get_signal_color(sem.get('correlacao_rtd'))}'>CORRELAÇÕES RTD<br>{sem.get('correlacao_rtd', '---')}</div>", unsafe_allow_html=True)
                with s3: st.markdown(f"<div class='status-box' style='{get_signal_color(sem.get('correlacao_interna'))}'>CORRELAÇÃO INTERNA<br>{sem.get('correlacao_interna', '---')}</div>", unsafe_allow_html=True)
            else:
                st.warning("Dados do Semáforo não encontrados no arquivo de sincronização.")

            # 3. Correlações RTD | Juros x Dólar
            st.markdown("---")
            st.markdown("#### ⚖️ CORRELAÇÕES RTD | JUROS x DÓLAR")
            
            if "correlacoes" in data and data["correlacoes"]:
                df_corr = pd.DataFrame(data["correlacoes"], columns=["Fator", "Cotação RTD", "Var % / Δ", "Leitura", "Impacto WIN"])
                
                def style_corr(row):
                    val = str(row['Var % / Δ'])
                    if '-' in val: color = '#FF4B4B'
                    elif '0' in val: color = '#E0E0E0'
                    else: color = '#00FFA3'
                    return [f'color: {color}'] * 5

                st.dataframe(df_corr.style.apply(style_corr, axis=1), use_container_width=True, hide_index=True)

            # 4. Análise de Inteligência Artificial (Macro Insight)
            st.markdown("---")
            st.markdown("#### 🤖 INSIGHT DO ANALISTA (IA)")
            ai_data = fetch_app_state("ai_insight")
            if ai_data:
                # Lógica de Cores Semáforo
                sent = ai_data.get('sentiment', 'NEUTRO')
                if sent == "COMPRA": 
                    bg_color, border_color = "#002611", "#00FFA3"
                elif sent == "VENDA": 
                    bg_color, border_color = "#400000", "#FF4B4B"
                else: 
                    bg_color, border_color = "#111111", "#333"

                st.markdown(f"""
                    <div style="background: {bg_color}; border: 1px solid {border_color}; border-left: 5px solid {border_color}; padding: 20px; border-radius: 5px; color: #E0E0E0; font-size: 0.95rem; line-height: 1.6;">
                        <b style="color: {border_color}; text-transform: uppercase;">VIÉS IA: {sent}</b><br><br>
                        {ai_data['insight'].replace('\n', '<br>')}
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.info("Aguardando primeira análise do Analista IA na nuvem...")

            # 5. Escada de Níveis (Tabela Estilizada)
            
            if "escada" in data and data["escada"]:
                df_escada = pd.DataFrame(data["escada"], columns=["Nível", "Δ %", "Preço", "Δ p/ Último"])
                
                # Formatação numérica
                for col in ["Δ %", "Preço", "Δ p/ Último"]:
                    df_escada[col] = df_escada[col].apply(lambda x: f"{float(x):.2f}" if x is not None else "---")

                def color_rows(row):
                    val = str(row['Nível'])
                    if 'AJUSTE' in val.upper(): return ['background-color: #262626; color: #FF9800; font-weight: bold'] * 4
                    if '-' in val: return ['background-color: #0A1F13; color: #00FFA3'] * 4 # Tons de verde para baixo
                    return ['background-color: #1F0A0A; color: #FF4B4B'] * 4 # Tons de vermelho para cima

                st.table(df_escada.style.apply(color_rows, axis=1))

            st.markdown("---")

        except Exception as e:
            st.error(f"Erro ao processar dados: {e}")
    else:
        st.info("Aguardando conexão com o Supabase na nuvem... (Verifique se a Ponte está rodando)")

