import json

import streamlit as st
import yfinance as yf


YAHOO_LIGHTWEIGHT_ASSETS = [
    {"symbol": "SP500", "label": "S&P 500", "ticker": "^GSPC"},
    {"symbol": "NASDAQ", "label": "NASDAQ", "ticker": "^IXIC"},
    {"symbol": "RUSSELL", "label": "RUSSELL", "ticker": "^RUT"},
    {"symbol": "DXY", "label": "DXY", "ticker": "DX-Y.NYB"},
    {"symbol": "6L1", "label": "6L1", "ticker": "6L=F"},
    {"symbol": "BRENT", "label": "BRENT", "ticker": "BZ=F"},
    {"symbol": "WTI", "label": "WTI", "ticker": "CL=F"},
    {"symbol": "XAUUSD", "label": "XAUUSD", "ticker": "GC=F"},
    {"symbol": "EEM", "label": "EEM", "ticker": "EEM"},
    {"symbol": "EWZ", "label": "EWZ", "ticker": "EWZ"},
    {"symbol": "IBOV", "label": "IBOV", "ticker": "^BVSP"},
]


@st.cache_data(ttl=60, show_spinner=False)
def load_yahoo_lightweight_payload():
    tickers = [asset["ticker"] for asset in YAHOO_LIGHTWEIGHT_ASSETS]
    payload = {}
    errors = []
    try:
        intraday_data = yf.download(
            tickers,
            period="5d",
            interval="1m",
            prepost=True,
            group_by="ticker",
            progress=False,
            threads=False,
            timeout=20,
        )
    except Exception as e:
        intraday_data = None
        errors.append(f"intraday: {e}")

    try:
        daily_data = yf.download(
            tickers,
            period="2y",
            interval="1d",
            prepost=True,
            group_by="ticker",
            progress=False,
            threads=False,
            timeout=20,
        )
    except Exception as e:
        daily_data = None
        errors.append(f"daily: {e}")

    if (intraday_data is None or intraday_data.empty) and (daily_data is None or daily_data.empty):
        return {
            "assets": YAHOO_LIGHTWEIGHT_ASSETS,
            "series": {},
            "error": "; ".join(errors) or "Yahoo Finance retornou vazio.",
        }

    def extract_candles(data, ticker, limit):
        if data is None or data.empty:
            return []
        if hasattr(data.columns, "levels"):
            if ticker not in set(data.columns.get_level_values(0)):
                return []
            df = data[ticker]
        else:
            df = data
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        candles = []
        for idx, row in df.tail(limit).iterrows():
            ts = int(idx.timestamp())
            volume = row.get("Volume", 0)
            candles.append({
                "time": ts,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(volume) if volume == volume else 0.0,
            })
        return candles

    for asset in YAHOO_LIGHTWEIGHT_ASSETS:
        ticker = asset["ticker"]
        try:
            intraday = extract_candles(intraday_data, ticker, 650)
            daily = extract_candles(daily_data, ticker, 520)
            if intraday or daily:
                payload[asset["symbol"]] = {
                    "label": asset["label"],
                    "ticker": ticker,
                    "intraday": intraday,
                    "daily": daily,
                }
        except Exception:
            continue
    return {"assets": YAHOO_LIGHTWEIGHT_ASSETS, "series": payload, "error": "; ".join(errors) or None}


