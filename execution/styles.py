"""styles.py — CSS premium para o dashboard."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
    --bg-primary: #06080d;
    --bg-card: rgba(12, 17, 28, 0.85);
    --bg-card-hover: rgba(18, 24, 38, 0.95);
    --border: rgba(55, 65, 81, 0.35);
    --border-hover: rgba(99, 102, 241, 0.45);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #818cf8;
    --accent-glow: rgba(99, 102, 241, 0.15);
    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, 0.08);
    --red: #f87171;
    --red-bg: rgba(248, 113, 113, 0.08);
    --yellow: #fbbf24;
}

* { font-family: 'Inter', -apple-system, sans-serif !important; }

.stApp {
    background: linear-gradient(160deg, #06080d 0%, #0a0f1a 40%, #080c14 100%);
}

/* Hide defaults */
#MainMenu, header, footer, .stDeployButton { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* === HEADER === */
.dash-header {
    text-align: center;
    padding: 1.8rem 0 1.2rem;
    margin-bottom: 0.5rem;
    position: relative;
}
.dash-header::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 10%;
    width: 80%;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
}
.dash-header h1 {
    font-size: 1.8rem;
    font-weight: 900;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #a5b4fc, #818cf8, #6366f1, #a78bfa);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 4s ease infinite;
    margin: 0;
}
@keyframes shimmer { 0%,100%{background-position:0% center} 50%{background-position:100% center} }
.dash-subtitle { color: var(--text-muted); font-size: 0.78rem; margin-top: 0.4rem; letter-spacing: 2px; text-transform: uppercase; }
.dash-clock { color: var(--accent); font-size: 0.75rem; margin-top: 0.3rem; font-weight: 600; }

/* === MARKET STRIP === */
.market-strip {
    display: flex;
    gap: 0.6rem;
    padding: 0.7rem 1rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    margin: 0.8rem 0 1.2rem;
    overflow-x: auto;
    backdrop-filter: blur(16px);
}
.strip-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.7rem;
    border-radius: 8px;
    white-space: nowrap;
    flex-shrink: 0;
}
.strip-name { font-size: 0.7rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.strip-price { font-size: 0.78rem; color: var(--text-primary); font-weight: 700; }
.strip-up { color: var(--green); font-size: 0.7rem; font-weight: 600; }
.strip-down { color: var(--red); font-size: 0.7rem; font-weight: 600; }

/* === CATEGORY HEADER === */
.cat-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 1.3rem 0 0.7rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid rgba(99, 102, 241, 0.12);
}
.cat-icon {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    background: var(--accent-glow);
}
.cat-label { font-size: 0.72rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1.5px; }

/* === QUOTE CARD === */
.qcard {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    backdrop-filter: blur(16px);
    position: relative;
    overflow: hidden;
}
.qcard::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: transparent;
    transition: background 0.35s ease;
}
.qcard:hover {
    border-color: var(--border-hover);
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(99, 102, 241, 0.12);
}
.qcard:hover::before { background: linear-gradient(90deg, var(--accent), #a78bfa); }
.qcard-up { border-left: 3px solid var(--green); }
.qcard-down { border-left: 3px solid var(--red); }
.qcard-na { border-left: 3px solid var(--text-muted); }
.q-name { font-size: 0.72rem; color: var(--text-muted); font-weight: 600; margin-bottom: 0.35rem; text-transform: uppercase; letter-spacing: 0.5px; }
.q-ticker { font-size: 0.62rem; color: var(--text-muted); opacity: 0.6; margin-left: 0.3rem; font-weight: 400; text-transform: none; letter-spacing: 0; }
.q-price { font-size: 1.35rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.3rem; letter-spacing: -0.5px; }
.q-change-up { font-size: 0.78rem; font-weight: 700; color: var(--green); display: flex; align-items: center; gap: 0.3rem; }
.q-change-down { font-size: 0.78rem; font-weight: 700; color: var(--red); display: flex; align-items: center; gap: 0.3rem; }
.q-badge-up { background: var(--green-bg); border: 1px solid rgba(74, 222, 128, 0.2); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; }
.q-badge-down { background: var(--red-bg); border: 1px solid rgba(248, 113, 113, 0.2); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; }

/* === SPARKLINE === */
.sparkline-container { margin-top: 0.5rem; height: 35px; }

/* === INSIGHT === */
.insight {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: 0 12px 12px 0;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.2s;
}
.insight:hover { border-left-color: #a78bfa; }
.insight-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.3rem; }
.insight-pair { font-size: 0.82rem; font-weight: 700; color: var(--text-primary); }
.insight-val { font-size: 0.72rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 6px; }
.insight-val-strong { background: rgba(248, 113, 113, 0.12); color: var(--red); }
.insight-val-mod { background: rgba(251, 191, 36, 0.12); color: var(--yellow); }
.insight-val-weak { background: rgba(74, 222, 128, 0.1); color: var(--green); }
.insight-body { font-size: 0.75rem; color: var(--text-secondary); line-height: 1.5; }

/* === NEWS === */
.ncard {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
    transition: all 0.25s ease;
}
.ncard:hover { border-color: var(--border-hover); transform: translateX(3px); }
.ncard-title { font-size: 0.85rem; font-weight: 700; color: var(--text-primary); line-height: 1.45; margin-bottom: 0.3rem; }
.ncard-title a { color: var(--text-primary); text-decoration: none; }
.ncard-title a:hover { color: var(--accent); }
.ncard-meta { font-size: 0.68rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.4rem; }
.ncard-meta .source-badge { background: var(--accent-glow); color: var(--accent); padding: 0.1rem 0.45rem; border-radius: 4px; font-weight: 600; font-size: 0.62rem; }
.ncard-body { font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.4rem; line-height: 1.5; }

/* === CALENDAR === */
.cal-row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.7rem 1rem;
    border-radius: 10px;
    margin-bottom: 0.35rem;
    border: 1px solid var(--border);
    transition: background 0.2s;
}
.cal-row:hover { background: var(--bg-card-hover); }
.cal-high { background: var(--red-bg); border-left: 3px solid var(--red); }
.cal-mid { background: rgba(251, 191, 36, 0.05); border-left: 3px solid var(--yellow); }
.cal-low { background: var(--bg-card); border-left: 3px solid var(--text-muted); }
.cal-time { font-size: 0.78rem; font-weight: 700; color: var(--accent); min-width: 50px; }
.cal-flag { font-size: 0.72rem; color: var(--text-muted); min-width: 35px; font-weight: 600; }
.cal-event { font-size: 0.8rem; color: var(--text-primary); font-weight: 500; flex: 1; }
.cal-impact { font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 5px; }
.impact-high { background: var(--red-bg); color: var(--red); }
.impact-mid { background: rgba(251, 191, 36, 0.1); color: var(--yellow); }
.impact-low { background: rgba(100, 116, 139, 0.1); color: var(--text-muted); }
.cal-vals { display: flex; gap: 0.6rem; font-size: 0.72rem; color: var(--text-secondary); }

/* === VIX GAUGE === */
.vix-gauge {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.2rem;
    text-align: center;
}
.vix-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
.vix-value { font-size: 2.2rem; font-weight: 900; margin: 0.3rem 0; letter-spacing: -1px; }
.vix-low { color: var(--green); }
.vix-mid { color: var(--yellow); }
.vix-high { color: var(--red); }
.vix-status { font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.7rem; border-radius: 6px; display: inline-block; margin-top: 0.2rem; }
.vix-bar { width: 100%; height: 6px; border-radius: 3px; background: linear-gradient(90deg, var(--green), var(--yellow), var(--red)); margin-top: 0.6rem; position: relative; }
.vix-marker { position: absolute; top: -3px; width: 12px; height: 12px; border-radius: 50%; background: white; border: 2px solid var(--bg-primary); box-shadow: 0 0 8px rgba(255,255,255,0.3); }

/* === SECTION TITLE === */
.sec-title {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 1rem 0 0.8rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(99,102,241,0.1);
}
.sec-title span { font-size: 1.05rem; font-weight: 800; color: var(--text-primary); letter-spacing: -0.3px; }
.sec-title .sec-badge { font-size: 0.62rem; background: var(--accent-glow); color: var(--accent); padding: 0.15rem 0.5rem; border-radius: 5px; font-weight: 600; }

/* === TABS === */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: rgba(12, 17, 28, 0.8);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.82rem;
    padding: 0.55rem 1.3rem;
    transition: all 0.2s;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text-secondary); }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(167,139,250,0.15)); color: var(--accent) !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 0.5rem; }
.stTabs [data-baseweb="tab-highlight"] { background-color: transparent !important; }
.stTabs [data-baseweb="tab-border"] { display: none; }

/* === REFRESH BTN === */
.stButton > button {
    background: linear-gradient(135deg, rgba(99,102,241,0.15), rgba(99,102,241,0.05));
    border: 1px solid rgba(99,102,241,0.3);
    color: var(--accent);
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.3s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, rgba(99,102,241,0.3), rgba(99,102,241,0.15));
    border-color: var(--accent);
    transform: scale(1.02);
}

/* === STATUS === */
.status-footer {
    text-align: center;
    padding: 1rem;
    margin-top: 2rem;
    font-size: 0.68rem;
    color: var(--text-muted);
    border-top: 1px solid var(--border);
}
.live-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--green);
    margin-right: 6px;
    animation: blink 2s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* === METRIC MINI CARDS === */
.metric-row { display: flex; gap: 0.6rem; margin-bottom: 1rem; }
.metric-mini {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    text-align: center;
}
.metric-mini-label { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
.metric-mini-val { font-size: 1.3rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem; }

hr { border-color: var(--border) !important; }
</style>
"""
