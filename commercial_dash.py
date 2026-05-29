import streamlit as st
import streamlit.components.v1 as components

import os
import html
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

@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_global_markets():
    """Busca cotacoes globais direto da fonte com cache curto para o Streamlit Cloud."""
    try:
        from execution.fetch_global_markets import fetch_global_data
        return fetch_global_data(save_file=False)
    except Exception as e:
        print(f"[ERROR] Live global markets: {e}")
        return None

def get_global_markets_data():
    """Usa dados ao vivo quando possivel e Supabase como fallback."""
    live_data = fetch_live_global_markets()
    if live_data:
        return live_data
    return fetch_app_state("mercados_globais")

def get_calendar_data():
    """Usa o snapshot sincronizado no Supabase para nao bloquear a renderizacao."""
    return fetch_app_state("calendario_economico")

@st.cache_data(ttl=5, show_spinner=False)
def load_bloomberg_news_feed(refresh_nonce: int = 0):
    """Monta o feed pesado com cache para evitar travamentos no rerender."""
    del refresh_nonce
    news_sources = []
    warnings = []
    news_list = fetch_app_state("financial_juice_news") or []
    if news_list:
        news_sources.append("Financial Juice")

    try:
        from execution.fetch_financial_juice import fetch_financial_juice_news
        live_news = fetch_financial_juice_news(
            limit=40,
            min_network_interval=5,
            fast_mode=True,
        )
        if live_news:
            news_list.extend(live_news)
            news_sources.append("Financial Juice RSS direto")
    except Exception as e:
        warnings.append(f"Financial Juice direto indisponivel: {e}")

    try:
        from execution.fetch_gdelt_news import fetch_gdelt_news
        gdelt_news = fetch_gdelt_news(limit=20, timespan="3h")
        if gdelt_news:
            news_list.extend(gdelt_news)
            news_sources.append("GDELT")
    except Exception as e:
        warnings.append(f"GDELT indisponivel: {e}")

    try:
        from execution.fetch_source_news import fetch_source_news
        source_news = fetch_source_news(limit=25, timespan="6h")
        if source_news:
            news_list.extend(source_news)
            news_sources.append("Reuters/Bloomberg/CNBC/SCMP")
    except Exception as e:
        warnings.append(f"Fontes editoriais indisponiveis: {e}")

    seen_news = set()
    unique_news = []
    for item in news_list:
        key = (item.get("link") or item.get("title_en") or item.get("title_pt") or "").strip().lower()[:160]
        if not key or key in seen_news:
            continue
        seen_news.add(key)
        unique_news.append(item)

    def news_sort_key(item):
        try:
            return float(item.get("timestamp") or 0)
        except Exception:
            return 0

    unique_news = sorted(unique_news, key=news_sort_key, reverse=True)
    try:
        from execution.fetch_financial_juice import ensure_brazil_time, ensure_portuguese_fields
        for item in unique_news:
            ensure_portuguese_fields(item)
            ensure_brazil_time(item)
    except Exception as e:
        warnings.append(f"Normalizacao rapida indisponivel: {e}")

    return unique_news, news_sources, warnings, datetime.now().strftime("%H:%M:%S")