def render_lightweight_chart_html():
    yahoo_payload = load_yahoo_lightweight_payload()
    yahoo_json = json.dumps(yahoo_payload, ensure_ascii=False)
    html = """
    <div id="lw-root">
      <style>
        #lw-root { background:#080d14; border:1px solid #1f2937; border-radius:8px; color:#e5e7eb; font-family:Inter,"Segoe UI",Arial,sans-serif; overflow:hidden; position:relative; }
        .lw-toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; padding:10px 12px; background:#0d1420; border-bottom:1px solid #1f2937; }
        .lw-group { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
        .lw-label { color:#94a3b8; font-size:.72rem; font-weight:800; text-transform:uppercase; letter-spacing:.04em; margin-right:2px; }
        .lw-btn { border:1px solid #334155; background:#111827; color:#cbd5e1; border-radius:5px; padding:6px 9px; font-size:.78rem; font-weight:800; cursor:pointer; }
        .lw-btn.active { border-color:#38bdf8; color:#fff; background:#0f3b5f; }
        .lw-btn.toggle-on { border-color:#22c55e; color:#eafff3; }
        .lw-btn.warn { border-color:#f59e0b; color:#fff7ed; }
        .lw-main { display:grid; grid-template-columns:minmax(0,1fr) 310px; gap:0; }
        #lw-chart { height:620px; min-width:0; }
        #lw-osc { height:150px; border-top:1px solid #1f2937; }
        .lw-chart-wrap { position:relative; min-width:0; }
        .lw-side { border-left:1px solid #1f2937; background:#0b1220; padding:10px; display:grid; align-content:start; gap:8px; }
        .lw-stat { background:#111827; border:1px solid #253044; border-radius:6px; padding:8px; }
        .lw-stat span { display:block; color:#94a3b8; font-size:.68rem; font-weight:800; text-transform:uppercase; }
        .lw-stat strong { display:block; color:#f8fafc; font-size:1rem; margin-top:3px; }
        .lw-stat small { display:block; color:#94a3b8; font-size:.72rem; margin-top:3px; line-height:1.25; }
        .lw-settings { border:1px solid #253044; border-radius:6px; padding:8px; background:#0f172a; display:grid; gap:8px; }
        .lw-settings-title { color:#cbd5e1; font-size:.72rem; text-transform:uppercase; font-weight:900; }
        .lw-setting-row { display:grid; grid-template-columns:52px 1fr 54px; gap:6px; align-items:center; font-size:.74rem; color:#cbd5e1; }
        .lw-setting-row input[type="number"] { width:100%; background:#111827; color:#e5e7eb; border:1px solid #334155; border-radius:5px; padding:5px; }
        .lw-setting-row select { background:#111827; color:#e5e7eb; border:1px solid #334155; border-radius:5px; padding:5px; }
        .lw-alerts { display:grid; gap:6px; }
        .lw-alert { border:1px solid #334155; border-left:4px solid #64748b; background:#111827; border-radius:5px; padding:7px; font-size:.76rem; color:#cbd5e1; font-weight:800; }
        .lw-alert.hot { border-left-color:#f59e0b; color:#fff7ed; }
        .lw-alert.buy { border-left-color:#22c55e; color:#dcfce7; }
        .lw-alert.sell { border-left-color:#ef4444; color:#fee2e2; }
        .lw-crosshair-card { position:absolute; z-index:5; pointer-events:none; min-width:250px; border:1px solid #334155; background:rgba(8,13,20,.95); border-radius:7px; padding:9px; box-shadow:0 12px 30px rgba(0,0,0,.35); display:none; }
        .lw-crosshair-card strong { display:block; color:#f8fafc; font-size:.85rem; margin-bottom:6px; }
        .lw-crosshair-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:4px 10px; color:#cbd5e1; font-size:.75rem; }
        .lw-crosshair-grid span { color:#94a3b8; }
        .lw-volume-profile { position:absolute; top:0; right:56px; width:150px; height:620px; z-index:3; pointer-events:none; opacity:.82; }
        .lw-vp-bar { position:absolute; right:0; height:3px; min-width:2px; border-radius:999px 0 0 999px; background:rgba(56,189,248,.32); }
        .lw-vp-bar.value-area { background:rgba(34,197,94,.38); }
        .lw-vp-bar.poc { height:5px; background:rgba(245,158,11,.9); box-shadow:0 0 8px rgba(245,158,11,.55); }
        .lw-vp-label { position:absolute; right:0; top:6px; color:#94a3b8; font-size:.66rem; font-weight:900; text-transform:uppercase; background:rgba(8,13,20,.72); padding:2px 5px; border:1px solid #334155; border-radius:4px; }
        .lw-skeleton { position:absolute; inset:0; z-index:4; display:none; background:linear-gradient(90deg,#0b1220 0%,#111827 50%,#0b1220 100%); background-size:220% 100%; animation:lwPulse 1.2s ease-in-out infinite; }
        .lw-skeleton.show { display:block; }
        @keyframes lwPulse { from{background-position:220% 0;} to{background-position:-220% 0;} }
        .lw-status { color:#94a3b8; font-size:.75rem; padding:8px 12px 10px; border-top:1px solid #1f2937; background:#0d1420; }
        @media (max-width:900px){ .lw-main{grid-template-columns:1fr;} .lw-side{border-left:0; border-top:1px solid #1f2937; grid-template-columns:repeat(2,minmax(0,1fr));} #lw-chart{height:520px;} }
      </style>
      <div class="lw-toolbar">
        <div class="lw-group" id="lw-assets"><span class="lw-label">Ativo</span></div>
        <div class="lw-group" id="lw-timeframes"><span class="lw-label">Tempo</span></div>
        <div class="lw-group" id="lw-toggles"><span class="lw-label">Camadas</span></div>
        <div class="lw-group" id="lw-actions"><span class="lw-label">Acoes</span></div>
      </div>
      <div class="lw-main">
        <div class="lw-chart-wrap">
          <div class="lw-skeleton" id="lw-skeleton"></div>
          <div class="lw-crosshair-card" id="lw-crosshair-card"></div>
          <div class="lw-volume-profile" id="lw-volume-profile"></div>
          <div id="lw-chart"></div>
          <div id="lw-osc"></div>
        </div>
        <aside class="lw-side">
          <div class="lw-stat"><span>Ultimo</span><strong id="lw-last">---</strong></div>
          <div class="lw-stat"><span>VWAP diaria</span><strong id="lw-vwap">---</strong><small id="lw-vwap-extra">---</small></div>
          <div class="lw-stat"><span>Dist. VWAP</span><strong id="lw-dist">---</strong></div>
          <div class="lw-stat"><span>Corr preco x volume</span><strong id="lw-corr">---</strong></div>
          <div class="lw-stat"><span>Volume</span><strong id="lw-volume">---</strong><small id="lw-rvol">RVOL ---</small></div>
          <div class="lw-stat"><span>Volume Profile sessao</span><strong id="lw-vp-poc">POC ---</strong><small id="lw-vp-range">---</small><small id="lw-vp-value-area">VAH --- | VAL ---</small></div>
          <div class="lw-stat"><span>Volatilidade historica</span><strong id="lw-hv252">HV252 ---</strong><small id="lw-hv30">HV30 ---</small><small id="lw-hv-levels">---</small></div>
          <div class="lw-stat"><span>Referencia do candle</span><strong id="lw-hover-title">Passe o mouse</strong><small id="lw-hover-data">OHLC, horario, variacao e distancia da VWAP.</small></div>
          <div class="lw-settings" id="lw-ma-settings">
            <div class="lw-settings-title">Medias moveis</div>
          </div>
          <div class="lw-alerts" id="lw-alerts"></div>
        </aside>
      </div>
      <div class="lw-status" id="lw-status">Inicializando grafico proprio com Lightweight Charts...</div>
    </div>
    <script src="https://unpkg.com/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    (() => {
      const { createChart, CandlestickSeries, HistogramSeries, LineSeries } = LightweightCharts;
      const yahooPayload = __YAHOO_PAYLOAD__;
      const binanceAssets = [
        { symbol: "BTCUSDT", label: "BTC", source: "binance" },
        { symbol: "ETHUSDT", label: "ETH", source: "binance" },
        { symbol: "SOLUSDT", label: "SOL", source: "binance" },
      ];
      const yahooAssets = (yahooPayload.assets || []).map((asset) => ({
        symbol: asset.symbol,
        label: asset.label,
        source: "yahoo",
        ticker: asset.ticker,
      }));
      const assets = [...binanceAssets, ...yahooAssets];
      const assetRegistry = Object.fromEntries(assets.map((asset) => [asset.symbol, asset]));
      const timeframes = ["30s", "1m", "5m", "h1", "1d", "1w", "1month"];
      const tfSeconds = { "30s": 30, "1m": 60, "5m": 300, "h1": 3600, "1d": 86400, "1w": 604800 };
      const binanceIntervals = { "1m": "1m", "5m": "5m", "h1": "1h", "1d": "1d", "1w": "1w", "1month": "1M" };
      const defaultPrefs = {
        symbol:"BTCUSDT",
        timeframe:"1m",
        toggles:{ ma:true, vwap:true, bands:true, stdevBands:false, volume:true, volumeProfile:true, historicalVol:true, oscillator:true, refs:true, signals:true },
        maType:"SMA",
        ma:[
          { id:"ma9", period:9, enabled:true, color:"#22c55e" },
          { id:"ma21", period:21, enabled:true, color:"#eab308" },
          { id:"ma80", period:80, enabled:true, color:"#38bdf8" },
          { id:"ma200", period:200, enabled:false, color:"#f8fafc" },
        ],
      };
      const storedPrefs = (() => { try { return JSON.parse(localStorage.getItem("lw_chart_prefs") || "{}"); } catch (_) { return {}; } })();
      const prefs = {
        ...defaultPrefs,
        ...storedPrefs,
        toggles:{ ...defaultPrefs.toggles, ...(storedPrefs.toggles || {}) },
        ma: Array.isArray(storedPrefs.ma) ? storedPrefs.ma : defaultPrefs.ma,
      };
      const state = { symbol:prefs.symbol, timeframe:prefs.timeframe, candles:[], indicators:null, chart:null, oscChart:null, series:{}, priceLines:[], markerApi:null, socket:null, toggles:prefs.toggles, maType:prefs.maType, ma:prefs.ma };
      if (!assetRegistry[state.symbol]) state.symbol = "BTCUSDT";
      if (!timeframes.includes(state.timeframe)) state.timeframe = "1m";
      const chartEl = document.getElementById("lw-chart");
      const oscEl = document.getElementById("lw-osc");
      const statusEl = document.getElementById("lw-status");
      const skeletonEl = document.getElementById("lw-skeleton");
      const crosshairCard = document.getElementById("lw-crosshair-card");
      const volumeProfileEl = document.getElementById("lw-volume-profile");
      const fmt = (n, d=2) => Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits:d, minimumFractionDigits:d }) : "---";
      const fmtTime = (time) => new Date(time * 1000).toLocaleString("pt-BR", { timeZone:"America/Sao_Paulo", hour12:false });
      const setStatus = (msg) => { statusEl.textContent = msg; };
      const setLoading = (on) => skeletonEl.classList.toggle("show", Boolean(on));
      const savePrefs = () => {
        localStorage.setItem("lw_chart_prefs", JSON.stringify({ symbol:state.symbol, timeframe:state.timeframe, toggles:state.toggles, maType:state.maType, ma:state.ma }));
      };

      function button(label, active, onClick, extraClass="") {
        const b = document.createElement("button");
        b.className = `lw-btn ${active ? "active" : ""} ${extraClass}`;
        b.textContent = label;
        b.onclick = onClick;
        return b;
      }
      function renderControls() {
        const assetBox = document.getElementById("lw-assets");
        const tfBox = document.getElementById("lw-timeframes");
        const toggleBox = document.getElementById("lw-toggles");
        const actionBox = document.getElementById("lw-actions");
        assetBox.querySelectorAll("button").forEach((el) => el.remove());
        tfBox.querySelectorAll("button").forEach((el) => el.remove());
        toggleBox.querySelectorAll("button").forEach((el) => el.remove());
        actionBox.querySelectorAll("button").forEach((el) => el.remove());
        assets.forEach((asset) => assetBox.appendChild(button(asset.label, state.symbol === asset.symbol, () => loadSymbol(asset.symbol, state.timeframe))));
        timeframes.forEach((tf) => tfBox.appendChild(button(tf, state.timeframe === tf, () => loadSymbol(state.symbol, tf))));
        [["ma","Medias"],["vwap","VWAP"],["bands","Bandas %"],["stdevBands","Desvios"],["refs","Refs"],["signals","Sinais"],["volume","Volume"],["volumeProfile","Vol Profile"],["historicalVol","HV"],["oscillator","Osc"]].forEach(([key,label]) => {
          toggleBox.appendChild(button(label, state.toggles[key], () => { state.toggles[key] = !state.toggles[key]; savePrefs(); renderControls(); renderCharts(false); }, state.toggles[key] ? "toggle-on" : ""));
        });
        actionBox.appendChild(button("Reset Zoom", false, () => { state.chart?.timeScale().fitContent(); state.oscChart?.timeScale().fitContent(); }));
        actionBox.appendChild(button("Ultimo candle", false, () => { state.chart?.timeScale().scrollToRealTime(); state.oscChart?.timeScale().scrollToRealTime(); }));
        actionBox.appendChild(button("Exportar PNG", false, exportPng));
        actionBox.appendChild(button("Recarregar", false, () => loadSymbol(state.symbol, state.timeframe), "warn"));
        renderMASettings();
      }
      function renderMASettings() {
        const box = document.getElementById("lw-ma-settings");
        box.innerHTML = '<div class="lw-settings-title">Medias moveis</div>';
        const typeRow = document.createElement("div");
        typeRow.className = "lw-setting-row";
        typeRow.innerHTML = '<span>Tipo</span><select id="lw-ma-type"><option>SMA</option><option>EMA</option></select><span></span>';
        box.appendChild(typeRow);
        typeRow.querySelector("select").value = state.maType;
        typeRow.querySelector("select").onchange = (e) => { state.maType = e.target.value; savePrefs(); renderCharts(false); };
        state.ma.forEach((ma, index) => {
          const row = document.createElement("div");
          row.className = "lw-setting-row";
          row.innerHTML = `<label><input type="checkbox" ${ma.enabled ? "checked" : ""}> MA</label><input type="number" min="2" max="500" value="${ma.period}"><span style="color:${ma.color};font-weight:900;">${ma.period}</span>`;
          row.querySelector("input[type='checkbox']").onchange = (e) => { state.ma[index].enabled = e.target.checked; savePrefs(); renderCharts(false); };
          row.querySelector("input[type='number']").onchange = (e) => { state.ma[index].period = Math.max(2, Math.min(500, Number(e.target.value) || ma.period)); savePrefs(); renderMASettings(); renderCharts(false); };
          box.appendChild(row);
        });
      }
      function exportPng() {
        try {
          const canvas = state.chart?.takeScreenshot?.();
          if (!canvas) { setStatus("Exportacao PNG indisponivel nesta versao do Lightweight Charts."); return; }
          const link = document.createElement("a");
          link.download = `${state.symbol}_${state.timeframe}.png`;
          link.href = canvas.toDataURL("image/png");
          link.click();
        } catch (err) { setStatus(`Nao foi possivel exportar PNG: ${err.message}`); }
      }
      function makeChart(container, height) {
        return createChart(container, {
          height,
          layout:{ background:{ type:"solid", color:"#080d14" }, textColor:"#cbd5e1" },
          grid:{ vertLines:{ color:"#111827" }, horzLines:{ color:"#111827" } },
          rightPriceScale:{ borderColor:"#1f2937" },
          timeScale:{ borderColor:"#1f2937", timeVisible:true, secondsVisible:true },
          crosshair:{ mode:1 },
        });
      }
      async function fetchHistorical(symbol, timeframe) {
        const asset = assetRegistry[symbol] || { source: "binance" };
        if (asset.source === "yahoo") return fetchYahooHistorical(symbol, timeframe);
        if (binanceIntervals[timeframe]) {
          const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${binanceIntervals[timeframe]}&limit=600`);
          if (!res.ok) throw new Error(`Binance klines ${res.status}`);
          const rows = await res.json();
          return rows.map((r) => ({ time:Math.floor(r[0]/1000), open:+r[1], high:+r[2], low:+r[3], close:+r[4], volume:+r[5] }));
        }
        const res = await fetch(`https://api.binance.com/api/v3/aggTrades?symbol=${symbol}&limit=1000`);
        if (!res.ok) throw new Error(`Binance trades ${res.status}`);
        const trades = await res.json();
        return aggregateTrades(trades.map((t) => ({ timeMs:t.T, price:+t.p, qty:+t.q })), tfSeconds[timeframe]);
      }
      function fetchYahooHistorical(symbol, timeframe) {
        const series = (yahooPayload.series && yahooPayload.series[symbol]) || {};
        const intraday = series.intraday || [];
        const daily = series.daily || [];
        if (timeframe === "30s" || timeframe === "1m") {
          if (!intraday.length) throw new Error(`Sem dados intraday yfinance para ${symbol}`);
          return intraday;
        }
        if (timeframe === "5m") {
          if (!intraday.length) throw new Error(`Sem dados intraday yfinance para ${symbol}`);
          return aggregateCandles(intraday, 300);
        }
        if (timeframe === "h1") {
          if (!intraday.length) throw new Error(`Sem dados intraday yfinance para ${symbol}`);
          return aggregateCandles(intraday, 3600);
        }
        if (timeframe === "1d") {
          if (!daily.length) throw new Error(`Sem dados diarios yfinance para ${symbol}`);
          return daily;
        }
        if (timeframe === "1w") {
          if (!daily.length) throw new Error(`Sem dados diarios yfinance para ${symbol}`);
          return aggregateCalendarCandles(daily, "week");
        }
        if (timeframe === "1month") {
          if (!daily.length) throw new Error(`Sem dados diarios yfinance para ${symbol}`);
          return aggregateCalendarCandles(daily, "month");
        }
        return intraday;
      }
      function aggregateCandles(candles, seconds) {
        const buckets = new Map();
        candles.forEach((c) => {
          const time = Math.floor(c.time / seconds) * seconds;
          const b = buckets.get(time) || { time, open:c.open, high:c.high, low:c.low, close:c.close, volume:0 };
          b.high = Math.max(b.high, c.high);
          b.low = Math.min(b.low, c.low);
          b.close = c.close;
          b.volume += Number(c.volume || 0);
          buckets.set(time, b);
        });
        return Array.from(buckets.values()).sort((a,b) => a.time - b.time);
      }
      function calendarBucket(time, mode) {
        const d = new Date(time * 1000);
        if (mode === "month") return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000;
        const day = d.getUTCDay() || 7;
        const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
        monday.setUTCDate(monday.getUTCDate() - day + 1);
        return Math.floor(monday.getTime() / 1000);
      }
      function aggregateCalendarCandles(candles, mode) {
        const buckets = new Map();
        candles.forEach((c) => {
          const time = calendarBucket(c.time, mode);
          const b = buckets.get(time) || { time, open:c.open, high:c.high, low:c.low, close:c.close, volume:0 };
          b.high = Math.max(b.high, c.high);
          b.low = Math.min(b.low, c.low);
          b.close = c.close;
          b.volume += Number(c.volume || 0);
          buckets.set(time, b);
        });
        return Array.from(buckets.values()).sort((a,b) => a.time - b.time);
      }
      function aggregateTrades(trades, seconds) {
        const buckets = new Map();
        trades.forEach((t) => {
          const time = Math.floor(Math.floor(t.timeMs / 1000) / seconds) * seconds;
          const b = buckets.get(time) || { time, open:t.price, high:t.price, low:t.price, close:t.price, volume:0 };
          b.high = Math.max(b.high, t.price); b.low = Math.min(b.low, t.price); b.close = t.price; b.volume += t.qty; buckets.set(time, b);
        });
        return Array.from(buckets.values()).sort((a,b) => a.time - b.time);
      }
      function anchorKey(time, anchor) {
        const d = new Date(time * 1000);
        if (anchor === "week") return `${d.getUTCFullYear()}-W${Math.floor((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - Date.UTC(d.getUTCFullYear(),0,1)) / 604800000)}`;
        if (anchor === "month") return `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
        return d.toISOString().slice(0, 10);
      }
      function computeVWAP(candles, anchor="day") {
        let cumPV = 0, cumVol = 0, day = "";
        return candles.map((c) => {
          const d = anchorKey(c.time, anchor);
          if (d !== day) { day = d; cumPV = 0; cumVol = 0; }
          const typical = (c.high + c.low + c.close) / 3;
          cumPV += typical * c.volume; cumVol += c.volume;
          return { time:c.time, value:cumVol ? cumPV / cumVol : c.close };
        });
      }
      function computeStdevBands(candles, vwap, multiplier) {
        let sum = 0, sumSq = 0, count = 0, day = "";
        const out = [];
        candles.forEach((c, i) => {
          const d = anchorKey(c.time, "day");
          if (d !== day) { day = d; sum = 0; sumSq = 0; count = 0; }
          const basis = vwap[i]?.value || c.close;
          const diff = c.close - basis;
          sum += diff; sumSq += diff * diff; count += 1;
          const mean = sum / count;
          const variance = Math.max(0, (sumSq / count) - (mean * mean));
          const stdev = Math.sqrt(variance);
          out.push({ time:c.time, upper:basis + stdev * multiplier, lower:basis - stdev * multiplier });
        });
        return out;
      }
      function computeVolumeStats(candles, period=20) {
        const out = []; let sum = 0;
        candles.forEach((c, i) => {
          sum += c.volume || 0;
          if (i >= period) sum -= candles[i - period].volume || 0;
          const avg = i >= period - 1 ? sum / period : NaN;
          out.push({ time:c.time, avg, rvol:Number.isFinite(avg) && avg > 0 ? c.volume / avg : NaN });
        });
        return out;
      }
      function computeMA(candles, period, type="SMA") {
        if (type === "EMA") {
          const out = [], k = 2 / (period + 1);
          let ema = null;
          candles.forEach((c, i) => {
            ema = ema === null ? c.close : c.close * k + ema * (1 - k);
            if (i >= period - 1) out.push({ time:c.time, value:ema });
          });
          return out;
        }
        const out = []; let sum = 0;
        candles.forEach((c, i) => { sum += c.close; if (i >= period) sum -= candles[i - period].close; if (i >= period - 1) out.push({ time:c.time, value:sum / period }); });
        return out;
      }
      function computeOsc(candles, vwap) {
        const byTime = new Map(vwap.map((v) => [v.time, v.value]));
        return candles.map((c) => { const v = byTime.get(c.time); return { time:c.time, value:v ? ((c.close - v) / v) * 100 : 0 }; });
      }
      function corrPriceVolume(candles, n=80) {
        const data = candles.slice(-n); if (data.length < 10) return NaN;
        const xs = data.map((c, i) => i === 0 ? 0 : c.close - data[i - 1].close), ys = data.map((c) => c.volume);
        const mx = xs.reduce((a,b)=>a+b,0)/xs.length, my = ys.reduce((a,b)=>a+b,0)/ys.length;
        let num=0, dx=0, dy=0; xs.forEach((x,i)=>{ const vx=x-mx, vy=ys[i]-my; num+=vx*vy; dx+=vx*vx; dy+=vy*vy; });
        return dx && dy ? num / Math.sqrt(dx * dy) : NaN;
      }
      function sessionRefs(candles) {
        if (!candles.length) return {};
        const lastDay = anchorKey(candles[candles.length - 1].time, "day");
        const today = candles.filter((c) => anchorKey(c.time, "day") === lastDay);
        const prev = candles.filter((c) => anchorKey(c.time, "day") !== lastDay);
        const open = today[0]?.open;
        const high = today.reduce((m,c) => Math.max(m, c.high), -Infinity);
        const low = today.reduce((m,c) => Math.min(m, c.low), Infinity);
        const prevClose = prev[prev.length - 1]?.close;
        return { open, high, low, prevClose, current:candles[candles.length - 1]?.close };
      }
      function volatilitySource(candles) {
        const series = (yahooPayload.series && yahooPayload.series[state.symbol]) || {};
        return Array.isArray(series.daily) && series.daily.length >= 31 ? series.daily : candles;
      }
      function historicalVolatility(candles, period, prevClose) {
        const source = volatilitySource(candles).filter((c) => Number.isFinite(c.close) && c.close > 0);
        if (source.length < Math.min(period + 1, 31) || !Number.isFinite(prevClose)) {
          return { period, vol:NaN, annualized:NaN, upper:NaN, lower:NaN };
        }
        const slice = source.slice(-(period + 1));
        const returns = [];
        for (let i = 1; i < slice.length; i += 1) {
          const prev = slice[i - 1].close;
          const curr = slice[i].close;
          if (prev > 0 && curr > 0) returns.push(Math.log(curr / prev));
        }
        if (returns.length < 2) return { period, vol:NaN, annualized:NaN, upper:NaN, lower:NaN };
        const mean = returns.reduce((a,b) => a + b, 0) / returns.length;
        const variance = returns.reduce((sum,r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
        const vol = Math.sqrt(Math.max(0, variance));
        const annualized = vol * Math.sqrt(252);
        return {
          period,
          vol,
          annualized,
          upper:prevClose * (1 + vol),
          lower:prevClose * (1 - vol),
        };
      }
      function horizontalSessionLine(candles, value) {
        if (!candles.length || !Number.isFinite(value)) return [];
        const lastDay = anchorKey(candles[candles.length - 1].time, "day");
        const session = candles.filter((c) => anchorKey(c.time, "day") === lastDay);
        const range = session.length ? session : candles;
        return range.map((c) => ({ time:c.time, value }));
      }
      function computeSessionVolumeProfile(candles, bins=36) {
        if (!candles.length) return { bins:[], poc:null, vah:null, val:null, min:NaN, max:NaN, total:0 };
        const lastDay = anchorKey(candles[candles.length - 1].time, "day");
        const session = candles.filter((c) => anchorKey(c.time, "day") === lastDay);
        if (!session.length) return { bins:[], poc:null, vah:null, val:null, min:NaN, max:NaN, total:0 };
        const min = session.reduce((m,c) => Math.min(m, c.low), Infinity);
        const max = session.reduce((m,c) => Math.max(m, c.high), -Infinity);
        const step = (max - min) / bins || 1;
        const profile = Array.from({ length:bins }, (_, i) => ({
          index:i,
          low:min + step * i,
          high:min + step * (i + 1),
          mid:min + step * (i + .5),
          volume:0,
        }));
        session.forEach((c) => {
          const from = Math.max(0, Math.floor((c.low - min) / step));
          const to = Math.min(bins - 1, Math.floor((c.high - min) / step));
          const parts = Math.max(1, to - from + 1);
          for (let i = from; i <= to; i += 1) profile[i].volume += (c.volume || 0) / parts;
        });
        const maxVolume = profile.reduce((m,b) => Math.max(m, b.volume), 0);
        const poc = profile.reduce((best,b) => b.volume > (best?.volume || 0) ? b : best, null);
        const total = session.reduce((sum,c) => sum + (c.volume || 0), 0);
        const valueAreaTarget = total * 0.7;
        let lowIndex = poc?.index ?? 0;
        let highIndex = poc?.index ?? 0;
        let valueVolume = poc?.volume || 0;
        while (valueVolume < valueAreaTarget && (lowIndex > 0 || highIndex < bins - 1)) {
          const lowerVolume = lowIndex > 0 ? profile[lowIndex - 1].volume : -1;
          const upperVolume = highIndex < bins - 1 ? profile[highIndex + 1].volume : -1;
          if (upperVolume >= lowerVolume && highIndex < bins - 1) {
            highIndex += 1;
            valueVolume += profile[highIndex].volume;
          } else if (lowIndex > 0) {
            lowIndex -= 1;
            valueVolume += profile[lowIndex].volume;
          } else {
            break;
          }
        }
        profile.forEach((bin) => { bin.inValueArea = bin.index >= lowIndex && bin.index <= highIndex; });
        const val = profile[lowIndex] || null;
        const vah = profile[highIndex] || null;
        return { bins:profile, poc, vah, val, min, max, maxVolume, total, valueVolume };
      }
      function detectSignals(candles, indicators) {
        const signals = [];
        candles.forEach((c, i) => {
          if (i < 1) return;
          const prev = candles[i - 1];
          const vwap = indicators.vwapDay[i]?.value;
          const rvol = indicators.volumeStats[i]?.rvol;
          if (!vwap || !Number.isFinite(rvol)) return;
          const bullishRejection = c.close > prev.high || (c.low < prev.low && c.close > c.open);
          const bearishRejection = c.close < prev.low || (c.high > prev.high && c.close < c.open);
          if (c.close <= vwap * 0.99 && c.close > c.open && rvol >= 1.5 && bullishRejection) {
            signals.push({ time:c.time, position:"belowBar", color:"#22c55e", shape:"arrowUp", text:"BUY VWAP" });
          }
          if (c.close >= vwap * 1.01 && c.close < c.open && rvol >= 1.5 && bearishRejection) {
            signals.push({ time:c.time, position:"aboveBar", color:"#ef4444", shape:"arrowDown", text:"SELL VWAP" });
          }
        });
        return signals;
      }
      function computeIndicators(candles) {
        const vwapDay = computeVWAP(candles, "day");
        const vwapWeek = computeVWAP(candles, "week");
        const vwapMonth = computeVWAP(candles, "month");
        const volumeStats = computeVolumeStats(candles, 20);
        const ma = state.ma.filter((m) => m.enabled).map((m) => ({ ...m, data:computeMA(candles, m.period, state.maType) }));
        const stdev1 = computeStdevBands(candles, vwapDay, 1);
        const stdev2 = computeStdevBands(candles, vwapDay, 2);
        const refs = sessionRefs(candles);
        const volumeProfile = computeSessionVolumeProfile(candles);
        const hv252 = historicalVolatility(candles, 252, refs.prevClose);
        const hv30 = historicalVolatility(candles, 30, refs.prevClose);
        const indicators = { vwapDay, vwapWeek, vwapMonth, volumeStats, ma, stdev1, stdev2, refs, volumeProfile, hv252, hv30 };
        indicators.signals = detectSignals(candles, indicators);
        return indicators;
      }
      function addLine(key, data, color, width) {
        const s = state.chart.addSeries(LineSeries, { color, lineWidth:width, priceLineVisible:false, lastValueVisible:false });
        s.setData(data); state.series[key] = s;
      }
      function addOscLine(key, data, color, width=1) {
        const s = state.oscChart.addSeries(LineSeries, { color, lineWidth:width, priceLineVisible:false, lastValueVisible:false });
        s.setData(data); state.series[key] = s;
      }
      function addPriceLine(series, title, price, color, style=2) {
        if (!Number.isFinite(price)) return;
        const line = series.createPriceLine({ price, color, lineWidth:1, lineStyle:style, axisLabelVisible:true, title });
        state.priceLines.push(line);
      }
      function applyMarkers(candleSeries, markers) {
        if (!state.toggles.signals) markers = [];
        try {
          if (typeof candleSeries.setMarkers === "function") candleSeries.setMarkers(markers);
          else if (typeof LightweightCharts.createSeriesMarkers === "function") {
            if (state.markerApi?.setMarkers) state.markerApi.setMarkers(markers);
            else state.markerApi = LightweightCharts.createSeriesMarkers(candleSeries, markers);
          }
        } catch (err) { console.warn("Markers indisponiveis", err); }
      }
      function renderVolumeProfile() {
        volumeProfileEl.innerHTML = "";
        volumeProfileEl.style.display = state.toggles.volumeProfile ? "block" : "none";
        const profile = state.indicators?.volumeProfile;
        if (!state.toggles.volumeProfile || !profile?.bins?.length || !state.series.candle) return;
        const chartHeight = chartEl.clientHeight || 620;
        volumeProfileEl.style.height = `${chartHeight}px`;
        const label = document.createElement("div");
        label.className = "lw-vp-label";
        label.textContent = "Sessao VP";
        volumeProfileEl.appendChild(label);
        const maxWidth = Math.max(72, volumeProfileEl.clientWidth - 8);
        profile.bins.forEach((bin) => {
          if (!bin.volume || !profile.maxVolume) return;
          const y = state.series.candle.priceToCoordinate(bin.mid);
          if (!Number.isFinite(y) || y < 0 || y > chartHeight) return;
          const bar = document.createElement("div");
          bar.className = `lw-vp-bar ${bin.inValueArea ? "value-area" : ""} ${profile.poc && bin.index === profile.poc.index ? "poc" : ""}`;
          bar.style.top = `${Math.max(0, y - 2)}px`;
          bar.style.width = `${Math.max(2, (bin.volume / profile.maxVolume) * maxWidth)}px`;
          bar.title = `${fmt(bin.low,2)} - ${fmt(bin.high,2)} | Vol ${fmt(bin.volume,2)}`;
          volumeProfileEl.appendChild(bar);
        });
      }
      function renderCharts(fit=true) {
        if (state.chart) state.chart.remove(); if (state.oscChart) state.oscChart.remove();
        chartEl.innerHTML = ""; oscEl.innerHTML = ""; state.series = {}; state.priceLines = []; state.markerApi = null;
        state.chart = makeChart(chartEl, chartEl.clientHeight || 620);
        state.oscChart = makeChart(oscEl, state.toggles.oscillator ? 150 : 1);
        oscEl.style.display = state.toggles.oscillator ? "block" : "none";
        state.indicators = computeIndicators(state.candles);
        const candleSeries = state.chart.addSeries(CandlestickSeries, { upColor:"#00c087", downColor:"#ff4b4b", borderVisible:false, wickUpColor:"#00c087", wickDownColor:"#ff4b4b" });
        candleSeries.setData(state.candles); state.series.candle = candleSeries;
        applyMarkers(candleSeries, state.indicators.signals);
        if (state.toggles.volume) {
          const volumeSeries = state.chart.addSeries(HistogramSeries, { priceFormat:{ type:"volume" }, priceScaleId:"", color:"#334155" });
          volumeSeries.priceScale().applyOptions({ scaleMargins:{ top:0.82, bottom:0 } });
          volumeSeries.setData(state.candles.map((c, i) => {
            const rvol = state.indicators.volumeStats[i]?.rvol;
            const base = c.close >= c.open ? "0,192,135" : "255,75,75";
            const color = rvol >= 2 ? "rgba(245,158,11,.78)" : rvol >= 1.5 ? `rgba(${base},.75)` : `rgba(${base},.32)`;
            return { time:c.time, value:c.volume, color };
          }));
          state.series.volume = volumeSeries;
          const volAvgSeries = state.chart.addSeries(LineSeries, { color:"#94a3b8", lineWidth:1, priceScaleId:"", priceLineVisible:false, lastValueVisible:false });
          volAvgSeries.priceScale().applyOptions({ scaleMargins:{ top:0.82, bottom:0 } });
          volAvgSeries.setData(state.indicators.volumeStats.filter((v) => Number.isFinite(v.avg)).map((v) => ({ time:v.time, value:v.avg })));
          state.series.vol20 = volAvgSeries;
        }
        const vwap = state.indicators.vwapDay;
        if (state.toggles.vwap) {
          addLine("vwap", state.indicators.vwapDay, "#ffd166", 2);
          addLine("vwapWeek", state.indicators.vwapWeek, "#06d6a0", 1);
          addLine("vwapMonth", state.indicators.vwapMonth, "#118ab2", 1);
        }
        if (state.toggles.bands) {
          [0.005,0.01,0.015,0.02].forEach((pct,i) => {
            const color = ["#38bdf8","#818cf8","#f472b6","#fb7185"][i];
            addLine(`vwap_p_${pct}`, vwap.map((p) => ({ time:p.time, value:p.value * (1 + pct) })), color, 1);
            addLine(`vwap_m_${pct}`, vwap.map((p) => ({ time:p.time, value:p.value * (1 - pct) })), color, 1);
          });
        }
        if (state.toggles.stdevBands) {
          addLine("stdev1u", state.indicators.stdev1.map((p) => ({ time:p.time, value:p.upper })), "#f59e0b", 1);
          addLine("stdev1l", state.indicators.stdev1.map((p) => ({ time:p.time, value:p.lower })), "#f59e0b", 1);
          addLine("stdev2u", state.indicators.stdev2.map((p) => ({ time:p.time, value:p.upper })), "#ef4444", 1);
          addLine("stdev2l", state.indicators.stdev2.map((p) => ({ time:p.time, value:p.lower })), "#ef4444", 1);
        }
        if (state.toggles.ma) state.indicators.ma.forEach((m) => addLine(m.id, m.data, m.color, m.period >= 200 ? 2 : 1));
        if (state.toggles.refs) {
          const refs = state.indicators.refs;
          addPriceLine(candleSeries, "Abertura", refs.open, "#38bdf8");
          addPriceLine(candleSeries, "Max dia", refs.high, "#22c55e");
          addPriceLine(candleSeries, "Min dia", refs.low, "#ef4444");
          addPriceLine(candleSeries, "Fech ant", refs.prevClose, "#f59e0b");
          addPriceLine(candleSeries, "Atual", refs.current, "#f8fafc", 0);
        }
        if (state.toggles.volumeProfile) {
          addPriceLine(candleSeries, "VAH", state.indicators.volumeProfile?.vah?.high, "#22c55e");
          addPriceLine(candleSeries, "VAL", state.indicators.volumeProfile?.val?.low, "#ef4444");
        }
        if (state.toggles.historicalVol) {
          addLine("hv252u", horizontalSessionLine(state.candles, state.indicators.hv252.upper), "#a78bfa", 1);
          addLine("hv252l", horizontalSessionLine(state.candles, state.indicators.hv252.lower), "#a78bfa", 1);
          addLine("hv30u", horizontalSessionLine(state.candles, state.indicators.hv30.upper), "#fb923c", 1);
          addLine("hv30l", horizontalSessionLine(state.candles, state.indicators.hv30.lower), "#fb923c", 1);
          addPriceLine(candleSeries, "HV252 +", state.indicators.hv252.upper, "#a78bfa");
          addPriceLine(candleSeries, "HV252 -", state.indicators.hv252.lower, "#a78bfa");
          addPriceLine(candleSeries, "HV30 +", state.indicators.hv30.upper, "#fb923c");
          addPriceLine(candleSeries, "HV30 -", state.indicators.hv30.lower, "#fb923c");
        }
        if (state.toggles.oscillator) {
          const oscSeries = state.oscChart.addSeries(HistogramSeries, { color:"#38bdf8", priceFormat:{ type:"price", precision:2, minMove:0.01 } });
          oscSeries.setData(computeOsc(state.candles, vwap).map((p) => ({ ...p, color:p.value >= 0 ? "rgba(34,197,94,.65)" : "rgba(239,68,68,.65)" })));
          state.series.osc = oscSeries;
          [0, .5, 1, 2, -.5, -1, -2].forEach((level) => oscSeries.createPriceLine({ price:level, color:level === 0 ? "#e5e7eb" : "#475569", lineWidth:1, lineStyle:2, axisLabelVisible:true, title:`${level}%` }));
          const flat = state.candles.map((c) => ({ time:c.time, value:0 }));
          addOscLine("oscZero", flat, "#e5e7eb", 1);
          if (fit) state.oscChart.timeScale().fitContent();
        }
        if (fit) state.chart.timeScale().fitContent();
        setupCrosshair();
        updateStats();
        requestAnimationFrame(renderVolumeProfile);
      }
      function updateStats() {
        const indicators = state.indicators || computeIndicators(state.candles);
        const vwap = indicators.vwapDay;
        const last = state.candles[state.candles.length - 1], lastVwap = vwap[vwap.length - 1]?.value;
        const lastWeek = indicators.vwapWeek[indicators.vwapWeek.length - 1]?.value;
        const lastMonth = indicators.vwapMonth[indicators.vwapMonth.length - 1]?.value;
        const lastVol = indicators.volumeStats[indicators.volumeStats.length - 1] || {};
        document.getElementById("lw-last").textContent = last ? fmt(last.close, 2) : "---";
        document.getElementById("lw-vwap").textContent = lastVwap ? fmt(lastVwap, 2) : "---";
        document.getElementById("lw-vwap-extra").textContent = `Sem ${fmt(lastWeek,2)} | Mes ${fmt(lastMonth,2)}`;
        document.getElementById("lw-dist").textContent = last && lastVwap ? `${(((last.close - lastVwap) / lastVwap) * 100).toFixed(2)}%` : "---";
        const corr = corrPriceVolume(state.candles);
        document.getElementById("lw-corr").textContent = Number.isFinite(corr) ? corr.toFixed(2) : "---";
        document.getElementById("lw-volume").textContent = last ? fmt(last.volume, 4) : "---";
        document.getElementById("lw-rvol").textContent = `Media20 ${fmt(lastVol.avg, 2)} | RVOL ${fmt(lastVol.rvol, 2)}x`;
        document.getElementById("lw-vp-poc").textContent = `POC ${fmt(indicators.volumeProfile?.poc?.mid, 2)}`;
        document.getElementById("lw-vp-range").textContent = `Range ${fmt(indicators.volumeProfile?.min, 2)} - ${fmt(indicators.volumeProfile?.max, 2)} | Vol ${fmt(indicators.volumeProfile?.total, 2)}`;
        document.getElementById("lw-vp-value-area").textContent = `VAH ${fmt(indicators.volumeProfile?.vah?.high, 2)} | VAL ${fmt(indicators.volumeProfile?.val?.low, 2)}`;
        document.getElementById("lw-hv252").textContent = `HV252 ${Number.isFinite(indicators.hv252?.annualized) ? (indicators.hv252.annualized * 100).toFixed(2) : "---"}% anual`;
        document.getElementById("lw-hv30").textContent = `HV30 ${Number.isFinite(indicators.hv30?.annualized) ? (indicators.hv30.annualized * 100).toFixed(2) : "---"}% anual`;
        document.getElementById("lw-hv-levels").textContent = `30: ${fmt(indicators.hv30?.lower, 2)} / ${fmt(indicators.hv30?.upper, 2)} | 252: ${fmt(indicators.hv252?.lower, 2)} / ${fmt(indicators.hv252?.upper, 2)}`;
        renderAlerts(last, lastVwap, lastVol.rvol, indicators.signals);
      }
      function renderAlerts(last, vwap, rvol, signals) {
        const box = document.getElementById("lw-alerts");
        box.innerHTML = "";
        const alerts = [];
        if (last && vwap) {
          const dist = (last.close - vwap) / vwap;
          if (dist >= .01) alerts.push(["Preço em banda +1%", "hot"]);
          if (dist <= -.01) alerts.push(["Preço em banda -1%", "hot"]);
        }
        if (Number.isFinite(rvol) && rvol >= 2) alerts.push(["Volume relativo extremo", "hot"]);
        else if (Number.isFinite(rvol) && rvol >= 1.5) alerts.push(["Volume relativo alto", "hot"]);
        const recent = (signals || []).filter((s) => last && s.time >= last.time - (tfSeconds[state.timeframe] || 60) * 3);
        if (recent.some((s) => s.text.includes("BUY"))) alerts.push(["Setup compra em formação", "buy"]);
        if (recent.some((s) => s.text.includes("SELL"))) alerts.push(["Setup venda em formação", "sell"]);
        if (!alerts.length) alerts.push(["Sem alerta operacional ativo", ""]);
        alerts.forEach(([text, cls]) => {
          const div = document.createElement("div");
          div.className = `lw-alert ${cls}`;
          div.textContent = text;
          box.appendChild(div);
        });
      }
      function candleByTime(time) {
        return state.candles.find((c) => c.time === time);
      }
      function vwapAt(time) {
        return (state.indicators?.vwapDay || []).find((v) => v.time === time)?.value;
      }
      function renderHover(c, x=12, y=12) {
        if (!c) return;
        const v = vwapAt(c.time);
        const change = ((c.close - c.open) / c.open) * 100;
        const dist = v ? ((c.close - v) / v) * 100 : NaN;
        const html = `
          <strong>${state.symbol} | ${fmtTime(c.time)}</strong>
          <div class="lw-crosshair-grid">
            <div><span>Open</span> ${fmt(c.open,2)}</div><div><span>High</span> ${fmt(c.high,2)}</div>
            <div><span>Low</span> ${fmt(c.low,2)}</div><div><span>Close</span> ${fmt(c.close,2)}</div>
            <div><span>Volume</span> ${fmt(c.volume,2)}</div><div><span>Var</span> ${Number.isFinite(change) ? change.toFixed(2) : "---"}%</div>
            <div><span>VWAP</span> ${fmt(v,2)}</div><div><span>Dist VWAP</span> ${Number.isFinite(dist) ? dist.toFixed(2) : "---"}%</div>
          </div>`;
        crosshairCard.innerHTML = html;
        crosshairCard.style.display = "block";
        crosshairCard.style.left = `${Math.min(x + 16, Math.max(12, chartEl.clientWidth - 280))}px`;
        crosshairCard.style.top = `${Math.min(y + 16, Math.max(12, chartEl.clientHeight - 160))}px`;
        document.getElementById("lw-hover-title").textContent = `${fmtTime(c.time)}`;
        document.getElementById("lw-hover-data").textContent = `O ${fmt(c.open,2)} H ${fmt(c.high,2)} L ${fmt(c.low,2)} C ${fmt(c.close,2)} | Vol ${fmt(c.volume,2)} | Dist VWAP ${Number.isFinite(dist) ? dist.toFixed(2) : "---"}%`;
      }
      function setupCrosshair() {
        state.chart.subscribeCrosshairMove((param) => {
          if (!param?.time || !param.point) { crosshairCard.style.display = "none"; return; }
          const c = candleByTime(param.time);
          renderHover(c, param.point.x, param.point.y);
        });
      }
      function refreshLiveSeries() {
        if (!state.series.candle || !state.candles.length) return renderCharts(false);
        state.indicators = computeIndicators(state.candles);
        const last = state.candles[state.candles.length - 1];
        state.series.candle.update(last);
        if (state.series.volume) {
          const i = state.candles.length - 1;
          const rvol = state.indicators.volumeStats[i]?.rvol;
          const base = last.close >= last.open ? "0,192,135" : "255,75,75";
          const color = rvol >= 2 ? "rgba(245,158,11,.78)" : rvol >= 1.5 ? `rgba(${base},.75)` : `rgba(${base},.32)`;
          state.series.volume.update({ time:last.time, value:last.volume, color });
        }
        if (state.series.vol20) state.series.vol20.setData(state.indicators.volumeStats.filter((v) => Number.isFinite(v.avg)).map((v) => ({ time:v.time, value:v.avg })));
        if (state.series.vwap) state.series.vwap.setData(state.indicators.vwapDay);
        if (state.series.vwapWeek) state.series.vwapWeek.setData(state.indicators.vwapWeek);
        if (state.series.vwapMonth) state.series.vwapMonth.setData(state.indicators.vwapMonth);
        [0.005,0.01,0.015,0.02].forEach((pct) => {
          state.series[`vwap_p_${pct}`]?.setData(state.indicators.vwapDay.map((p) => ({ time:p.time, value:p.value * (1 + pct) })));
          state.series[`vwap_m_${pct}`]?.setData(state.indicators.vwapDay.map((p) => ({ time:p.time, value:p.value * (1 - pct) })));
        });
        state.series.stdev1u?.setData(state.indicators.stdev1.map((p) => ({ time:p.time, value:p.upper })));
        state.series.stdev1l?.setData(state.indicators.stdev1.map((p) => ({ time:p.time, value:p.lower })));
        state.series.stdev2u?.setData(state.indicators.stdev2.map((p) => ({ time:p.time, value:p.upper })));
        state.series.stdev2l?.setData(state.indicators.stdev2.map((p) => ({ time:p.time, value:p.lower })));
        state.series.hv252u?.setData(horizontalSessionLine(state.candles, state.indicators.hv252.upper));
        state.series.hv252l?.setData(horizontalSessionLine(state.candles, state.indicators.hv252.lower));
        state.series.hv30u?.setData(horizontalSessionLine(state.candles, state.indicators.hv30.upper));
        state.series.hv30l?.setData(horizontalSessionLine(state.candles, state.indicators.hv30.lower));
        state.indicators.ma.forEach((m) => state.series[m.id]?.setData(m.data));
        if (state.series.osc) {
          state.series.osc.setData(computeOsc(state.candles, state.indicators.vwapDay).map((p) => ({ ...p, color:p.value >= 0 ? "rgba(34,197,94,.65)" : "rgba(239,68,68,.65)" })));
        }
        applyMarkers(state.series.candle, state.indicators.signals);
        updateStats();
        requestAnimationFrame(renderVolumeProfile);
      }
      function startSocket() {
        if (state.socket) state.socket.close();
        const asset = assetRegistry[state.symbol] || { source: "binance" };
        if (asset.source !== "binance") {
          state.socket = null;
          setStatus(`Dados yfinance carregados: ${asset.label} (${asset.ticker}). Sem WebSocket em tempo real; atualize a pagina para recarregar.`);
          return;
        }
        state.socket = new WebSocket(`wss://stream.binance.com:9443/ws/${state.symbol.toLowerCase()}@aggTrade`);
        state.socket.onmessage = (event) => {
          const t = JSON.parse(event.data), price = +t.p, qty = +t.q;
          const rawTime = Math.floor(t.T / 1000);
          const time = state.timeframe === "1month"
            ? calendarBucket(rawTime, "month")
            : state.timeframe === "1w"
              ? calendarBucket(rawTime, "week")
              : Math.floor(rawTime / tfSeconds[state.timeframe]) * tfSeconds[state.timeframe];
          let last = state.candles[state.candles.length - 1];
          if (!last || time > last.time) { last = { time, open:price, high:price, low:price, close:price, volume:qty }; state.candles.push(last); if (state.candles.length > 650) state.candles.shift(); }
          else { last.high = Math.max(last.high, price); last.low = Math.min(last.low, price); last.close = price; last.volume += qty; }
          refreshLiveSeries(); setStatus(`Tempo real Binance ativo: ${state.symbol} ${state.timeframe}`);
        };
        state.socket.onerror = () => setStatus("WebSocket Binance indisponivel no momento.");
      }
      async function loadSymbol(symbol, timeframe) {
        state.symbol = symbol; state.timeframe = timeframe; renderControls();
        savePrefs();
        const asset = assetRegistry[symbol] || { source: "binance", label: symbol };
        setLoading(true);
        if (asset.source === "yahoo" && timeframe === "30s") {
          setStatus(`${asset.label}: yfinance nao possui 30s; usando candles de 1m.`);
        } else {
          setStatus(`Carregando historico ${asset.source === "yahoo" ? "yfinance" : "Binance"}: ${asset.label || symbol} ${timeframe}...`);
        }
        try {
          state.candles = await fetchHistorical(symbol, timeframe);
          if (!state.candles.length) throw new Error(`Ativo ${asset.label || symbol} sem candles para ${timeframe}.`);
          renderCharts();
          startSocket();
          if (asset.source === "binance") setStatus("Historico carregado. Atualizacao em tempo real via Binance WebSocket.");
        }
        catch (err) {
          console.error(err);
          chartEl.innerHTML = '<div style="display:grid;place-items:center;height:100%;color:#cbd5e1;font-weight:900;">Sem dados para este ativo/timeframe.</div>';
          oscEl.innerHTML = "";
          setStatus(`Erro ao carregar dados: ${err.message}`);
        }
        finally { setLoading(false); }
      }
      window.addEventListener("resize", () => {
        if (state.chart) state.chart.applyOptions({ width:chartEl.clientWidth });
        if (state.oscChart) state.oscChart.applyOptions({ width:oscEl.clientWidth });
        requestAnimationFrame(renderVolumeProfile);
      });
      renderControls(); loadSymbol(state.symbol, state.timeframe);
    })();
    </script>
    """
    return html.replace("__YAHOO_PAYLOAD__", yahoo_json)
