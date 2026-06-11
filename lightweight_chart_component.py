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
    try:
        data = yf.download(
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
        return {"assets": YAHOO_LIGHTWEIGHT_ASSETS, "series": {}, "error": str(e)}

    if data is None or data.empty:
        return {"assets": YAHOO_LIGHTWEIGHT_ASSETS, "series": {}, "error": "Yahoo Finance retornou vazio."}

    for asset in YAHOO_LIGHTWEIGHT_ASSETS:
        ticker = asset["ticker"]
        try:
            if hasattr(data.columns, "levels"):
                if ticker not in set(data.columns.get_level_values(0)):
                    continue
                df = data[ticker]
            else:
                df = data
            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            candles = []
            for idx, row in df.tail(650).iterrows():
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
            if candles:
                payload[asset["symbol"]] = {
                    "label": asset["label"],
                    "ticker": ticker,
                    "candles": candles,
                }
        except Exception:
            continue
    return {"assets": YAHOO_LIGHTWEIGHT_ASSETS, "series": payload, "error": None}


def render_lightweight_chart_html():
    yahoo_payload = load_yahoo_lightweight_payload()
    yahoo_json = json.dumps(yahoo_payload, ensure_ascii=False)
    html = """
    <div id="lw-root">
      <style>
        #lw-root { background:#080d14; border:1px solid #1f2937; border-radius:8px; color:#e5e7eb; font-family:Inter,"Segoe UI",Arial,sans-serif; overflow:hidden; }
        .lw-toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; padding:10px 12px; background:#0d1420; border-bottom:1px solid #1f2937; }
        .lw-group { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
        .lw-label { color:#94a3b8; font-size:.72rem; font-weight:800; text-transform:uppercase; letter-spacing:.04em; margin-right:2px; }
        .lw-btn { border:1px solid #334155; background:#111827; color:#cbd5e1; border-radius:5px; padding:6px 9px; font-size:.78rem; font-weight:800; cursor:pointer; }
        .lw-btn.active { border-color:#38bdf8; color:#fff; background:#0f3b5f; }
        .lw-btn.toggle-on { border-color:#22c55e; color:#eafff3; }
        .lw-main { display:grid; grid-template-columns:minmax(0,1fr) 250px; gap:0; }
        #lw-chart { height:620px; min-width:0; }
        #lw-osc { height:150px; border-top:1px solid #1f2937; }
        .lw-side { border-left:1px solid #1f2937; background:#0b1220; padding:10px; display:grid; align-content:start; gap:8px; }
        .lw-stat { background:#111827; border:1px solid #253044; border-radius:6px; padding:8px; }
        .lw-stat span { display:block; color:#94a3b8; font-size:.68rem; font-weight:800; text-transform:uppercase; }
        .lw-stat strong { display:block; color:#f8fafc; font-size:1rem; margin-top:3px; }
        .lw-status { color:#94a3b8; font-size:.75rem; padding:8px 12px 10px; border-top:1px solid #1f2937; background:#0d1420; }
        @media (max-width:900px){ .lw-main{grid-template-columns:1fr;} .lw-side{border-left:0; border-top:1px solid #1f2937; grid-template-columns:repeat(2,minmax(0,1fr));} #lw-chart{height:520px;} }
      </style>
      <div class="lw-toolbar">
        <div class="lw-group" id="lw-assets"><span class="lw-label">Ativo</span></div>
        <div class="lw-group" id="lw-timeframes"><span class="lw-label">Tempo</span></div>
        <div class="lw-group" id="lw-toggles"><span class="lw-label">Camadas</span></div>
      </div>
      <div class="lw-main">
        <div><div id="lw-chart"></div><div id="lw-osc"></div></div>
        <aside class="lw-side">
          <div class="lw-stat"><span>Ultimo</span><strong id="lw-last">---</strong></div>
          <div class="lw-stat"><span>VWAP</span><strong id="lw-vwap">---</strong></div>
          <div class="lw-stat"><span>Dist. VWAP</span><strong id="lw-dist">---</strong></div>
          <div class="lw-stat"><span>Corr preco x volume</span><strong id="lw-corr">---</strong></div>
          <div class="lw-stat"><span>Volume candle</span><strong id="lw-volume">---</strong></div>
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
      const timeframes = ["15s", "30s", "1m", "5m", "15m"];
      const tfSeconds = { "15s": 15, "30s": 30, "1m": 60, "5m": 300, "15m": 900 };
      const state = { symbol:"BTCUSDT", timeframe:"1m", candles:[], chart:null, oscChart:null, series:{}, socket:null, toggles:{ ma:true, ma200:false, vwap:true, bands:true, volume:true, oscillator:true } };
      const chartEl = document.getElementById("lw-chart");
      const oscEl = document.getElementById("lw-osc");
      const statusEl = document.getElementById("lw-status");
      const fmt = (n, d=2) => Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits:d, minimumFractionDigits:d }) : "---";
      const setStatus = (msg) => { statusEl.textContent = msg; };

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
        assetBox.querySelectorAll("button").forEach((el) => el.remove());
        tfBox.querySelectorAll("button").forEach((el) => el.remove());
        toggleBox.querySelectorAll("button").forEach((el) => el.remove());
        assets.forEach((asset) => assetBox.appendChild(button(asset.label, state.symbol === asset.symbol, () => loadSymbol(asset.symbol, state.timeframe))));
        timeframes.forEach((tf) => tfBox.appendChild(button(tf, state.timeframe === tf, () => loadSymbol(state.symbol, tf))));
        [["ma","Medias"],["ma200","MA200"],["vwap","VWAP"],["bands","Bandas"],["volume","Volume"],["oscillator","Osc"]].forEach(([key,label]) => {
          toggleBox.appendChild(button(label, state.toggles[key], () => { state.toggles[key] = !state.toggles[key]; renderControls(); renderCharts(); }, state.toggles[key] ? "toggle-on" : ""));
        });
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
        if (["1m","5m","15m"].includes(timeframe)) {
          const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${timeframe}&limit=600`);
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
        const base = (yahooPayload.series && yahooPayload.series[symbol] && yahooPayload.series[symbol].candles) || [];
        if (!base.length) throw new Error(`Sem dados yfinance para ${symbol}`);
        if (timeframe === "5m") return aggregateCandles(base, 300);
        if (timeframe === "15m") return aggregateCandles(base, 900);
        return base;
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
      function aggregateTrades(trades, seconds) {
        const buckets = new Map();
        trades.forEach((t) => {
          const time = Math.floor(Math.floor(t.timeMs / 1000) / seconds) * seconds;
          const b = buckets.get(time) || { time, open:t.price, high:t.price, low:t.price, close:t.price, volume:0 };
          b.high = Math.max(b.high, t.price); b.low = Math.min(b.low, t.price); b.close = t.price; b.volume += t.qty; buckets.set(time, b);
        });
        return Array.from(buckets.values()).sort((a,b) => a.time - b.time);
      }
      function computeVWAP(candles) {
        let cumPV = 0, cumVol = 0, day = "";
        return candles.map((c) => {
          const d = new Date(c.time * 1000).toISOString().slice(0, 10);
          if (d !== day) { day = d; cumPV = 0; cumVol = 0; }
          const typical = (c.high + c.low + c.close) / 3;
          cumPV += typical * c.volume; cumVol += c.volume;
          return { time:c.time, value:cumVol ? cumPV / cumVol : c.close };
        });
      }
      function computeMA(candles, period) {
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
      function addLine(key, data, color, width) {
        const s = state.chart.addSeries(LineSeries, { color, lineWidth:width, priceLineVisible:false, lastValueVisible:false });
        s.setData(data); state.series[key] = s;
      }
      function renderCharts() {
        if (state.chart) state.chart.remove(); if (state.oscChart) state.oscChart.remove();
        chartEl.innerHTML = ""; oscEl.innerHTML = ""; state.series = {};
        state.chart = makeChart(chartEl, chartEl.clientHeight || 620);
        state.oscChart = makeChart(oscEl, state.toggles.oscillator ? 150 : 1);
        oscEl.style.display = state.toggles.oscillator ? "block" : "none";
        const candleSeries = state.chart.addSeries(CandlestickSeries, { upColor:"#00c087", downColor:"#ff4b4b", borderVisible:false, wickUpColor:"#00c087", wickDownColor:"#ff4b4b" });
        candleSeries.setData(state.candles); state.series.candle = candleSeries;
        if (state.toggles.volume) {
          const volumeSeries = state.chart.addSeries(HistogramSeries, { priceFormat:{ type:"volume" }, priceScaleId:"", color:"#334155" });
          volumeSeries.priceScale().applyOptions({ scaleMargins:{ top:0.82, bottom:0 } });
          volumeSeries.setData(state.candles.map((c) => ({ time:c.time, value:c.volume, color:c.close >= c.open ? "rgba(0,192,135,.35)" : "rgba(255,75,75,.35)" })));
          state.series.volume = volumeSeries;
        }
        const vwap = computeVWAP(state.candles);
        if (state.toggles.vwap) addLine("vwap", vwap, "#ffd166", 2);
        if (state.toggles.bands) {
          [0.005,0.01,0.015,0.02].forEach((pct,i) => {
            const color = ["#38bdf8","#818cf8","#f472b6","#fb7185"][i];
            addLine(`vwap_p_${pct}`, vwap.map((p) => ({ time:p.time, value:p.value * (1 + pct) })), color, 1);
            addLine(`vwap_m_${pct}`, vwap.map((p) => ({ time:p.time, value:p.value * (1 - pct) })), color, 1);
          });
        }
        if (state.toggles.ma) [[9,"#22c55e"],[21,"#eab308"],[80,"#38bdf8"]].forEach(([p,color]) => addLine(`ma${p}`, computeMA(state.candles, p), color, 1));
        if (state.toggles.ma200) addLine("ma200", computeMA(state.candles, 200), "#f8fafc", 1);
        if (state.toggles.oscillator) {
          const oscSeries = state.oscChart.addSeries(HistogramSeries, { color:"#38bdf8", priceFormat:{ type:"price", precision:2, minMove:0.01 } });
          oscSeries.setData(computeOsc(state.candles, vwap).map((p) => ({ ...p, color:p.value >= 0 ? "rgba(34,197,94,.65)" : "rgba(239,68,68,.65)" })));
          state.oscChart.timeScale().fitContent();
        }
        state.chart.timeScale().fitContent(); updateStats(vwap);
      }
      function updateStats(vwap) {
        const last = state.candles[state.candles.length - 1], lastVwap = vwap[vwap.length - 1]?.value;
        document.getElementById("lw-last").textContent = last ? fmt(last.close, 2) : "---";
        document.getElementById("lw-vwap").textContent = lastVwap ? fmt(lastVwap, 2) : "---";
        document.getElementById("lw-dist").textContent = last && lastVwap ? `${(((last.close - lastVwap) / lastVwap) * 100).toFixed(2)}%` : "---";
        const corr = corrPriceVolume(state.candles);
        document.getElementById("lw-corr").textContent = Number.isFinite(corr) ? corr.toFixed(2) : "---";
        document.getElementById("lw-volume").textContent = last ? fmt(last.volume, 4) : "---";
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
          const t = JSON.parse(event.data), price = +t.p, qty = +t.q, seconds = tfSeconds[state.timeframe];
          const time = Math.floor(Math.floor(t.T / 1000) / seconds) * seconds;
          let last = state.candles[state.candles.length - 1];
          if (!last || time > last.time) { last = { time, open:price, high:price, low:price, close:price, volume:qty }; state.candles.push(last); if (state.candles.length > 650) state.candles.shift(); }
          else { last.high = Math.max(last.high, price); last.low = Math.min(last.low, price); last.close = price; last.volume += qty; }
          renderCharts(); setStatus(`Tempo real Binance ativo: ${state.symbol} ${state.timeframe}`);
        };
        state.socket.onerror = () => setStatus("WebSocket Binance indisponivel no momento.");
      }
      async function loadSymbol(symbol, timeframe) {
        state.symbol = symbol; state.timeframe = timeframe; renderControls();
        const asset = assetRegistry[symbol] || { source: "binance", label: symbol };
        if (asset.source === "yahoo" && ["15s", "30s"].includes(timeframe)) {
          setStatus(`${asset.label}: yfinance nao possui 15s/30s; usando candles de 1m.`);
        } else {
          setStatus(`Carregando historico ${asset.source === "yahoo" ? "yfinance" : "Binance"}: ${asset.label || symbol} ${timeframe}...`);
        }
        try { state.candles = await fetchHistorical(symbol, timeframe); renderCharts(); startSocket(); if (asset.source === "binance") setStatus("Historico carregado. Atualizacao em tempo real via Binance WebSocket."); }
        catch (err) { console.error(err); setStatus(`Erro ao carregar dados: ${err.message}`); }
      }
      window.addEventListener("resize", () => { if (state.chart) state.chart.applyOptions({ width:chartEl.clientWidth }); if (state.oscChart) state.oscChart.applyOptions({ width:oscEl.clientWidth }); });
      renderControls(); loadSymbol(state.symbol, state.timeframe);
    })();
    </script>
    """
    return html.replace("__YAHOO_PAYLOAD__", yahoo_json)