@st.fragment(run_every=5)
def render_bloomberg_news_feed_fragment():
    """Atualiza somente o feed de noticias, sem redesenhar o terminal inteiro."""
    def esc(value) -> str:
        return html.escape(str(value or ""), quote=True)

    def infer_tags(item) -> list[str]:
        text = f"{item.get('title_pt', '')} {item.get('title_en', '')} {item.get('summary', '')}".lower()
        rules = [
            ("Fed", ["fed", "fomc", "powell"]),
            ("Inflacao", ["inflacao", "inflação", "inflation", "cpi", "pce"]),
            ("Treasuries", ["treasury", "treasuries", "yield", "yields", "titulos", "títulos"]),
            ("USD", ["dolar", "dólar", "dollar", "usd", "dxy"]),
            ("Energia", ["petroleo", "petróleo", "oil", "crude", "brent", "wti"]),
            ("Geopolitica", ["ira", "irã", "iran", "israel", "ataque", "war", "guerra"]),
            ("China", ["china", "pboc", "yuan"]),
            ("Brasil", ["brasil", "bcb", "copom", "real", "ibovespa"]),
        ]
        tags = [label for label, needles in rules if any(needle in text for needle in needles)]
        return tags[:4] or ["Macro"]

    def market_impact(item):
        text = (
            f"{item.get('title_pt', '')} {item.get('title_en', '')} "
            f"{item.get('summary_pt', '')} {item.get('summary', '')}"
        ).lower()
        source = str(item.get("source", "")).lower()
        score = 0
        reasons = []
        rules = [
            (5, "Banco Central", ["fed", "fomc", "powell", "ecb", "bce", "boj", "boe", "copom", "bcb", "juros", "interest rate"]),
            (5, "Inflacao", ["cpi", "pce", "ppi", "inflacao", "inflação", "inflation", "core prices"]),
            (4, "Treasuries", ["treasury", "treasuries", "yield", "yields", "titulos", "títulos", "rendimentos"]),
            (4, "USD", ["dolar", "dólar", "dollar", "usd", "dxy", "forex", "cambio", "câmbio"]),
            (4, "Energia", ["petroleo", "petróleo", "oil", "crude", "brent", "wti", "opep", "opec"]),
            (4, "Geopolitica", ["ira", "irã", "iran", "israel", "china", "russia", "rússia", "guerra", "war", "ataque", "sanctions", "sanções"]),
            (4, "Dados Macro", ["payroll", "emprego", "jobs", "jobless", "gdp", "pib", "retail sales", "pmi", "ism"]),
            (3, "Bolsas", ["s&p", "nasdaq", "dow", "stocks", "acoes", "ações", "indices", "índices", "futuros"]),
            (3, "Emergentes", ["brazil", "brasil", "real", "ibovespa", "ewz", "eem", "china", "yuan"]),
        ]
        for weight, label, keywords in rules:
            if any(keyword in text for keyword in keywords):
                score += weight
                reasons.append(label)
        if any(word in text for word in ["breaking", "urgente", "alerta", "unexpected", "surpresa", "forecast", "previsao", "previsão"]):
            score += 3
            reasons.append("Surpresa")
        if any(name in source for name in ["financial", "reuters", "bloomberg", "cnbc"]):
            score += 1

        unique_reasons = []
        for reason in reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)
        if score >= 8:
            return "high", "ALTO IMPACTO", unique_reasons[:3]
        if score >= 4:
            return "medium", "IMPACTO", unique_reasons[:3]
        return "low", "", unique_reasons[:2]

    st.caption("Somente este feed atualiza a cada 5s. O restante do terminal permanece estavel.")
    if st.button("Atualizar feed agora", use_container_width=True, key="bb_refresh_news_fast"):
        load_bloomberg_news_feed.clear()

    filter_term = st.text_input(
        "Filtrar noticias",
        placeholder="Digite Fed, dolar, petroleo, Brasil...",
        label_visibility="collapsed",
        key="bb_news_filter_fast",
    ).strip()

    news_list, news_sources, news_warnings, feed_loaded_at = load_bloomberg_news_feed(0)
    for warning in news_warnings[:2]:
        st.warning(warning)
    if not news_list:
        st.info("Aguardando noticias em tempo real.")
        return

    if filter_term:
        term = filter_term.lower()
        filtered_news = [
            item for item in news_list
            if term in item.get("title_pt", "").lower()
            or term in item.get("title_en", "").lower()
            or term in item.get("summary_pt", "").lower()
            or term in item.get("summary", "").lower()
        ]
    else:
        filtered_news = news_list

    if "selected_news_id" not in st.session_state:
        st.session_state.selected_news_id = None
    if not st.session_state.selected_news_id and filtered_news:
        st.session_state.selected_news_id = filtered_news[0].get("id")

    if not filtered_news:
        st.info("Nenhuma manchete correspondente encontrada.")
        return

    cards = []
    for idx, item in enumerate(filtered_news[:45]):
        is_featured = item.get("id") == st.session_state.selected_news_id or idx == 0
        impact_level, impact_label, impact_reasons = market_impact(item)
        title_pt = esc(item.get("title_pt") or item.get("title_en") or "---")
        summary_raw = item.get("summary_pt") or item.get("title_pt") or item.get("summary") or ""
        summary = esc(summary_raw)
        published = esc(item.get("published_str", "00:00"))
        source = esc(item.get("source", "Financial Juice"))
        link = esc(item.get("link", "#"))
        icon_text = esc("FJ" if source == "Financial Juice" else source[:2].upper())
        tags_html = "".join(f'<span class="bb-news-tag">{esc(tag)}</span>' for tag in infer_tags(item))
        impact_badge = (
            f'<span class="bb-impact-badge {impact_level}">{esc(impact_label)}</span>'
            if impact_label
            else ""
        )
        reason_tags = "".join(f'<span class="bb-news-tag">{esc(reason)}</span>' for reason in impact_reasons)
        featured_class = " bb-featured" if is_featured else ""
        impact_class = f" bb-impact-{impact_level}" if impact_level in ["high", "medium"] else ""
        close_html = '<span class="bb-news-close">x</span>' if is_featured else ""
        summary_html = (
            f'<div class="bb-news-summary">{summary}</div>'
            if summary and summary != title_pt
            else ""
        )
        cards.append(
            f'<div class="bb-news-card{featured_class}{impact_class}">'
            f'{close_html}'
            f'<div class="bb-news-rail"></div>'
            f'<div class="bb-news-icon">{icon_text}</div>'
            f'<div class="bb-news-content">'
            f'<div class="bb-news-title">{title_pt}</div>'
            f'{summary_html}'
            f'<div class="bb-news-meta">'
            f'<span>{published}</span><span>{source}</span>{impact_badge}{reason_tags}{tags_html}'
            f'</div>'
            f'</div>'
            f'<a class="bb-news-link" href="{link}" target="_blank" rel="noopener noreferrer">↗</a>'
            f'</div>'
        )

    feed_header = (
        f'<div class="bb-feed-header">'
        f'<span>Feed de Noticias em Tempo Real</span>'
        f'<span class="bb-live-pill"><span class="bb-status-led"></span>LIVE 5s - {esc(" + ".join(news_sources) or "Fontes")} - {len(filtered_news)} noticias</span>'
        f'</div>'
    )
    st.markdown(f'<div class="bb-news-feed">{feed_header}{"".join(cards)}</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="bb-status-footer">
        <div>
            <span class="bb-status-led"></span>
            <span style="color: #00FFA3; font-weight: bold;">LIVE FEED</span>
            &nbsp;|&nbsp; Somente o feed atualiza a cada 5s
            &nbsp;|&nbsp; Origem: {esc(" + ".join(news_sources) or "Fontes")}
        </div>
        <div>
            Ultimo Refresh: {feed_loaded_at}
            &nbsp;|&nbsp; Fontes: Financial Juice + Reuters + Bloomberg + CNBC + SCMP + GDELT
        </div>
    </div>
    """, unsafe_allow_html=True)

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

# ── Persistência de Trades Manuais ─────────────────────────────────────────
_TRADES_KEY  = "risk_manual_trades"
_TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp", "manual_trades.json")

def load_manual_trades() -> list:
    """Carrega trades do Supabase; usa cache local como fallback."""
    # Tenta Supabase primeiro
    if supabase:
        try:
            resp = supabase.table("app_state").select("value").eq("key", _TRADES_KEY).execute()
            if resp.data and len(resp.data) > 0:
                val = resp.data[0]["value"]
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    import json as _json
                    return _json.loads(val)
        except Exception as e:
            print(f"[WARN] load_manual_trades supabase: {e}")
    # Fallback local
    try:
        if os.path.exists(_TRADES_FILE):
            import json as _json
            with open(_TRADES_FILE, "r", encoding="utf-8") as f:
                return _json.load(f)
    except Exception as e:
        print(f"[WARN] load_manual_trades local: {e}")
    return []

def save_manual_trades(trades: list):
    """Salva trades no Supabase e em cache local (.tmp/manual_trades.json)."""
    import json as _json
    # Salva local (backup)
    try:
        os.makedirs(os.path.dirname(_TRADES_FILE), exist_ok=True)
        with open(_TRADES_FILE, "w", encoding="utf-8") as f:
            _json.dump(trades, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] save_manual_trades local: {e}")
    # Salva Supabase
    if supabase:
        try:
            supabase.table("app_state").upsert({
                "key": _TRADES_KEY,
                "value": trades,
                "updated_at": "now()"
            }).execute()
        except Exception as e:
            print(f"[WARN] save_manual_trades supabase: {e}")

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

@st.fragment(run_every=30)
def painel_tickers_topo():
    """Mini cards de cotações globais no topo do terminal."""
    global_data = get_global_markets_data()
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
    """Renderiza o Market Report com os tres registros do dia."""
    daily_data = fetch_app_state("market_report_daily")
    latest_report = fetch_app_state("market_report")
    reports = []
    if isinstance(daily_data, dict):
        reports = daily_data.get("reports") or []
    if not reports and latest_report:
        reports = [latest_report]

    st.markdown("---")
    st.markdown("### Market Report")
    st.caption("Atualizacao automatica: 07:05, 13:05 e 19:05 (Sao Paulo). Os reports ficam registrados ate virar o dia.")

    if st.button("Atualizar analise agora", type="primary", use_container_width=True, key="market_report_refresh_now"):
        if not supabase:
            st.error("Supabase indisponivel para salvar a analise.")
        else:
            with st.spinner("Gerando nova analise do Market Report..."):
                try:
                    import json as _json
                    from execution.market_report import generate_market_report

                    try:
                        for secret_key in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                            secret_value = st.secrets.get(secret_key, "")
                            if secret_value:
                                os.environ[secret_key] = secret_value
                    except Exception:
                        pass

                    generated = generate_market_report(force=True)
                    if not generated:
                        st.warning("Nao foi possivel gerar uma nova analise agora.")
                    else:
                        for key, paths in {
                            "market_report": ["market_report.json", "execution/market_report.json"],
                            "market_report_daily": ["market_report_daily.json", "execution/market_report_daily.json"],
                        }.items():
                            for path in paths:
                                if os.path.exists(path):
                                    with open(path, "r", encoding="utf-8") as f:
                                        supabase.table("app_state").upsert({
                                            "key": key,
                                            "value": _json.load(f),
                                            "updated_at": "now()",
                                        }).execute()
                                    break
                        st.success("Analise atualizada.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao atualizar Market Report: {e}")

    if not reports:
        st.info("Nenhum Market Report registrado para hoje ainda.")
        return

    slot_order = {"manha": 1, "tarde": 2, "noite": 3}
    reports = sorted(reports, key=lambda item: slot_order.get(item.get("slot"), 99))
    latest = reports[-1]

    st.markdown(f"""
        <div style="background: #0A0A0A; border: 1px solid #1a1a1a; border-top: 4px solid #FF9800; padding: 22px; border-radius: 8px; margin: 15px 0;">
            <div style="display: flex; justify-content: space-between; gap: 15px; align-items: center; margin-bottom: 12px;">
                <h3 style="margin: 0; color: #FF9800; font-family: 'Inter', sans-serif;">ULTIMO REPORT: {sanitize_text(latest.get('slot_label', 'Market Report')).upper()}</h3>
                <span style="color: #777; font-size: 0.75rem; font-family: 'Roboto Mono', monospace;">{latest.get('updated_at', '---')}</span>
            </div>
            <div style="color: #CCC; font-size: 0.9rem; line-height: 1.6; font-family: 'Inter', sans-serif;">
                {sanitize_text(latest.get('report', '')).replace(chr(10), '<br>')}
            </div>
        </div>
    """, unsafe_allow_html=True)

    tab_labels = [
        f"{report.get('slot_label', report.get('slot', 'Report'))} - {report.get('updated_at', '---')[-8:-3]}"
        for report in reports
    ]
    tabs = st.tabs(tab_labels)
    for tab, report in zip(tabs, reports):
        with tab:
            st.markdown(
                f"**Janela:** `{report.get('slot_window', '---')}`  "
                f"**Atualizado:** `{report.get('updated_at', '---')}`"
            )
            st.markdown(sanitize_text(report.get("report", "")))


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

@st.fragment(run_every=30)
def painel_topo_global():
    """Cards de destaque para o mercado global."""
    global_data = get_global_markets_data()
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

@st.fragment(run_every=30)
def painel_corpo_global():
    """Tabelas detalhadas de mercados globais."""
    global_data = get_global_markets_data()
    if not global_data: return
    
    categories = global_data.get("categories", global_data)

    def styled_change_dataframe(df):
        def color_change(val):
            try:
                v = float(val)
                color = '#00FFA3' if v >= 0 else '#FF4B4B'
                return f'color: {color}; font-weight: bold'
            except Exception:
                return ''

        styler = df.style
        if hasattr(styler, "map"):
            return styler.map(color_change, subset=['Var %'])
        return styler.applymap(color_change, subset=['Var %'])
    
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
            st.dataframe(styled_change_dataframe(df), hide_index=True, use_container_width=True)
        
        if i + 1 < len(cat_names):
            with c2:
                cat = cat_names[i+1]
                st.markdown(f"##### {cat}")
                assets = categories[cat]
                df = pd.DataFrame(assets)[['name', 'price', 'change']]
                df.columns = ['Ativo', 'Preço', 'Var %']
                st.dataframe(styled_change_dataframe(df), hide_index=True, use_container_width=True)

def pagina_terminal_bloomberg():
    """Pagina do Terminal Bloomberg de noticias com atualizacao leve e cacheada."""
    def esc(value) -> str:
        return html.escape(str(value or ""), quote=True)

    def infer_tags(item) -> list[str]:
        text = f"{item.get('title_pt', '')} {item.get('title_en', '')} {item.get('summary', '')}".lower()
        rules = [
            ("Fed", ["fed", "fomc", "powell"]),
            ("Inflação", ["inflação", "inflation", "cpi", "pce"]),
            ("Títulos dos EUA", ["treasury", "treasuries", "yield", "yields", "títulos"]),
            ("Índices dos EUA", ["s&p", "nasdaq", "dow", "índices", "stocks", "ações"]),
            ("USD", ["dólar", "dollar", "usd", "dxy"]),
            ("Energia", ["petróleo", "oil", "crude", "brent", "wti"]),
            ("Geopolítica", ["irã", "iran", "israel", "ataque", "war", "guerra"]),
            ("China", ["china", "pboc", "yuan"]),
            ("Brasil", ["brasil", "bcb", "copom", "real", "ibovespa"]),
        ]
        tags = [label for label, needles in rules if any(needle in text for needle in needles)]
        return tags[:4] or ["Macro"]

    def market_impact(item):
        text = (
            f"{item.get('title_pt', '')} {item.get('title_en', '')} "
            f"{item.get('summary_pt', '')} {item.get('summary', '')}"
        ).lower()
        source = str(item.get("source", "")).lower()
        score = 0
        reasons = []

        rules = [
            (5, "Banco Central", ["fed", "fomc", "powell", "williams", "jefferson", "musalem", "bce", "ecb", "boj", "boe", "copom", "bcb", "juros", "taxa de juros", "interest rate"]),
            (5, "Inflação", ["cpi", "pce", "ppi", "inflação", "inflation", "núcleo", "core prices"]),
            (4, "Treasuries", ["treasury", "treasuries", "yield", "yields", "títulos dos eua", "rendimentos"]),
            (4, "USD", ["dólar", "dollar", "usd", "dxy", "forex", "câmbio"]),
            (4, "Energia", ["petróleo", "oil", "crude", "brent", "wti", "opep", "opec", "hormuz"]),
            (4, "Geopolítica", ["irã", "iran", "israel", "china", "russia", "rússia", "guerra", "war", "ataque", "missile", "sanções"]),
            (4, "Dados Macro", ["payroll", "emprego", "jobs", "jobless", "gdp", "pib", "retail sales", "pmi", "ism"]),
            (3, "Bolsas", ["s&p", "nasdaq", "dow", "stocks", "ações", "índices", "futuros"]),
            (3, "Emergentes", ["brazil", "brasil", "real", "ibovespa", "ewz", "eem", "china", "yuan"]),
            (3, "Cripto", ["bitcoin", "crypto", "ethereum", "cripto"]),
        ]

        for weight, label, keywords in rules:
            if any(keyword in text for keyword in keywords):
                score += weight
                reasons.append(label)

        if any(word in text for word in ["breaking", "urgente", "alerta", "unexpected", "surpresa", "forecast", "previsão", "acima do esperado", "abaixo do esperado"]):
            score += 3
            reasons.append("Surpresa")

        if any(name in source for name in ["financial", "reuters", "bloomberg", "cnbc"]):
            score += 1

        unique_reasons = []
        for reason in reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)

        if score >= 8:
            return "high", "ALTO IMPACTO", unique_reasons[:3]
        if score >= 4:
            return "medium", "IMPACTO", unique_reasons[:3]
        return "low", "", unique_reasons[:2]
    
    # CSS Customizado Exclusivo para o Terminal Bloomberg
    st.markdown("""
    <style>
        .bb-terminal-container {
            background-color: #000000 !important;
            color: #00FF00 !important;
            font-family: 'Consolas', 'Courier New', monospace !important;
            padding: 1.5rem;
            border-radius: 8px;
            border: 2px solid #222222;
            margin-bottom: 20px;
        }
        
        .bb-ticker-bar {
            background-color: #000000;
            border: 1px solid #222222;
            padding: 0.5rem;
            border-radius: 6px;
            display: flex;
            overflow-x: auto;
            white-space: nowrap;
            margin-bottom: 15px;
            font-family: 'Consolas', monospace;
            font-size: 0.8rem;
        }
        
        .bb-ticker-item {
            margin-right: 1.5rem;
            display: inline-block;
        }
        
        .bb-ticker-up {
            color: #00FFA3 !important;
            font-weight: bold;
        }
        
        .bb-ticker-down {
            color: #FF4B4B !important;
            font-weight: bold;
        }

        .bb-quote-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 18px 14px;
            margin: 14px 0 18px;
        }

        .bb-quote-panel {
            min-width: 0;
        }

        .bb-quote-title {
            color: #f4f7fb;
            font-family: "Inter", "Segoe UI", Arial, sans-serif;
            font-size: 0.88rem;
            font-weight: 900;
            letter-spacing: 0;
            margin: 0 0 10px;
            text-transform: uppercase;
        }

        .bb-quote-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            overflow: hidden;
            border: 1px solid #26303c;
            border-radius: 7px;
            background: #0b1016;
            font-family: "Roboto Mono", "Consolas", monospace;
            font-size: 0.68rem;
        }

        .bb-quote-table th {
            background: #1a1f27;
            color: #aab6c5;
            font-weight: 500;
            text-align: left;
            padding: 7px 6px;
            border-right: 1px solid #303846;
            border-bottom: 1px solid #303846;
        }

        .bb-quote-table th:last-child,
        .bb-quote-table td:last-child {
            border-right: 0;
            text-align: right;
        }

        .bb-quote-table td {
            color: #f3f7fb;
            padding: 6px;
            border-right: 1px solid #26303c;
            border-bottom: 1px solid #202833;
            font-weight: 800;
            white-space: nowrap;
        }

        .bb-quote-table tr:last-child td {
            border-bottom: 0;
        }

        .bb-quote-table td:nth-child(2) {
            text-align: right;
        }

        .bb-quote-table .quote-up {
            color: #00ffa3;
        }

        .bb-quote-table .quote-down {
            color: #ff4b4b;
        }

        .bb-quote-table .quote-flat {
            color: #cbd5e1;
        }
        
        .bb-news-feed {
            position: sticky;
            top: 0.75rem;
            max-height: calc(100vh - 225px);
            min-height: 420px;
            overflow-y: auto;
            background: #090d12;
            border: 1px solid #263443;
            border-radius: 7px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }

        .bb-feed-header {
            position: sticky;
            top: 0;
            z-index: 2;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 7px 10px;
            background: #151f2a;
            border-bottom: 1px solid #283544;
            color: #9aa6b2;
            font-family: "Consolas", monospace;
            font-size: 0.75rem;
            text-transform: uppercase;
        }

        .bb-live-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            color: #00FFA3;
            font-weight: 800;
        }

        .bb-news-card {
            position: relative;
            display: grid;
            grid-template-columns: 6px 34px minmax(0, 1fr) 22px;
            gap: 9px;
            padding: 9px 10px 8px 0;
            min-height: 64px;
            background: #18222d;
            border-bottom: 1px solid #0c1218;
            color: #d8dee7;
            font-family: "Inter", "Segoe UI", Arial, sans-serif;
        }

        .bb-news-card.bb-featured {
            background: #1f3141;
            min-height: 124px;
        }

        .bb-news-rail {
            width: 6px;
            align-self: stretch;
            background: #34495e;
        }

        .bb-news-card.bb-impact-high {
            background: #2a181b;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 0 0 1px rgba(255,59,48,0.18);
        }

        .bb-news-card.bb-impact-medium {
            background: #261f12;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 0 0 1px rgba(255,153,0,0.14);
        }

        .bb-news-card.bb-impact-high .bb-news-rail {
            background: #ff3b30;
        }

        .bb-news-card.bb-impact-medium .bb-news-rail {
            background: #ff9900;
        }

        .bb-news-card.bb-impact-high .bb-news-title {
            color: #ff6b5f;
            font-weight: 800;
        }

        .bb-news-card.bb-impact-medium .bb-news-title {
            color: #ffb24a;
        }

        .bb-news-icon {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: 4px;
            background: #18222d;
            border: 3px solid #36d5f5;
            color: #d8f8ff;
            font-size: 0.62rem;
            font-weight: 900;
            letter-spacing: 0.2px;
        }

        .bb-news-title {
            color: #edf2f7;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.3;
            margin-bottom: 3px;
        }

        .bb-news-card:not(.bb-featured) .bb-news-title {
            font-weight: 500;
        }

        .bb-news-summary {
            color: #d1d8e0;
            font-size: 0.88rem;
            line-height: 1.42;
            margin-top: 4px;
        }

        .bb-news-card:not(.bb-featured) .bb-news-summary {
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .bb-news-meta {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
            color: #9aa6b2;
            font-size: 0.76rem;
            line-height: 1.25;
        }

        .bb-news-tag {
            display: inline-flex;
            align-items: center;
            border-radius: 4px;
            padding: 1px 6px;
            background: #303946;
            color: #b7c0ca;
            font-size: 0.7rem;
            line-height: 1.45;
        }

        .bb-impact-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 0.68rem;
            line-height: 1.45;
            font-weight: 900;
            letter-spacing: 0.3px;
        }

        .bb-impact-badge.high {
            background: #4a1111;
            color: #ff6b5f;
            border: 1px solid rgba(255,59,48,0.35);
        }

        .bb-impact-badge.medium {
            background: #3d2804;
            color: #ffb24a;
            border: 1px solid rgba(255,153,0,0.35);
        }

        .bb-news-link {
            color: #aeb8c4 !important;
            text-decoration: none !important;
            align-self: end;
            justify-self: center;
            font-size: 0.9rem;
            opacity: 0.85;
        }

        .bb-news-link:hover {
            color: #36d5f5 !important;
            opacity: 1;
        }

        .bb-news-close {
            position: absolute;
            top: 4px;
            right: 6px;
            color: #bac4ce;
            font-size: 1.2rem;
            font-weight: 800;
            line-height: 1;
        }
        
        .bb-status-footer {
            background-color: #050505;
            border: 1px solid #222222;
            padding: 0.4rem 1rem;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            font-size: 0.75rem;
            color: #6b7280;
            margin-top: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        @media (max-width: 900px) {
            .bb-quote-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 18px;
            }
            .bb-status-footer {
                display: block;
            }
        }

        @media (max-width: 640px) {
            .bb-quote-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .bb-status-led {
            display: inline-block;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: #00FFA3;
            box-shadow: 0 0 6px #00FFA3;
            margin-right: 5px;
            animation: bb-led-pulse 1.2s infinite;
        }
        
        @keyframes bb-led-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
    </style>
    """, unsafe_allow_html=True)

    global_data = get_global_markets_data()

    def render_quote_grids(data):
        if not data:
            st.info("Aguardando grades de cotacoes globais.")
            return

        categories = data.get("categories", data)
        preferred_order = [
            "📊 ÍNDICES",
            "💱 MOEDAS / FOREX",
            "🇺🇸 ETFs SETORIAIS",
            "🌏 EMERGENTES & BRASIL",
            "🇺🇸 TREASURIES (YIELDS)",
            "🛢️ COMMODITIES & CRIPTO",
        ]

        def find_category(name):
            if name in categories:
                return categories.get(name)
            normalized = name.split(" ", 1)[-1].lower()
            for key, value in categories.items():
                if str(key).split(" ", 1)[-1].lower() == normalized:
                    return value
            return None

        def fmt_num(value):
            try:
                return f"{float(value):.6f}"
            except Exception:
                return "---"

        panels = []
        for category_name in preferred_order:
            assets = find_category(category_name)
            if not isinstance(assets, list) or not assets:
                continue

            rows = []
            for asset in assets:
                name = esc(asset.get("name", "---"))
                price = fmt_num(asset.get("price"))
                try:
                    change_value = float(asset.get("change", 0))
                    change = f"{change_value:.6f}"
                    change_class = "quote-up" if change_value > 0 else "quote-down" if change_value < 0 else "quote-flat"
                except Exception:
                    change = "---"
                    change_class = "quote-flat"
                rows.append(
                    f"<tr><td>{name}</td><td>{price}</td><td class='{change_class}'>{change}</td></tr>"
                )

            panels.append(
                f"<section class='bb-quote-panel'>"
                f"<h3 class='bb-quote-title'>{esc(category_name)}</h3>"
                f"<table class='bb-quote-table'>"
                f"<thead><tr><th>Ativo</th><th>Preço</th><th>Var %</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody>"
                f"</table>"
                f"</section>"
            )

        if panels:
            st.markdown(f"<div class='bb-quote-grid'>{''.join(panels)}</div>", unsafe_allow_html=True)

    render_bloomberg_news_feed_fragment()
    render_quote_grids(global_data)
    return

    st.caption("Atualizacao automatica reduzida para 60s para manter a pagina responsiva. Use o filtro para focar nas manchetes relevantes.")
    if st.button("Atualizar feed agora", use_container_width=True, key="bb_refresh_news"):
        load_bloomberg_news_feed.clear()
    filter_term = st.text_input(
        "Filtrar noticias",
        placeholder="Digite Fed, dolar, petroleo, Brasil...",
        label_visibility="collapsed",
        key="bb_news_filter",
    ).strip()

    news_list, news_sources, news_warnings, feed_loaded_at = load_bloomberg_news_feed(0)
    for warning in news_warnings[:2]:
        st.warning(warning)

    if not news_list:
        st.info("Aguardando noticias em tempo real.")
        return

    # Filtra notícias se houver termo ativo
    if filter_term:
        filtered_news = [
            item for item in news_list
            if filter_term.lower() in item.get("title_pt", "").lower()
            or filter_term.lower() in item.get("title_en", "").lower()
        ]
    else:
        filtered_news = news_list

    high_count = sum(1 for item in filtered_news if market_impact(item)[0] == "high")
    medium_count = sum(1 for item in filtered_news if market_impact(item)[0] == "medium")
    latest_time = esc(filtered_news[0].get("published_str", "--:--")) if filtered_news else "--:--"
    st.markdown(
        f'<div class="bb-news-toolbar">'
        f'<div class="bb-news-stat"><span>Noticias</span><strong>{len(filtered_news)}</strong></div>'
        f'<div class="bb-news-stat"><span>Alto impacto</span><strong style="color:#ff6b5f;">{high_count}</strong></div>'
        f'<div class="bb-news-stat"><span>Impacto medio</span><strong style="color:#ffb24a;">{medium_count}</strong></div>'
        f'<div class="bb-news-stat"><span>Mais recente</span><strong>{latest_time}</strong></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Notícia ativa
    if "selected_news_id" not in st.session_state:
        st.session_state.selected_news_id = None
    if not st.session_state.selected_news_id and filtered_news:
        st.session_state.selected_news_id = filtered_news[0]["id"]

    # 3. Feed de Notícias fixo
    if filtered_news:
        cards = []
        for idx, item in enumerate(filtered_news[:45]):
            is_featured = item.get("id") == st.session_state.selected_news_id or idx == 0
            impact_level, impact_label, impact_reasons = market_impact(item)
            title_pt = esc(item.get("title_pt") or item.get("title_en") or "---")
            summary_raw = item.get("summary_pt") or item.get("title_pt") or item.get("summary") or ""
            summary = esc(summary_raw)
            published = esc(item.get("published_str", "00:00"))
            source = esc(item.get("source", "Financial Juice"))
            link = esc(item.get("link", "#"))
            icon_text = esc("FJ" if source == "Financial Juice" else source[:2].upper())
            tags_html = "".join(f'<span class="bb-news-tag">{esc(tag)}</span>' for tag in infer_tags(item))
            impact_badge = (
                f'<span class="bb-impact-badge {impact_level}">{esc(impact_label)}</span>'
                if impact_label
                else ""
            )
            reason_tags = "".join(f'<span class="bb-news-tag">{esc(reason)}</span>' for reason in impact_reasons)
            featured_class = " bb-featured" if is_featured else ""
            impact_class = f" bb-impact-{impact_level}" if impact_level in ["high", "medium"] else ""
            close_html = '<span class="bb-news-close">×</span>' if is_featured else ""
            summary_html = (
                f'<div class="bb-news-summary">{summary}</div>'
                if summary and summary != title_pt
                else ""
            )

            cards.append(
                f'<div class="bb-news-card{featured_class}{impact_class}">'
                f'{close_html}'
                f'<div class="bb-news-rail"></div>'
                f'<div class="bb-news-icon">{icon_text}</div>'
                f'<div class="bb-news-content">'
                f'<div class="bb-news-title">{title_pt}</div>'
                f'{summary_html}'
                f'<div class="bb-news-meta">'
                f'<span>{published}</span><span>{source}</span>{impact_badge}{reason_tags}{tags_html}'
                f'</div>'
                f'</div>'
                f'<a class="bb-news-link" href="{link}" target="_blank" rel="noopener noreferrer">↗</a>'
                f'</div>'
            )
        feed_header = (
            f'<div class="bb-feed-header">'
            f'<span>Feed de Noticias em Tempo Real</span>'
            f'<span class="bb-live-pill"><span class="bb-status-led"></span>LIVE • {esc(" + ".join(news_sources) or "Fontes")} • {len(filtered_news)} noticias</span>'
            f'</div>'
        )
        st.markdown(f'<div class="bb-news-feed">{feed_header}{"".join(cards)}</div>', unsafe_allow_html=True)
    else:
        st.info("Nenhuma manchete correspondente encontrada.")

    # 4. Status Bar inferior
    st.markdown(f"""
    <div class="bb-status-footer">
        <div>
            <span class="bb-status-led"></span>
            <span style="color: #00FFA3; font-weight: bold;">LIVE FEED</span>
            &nbsp;|&nbsp; Atualizacao da tela a cada 60s
            &nbsp;|&nbsp; Origem: {esc(" + ".join(news_sources) or "Fontes")}
        </div>
        <div>
            Ultimo Refresh: {feed_loaded_at}
            &nbsp;|&nbsp; Fontes: Financial Juice + Reuters + Bloomberg + CNBC + SCMP + GDELT
        </div>
    </div>
    """, unsafe_allow_html=True)

def pagina_terminal_global():
    """Página de Terminal Global."""
    painel_topo_global()
    
    st.markdown("---")
    
    global_chart_assets = {
        "S&P 500": {"tv": "USA500", "yf": "^GSPC"},
        "NASDAQ": {"tv": "ACTIVTRADES:USATEC", "yf": "^IXIC"},
        "BRENT OIL": {"tv": "TVC:UKOIL", "yf": "BZ=F"},
        "WTI OIL": {"tv": "TVC:USOIL", "yf": "CL=F"},
        "GOLD": {"tv": "TVC:GOLD", "yf": "GC=F"},
        "BITCOIN": {"tv": "BINANCE:BTCUSDT", "yf": "BTC-USD"},
        "DXY (Dólar Index)": {"tv": "CAPITALCOM:DXY", "yf": "DX-Y.NYB"},
        "US 10Y (Yield)": {"tv": "TVC:US10Y", "yf": "^TNX"},
        "EWZ (Brazil ETF)": {"tv": "AMEX:EWZ", "yf": "EWZ"},
        "EEM (Emerging Markets)": {"tv": "AMEX:EEM", "yf": "EEM"},
    }
    
    chart_col_1, chart_col_2 = st.columns(2)
    
    with chart_col_1:
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
            "hide_volume": true,
            "container_id": "tv_global",
            "studies": [
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Session" }}, "plots": {{ "VWAP": {{ "color": "#FFD166" }} }} }},
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Week" }}, "plots": {{ "VWAP": {{ "color": "#06D6A0" }} }} }},
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Month" }}, "plots": {{ "VWAP": {{ "color": "#118AB2" }} }} }}
            ]
          }});
          </script>
        </div>
        """
        components.html(tv_html, height=500)

    with chart_col_2:
        st.markdown("#### Grafico Global 2")
        col_sel_2, col_int_2 = st.columns([2, 1])
        with col_sel_2:
            sym_2 = st.selectbox("Ativo", list(global_chart_assets.keys()), index=1, key="global_sym_2")
        with col_int_2:
            interval_2 = st.selectbox("Intervalo", ["1", "5", "15", "60", "D", "W"], index=4, key="global_int_2")

        tv_html_2 = f"""
        <div class="tradingview-widget-container" style="height: 480px; width: 100%;">
          <div id="tv_global_2" style="height: 100%; width: 100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "autosize": true,
            "symbol": "{global_chart_assets[sym_2]['tv']}",
            "interval": "{interval_2}",
            "timezone": "America/Sao_Paulo",
            "theme": "dark",
            "style": "1",
            "locale": "br",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_top_toolbar": false,
            "save_image": true,
            "hide_volume": true,
            "container_id": "tv_global_2",
            "studies": [
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Session" }}, "plots": {{ "VWAP": {{ "color": "#FFD166" }} }} }},
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Week" }}, "plots": {{ "VWAP": {{ "color": "#06D6A0" }} }} }},
              {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Month" }}, "plots": {{ "VWAP": {{ "color": "#118AB2" }} }} }}
            ]
          }});
          </script>
        </div>
        """
        components.html(tv_html_2, height=500)

    st.markdown("---")

    with st.container():
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
            
    secao_calendario_global_fragment()
    painel_corpo_global()

@st.fragment(run_every=30)
def sidebar_mercados():
    global_data = get_global_markets_data()
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
    calendar_data = get_calendar_data()
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

@st.fragment(run_every=1800)
def secao_calendario_global_fragment():
    """Calendario economico compacto dentro do Terminal Global."""
    calendar_data = get_calendar_data()
    if not calendar_data:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    selected_currencies = ["USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "NZD", "CHF"]
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "HOLIDAY": 3}

    events = [
        event for event in calendar_data
        if event.get("date") == today_str and event.get("currency") in selected_currencies
    ]
    events.sort(key=lambda item: (item.get("time", "99:99"), impact_rank.get(item.get("impact", ""), 9)))

    st.markdown("---")
    st.markdown("#### Calendario Economico")
    st.caption(f"Eventos de hoje ({today_str}) | Fonte: ForexFactory/Faireconomy")

    if not events:
        st.info("Nenhum evento economico relevante para hoje.")
        return

    rows = []
    for event in events[:40]:
        impact = event.get("impact", "")
        if impact == "HIGH":
            impact_label = "ALTO"
        elif impact == "MEDIUM":
            impact_label = "MEDIO"
        elif impact == "LOW":
            impact_label = "BAIXO"
        else:
            impact_label = impact or "---"

        rows.append({
            "Hora": event.get("time", "---"),
            "Moe.": event.get("currency", "---"),
            "Imp.": impact_label,
            "Evento": event.get("event", "---"),
            "Atual": event.get("actual", "---") or "---",
            "Projecao": event.get("forecast", "---") or "---",
            "Anterior": event.get("previous", "---") or "---",
        })

    df = pd.DataFrame(rows)

    def color_impact(value):
        if value == "ALTO":
            return "color: #FF4B4B; font-weight: bold"
        if value == "MEDIO":
            return "color: #FF9800; font-weight: bold"
        if value == "BAIXO":
            return "color: #888; font-weight: bold"
        return "color: #AAA"

    styler = df.style
    if hasattr(styler, "map"):
        styler = styler.map(color_impact, subset=["Imp."])
    else:
        styler = styler.applymap(color_impact, subset=["Imp."])
    st.dataframe(styler, hide_index=True, use_container_width=True, height=360)

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
        "NASDAQ (Futuro)": "ACTIVTRADES:USATEC",
        "VIX": "CBOE:VIX",
        "DXY (Dólar Index)": "CAPITALCOM:DXY",
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
        "container_id": "tv_chart_1",
        "studies": [
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Session" }}, "plots": {{ "VWAP": {{ "color": "#FFD166" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Week" }}, "plots": {{ "VWAP": {{ "color": "#06D6A0" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Month" }}, "plots": {{ "VWAP": {{ "color": "#118AB2" }} }} }}
        ]
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
        "container_id": "tv_chart_2",
        "studies": [
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Session" }}, "plots": {{ "VWAP": {{ "color": "#FFD166" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Week" }}, "plots": {{ "VWAP": {{ "color": "#06D6A0" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Month" }}, "plots": {{ "VWAP": {{ "color": "#118AB2" }} }} }}
        ]
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
    st.info("💡 Dica: Nos gráficos abaixo, você pode clicar em cada ativo na legenda (canto superior esquerdo) para ajustar a cor e a espessura da linha para melhor visibilidade.")

    # Widget 1: Correlação Macro Tradicional
    st.markdown("#### 📊 Correlação Macro (USA500, Ouro, Petróleo, US10Y, US30Y)")
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
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "OTCB:US10Y" }}, "plots": {{ "Plot": {{ "color": "#FF9800" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "OTCB:US30Y" }}, "plots": {{ "Plot": {{ "color": "#00BFFF" }} }} }}
        ]
      }}
      );
      </script>
    </div>
    """
    components.html(tv_html, height=c_height + 20)

    # Widget 2: Comparativo de Moedas vs DXY
    st.markdown("---")
    st.markdown("#### 💱 Comparativo de Moedas vs DXY (Escala em Porcentagem)")
    st.markdown("<p style='color:#888; font-size:0.85rem;'>Gráfico comparando o DXY (base em Branco) com as taxas Spot de Real Brasileiro (BRLUSD - Verde), Euro (EURUSD - Azul Claro) e Iene Japonês (JPYUSD - Vermelho).</p>", unsafe_allow_html=True)
    
    tv_html_currencies = f"""
    <div class="tradingview-widget-container" style="height: {c_height}px; width: 100%;">
      <div id="tradingview_currencies_v2" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "CAPITALCOM:DXY",
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
        "container_id": "tradingview_currencies_v2",
        "overrides": {{
            "mainSeriesProperties.lineStyle.color": "#FFFFFF",
            "mainSeriesProperties.lineStyle.linewidth": 3,
            "scalesProperties.scaleMode": 2
        }},
        "studies": [
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Session" }}, "plots": {{ "VWAP": {{ "color": "#FFD166" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Week" }}, "plots": {{ "VWAP": {{ "color": "#06D6A0" }} }} }},
          {{ "id": "VWAP@tv-basicstudies", "inputs": {{ "Anchor Period": "Month" }}, "plots": {{ "VWAP": {{ "color": "#118AB2" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "FX_IDC:BRLUSD" }}, "plots": {{ "Plot": {{ "color": "#00FFA3" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "FX:EURUSD" }}, "plots": {{ "Plot": {{ "color": "#00BFFF" }} }} }},
          {{ "id": "Overlay@tv-basicstudies", "inputs": {{ "symbol": "FX_IDC:JPYUSD" }}, "plots": {{ "Plot": {{ "color": "#FF4B4B" }} }} }}
        ]
      }}
      );
      </script>
    </div>
    """
    components.html(tv_html_currencies, height=c_height + 20)


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
                    generate_market_report(force=True)
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
                    daily_paths = ["market_report_daily.json", "execution/market_report_daily.json"]
                    for p in daily_paths:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                supabase.table("app_state").upsert({
                                    "key": "market_report_daily",
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

def pagina_gestao_risco():
    """Página de Gestão de Risco com backtest manual por estratégia."""
    import json, base64, uuid
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.markdown("### 🛡️ Gestão de Risco & Backtest por Estratégia")
    st.markdown("<p style='color:#888; font-size:0.9rem;'>Registre suas operações por estratégia, acompanhe a curva de capital individual, compare estratégias e receba análise IA de performance.</p>", unsafe_allow_html=True)

    # ── CSS ──
    st.markdown("""
    <style>
    .risk-card { background: #111; border: 1px solid #222; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
    .risk-metric { font-size: 2rem; font-weight: bold; color: #FFF; }
    .risk-label  { font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
    .ai-feedback  { background:#0A0A0A; border:1px solid #333; border-left:6px solid #FF9800; padding:20px; border-radius:8px; margin-top:12px; color:#E0E0E0; font-size:0.9rem; line-height:1.7; }
    </style>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════
    # BLOCO 1 — Calculadora de Tamanho de Posição
    # ══════════════════════════════════════════════════
    with st.expander("📐 Calculadora de Tamanho de Posição", expanded=False):
        col_p, col_m = st.columns([1, 1])
        with col_p:
            capital_total   = st.number_input("Capital Total (R$)", min_value=1000.0, value=10000.0, step=500.0, format="%.2f", key="risk_capital")
            risco_por_trade = st.slider("Risco por Trade (%)", 0.5, 5.0, 1.0, 0.25, key="risk_pct", format="%.2f%%")
        with col_m:
            stop_pontos     = st.number_input("Stop Loss (pontos)", min_value=1.0, value=50.0, step=5.0, key="risk_stop")
            valor_por_ponto = st.number_input("Valor por Contrato/Ponto (R$)", min_value=0.1, value=0.20, step=0.05, format="%.2f", key="risk_vpp")

        risco_valor = capital_total * (risco_por_trade / 100.0)
        denom       = stop_pontos * valor_por_ponto
        tamanho_pos = risco_valor / denom if denom > 0 else 0
        alv_2r      = risco_valor * 2
        stop_total  = stop_pontos * valor_por_ponto * tamanho_pos

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risco (R$)",      f"R$ {risco_valor:,.2f}")
        m2.metric("Contratos",       f"{tamanho_pos:.1f}")
        m3.metric("Stop Total (R$)", f"R$ {stop_total:,.2f}")
        m4.metric("Alvo 2:1 (R$)",  f"R$ {alv_2r:,.2f}")

    st.markdown("---")

    # ══════════════════════════════════════════════════
    # BLOCO 2 — Registro Manual de Trades por Estratégia
    # ══════════════════════════════════════════════════
    st.markdown("#### ✏️ Registro de Trades por Estratégia")

    # Carrega histórico persistido (Supabase → local)
    if "manual_trades" not in st.session_state:
        st.session_state["manual_trades"] = load_manual_trades()

    trades: list = st.session_state["manual_trades"]

    # Deriva lista de estratégias já cadastradas
    estrategias_existentes = sorted(set(t.get("estrategia", "") for t in trades if t.get("estrategia")))

    col_form, col_hist = st.columns([1, 1.4], gap="large")

    with col_form:
        st.markdown("<div style='background:#0d0d0d; border:1px solid #1e1e1e; border-radius:10px; padding:18px;'>", unsafe_allow_html=True)
        st.markdown("<div class='risk-label'>📋 Novo Trade</div>", unsafe_allow_html=True)

        with st.form("form_novo_trade", clear_on_submit=True):
            opcoes_estrategia = ["+ Nova Estratégia"] + estrategias_existentes
            sel = st.selectbox("Estratégia", opcoes_estrategia, key="form_sel_estrategia")
            nova_nome = ""
            if sel == "+ Nova Estratégia":
                nova_nome = st.text_input("Nome da nova estratégia",
                                          placeholder="Ex: Wyckoff M5, Filippo M15, ICT HTF...",
                                          key="form_nova_nome")
            estrategia_final = nova_nome.strip() if sel == "+ Nova Estratégia" else sel

            c1f, c2f = st.columns(2)
            with c1f:
                ativo    = st.text_input("Ativo", placeholder="WIN, WDO, EURUSD", key="form_ativo")
                direcao  = st.selectbox("Direção", ["Compra", "Venda"], key="form_dir")
            with c2f:
                resultado  = st.number_input("Resultado (R$)", value=0.0, step=10.0, format="%.2f", key="form_res")
                data_trade = st.date_input("Data do Trade", value=datetime.now().date(), key="form_data")

            obs = st.text_input("Observação (opcional)",
                                placeholder="Ex: Setup no teste de estrutura...", key="form_obs")

            submitted = st.form_submit_button("➕ Registrar Trade",
                                              use_container_width=True, type="primary")

        if submitted:
            if not estrategia_final:
                st.warning("⚠️ Informe o nome da estratégia.")
            else:
                novo_trade = {
                    "id":         str(uuid.uuid4())[:8],
                    "estrategia": estrategia_final,
                    "ativo":      ativo.upper().strip() if ativo else "—",
                    "direcao":    direcao,
                    "resultado":  resultado,
                    "data":       str(data_trade),
                    "obs":        obs,
                }
                trades.append(novo_trade)
                st.session_state["manual_trades"] = trades
                save_manual_trades(trades)
                st.success(f"✅ Trade registrado em **{estrategia_final}**: R$ {resultado:+.2f}")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col_hist:
        if trades:
            st.markdown(f"<div class='risk-label'>📚 Histórico — {len(trades)} operações</div>",
                        unsafe_allow_html=True)
            df_hist = pd.DataFrame(trades)
            df_hist["resultado"] = pd.to_numeric(df_hist["resultado"], errors="coerce").fillna(0)
            df_hist_show = df_hist[["data", "estrategia", "ativo", "direcao", "resultado", "obs"]].copy()
            df_hist_show.columns = ["Data", "Estratégia", "Ativo", "Dir.", "Resultado (R$)", "Obs."]
            df_hist_show = df_hist_show.sort_values("Data", ascending=False)

            def color_row(row):
                c = "#003318" if row["Resultado (R$)"] >= 0 else "#330000"
                return [f"background-color: {c}" for _ in row]

            styled = (
                df_hist_show.style
                .apply(color_row, axis=1)
                .format({"Resultado (R$)": "R$ {:+,.2f}"})
                .set_properties(**{"font-size": "0.78rem", "color": "#DDD"})
            )
            st.dataframe(styled, use_container_width=True, hide_index=True, height=260)

            # Exclusão por índice
            col_del1, col_del2 = st.columns([2, 1])
            with col_del1:
                labels_del = [
                    f"{t['data']} | {t['estrategia']} | R$ {float(t.get('resultado', 0)):+.2f}"
                    for t in trades
                ]
                idx_del = st.selectbox(
                    "Selecionar trade para excluir",
                    options=range(len(trades)),
                    format_func=lambda i: labels_del[i],
                    key="sel_del_trade"
                )
            with col_del2:
                st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
                if st.button("🗑️ Excluir", key="btn_del_trade", use_container_width=True):
                    trades.pop(idx_del)
                    st.session_state["manual_trades"] = trades
                    save_manual_trades(trades)
                    st.success("Trade excluído.")
                    st.rerun()

            if st.button("🗑️ Limpar TODO o histórico", key="btn_clear_all", type="secondary"):
                st.session_state["manual_trades"] = []
                save_manual_trades([])
                st.rerun()
        else:
            st.info("📭 Nenhum trade registrado ainda. Use o formulário ao lado para começar.")

    st.markdown("---")

    # ══════════════════════════════════════════════════
    # BLOCO 3 — Gráficos e Métricas por Estratégia
    # ══════════════════════════════════════════════════
    st.markdown("#### 📊 Performance por Estratégia")

    if not trades:
        st.info("✏️ Registre operações para visualizar os gráficos de rentabilidade.")
    else:
        df_all = pd.DataFrame(trades)
        df_all["resultado"] = pd.to_numeric(df_all["resultado"], errors="coerce").fillna(0)
        df_all["data"]      = pd.to_datetime(df_all["data"], errors="coerce")
        df_all = df_all.sort_values("data").reset_index(drop=True)

        estrategias_list = sorted(df_all["estrategia"].unique().tolist())

        tab_todas, *tabs_ind = st.tabs(
            ["📈 Todas Consolidadas"] + [f"🎯 {e}" for e in estrategias_list]
        )

        # ── Aba Consolidada ──
        with tab_todas:
            _plot_rentabilidade_df(df_all, "Curva de Capital Consolidada — Todas as Estratégias")

            st.markdown("##### 📊 Comparativo entre Estratégias")
            resumo = []
            for est in estrategias_list:
                df_e  = df_all[df_all["estrategia"] == est]
                res   = df_e["resultado"].tolist()
                n_e   = len(res)
                wins  = sum(1 for r in res if r > 0)
                total = sum(res)
                wr_e  = wins / n_e * 100 if n_e else 0
                gross_w = sum(r for r in res if r > 0)
                gross_l = abs(sum(r for r in res if r < 0))
                pf_e = gross_w / gross_l if gross_l else float("inf")
                peak_e = s_e = max_dd_e = 0.0
                for r in res:
                    s_e += r
                    if s_e > peak_e: peak_e = s_e
                    dd_e = peak_e - s_e
                    if dd_e > max_dd_e: max_dd_e = dd_e
                resumo.append({
                    "Estratégia":    est,
                    "Trades":        n_e,
                    "Win Rate":      f"{wr_e:.0f}%",
                    "Total (R$)":    total,
                    "Profit Factor": f"{pf_e:.2f}" if pf_e != float("inf") else "∞",
                    "Max DD (R$)":   max_dd_e,
                })

            df_resumo = pd.DataFrame(resumo)
            cores_bar = ["#00FFA3" if v >= 0 else "#FF4B4B" for v in df_resumo["Total (R$)"]]

            fig_comp = go.Figure(go.Bar(
                x=df_resumo["Estratégia"],
                y=df_resumo["Total (R$)"],
                marker_color=cores_bar,
                text=[f"R$ {v:+,.0f}" for v in df_resumo["Total (R$)"]],
                textposition="outside",
                marker_line_width=0,
            ))
            fig_comp.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E0E0E0", size=11),
                margin=dict(l=10, r=10, t=30, b=10), height=280,
                xaxis=dict(showgrid=False, color="#888"),
                yaxis=dict(showgrid=True, gridcolor="#1a1a1a", zeroline=True,
                           zerolinecolor="#444", tickprefix="R$ "),
                showlegend=False,
            )
            fig_comp.add_hline(y=0, line_dash="dot", line_color="#444")
            st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})

            def _color_total(val):
                return "color: #00FFA3; font-weight:bold" if val >= 0 else "color: #FF4B4B; font-weight:bold"

            resumo_styler = df_resumo.style
            if hasattr(resumo_styler, "map"):
                resumo_styler = resumo_styler.map(_color_total, subset=["Total (R$)"])
            else:
                resumo_styler = resumo_styler.applymap(_color_total, subset=["Total (R$)"])
            styled_resumo = (
                resumo_styler
                .format({"Total (R$)": "R$ {:+,.2f}", "Max DD (R$)": "R$ {:.2f}"})
                .set_properties(**{"font-size": "0.82rem", "color": "#DDD",
                                   "background-color": "#0d0d0d"})
            )
            st.dataframe(styled_resumo, use_container_width=True, hide_index=True)

        # ── Abas individuais ──
        for tab_e, est in zip(tabs_ind, estrategias_list):
            with tab_e:
                df_e = df_all[df_all["estrategia"] == est].reset_index(drop=True)
                _plot_rentabilidade_df(df_e, f"Curva de Capital — {est}")

    st.markdown("---")

    # ══════════════════════════════════════════════════
    # BLOCO 4 — Upload + Análise IA
    # ══════════════════════════════════════════════════
    with st.expander("🤖 Análise IA de Relatório (Upload CSV/Excel/Imagem)", expanded=False):
        st.markdown("<p style='color:#666; font-size:0.8rem;'>Aceita: Excel (.xlsx), CSV, ou imagem (print/foto)</p>",
                    unsafe_allow_html=True)
        col_up, col_p2 = st.columns([1.5, 1])
        with col_up:
            uploaded_file = st.file_uploader(
                "Selecione o arquivo",
                type=["xlsx", "csv", "png", "jpg", "jpeg", "webp"],
                label_visibility="collapsed", key="risk_upload"
            )
        with col_p2:
            cap_ia = st.number_input("Capital (R$)", min_value=1000.0, value=10000.0,
                                     step=500.0, format="%.2f", key="risk_cap_ia")
            rpc_ia = st.slider("Risco/Trade (%)", 0.5, 5.0, 1.0, 0.25,
                               key="risk_pct_ia", format="%.2f%%")
            stp_ia = st.number_input("Stop (pts)", min_value=1.0, value=50.0,
                                     step=5.0, key="risk_stop_ia")
            vpp_ia = st.number_input("Vlr/Ponto (R$)", min_value=0.1, value=0.20,
                                     step=0.05, format="%.2f", key="risk_vpp_ia")

        if uploaded_file:
            file_ext = uploaded_file.name.split(".")[-1].lower()
            df_trades_ia = None
            img_b64 = None

            if file_ext in ["csv", "xlsx"]:
                try:
                    df_trades_ia = (pd.read_csv(uploaded_file) if file_ext == "csv"
                                    else pd.read_excel(uploaded_file))
                    st.success(f"✅ {len(df_trades_ia)} registros carregados.")
                    with st.expander("Pré-visualização", expanded=False):
                        st.dataframe(df_trades_ia.head(30), use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Erro ao ler arquivo: {e}")
            else:
                img_bytes = uploaded_file.read()
                img_b64 = base64.b64encode(img_bytes).decode()
                st.image(img_bytes, caption="Relatório enviado", use_column_width=True)

            risco_v = cap_ia * (rpc_ia / 100.0)
            den2    = stp_ia * vpp_ia
            tam_ia  = risco_v / den2 if den2 > 0 else 0

            if st.button("🤖 Analisar com IA", use_container_width=True,
                         type="primary", key="btn_ia_analise"):
                api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
                try:
                    api_key = api_key or st.secrets.get(
                        "GOOGLE_API_KEY", st.secrets.get("GEMINI_API_KEY", ""))
                except Exception:
                    pass
                if not api_key:
                    st.error("🔑 Configure GOOGLE_API_KEY nos segredos.")
                else:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    prompt_base = f"""
Você é um Coach de Trading e Gestor de Risco profissional. Analise o relatório e forneça:

PARÂMETROS: Capital R$ {cap_ia:,.2f} | Risco {rpc_ia:.2f}% | Stop {stp_ia:.0f}pts | Vlr/ponto R$ {vpp_ia:.2f} | Sizing calculado: {tam_ia:.1f} contratos

RELATÓRIO: {df_trades_ia.to_string() if df_trades_ia is not None else '[Imagem enviada]'}

Forneça:
1. 📊 DIAGNÓSTICO (Win Rate, Profit Factor, Max Drawdown, R/R médio)
2. 📐 SIZING RECOMENDADO (manter, aumentar ou reduzir {tam_ia:.1f} contratos — justifique)
3. 🧠 ANÁLISE PSICOLÓGICA (overtrading, revenge, FOMO, cortar gains, deixar losses)
4. 🎯 TOP 3 AÇÕES para os próximos 30 dias
5. ⚠️ ALERTAS DE RISCO críticos
Seja direto e cirúrgico.
                    """
                    with st.spinner("🧠 Analisando..."):
                        try:
                            model = genai.GenerativeModel("gemini-2.0-flash")
                            if img_b64:
                                mime = f"image/{file_ext if file_ext != 'jpg' else 'jpeg'}"
                                response = model.generate_content(
                                    [prompt_base, {"mime_type": mime, "data": img_b64}])
                            else:
                                response = model.generate_content(prompt_base)
                            st.session_state["risco_ia_resultado"] = response.text
                        except Exception as e:
                            st.error(f"Erro na análise IA: {e}")

        if "risco_ia_resultado" in st.session_state:
            ia_text = st.session_state["risco_ia_resultado"]
            st.markdown(
                f"<div class='ai-feedback'>"
                f"{sanitize_text(ia_text).replace(chr(10), '<br>')}"
                f"</div>",
                unsafe_allow_html=True
            )


def _plot_rentabilidade_df(df: "pd.DataFrame", titulo: str = "Curva de Capital"):
    """Plota gráfico premium de rentabilidade acumulada a partir de um DataFrame de trades."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if df.empty:
        st.info("Nenhum dado para exibir.")
        return

    df = df.copy()
    df["resultado"] = pd.to_numeric(df["resultado"], errors="coerce").fillna(0)
    resultados = df["resultado"].tolist()
    acumulado  = []
    soma = 0.0
    for r in resultados:
        soma += r
        acumulado.append(soma)

    n      = len(acumulado)
    trades = list(range(1, n + 1))
    ultimo = acumulado[-1]
    wins   = sum(1 for r in resultados if r > 0)
    wr     = wins / n * 100 if n else 0
    gross_w = sum(r for r in resultados if r > 0)
    gross_l = abs(sum(r for r in resultados if r < 0))
    pf      = gross_w / gross_l if gross_l else float("inf")
    peak = max_dd = 0.0
    for v in acumulado:
        if v > peak: peak = v
        dd = peak - v
        if dd > max_dd: max_dd = dd

    cores_barras = ["#00FFA3" if r >= 0 else "#FF4B4B" for r in resultados]
    color_tot    = "#00FFA3" if ultimo >= 0 else "#FF4B4B"
    pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35], vertical_spacing=0.06,
        subplot_titles=(titulo, "Resultado por Trade (R$)")
    )
    fig.add_trace(go.Scatter(
        x=trades, y=acumulado, mode="lines+markers",
        line=dict(color="#FF9800", width=2.5),
        marker=dict(size=5, color="#FF9800"),
        fill="tozeroy", fillcolor="rgba(255,152,0,0.08)",
        name="Capital Acumulado"
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#444", row=1, col=1)
    fig.add_trace(go.Bar(
        x=trades, y=resultados,
        marker_color=cores_barras, name="Resultado",
        marker_line_width=0, opacity=0.85
    ), row=2, col=1)
    fig.add_annotation(
        text=(f"Total: R$ {ultimo:+,.2f} | Win Rate: {wr:.0f}% | "
              f"Profit Factor: {pf_str} | Max DD: R$ {max_dd:,.2f}"),
        xref="paper", yref="paper", x=0.5, y=1.02,
        showarrow=False, font=dict(size=11, color=color_tot),
        bgcolor="rgba(0,0,0,0.5)"
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='"Roboto Mono", monospace', color="#E0E0E0", size=11),
        margin=dict(l=10, r=10, t=40, b=10), height=440,
        showlegend=False,
        xaxis2=dict(title="Nº do Trade", showgrid=False, color="#888"),
        yaxis=dict(showgrid=True, gridcolor="#1a1a1a", zeroline=True,
                   zerolinecolor="#444", tickprefix="R$ "),
        yaxis2=dict(showgrid=True, gridcolor="#1a1a1a", zeroline=True,
                    zerolinecolor="#444", tickprefix="R$ "),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Trades",  n)
    c2.metric("Win Rate",      f"{wr:.1f}%")
    c3.metric("Resultado",     f"R$ {ultimo:+,.2f}")
    c4.metric("Profit Factor", pf_str)
    c5.metric("Max Drawdown",  f"R$ {max_dd:,.2f}")


def _plot_rentabilidade(resultados: list, acumulado: list):
    """Wrapper legado — mantido para compatibilidade."""
    df_tmp = pd.DataFrame({"resultado": resultados})
    _plot_rentabilidade_df(df_tmp)


# Navegação na Barra Lateral
with st.sidebar:
    st.markdown("### 🧭 Navegação")
    page = st.radio("Ir para:", ["📉 Terminal de Trading", "🌎 Terminal Global", "📺 Terminal Bloomberg", "📰 Market Report", "📊 Gráficos Avançados", "⚖️ Painel de Correlação", "🛡️ Gestão de Risco", "⚙️ Painel de Controle"], index=2, label_visibility="collapsed")
    
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["🌍 MERCADOS", "📅 CALENDÁRIO"])
    with tab1: sidebar_mercados()
    with tab2: sidebar_calendario()

# Roteamento de Páginas
if page == "📉 Terminal de Trading":
    pagina_terminal()
elif page == "🌎 Terminal Global":
    pagina_terminal_global()
elif page == "📺 Terminal Bloomberg":
    pagina_terminal_bloomberg()
elif page == "📰 Market Report":
    pagina_market_report()
elif page == "📊 Gráficos Avançados":
    pagina_graficos()
elif page == "⚖️ Painel de Correlação":
    pagina_correlacao()
elif page == "🛡️ Gestão de Risco":
    pagina_gestao_risco()
elif page == "⚙️ Painel de Controle":
    pagina_painel_controle()



