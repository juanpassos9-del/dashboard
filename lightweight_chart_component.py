import json
import os
import time

import requests
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

FRED_LIGHTWEIGHT_ASSETS = [
    {"symbol": "FRED_DGS10", "label": "US10Y FRED", "series_id": "DGS10"},
    {"symbol": "FRED_DGS30", "label": "US30Y FRED", "series_id": "DGS30"},
    {"symbol": "FRED_DFF", "label": "Fed Funds", "series_id": "DFF"},
    {"symbol": "FRED_CPIAUCSL", "label": "CPI FRED", "series_id": "CPIAUCSL"},
    {"symbol": "FRED_UNRATE", "label": "Unemp FRED", "series_id": "UNRATE"},
]


def _clean_secret(value) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _secret_or_env(name: str) -> str:
    try:
        value = st.secrets.get(name, "") or os.environ.get(name, "")
        return _clean_secret(value)
    except Exception:
        return _clean_secret(os.environ.get(name, ""))


def _nested_secret_or_env(name: str, *paths) -> str:
    direct = _secret_or_env(name)
    if direct:
        return direct
    for path in paths:
        try:
            node = st.secrets
            for part in path:
                node = node.get(part, {})
            value = _clean_secret(node)
            if value:
                return value
        except Exception:
            continue
    return ""


def _rows_to_candles(rows, limit=650):
    candles = []
    for row in rows[-limit:]:
        try:
            candles.append({
                "time": int(row["time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0) or 0),
            })
        except Exception:
            continue
    return candles


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


@st.cache_data(ttl=900, show_spinner=False)
def load_fred_lightweight_payload():
    api_key = _nested_secret_or_env("FRED_API_KEY", ("fred", "api_key"), ("FRED", "API_KEY"))
    if not api_key:
        return {
            "enabled": False,
            "assets": FRED_LIGHTWEIGHT_ASSETS,
            "series": {},
            "error": "Configure FRED_API_KEY para habilitar FRED.",
        }

    payload = {}
    errors = []
    for asset in FRED_LIGHTWEIGHT_ASSETS:
        series_id = asset["series_id"]
        try:
            res = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 650,
                },
                timeout=12,
            )
            res.raise_for_status()
            observations = list(reversed(res.json().get("observations", [])))
            candles = []
            previous = None
            for item in observations:
                value = item.get("value")
                if value in (None, "."):
                    continue
                close = float(value)
                open_ = previous if previous is not None else close
                ts = int(time.mktime(time.strptime(item["date"], "%Y-%m-%d")))
                candles.append({
                    "time": ts,
                    "open": open_,
                    "high": max(open_, close),
                    "low": min(open_, close),
                    "close": close,
                    "volume": 0.0,
                })
                previous = close
            if candles:
                payload[asset["symbol"]] = {
                    "label": asset["label"],
                    "series_id": series_id,
                    "daily": candles[-650:],
                    "intraday": [],
                }
        except Exception as e:
            errors.append(f"{series_id}: {e}")
    return {"enabled": True, "assets": FRED_LIGHTWEIGHT_ASSETS, "series": payload, "error": "; ".join(errors) or None}


def render_lightweight_chart_html(signal_mode="all", chart_title=None, instance_id="main"):
    signal_mode = signal_mode if signal_mode in {"all", "reversal"} else "reversal"
    instance_id = "".join(ch for ch in str(instance_id or "main") if ch.isalnum() or ch in ("_", "-")) or "main"
    chart_title = chart_title or {
        "all": "Grafico operacional - Reversao",
        "reversal": "Grafico operacional - Reversao",
    }[signal_mode]
    yahoo_payload = load_yahoo_lightweight_payload()
    fred_payload = load_fred_lightweight_payload()
    yahoo_json = json.dumps(yahoo_payload, ensure_ascii=False)
    fred_json = json.dumps(fred_payload, ensure_ascii=False)
    signal_mode_json = json.dumps(signal_mode)
    chart_title_json = json.dumps(chart_title, ensure_ascii=False)
    instance_id_json = json.dumps(instance_id)
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
        #lw-chart { height:1000px; min-width:0; }
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
        .lw-volume-profile { position:absolute; top:0; right:56px; width:150px; height:1000px; z-index:3; pointer-events:none; opacity:.82; }
        .lw-vp-bar { position:absolute; right:0; height:3px; min-width:2px; border-radius:999px 0 0 999px; background:rgba(56,189,248,.32); }
        .lw-vp-bar.value-area { background:rgba(34,197,94,.38); }
        .lw-vp-bar.poc { height:5px; background:rgba(245,158,11,.9); box-shadow:0 0 8px rgba(245,158,11,.55); }
        .lw-vp-label { position:absolute; right:0; top:6px; color:#94a3b8; font-size:.66rem; font-weight:900; text-transform:uppercase; background:rgba(8,13,20,.72); padding:2px 5px; border:1px solid #334155; border-radius:4px; }
        .lw-skeleton { position:absolute; inset:0; z-index:4; display:none; background:linear-gradient(90deg,#0b1220 0%,#111827 50%,#0b1220 100%); background-size:220% 100%; animation:lwPulse 1.2s ease-in-out infinite; }
        .lw-skeleton.show { display:block; }
        @keyframes lwPulse { from{background-position:220% 0;} to{background-position:-220% 0;} }
        .lw-status { color:#94a3b8; font-size:.75rem; padding:8px 12px 10px; border-top:1px solid #1f2937; background:#0d1420; }
        @media (max-width:900px){ .lw-main{grid-template-columns:1fr;} .lw-side{border-left:0; border-top:1px solid #1f2937; grid-template-columns:repeat(2,minmax(0,1fr));} #lw-chart{height:640px;} }
      </style>
      <div class="lw-toolbar">
        <div class="lw-group"><span class="lw-label" id="lw-chart-title">Grafico operacional</span></div>
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
        </div>
        <aside class="lw-side">
          <div class="lw-stat"><span>Ultimo</span><strong id="lw-last">---</strong></div>
          <div class="lw-stat"><span>VWAP / distancia</span><strong id="lw-vwap">---</strong><small id="lw-vwap-extra">---</small></div>
          <div class="lw-stat"><span>Volume</span><strong id="lw-volume">---</strong><small id="lw-rvol">RVOL ---</small></div>
          <div class="lw-stat"><span>Volume Profile</span><strong id="lw-vp-poc">POC ---</strong><small id="lw-vp-value-area">VAH --- | VAL ---</small></div>
          <div class="lw-stat"><span>HV 252</span><strong id="lw-hv252">HV252 ---</strong><small id="lw-hv30">---</small><small id="lw-hv-levels" style="display:none;">---</small></div>
          <div class="lw-stat"><span>Sinal / Candle</span><strong id="lw-hover-title">Passe o mouse</strong><small id="lw-hover-data">OHLC, VWAP e sinal.</small></div>
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
      const fredPayload = __FRED_PAYLOAD__;
      const signalMode = __SIGNAL_MODE__;
      const chartTitle = __CHART_TITLE__;
      const instanceId = __INSTANCE_ID__;
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
      const fredAssets = (fredPayload.assets || []).map((asset) => ({
        symbol: asset.symbol,
        label: asset.label,
        source: "fred",
        seriesId: asset.series_id,
      }));
      const assets = [...binanceAssets, ...yahooAssets, ...fredAssets];
      const assetRegistry = Object.fromEntries(assets.map((asset) => [asset.symbol, asset]));
      const timeframes = ["30s", "1m", "5m", "h1", "1d", "1w", "1month"];
      const tfSeconds = { "30s": 30, "1m": 60, "5m": 300, "h1": 3600, "1d": 86400, "1w": 604800 };
      const binanceIntervals = { "1m": "1m", "5m": "5m", "h1": "1h", "1d": "1d", "1w": "1w", "1month": "1M" };
      const intradayTimeframes = ["30s", "1m", "5m", "h1"];
      const vwapStdevMultipliers = [1, 2, 3];
      const signalModeTypes = {
        all:["REV_BUY","REV_SELL"],
        reversal:["REV_BUY","REV_SELL"],
      };
      const allowedSignalTypes = signalModeTypes[signalMode] || signalModeTypes.all;
      const signalStorageKey = `lw_chart_prefs_${signalMode}_${instanceId}`;
      const defaultSignalConfig = {
        enabled:true,
        signalFamilies:{ reversal:true, trend:false },
        enabledSignals:{
          REV_BUY:allowedSignalTypes.includes("REV_BUY"),
          REV_SELL:allowedSignalTypes.includes("REV_SELL"),
          TREND_BUY:false,
          TREND_SELL:false,
        },
        minScore:9,
        cooldownCandles:24,
        rsi:{ enabled:true, length:14, oversold:35, overbought:65, trendBuyMin:40, trendBuyMax:55, trendSellMin:45, trendSellMax:60, requireTurn:true },
        reversal:{ minDistanceFromVWAPPercent:0.5, proximityPercent:0.15, requireVwapHvConfluence:true, minStdevMultiplier:1, hvProximityPercent:0.35 },
        trend:{ maxPullbackDistancePercent:0.15, maxVWAPDistancePercent:0.45, minBodyPercent:0.55, requireRsiPullback:true, rsiPeriod:14, rsiBuyMin:40, rsiBuyMax:55, rsiSellMin:45, rsiSellMax:60 },
        volume:{ enabled:true, lookback:20, minVolumeMultiplier:1.2, minRelativeVolume:1.2, strongRelativeVolume:1.5, blockLowVolumeSignals:true, requireBarVolumeAboveAverage:true, requireVolumeExpansion:true, legLookback:5, minLegRelativeVolume:1.1, requireReversalVolumeClimaxOrRejection:true, requireTrendVolumeResumption:true, blockFallingVolume:true, fallingVolumeLookback:3 },
        sessionFilter:{ enabled:false, blockedTimes:[] },
        weights:{
          favorableRegime:2,
          movingAverageAlignment:2,
          vwapDistance:2,
          proximityToKeyLevel:1,
          extremeLocation:3,
          pullbackLocation:3,
          rejectionCandle:2,
          impulseCandle:2,
          rsiConfirmation:3,
          hvConfluence:2,
          volumeConfirmation:3,
          barVolumeConfirmation:3,
          relativeVolumeConfirmation:2,
          strongRelativeVolumeConfirmation:2,
          legVolumeConfirmation:2,
          volumeExpansion:2,
          weakPullbackVolume:2,
          trendVolumeResumption:2,
          previousCandleBreak:1,
          vwapSide:1,
        },
      };
      const defaultPrefs = {
        symbol:"BTCUSDT",
        timeframe:"1m",
        toggles:{ ma:true, vwap:true, bandsDay:true, bandsWeek:false, bandsWeekVol:false, bands:false, stdevBands:false, volume:true, volumeProfile:true, hv252:true, refs:true, signals:true },
        maType:"SMA",
        ma:[
          { id:"ma9", period:9, enabled:true, color:"#22c55e" },
          { id:"ma21", period:21, enabled:true, color:"#eab308" },
          { id:"ma80", period:80, enabled:true, color:"#38bdf8" },
          { id:"ma200", period:200, enabled:false, color:"#f8fafc" },
        ],
      };
      const storedPrefs = (() => { try { return JSON.parse(localStorage.getItem(signalStorageKey) || "{}"); } catch (_) { return {}; } })();
      const prefs = {
        ...defaultPrefs,
        ...storedPrefs,
        toggles:{ ...defaultPrefs.toggles, ...(storedPrefs.toggles || {}) },
        ma: Array.isArray(storedPrefs.ma) ? storedPrefs.ma : defaultPrefs.ma,
        signalConfig:{
          ...defaultSignalConfig,
          ...(storedPrefs.signalConfig || {}),
          signalFamilies:{ ...defaultSignalConfig.signalFamilies, ...((storedPrefs.signalConfig || {}).signalFamilies || {}) },
          enabledSignals:{ ...defaultSignalConfig.enabledSignals, ...((storedPrefs.signalConfig || {}).enabledSignals || {}) },
          rsi:{ ...defaultSignalConfig.rsi, ...((storedPrefs.signalConfig || {}).rsi || {}) },
          reversal:{ ...defaultSignalConfig.reversal, ...((storedPrefs.signalConfig || {}).reversal || {}) },
          trend:{ ...defaultSignalConfig.trend, ...((storedPrefs.signalConfig || {}).trend || {}) },
          volume:{ ...defaultSignalConfig.volume, ...((storedPrefs.signalConfig || {}).volume || {}) },
          weights:{ ...defaultSignalConfig.weights, ...((storedPrefs.signalConfig || {}).weights || {}) },
        },
      };
      const state = { symbol:prefs.symbol, timeframe:prefs.timeframe, candles:[], dailyCandles:[], indicators:null, chart:null, series:{}, priceLines:[], markerApi:null, socket:null, liveUpdateQueued:false, lastFullRefresh:0, toggles:prefs.toggles, maType:prefs.maType, ma:prefs.ma, signalConfig:prefs.signalConfig };
      allowedSignalTypes.forEach((type) => { state.signalConfig.enabledSignals[type] = state.signalConfig.enabledSignals[type] !== false; });
      Object.keys(state.signalConfig.enabledSignals).forEach((type) => { if (!allowedSignalTypes.includes(type)) state.signalConfig.enabledSignals[type] = false; });
      state.signalConfig.signalFamilies.reversal = true;
      state.signalConfig.signalFamilies.trend = false;
      state.signalConfig.enabledSignals.TREND_BUY = false;
      state.signalConfig.enabledSignals.TREND_SELL = false;
      if (!assetRegistry[state.symbol]) state.symbol = "BTCUSDT";
      if (assetRegistry[state.symbol]?.source === "fred" && !fredPayload.enabled) state.symbol = "BTCUSDT";
      if (!timeframes.includes(state.timeframe)) state.timeframe = "1m";
      if (assetRegistry[state.symbol]?.source === "fred" && intradayTimeframes.includes(state.timeframe)) state.timeframe = "1d";
      const chartEl = document.getElementById("lw-chart");
      const statusEl = document.getElementById("lw-status");
      const skeletonEl = document.getElementById("lw-skeleton");
      const crosshairCard = document.getElementById("lw-crosshair-card");
      const volumeProfileEl = document.getElementById("lw-volume-profile");
      const fmt = (n, d=2) => Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits:d, minimumFractionDigits:d }) : "---";
      const fmtTime = (time) => new Date(time * 1000).toLocaleString("pt-BR", { timeZone:"America/Sao_Paulo", hour12:false });
      const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[ch]));
      const setStatus = (msg) => { statusEl.textContent = msg; };
      const setLoading = (on) => skeletonEl.classList.toggle("show", Boolean(on));
      const savePrefs = () => {
        localStorage.setItem(signalStorageKey, JSON.stringify({ symbol:state.symbol, timeframe:state.timeframe, toggles:state.toggles, maType:state.maType, ma:state.ma, signalConfig:state.signalConfig }));
      };
      const providerNotes = [fredPayload.enabled ? "" : fredPayload.error].filter(Boolean).join(" | ");
      document.getElementById("lw-chart-title").textContent = chartTitle;

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
        [["ma","Medias"],["vwap","VWAP"],["bandsDay","Bandas D"],["bandsWeek","Bandas W %"],["bandsWeekVol","Bandas W Vol"],["stdevBands","Desvios"],["refs","Refs"],["signals","Sinais"],["volume","Volume"],["volumeProfile","Vol Profile"],["hv252","HV 252"]].forEach(([key,label]) => {
          toggleBox.appendChild(button(label, state.toggles[key], () => { state.toggles[key] = !state.toggles[key]; savePrefs(); renderControls(); renderCharts(false); }, state.toggles[key] ? "toggle-on" : ""));
        });
        actionBox.appendChild(button("Reset Zoom", false, () => { state.chart?.timeScale().fitContent(); }));
        actionBox.appendChild(button("Ultimo candle", false, () => { state.chart?.timeScale().scrollToRealTime(); }));
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
        renderSignalSettings(box);
      }
      function renderSignalSettings(box) {
        const cfg = state.signalConfig;
        const title = document.createElement("div");
        title.className = "lw-settings-title";
        title.style.marginTop = "6px";
        title.textContent = "Motor de sinais";
        box.appendChild(title);
        const familyChecks = [["family:reversal", "REV"]].filter(([key]) => {
          if (signalMode === "reversal") return key === "family:reversal";
          return true;
        });
        const checks = [["enabled", "Motor"], ...familyChecks, ...allowedSignalTypes.map((type) => [type, type.replace("_", " ")])];
        checks.forEach(([key, label]) => {
          const row = document.createElement("div");
          row.className = "lw-setting-row";
          const checked = key === "enabled" ? cfg.enabled : key.startsWith("family:") ? cfg.signalFamilies[key.split(":")[1]] : cfg.enabledSignals[key];
          row.innerHTML = `<label style="grid-column:1 / 3;"><input type="checkbox" ${checked ? "checked" : ""}> ${label}</label><span></span>`;
          row.querySelector("input").onchange = (e) => {
            if (key === "enabled") cfg.enabled = e.target.checked;
            else if (key.startsWith("family:")) cfg.signalFamilies[key.split(":")[1]] = e.target.checked;
            else cfg.enabledSignals[key] = e.target.checked;
            savePrefs(); renderCharts(false);
          };
          box.appendChild(row);
        });
        [
          ["minScore", "Score", 1, 20, 1, cfg.minScore, (v) => { cfg.minScore = v; }],
          ["cooldown", "Cooldown", 0, 80, 1, cfg.cooldownCandles, (v) => { cfg.cooldownCandles = v; }],
          ["vwapDist", "Dist %", 0.1, 5, 0.1, cfg.reversal.minDistanceFromVWAPPercent, (v) => { cfg.reversal.minDistanceFromVWAPPercent = v; }],
          ["near", "Nivel %", 0.05, 2, 0.05, cfg.reversal.proximityPercent, (v) => { cfg.reversal.proximityPercent = v; }],
          ["hvNear", "HV %", 0.05, 2, 0.05, cfg.reversal.hvProximityPercent, (v) => { cfg.reversal.hvProximityPercent = v; }],
          ["devMin", "Dev REV", 1, 3, 1, cfg.reversal.minStdevMultiplier, (v) => { cfg.reversal.minStdevMultiplier = v; }],
          ["rsiLen", "RSI len", 2, 50, 1, cfg.rsi.length, (v) => { cfg.rsi.length = v; }],
          ["rsiOS", "RSI Sobrev", 15, 50, 1, cfg.rsi.oversold, (v) => { cfg.rsi.oversold = v; }],
          ["rsiOB", "RSI Sobrecomp", 50, 85, 1, cfg.rsi.overbought, (v) => { cfg.rsi.overbought = v; }],
          ["volLook", "Vol M", 5, 80, 1, cfg.volume.lookback, (v) => { cfg.volume.lookback = v; }],
          ["rvol", "RVOL min", 0.5, 5, 0.05, cfg.volume.minRelativeVolume ?? cfg.volume.minVolumeMultiplier, (v) => { cfg.volume.minRelativeVolume = v; cfg.volume.minVolumeMultiplier = v; }],
          ["rvolStrong", "RVOL forte", 1, 8, 0.1, cfg.volume.strongRelativeVolume, (v) => { cfg.volume.strongRelativeVolume = v; }],
          ["legLook", "Pernada", 2, 20, 1, cfg.volume.legLookback, (v) => { cfg.volume.legLookback = v; }],
          ["legMin", "Leg RVOL", 0.5, 5, 0.05, cfg.volume.minLegRelativeVolume, (v) => { cfg.volume.minLegRelativeVolume = v; }],
        ].forEach((item) => {
          const [, label, min, max, step, value, setter] = item;
          const row = document.createElement("div");
          row.className = "lw-setting-row";
          row.innerHTML = `<span>${label}</span><input type="number" min="${min}" max="${max}" step="${step}" value="${value}"><span>${value}</span>`;
          row.querySelector("input").onchange = (e) => {
            const v = Math.max(min, Math.min(max, Number(e.target.value) || value));
            setter(v); savePrefs(); renderMASettings(); renderCharts(false);
          };
          box.appendChild(row);
        });
        [
          ["volOn", "Filtro volume", cfg.volume.enabled, (v) => { cfg.volume.enabled = v; }],
          ["revHv", "REV VWAP+HV", cfg.reversal.requireVwapHvConfluence, (v) => { cfg.reversal.requireVwapHvConfluence = v; }],
          ["volAbove", "Vol > media", cfg.volume.requireBarVolumeAboveAverage, (v) => { cfg.volume.requireBarVolumeAboveAverage = v; }],
          ["volExp", "Expansao volume", cfg.volume.requireVolumeExpansion, (v) => { cfg.volume.requireVolumeExpansion = v; }],
          ["volLeg", "Volume pernada", cfg.volume.requireReversalVolumeClimaxOrRejection, (v) => { cfg.volume.requireReversalVolumeClimaxOrRejection = v; }],
          ["volFall", "Bloquear vol caindo", cfg.volume.blockFallingVolume, (v) => { cfg.volume.blockFallingVolume = v; }],
        ].forEach((item) => {
          const [, label, checked, setter] = item;
          const row = document.createElement("div");
          row.className = "lw-setting-row";
          row.innerHTML = `<label style="grid-column:1 / 3;"><input type="checkbox" ${checked ? "checked" : ""}> ${label}</label><span></span>`;
          row.querySelector("input").onchange = (e) => { setter(e.target.checked); savePrefs(); renderCharts(false); };
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
      function renderChartMessage(title, detail="") {
        chartEl.innerHTML = `
          <div style="display:grid;place-items:center;height:100%;padding:24px;color:#cbd5e1;text-align:center;">
            <div>
              <div style="font-weight:900;font-size:1rem;color:#f8fafc;">${escapeHtml(title)}</div>
              ${detail ? `<div style="margin-top:8px;color:#94a3b8;font-size:.82rem;max-width:620px;line-height:1.45;">${escapeHtml(detail)}</div>` : ""}
            </div>
          </div>`;
        volumeProfileEl.innerHTML = "";
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
        if (asset.source === "fred") return fetchFredHistorical(symbol, timeframe);
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
      async function fetchDailyCandles(symbol) {
        const asset = assetRegistry[symbol] || { source: "binance" };
        if (asset.source === "yahoo") {
          const series = (yahooPayload.series && yahooPayload.series[symbol]) || {};
          return Array.isArray(series.daily) ? series.daily : [];
        }
        if (asset.source === "fred") {
          const series = (fredPayload.series && fredPayload.series[symbol]) || {};
          return Array.isArray(series.daily) ? series.daily : [];
        }
        const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1d&limit=300`);
        if (!res.ok) throw new Error(`Binance daily klines ${res.status}`);
        const rows = await res.json();
        return rows.map((r) => ({ time:Math.floor(r[0]/1000), open:+r[1], high:+r[2], low:+r[3], close:+r[4], volume:+r[5] }));
      }
      function fetchFredHistorical(symbol, timeframe) {
        if (!fredPayload.enabled) throw new Error(fredPayload.error || "Configure FRED_API_KEY para habilitar FRED.");
        const series = (fredPayload.series && fredPayload.series[symbol]) || {};
        const daily = series.daily || [];
        if (!daily.length) throw new Error(`Sem dados FRED para ${symbol}`);
        if (["30s", "1m", "5m", "h1"].includes(timeframe)) {
          throw new Error("FRED entrega series macro diarias. Use 1d, 1w ou 1month.");
        }
        if (timeframe === "1w") return aggregateCalendarCandles(daily, "week");
        if (timeframe === "1month") return aggregateCalendarCandles(daily, "month");
        return daily;
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
      function computeStdevBands(candles, vwap, multiplier, anchor="day") {
        let sum = 0, sumSq = 0, count = 0, bucket = "";
        const out = [];
        candles.forEach((c, i) => {
          const d = anchorKey(c.time, anchor);
          if (d !== bucket) { bucket = d; sum = 0; sumSq = 0; count = 0; }
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
      function getAverageVolume(candles, index, lookback) {
        const start = Math.max(0, index - lookback);
        const rows = candles.slice(start, index);
        if (!rows.length) return 0;
        return rows.reduce((sum,c) => sum + Number(c.volume || 0), 0) / rows.length;
      }
      function getRelativeVolume(candles, index, lookback) {
        const avgVolume = getAverageVolume(candles, index, lookback);
        const currentVolume = Number(candles[index]?.volume || 0);
        if (!avgVolume || avgVolume <= 0) return 0;
        return currentVolume / avgVolume;
      }
      function calculateVolumeMA(candles, lookback) {
        return candles.map((_, index) => getAverageVolume(candles, index, lookback));
      }
      function calculateRelativeVolume(candles, volumeMA) {
        return candles.map((c, index) => {
          const avg = volumeMA[index];
          return avg > 0 ? Number(c.volume || 0) / avg : 0;
        });
      }
      function getLegVolume(candles, index, lookback) {
        let total = 0;
        for (let i = index - lookback + 1; i <= index; i += 1) {
          if (i >= 0) total += Number(candles[i]?.volume || 0);
        }
        return total;
      }
      function getAverageLegVolume(candles, index, legLookback, averageLookback) {
        let total = 0, count = 0;
        for (let i = index - averageLookback; i < index - legLookback; i += legLookback) {
          if (i < 0) continue;
          const legVol = getLegVolume(candles, i, legLookback);
          if (legVol > 0) { total += legVol; count += 1; }
        }
        return count ? total / count : 0;
      }
      function getLegRelativeVolume(candles, index, cfg) {
        const legLookback = cfg.volume.legLookback || 5;
        const currentLegVolume = getLegVolume(candles, index, legLookback);
        const avgLegVolume = getAverageLegVolume(candles, index, legLookback, cfg.volume.lookback || 20);
        return avgLegVolume > 0 ? currentLegVolume / avgLegVolume : 0;
      }
      function hasRelativeVolumeConfirmation(candles, index, cfg) {
        if (!cfg.volume.enabled) return true;
        return getRelativeVolume(candles, index, cfg.volume.lookback || 20) >= (cfg.volume.minRelativeVolume || cfg.volume.minVolumeMultiplier || 1.2);
      }
      function hasStrongRelativeVolume(candles, index, cfg) {
        return getRelativeVolume(candles, index, cfg.volume.lookback || 20) >= (cfg.volume.strongRelativeVolume || 1.5);
      }
      function isBarVolumeAboveAverage(candles, index, cfg) {
        if (!cfg.volume.enabled || !cfg.volume.requireBarVolumeAboveAverage) return true;
        return Number(candles[index]?.volume || 0) > getAverageVolume(candles, index, cfg.volume.lookback || 20);
      }
      function hasVolumeExpansion(candles, index, cfg) {
        if (!cfg.volume.enabled || !cfg.volume.requireVolumeExpansion) return true;
        const current = Number(candles[index]?.volume || 0);
        const previous1 = Number(candles[index - 1]?.volume || 0);
        const previous2 = Number(candles[index - 2]?.volume || 0);
        return current > previous1 && current > previous2;
      }
      function isVolumeFalling(candles, index, lookback=3) {
        if (index < lookback) return false;
        for (let i = index - lookback + 1; i <= index; i += 1) {
          if (Number(candles[i]?.volume || 0) >= Number(candles[i - 1]?.volume || 0)) return false;
        }
        return true;
      }
      function hasLegVolumeConfirmation(candles, index, cfg) {
        if (!cfg.volume.enabled) return true;
        return getLegRelativeVolume(candles, index, cfg) >= (cfg.volume.minLegRelativeVolume || 1.1);
      }
      function hasWeakPullbackVolume(candles, index, cfg) {
        const lookback = cfg.volume.legLookback || 5;
        const avgVolume = getAverageVolume(candles, index, cfg.volume.lookback || 20);
        if (!avgVolume || avgVolume <= 0) return false;
        let pullbackVolume = 0, count = 0;
        for (let i = index - lookback; i < index; i += 1) {
          if (i >= 0) { pullbackVolume += Number(candles[i]?.volume || 0); count += 1; }
        }
        return count > 0 && (pullbackVolume / count) < avgVolume;
      }
      function hasReversalVolumeClimaxOrRejection(candles, index, cfg) {
        if (!cfg.volume.enabled || !cfg.volume.requireReversalVolumeClimaxOrRejection) return true;
        return hasVolumeExpansion(candles, index, cfg) || hasLegVolumeConfirmation(candles, index, cfg) || hasStrongRelativeVolume(candles, index, cfg);
      }
      function hasTrendVolumeResumption(candles, index, cfg) {
        if (!cfg.volume.enabled || !cfg.volume.requireTrendVolumeResumption) return true;
        return hasRelativeVolumeConfirmation(candles, index, cfg) && hasVolumeExpansion(candles, index, cfg);
      }
      function computeVolumeStats(candles, period=20) {
        const out = []; let sum = 0;
        const volumeCfg = state?.signalConfig?.volume || { lookback:period, legLookback:5, minLegRelativeVolume:1.1, enabled:true };
        const volumeMA = calculateVolumeMA(candles, period);
        const relativeVolume = calculateRelativeVolume(candles, volumeMA);
        candles.forEach((c, i) => {
          sum += c.volume || 0;
          if (i >= period) sum -= candles[i - period].volume || 0;
          const avg = i >= period - 1 ? sum / period : NaN;
          out.push({
            time:c.time,
            avg,
            volumeMA:volumeMA[i],
            rvol:relativeVolume[i],
            legVolume:getLegVolume(candles, i, volumeCfg.legLookback || 5),
            legRelativeVolume:getLegRelativeVolume(candles, i, { volume:{ ...volumeCfg, lookback:period } }),
          });
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
      function corrPriceVolume(candles, n=80) {
        const data = candles.slice(-n); if (data.length < 10) return NaN;
        const xs = data.map((c, i) => i === 0 ? 0 : c.close - data[i - 1].close), ys = data.map((c) => c.volume);
        const mx = xs.reduce((a,b)=>a+b,0)/xs.length, my = ys.reduce((a,b)=>a+b,0)/ys.length;
        let num=0, dx=0, dy=0; xs.forEach((x,i)=>{ const vx=x-mx, vy=ys[i]-my; num+=vx*vy; dx+=vx*vx; dy+=vy*vy; });
        return dx && dy ? num / Math.sqrt(dx * dy) : NaN;
      }
      function sessionRefs(candles) {
        if (!candles.length) return {};
        const statsFor = (anchor, offset=0) => {
          const grouped = new Map();
          candles.forEach((c) => {
            const key = anchorKey(c.time, anchor);
            if (!grouped.has(key)) grouped.set(key, []);
            grouped.get(key).push(c);
          });
          const keys = Array.from(grouped.keys());
          const key = keys[keys.length - 1 - offset];
          const rows = grouped.get(key) || [];
          if (!rows.length) return {};
          return {
            key,
            open:rows[0]?.open,
            high:rows.reduce((m,c) => Math.max(m, c.high), -Infinity),
            low:rows.reduce((m,c) => Math.min(m, c.low), Infinity),
            close:rows[rows.length - 1]?.close,
          };
        };
        const day = statsFor("day", 0);
        const prevDay = statsFor("day", 1);
        const prevWeek = statsFor("week", 1);
        const prevMonth = statsFor("month", 1);
        return {
          open:day.open,
          high:day.high,
          low:day.low,
          prevClose:prevDay.close,
          current:candles[candles.length - 1]?.close,
          day,
          prevDay,
          prevWeek,
          prevMonth,
        };
      }
      function calculateLogReturns(closes) {
        const returns = [];
        for (let i = 1; i < closes.length; i += 1) {
          const prev = closes[i - 1];
          const curr = closes[i];
          if (prev > 0 && curr > 0) returns.push(Math.log(curr / prev));
        }
        return returns;
      }
      function calculateHistoricalVolatility(dailyCandles, period=252) {
        const source = (dailyCandles || []).filter((c) => Number.isFinite(c.close) && c.close > 0);
        if (source.length < period + 1) {
          return { ok:false, period, warning:`Historico insuficiente para HV ${period}`, prevClose:NaN, dailyVol:NaN, annualVol:NaN, levels:[] };
        }
        const closes = source.map((c) => c.close);
        const returns = calculateLogReturns(closes).slice(-period);
        if (returns.length < period) return { ok:false, period, warning:`Historico insuficiente para HV ${period}`, prevClose:NaN, dailyVol:NaN, annualVol:NaN, levels:[] };
        const mean = returns.reduce((a,b) => a + b, 0) / returns.length;
        const variance = returns.reduce((sum,r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
        const dailyVol = Math.sqrt(Math.max(0, variance));
        const annualVol = dailyVol * Math.sqrt(252);
        const prevClose = source[source.length - 2]?.close ?? source[source.length - 1]?.close;
        return { ok:true, period, warning:"", prevClose, dailyVol, annualVol, levels:calculateVolatilityLevels(prevClose, dailyVol) };
      }
      function calculateVolatilityLevels(prevClose, dailyVol, multipliers=[1, 1.5, 2]) {
        if (!Number.isFinite(prevClose) || !Number.isFinite(dailyVol)) return [];
        const levels = [{ label:"Fech. Ant.", price:prevClose, multiplier:0 }];
        multipliers.forEach((m) => {
          levels.push({ label:`HV +${m}σ`, price:prevClose * Math.exp(m * dailyVol), multiplier:m });
          levels.push({ label:`HV -${m}σ`, price:prevClose * Math.exp(-m * dailyVol), multiplier:-m });
        });
        return levels;
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
      const safe = (n) => Number.isFinite(n) ? n : NaN;
      const pctDistance = (price, level) => Number.isFinite(price) && Number.isFinite(level) && level !== 0 ? ((price - level) / level) * 100 : NaN;
      const minFinite = (...values) => {
        const nums = values.filter(Number.isFinite);
        return nums.length ? Math.min(...nums) : NaN;
      };
      const maxFinite = (...values) => {
        const nums = values.filter(Number.isFinite);
        return nums.length ? Math.max(...nums) : NaN;
      };
      function valueAt(series, time) {
        return (series || []).find((item) => item.time === time)?.value;
      }
      function computeSignalMAs(candles) {
        const periods = [9, 21, 80, 200];
        const out = {};
        periods.forEach((period) => {
          const map = new Map(computeMA(candles, period, "EMA").map((item) => [item.time, item.value]));
          out[`ema${period}`] = candles.map((c) => ({ time:c.time, value:map.get(c.time) }));
        });
        return out;
      }
      function computeRSI(candles, period=14) {
        const out = candles.map((c) => ({ time:c.time, value:NaN }));
        if (candles.length <= period) return out;
        let gain = 0, loss = 0;
        for (let i = 1; i <= period; i += 1) {
          const diff = candles[i].close - candles[i - 1].close;
          if (diff >= 0) gain += diff;
          else loss -= diff;
        }
        let avgGain = gain / period;
        let avgLoss = loss / period;
        out[period].value = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
        for (let i = period + 1; i < candles.length; i += 1) {
          const diff = candles[i].close - candles[i - 1].close;
          const up = Math.max(diff, 0);
          const down = Math.max(-diff, 0);
          avgGain = ((avgGain * (period - 1)) + up) / period;
          avgLoss = ((avgLoss * (period - 1)) + down) / period;
          out[i].value = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
        }
        return out;
      }
      function bandAt(bands, multiplier, time) {
        const band = (bands || []).find((item) => Number(item.multiplier) === Number(multiplier));
        return (band?.data || []).find((item) => item.time === time);
      }
      function isNearLevel(price, level, tolerancePercent) {
        return Number.isFinite(price) && Number.isFinite(level) && Math.abs(pctDistance(price, level)) <= tolerancePercent;
      }
      function candleShape(c) {
        const range = Math.max(0, c.high - c.low);
        const body = Math.abs(c.close - c.open);
        const upperWick = c.high - Math.max(c.open, c.close);
        const lowerWick = Math.min(c.open, c.close) - c.low;
        const closePosition = range > 0 ? (c.close - c.low) / range : 0.5;
        const bodyShare = range > 0 ? body / range : 0;
        return { range, body, upperWick, lowerWick, closePosition, bodyShare };
      }
      function isBullishRejectionCandle(c) {
        const s = candleShape(c);
        return s.range > 0 && s.lowerWick >= Math.max(s.body * 1.5, s.range * 0.18) && s.closePosition >= 0.6 && c.close >= c.open;
      }
      function isBearishRejectionCandle(c) {
        const s = candleShape(c);
        return s.range > 0 && s.upperWick >= Math.max(s.body * 1.5, s.range * 0.18) && s.closePosition <= 0.4 && c.close <= c.open;
      }
      function isBullishImpulseCandle(c, minBodyPercent) {
        const s = candleShape(c);
        return s.range > 0 && c.close > c.open && s.bodyShare >= minBodyPercent && s.closePosition >= 0.65;
      }
      function isBearishImpulseCandle(c, minBodyPercent) {
        const s = candleShape(c);
        return s.range > 0 && c.close < c.open && s.bodyShare >= minBodyPercent && s.closePosition <= 0.35;
      }
      function getRecentSwingHigh(candles, index, lookback=20) {
        return candles.slice(Math.max(0, index - lookback), index).reduce((m,c) => Math.max(m, c.high), -Infinity);
      }
      function getRecentSwingLow(candles, index, lookback=20) {
        return candles.slice(Math.max(0, index - lookback), index).reduce((m,c) => Math.min(m, c.low), Infinity);
      }
      function isPullbackNearEMAOrVWAP(c, levels, tolerancePercent) {
        return levels.some((level) => Number.isFinite(level) && (isNearLevel(c.low, level, tolerancePercent) || isNearLevel(c.high, level, tolerancePercent) || isNearLevel(c.close, level, tolerancePercent)));
      }
      function signalContext(candles, indicators, i) {
        const c = candles[i];
        const refs = indicators.refs || {};
        const hv = indicators.hv252 || {};
        const hvLevel = (mult) => (hv.levels || []).find((item) => item.multiplier === mult)?.price;
        const stdevLevel = (mult) => bandAt(indicators.stdevBands, mult, c.time);
        return {
          c,
          prev:candles[i - 1],
          vwap:valueAt(indicators.vwapDay, c.time),
          rsi14:valueAt(indicators.rsi14, c.time),
          rsi14Prev:valueAt(indicators.rsi14, candles[Math.max(0, i - 1)]?.time),
          ema9:valueAt(indicators.signalMAs.ema9, c.time),
          ema21:valueAt(indicators.signalMAs.ema21, c.time),
          ema80:valueAt(indicators.signalMAs.ema80, c.time),
          ema200:valueAt(indicators.signalMAs.ema200, c.time),
          ema21Prev:valueAt(indicators.signalMAs.ema21, candles[Math.max(0, i - 5)]?.time),
          rvol:indicators.volumeStats[i]?.rvol,
          avgVol:indicators.volumeStats[i]?.avg,
          volumeMA:indicators.volumeStats[i]?.volumeMA,
          legVolume:indicators.volumeStats[i]?.legVolume,
          legRelativeVolume:indicators.volumeStats[i]?.legRelativeVolume,
          prevClose:refs.prevClose,
          dayHigh:refs.high,
          dayLow:refs.low,
          hvUpper1:hvLevel(1),
          hvLower1:hvLevel(-1),
          hvUpper2:hvLevel(2),
          hvLower2:hvLevel(-2),
          hvUpper15:hvLevel(1.5),
          hvLower15:hvLevel(-1.5),
          stdev1:stdevLevel(1),
          stdev2:stdevLevel(2),
          stdev3:stdevLevel(3),
        };
      }
      function detectRegime(ctx, cfg) {
        const { c, vwap, ema9, ema21, ema80, ema200, ema21Prev, dayHigh, dayLow, hvUpper1, hvLower1 } = ctx;
        const dist = pctDistance(c.close, vwap);
        const emaSpread = Number.isFinite(ema9) && Number.isFinite(ema21) ? Math.abs(ema9 - ema21) / c.close : Infinity;
        const slope21 = Number.isFinite(ema21) && Number.isFinite(ema21Prev) ? ema21 - ema21Prev : NaN;
        if (Number.isFinite(dist) && dist >= cfg.reversal.minDistanceFromVWAPPercent && [dayHigh, hvUpper1].some((level) => isNearLevel(c.close, level, cfg.reversal.proximityPercent * 2))) return "stretched_up";
        if (Number.isFinite(dist) && dist <= -cfg.reversal.minDistanceFromVWAPPercent && [dayLow, hvLower1].some((level) => isNearLevel(c.close, level, cfg.reversal.proximityPercent * 2))) return "stretched_down";
        if (Number.isFinite(dist) && Math.abs(dist) < 0.3 && emaSpread < 0.0015) return "range";
        if (c.close > vwap && ema9 > ema21 && ema21 > ema80 && (ema80 >= ema200 || c.close > ema200 || !Number.isFinite(ema200)) && slope21 > 0) return "uptrend";
        if (c.close < vwap && ema9 < ema21 && ema21 < ema80 && (ema80 <= ema200 || c.close < ema200 || !Number.isFinite(ema200)) && slope21 < 0) return "downtrend";
        if (Number.isFinite(dist) && Math.abs(dist) < 0.5) return "range";
        return dist >= 0 ? "stretched_up" : "stretched_down";
      }
      function addScore(parts, ok, weight, reason) {
        if (ok) { parts.score += weight; parts.reasons.push(reason); }
      }
      function addTag(parts, ok, tag) {
        if (ok && tag && !parts.tags.includes(tag)) parts.tags.push(tag);
      }
      function buildSignal(type, ctx, parts, regime, stop, target1, target2) {
        return {
          time:ctx.c.time,
          type,
          price:ctx.c.close,
          score:parts.score,
          regime,
          rsi:ctx.rsi14,
          vwapDistancePercent:pctDistance(ctx.c.close, ctx.vwap),
          volume:ctx.c.volume,
          volumeMA:ctx.volumeMA,
          relativeVolume:ctx.rvol,
          legVolume:ctx.legVolume,
          legRelativeVolume:ctx.legRelativeVolume,
          locationTags:parts.tags,
          reasons:parts.reasons,
          suggestedStop:safe(stop),
          suggestedTarget1:safe(target1),
          suggestedTarget2:safe(target2),
        };
      }
      function reversalConfluence(ctx, side, cfg) {
        const minMult = Math.max(1, Math.min(3, Number(cfg.reversal.minStdevMultiplier) || 1));
        const stdevBands = [ctx.stdev1, ctx.stdev2, ctx.stdev3].filter((band, index) => index + 1 >= minMult);
        const hvLevels = side === "buy"
          ? [ctx.hvLower1, ctx.hvLower15, ctx.hvLower2]
          : [ctx.hvUpper1, ctx.hvUpper15, ctx.hvUpper2];
        const price = side === "buy" ? ctx.c.low : ctx.c.high;
        const vwapExtreme = stdevBands.some((band) => {
          if (!band) return false;
          return side === "buy" ? ctx.c.low <= band.lower || ctx.c.close <= band.lower : ctx.c.high >= band.upper || ctx.c.close >= band.upper;
        });
        const hvExtreme = hvLevels.some((level) => isNearLevel(price, level, cfg.reversal.hvProximityPercent) || (side === "buy" ? price <= level : price >= level));
        return { ok:vwapExtreme && hvExtreme, vwapExtreme, hvExtreme };
      }
      function trendRsiConfirmation(ctx, side, cfg) {
        const rsi = ctx.rsi14;
        const prev = ctx.rsi14Prev;
        if (!Number.isFinite(rsi)) return { ok:false, reason:"RSI14 indisponivel" };
        if (side === "buy") {
          const inPullbackZone = rsi >= (cfg.rsi?.trendBuyMin ?? cfg.trend.rsiBuyMin) && rsi <= (cfg.rsi?.trendBuyMax ?? cfg.trend.rsiBuyMax);
          const turningUp = !cfg.rsi?.requireTurn || !Number.isFinite(prev) || rsi >= prev;
          return { ok:inPullbackZone && turningUp, reason:`RSI14 ${fmt(rsi,1)} em pullback comprador` };
        }
        const inPullbackZone = rsi >= (cfg.rsi?.trendSellMin ?? cfg.trend.rsiSellMin) && rsi <= (cfg.rsi?.trendSellMax ?? cfg.trend.rsiSellMax);
        const turningDown = !cfg.rsi?.requireTurn || !Number.isFinite(prev) || rsi <= prev;
        return { ok:inPullbackZone && turningDown, reason:`RSI14 ${fmt(rsi,1)} em pullback vendedor` };
      }
      function reversalRsiConfirmation(ctx, side, cfg) {
        const rsi = ctx.rsi14;
        const prev = ctx.rsi14Prev;
        if (!Number.isFinite(rsi)) return { ok:false, reason:"RSI14 indisponivel" };
        if (side === "buy") {
          const ok = rsi <= (cfg.rsi?.oversold ?? 35) && (!cfg.rsi?.requireTurn || !Number.isFinite(prev) || rsi >= prev);
          return { ok, reason:`RSI14 ${fmt(rsi,1)} sobrevendido e virando` };
        }
        const ok = rsi >= (cfg.rsi?.overbought ?? 65) && (!cfg.rsi?.requireTurn || !Number.isFinite(prev) || rsi <= prev);
        return { ok, reason:`RSI14 ${fmt(rsi,1)} sobrecomprado e virando` };
      }
      function volumeChecks(candles, i, cfg) {
        const rvol = getRelativeVolume(candles, i, cfg.volume.lookback || 20);
        const legRvol = getLegRelativeVolume(candles, i, cfg);
        const barAbove = isBarVolumeAboveAverage(candles, i, cfg);
        const relativeOk = hasRelativeVolumeConfirmation(candles, i, cfg);
        const strong = hasStrongRelativeVolume(candles, i, cfg);
        const expansion = hasVolumeExpansion(candles, i, cfg);
        const legOk = hasLegVolumeConfirmation(candles, i, cfg);
        const weakPullback = hasWeakPullbackVolume(candles, i, cfg);
        const falling = cfg.volume.blockFallingVolume && isVolumeFalling(candles, i, cfg.volume.fallingVolumeLookback || 3);
        return { rvol, legRvol, barAbove, relativeOk, strong, expansion, legOk, weakPullback, falling };
      }
      function scoreCandidate(type, candles, indicators, i, regime) {
        const cfg = state.signalConfig;
        const w = cfg.weights;
        const ctx = signalContext(candles, indicators, i);
        const { c, prev, vwap, ema9, ema21, ema80, prevClose, dayHigh, dayLow, hvUpper1, hvLower1, hvUpper2, hvLower2 } = ctx;
        if (!prev || !Number.isFinite(vwap)) return null;
        const parts = { score:0, reasons:[], tags:[] };
        const dist = pctDistance(c.close, vwap);
        const vol = volumeChecks(candles, i, cfg);
        if (cfg.volume.enabled && vol.falling) return null;
        const nearLow = [dayLow, hvLower1, hvLower2].some((level) => isNearLevel(c.low, level, cfg.reversal.proximityPercent));
        const nearHigh = [dayHigh, hvUpper1, hvUpper2].some((level) => isNearLevel(c.high, level, cfg.reversal.proximityPercent));
        const maBull = ema9 > ema21 && ema21 > ema80;
        const maBear = ema9 < ema21 && ema21 < ema80;
        const trendTooFar = Number.isFinite(dist) && Math.abs(dist) > (cfg.trend.maxVWAPDistancePercent || 0.45);
        const addVolumeScores = () => {
          addScore(parts, vol.barAbove, w.barVolumeConfirmation || w.volumeConfirmation, "Volume da barra acima da media");
          addScore(parts, vol.relativeOk, w.relativeVolumeConfirmation || w.volumeConfirmation, `RVOL ${fmt(vol.rvol,2)}x`);
          addScore(parts, vol.strong, w.strongRelativeVolumeConfirmation || 0, `RVOL forte ${fmt(vol.rvol,2)}x`);
          addScore(parts, vol.expansion, w.volumeExpansion || 0, "Volume em expansao");
          addScore(parts, vol.legOk, w.legVolumeConfirmation || 0, `Volume da pernada ${fmt(vol.legRvol,2)}x`);
          addTag(parts, vol.barAbove, "VOLUME_ABOVE_AVERAGE");
          addTag(parts, vol.strong, "RELATIVE_VOLUME_STRONG");
          addTag(parts, vol.expansion, "VOLUME_EXPANSION");
          addTag(parts, vol.legOk, "LEG_VOLUME_CONFIRMATION");
        };
        if (type === "REV_BUY") {
          const confluence = reversalConfluence(ctx, "buy", cfg);
          if (cfg.reversal.requireVwapHvConfluence && !confluence.ok) return null;
          const rsi = reversalRsiConfirmation(ctx, "buy", cfg);
          const candleOk = isBullishRejectionCandle(c) || c.close > prev.high || (c.low < prev.low && c.close > prev.close);
          const volumeOk = vol.relativeOk && (vol.expansion || vol.legOk || vol.strong);
          if (!rsi.ok || !candleOk || !volumeOk || Math.abs(dist) < cfg.reversal.minDistanceFromVWAPPercent || isNearLevel(c.close, vwap, cfg.reversal.proximityPercent)) return null;
          addScore(parts, ["range","stretched_down"].includes(regime), w.favorableRegime, `Regime ${regime}`);
          addScore(parts, c.close < vwap, w.vwapSide, "Preco abaixo da VWAP");
          addScore(parts, Number.isFinite(dist) && dist <= -cfg.reversal.minDistanceFromVWAPPercent, w.vwapDistance, `Distancia VWAP ${dist.toFixed(2)}%`);
          addScore(parts, confluence.vwapExtreme, w.extremeLocation || w.vwapDistance, `Extremo em desvio VWAP >= ${cfg.reversal.minStdevMultiplier}`);
          addScore(parts, confluence.hvExtreme, w.hvConfluence, "Confluencia com banda HV252 inferior");
          addScore(parts, rsi.ok, w.rsiConfirmation, rsi.reason);
          addScore(parts, nearLow, w.proximityToKeyLevel, "Proximo de minima/HV inferior");
          addScore(parts, candleOk, w.rejectionCandle, "Candle de rejeicao/falha inferior");
          addScore(parts, c.close > prev.close || c.close > prev.high, w.previousCandleBreak, "Virada sobre candle anterior");
          addVolumeScores();
          addTag(parts, nearLow, "DAY_LOW");
          addTag(parts, confluence.hvExtreme, "HV_LOWER_1");
          addTag(parts, confluence.vwapExtreme, "VWAP_DEV_NEG_1");
          return buildSignal(type, ctx, parts, regime, minFinite(c.low, dayLow, hvLower1), vwap, Number.isFinite(prevClose) ? prevClose : hvUpper1);
        }
        if (type === "REV_SELL") {
          const confluence = reversalConfluence(ctx, "sell", cfg);
          if (cfg.reversal.requireVwapHvConfluence && !confluence.ok) return null;
          const rsi = reversalRsiConfirmation(ctx, "sell", cfg);
          const candleOk = isBearishRejectionCandle(c) || c.close < prev.low || (c.high > prev.high && c.close < prev.close);
          const volumeOk = vol.relativeOk && (vol.expansion || vol.legOk || vol.strong);
          if (!rsi.ok || !candleOk || !volumeOk || Math.abs(dist) < cfg.reversal.minDistanceFromVWAPPercent || isNearLevel(c.close, vwap, cfg.reversal.proximityPercent)) return null;
          addScore(parts, ["range","stretched_up"].includes(regime), w.favorableRegime, `Regime ${regime}`);
          addScore(parts, c.close > vwap, w.vwapSide, "Preco acima da VWAP");
          addScore(parts, Number.isFinite(dist) && dist >= cfg.reversal.minDistanceFromVWAPPercent, w.vwapDistance, `Distancia VWAP +${dist.toFixed(2)}%`);
          addScore(parts, confluence.vwapExtreme, w.extremeLocation || w.vwapDistance, `Extremo em desvio VWAP >= ${cfg.reversal.minStdevMultiplier}`);
          addScore(parts, confluence.hvExtreme, w.hvConfluence, "Confluencia com banda HV252 superior");
          addScore(parts, rsi.ok, w.rsiConfirmation, rsi.reason);
          addScore(parts, nearHigh, w.proximityToKeyLevel, "Proximo de maxima/HV superior");
          addScore(parts, candleOk, w.rejectionCandle, "Candle de rejeicao/falha superior");
          addScore(parts, c.close < prev.close || c.close < prev.low, w.previousCandleBreak, "Virada abaixo do candle anterior");
          addVolumeScores();
          addTag(parts, nearHigh, "DAY_HIGH");
          addTag(parts, confluence.hvExtreme, "HV_UPPER_1");
          addTag(parts, confluence.vwapExtreme, "VWAP_DEV_POS_1");
          return buildSignal(type, ctx, parts, regime, maxFinite(c.high, dayHigh, hvUpper1), vwap, Number.isFinite(prevClose) ? prevClose : hvLower1);
        }
        if (type === "TREND_BUY") {
          const rsi = trendRsiConfirmation(ctx, "buy", cfg);
          if (cfg.trend.requireRsiPullback && !rsi.ok) return null;
          const pullbackOk = isPullbackNearEMAOrVWAP(c, [ema9, ema21, vwap], cfg.trend.maxPullbackDistancePercent);
          const candleOk = isBullishImpulseCandle(c, cfg.trend.minBodyPercent);
          if (regime !== "uptrend" || !maBull || c.close <= vwap || trendTooFar || !pullbackOk || !candleOk || !vol.relativeOk || !vol.expansion) return null;
          addScore(parts, regime === "uptrend", w.favorableRegime, "Regime de alta");
          addScore(parts, c.close > vwap, w.vwapSide, "Preco acima da VWAP");
          addScore(parts, maBull, w.movingAverageAlignment, "Medias alinhadas para alta");
          addScore(parts, pullbackOk, w.pullbackLocation || w.proximityToKeyLevel, "Pullback em EMA/VWAP");
          addScore(parts, rsi.ok, w.rsiConfirmation, rsi.reason);
          addScore(parts, candleOk, w.impulseCandle, "Candle de impulso comprador");
          addScore(parts, c.close > prev.high, w.previousCandleBreak, "Rompimento da maxima anterior");
          addVolumeScores();
          addScore(parts, vol.weakPullback, w.weakPullbackVolume || 0, "Pullback anterior com volume fraco");
          addScore(parts, hasTrendVolumeResumption(candles, i, cfg), w.trendVolumeResumption || 0, "Retomada com volume");
          addTag(parts, pullbackOk, "EMA21_PULLBACK");
          addTag(parts, vol.weakPullback, "WEAK_PULLBACK_VOLUME");
          addTag(parts, hasTrendVolumeResumption(candles, i, cfg), "TREND_VOLUME_RESUMPTION");
          return buildSignal(type, ctx, parts, regime, minFinite(ema21, vwap, getRecentSwingLow(candles, i, 12)), getRecentSwingHigh(candles, i, 24), Number.isFinite(dayHigh) ? dayHigh : hvUpper1);
        }
        const rsi = trendRsiConfirmation(ctx, "sell", cfg);
        if (cfg.trend.requireRsiPullback && !rsi.ok) return null;
        const pullbackOk = isPullbackNearEMAOrVWAP(c, [ema9, ema21, vwap], cfg.trend.maxPullbackDistancePercent);
        const candleOk = isBearishImpulseCandle(c, cfg.trend.minBodyPercent);
        if (regime !== "downtrend" || !maBear || c.close >= vwap || trendTooFar || !pullbackOk || !candleOk || !vol.relativeOk || !vol.expansion) return null;
        addScore(parts, regime === "downtrend", w.favorableRegime, "Regime de baixa");
        addScore(parts, c.close < vwap, w.vwapSide, "Preco abaixo da VWAP");
        addScore(parts, maBear, w.movingAverageAlignment, "Medias alinhadas para baixa");
        addScore(parts, pullbackOk, w.pullbackLocation || w.proximityToKeyLevel, "Pullback em EMA/VWAP");
        addScore(parts, rsi.ok, w.rsiConfirmation, rsi.reason);
        addScore(parts, candleOk, w.impulseCandle, "Candle de impulso vendedor");
        addScore(parts, c.close < prev.low, w.previousCandleBreak, "Rompimento da minima anterior");
        addVolumeScores();
        addScore(parts, vol.weakPullback, w.weakPullbackVolume || 0, "Pullback anterior com volume fraco");
        addScore(parts, hasTrendVolumeResumption(candles, i, cfg), w.trendVolumeResumption || 0, "Retomada com volume");
        addTag(parts, pullbackOk, "EMA21_PULLBACK");
        addTag(parts, vol.weakPullback, "WEAK_PULLBACK_VOLUME");
        addTag(parts, hasTrendVolumeResumption(candles, i, cfg), "TREND_VOLUME_RESUMPTION");
        return buildSignal(type, ctx, parts, regime, maxFinite(ema21, vwap, getRecentSwingHigh(candles, i, 12)), getRecentSwingLow(candles, i, 24), Number.isFinite(dayLow) ? dayLow : hvLower1);
      }
      function generateSignals(candles, indicators) {
        const cfg = state.signalConfig;
        if (!cfg.enabled || candles.length < 50) return [];
        const out = [];
        const lastByType = {};
        for (let i = 50; i < candles.length; i += 1) {
          const ctx = signalContext(candles, indicators, i);
          const regime = detectRegime(ctx, cfg);
          const candidates = ["REV_BUY","REV_SELL"]
            .filter((type) => cfg.enabledSignals[type])
            .filter((type) => cfg.signalFamilies.reversal)
            .map((type) => scoreCandidate(type, candles, indicators, i, regime))
            .filter((sig) => sig && sig.score >= cfg.minScore);
          if (!candidates.length) continue;
          candidates.sort((a,b) => b.score - a.score);
          const best = candidates[0];
          if (lastByType[best.type] !== undefined && i - lastByType[best.type] < cfg.cooldownCandles) continue;
          const lastAny = out[out.length - 1];
          if (lastAny && i - lastAny.index < Math.max(1, Math.floor(cfg.cooldownCandles / 2)) && lastAny.signal.type === best.type) continue;
          out.push({ index:i, signal:best });
          lastByType[best.type] = i;
        }
        return out.map((item) => item.signal);
      }
      function buildSignalMarkers(signals) {
        const style = {
          REV_BUY:{ position:"belowBar", shape:"arrowUp", color:"#00C853", label:"REV BUY" },
          REV_SELL:{ position:"aboveBar", shape:"arrowDown", color:"#D50000", label:"REV SELL" },
        };
        return (signals || []).map((signal) => {
          const s = style[signal.type] || style.REV_BUY;
          return { time:signal.time, position:s.position, shape:s.shape, color:s.color, text:`${s.label} ${signal.score}` };
        });
      }
      function computeIndicators(candles) {
        const vwapDay = computeVWAP(candles, "day");
        const vwapWeek = computeVWAP(candles, "week");
        const vwapMonth = computeVWAP(candles, "month");
        const volumeStats = computeVolumeStats(candles, state.signalConfig.volume.lookback || 20);
        const ma = state.ma.filter((m) => m.enabled).map((m) => ({ ...m, data:computeMA(candles, m.period, state.maType) }));
        const signalMAs = computeSignalMAs(candles);
        const rsi14 = computeRSI(candles, state.signalConfig.rsi?.length || 14);
        const stdevBands = vwapStdevMultipliers.map((multiplier) => ({ multiplier, data:computeStdevBands(candles, vwapDay, multiplier) }));
        const weekVolBands = vwapStdevMultipliers.map((multiplier) => ({ multiplier, data:computeStdevBands(candles, vwapWeek, multiplier, "week") }));
        const refs = sessionRefs(candles);
        const volumeProfile = computeSessionVolumeProfile(candles);
        const hv252 = calculateHistoricalVolatility(state.dailyCandles, 252);
        const indicators = { vwapDay, vwapWeek, vwapMonth, volumeStats, ma, signalMAs, rsi14, stdevBands, weekVolBands, refs, volumeProfile, hv252 };
        indicators.signals = generateSignals(candles, indicators);
        return indicators;
      }
      function addLine(key, data, color, width) {
        const s = state.chart.addSeries(LineSeries, { color, lineWidth:width, priceLineVisible:false, lastValueVisible:false });
        s.setData(data); state.series[key] = s;
      }
      function percentBandData(series, pct, side) {
        const factor = side === "upper" ? 1 + pct : 1 - pct;
        return (series || []).map((p) => ({ time:p.time, value:p.value * factor }));
      }
      function addVWAPPercentBands(prefix, series, colors, width=1) {
        [0.005,0.01,0.015,0.02].forEach((pct,i) => {
          const color = colors[i] || "#94a3b8";
          addLine(`${prefix}_p_${pct}`, percentBandData(series, pct, "upper"), color, width);
          addLine(`${prefix}_m_${pct}`, percentBandData(series, pct, "lower"), color, width);
        });
      }
      function updateVWAPPercentBands(prefix, series) {
        [0.005,0.01,0.015,0.02].forEach((pct) => {
          state.series[`${prefix}_p_${pct}`]?.setData(percentBandData(series, pct, "upper"));
          state.series[`${prefix}_m_${pct}`]?.setData(percentBandData(series, pct, "lower"));
        });
      }
      function addPriceLine(series, title, price, color, style=2, width=1) {
        if (!Number.isFinite(price)) return;
        const line = series.createPriceLine({ price, color, lineWidth:width, lineStyle:style, axisLabelVisible:true, title });
        state.priceLines.push(line);
      }
      function applyMarkers(candleSeries, markers) {
        markers = state.toggles.signals ? buildSignalMarkers(markers) : [];
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
        const chartHeight = chartEl.clientHeight || 1000;
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
        if (state.chart) state.chart.remove();
        chartEl.innerHTML = ""; state.series = {}; state.priceLines = []; state.markerApi = null;
        state.chart = makeChart(chartEl, chartEl.clientHeight || 1000);
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
        if (state.toggles.bandsDay || (state.toggles.bands && state.toggles.bandsDay !== false)) {
          addVWAPPercentBands("vwap", state.indicators.vwapDay, ["#38bdf8","#60a5fa","#818cf8","#a78bfa"], 1);
        }
        if (state.toggles.bandsWeek) {
          addVWAPPercentBands("vwapWeek", state.indicators.vwapWeek, ["#fbbf24","#f59e0b","#f97316","#ef4444"], 1);
        }
        if (state.toggles.bandsWeekVol) {
          const colors = ["#2dd4bf", "#14b8a6", "#0f766e"];
          state.indicators.weekVolBands.forEach((band, i) => {
            const key = String(band.multiplier).replace(".", "_");
            const color = colors[i] || "#2dd4bf";
            addLine(`week_vol_${key}_u`, band.data.map((p) => ({ time:p.time, value:p.upper })), color, 1);
            addLine(`week_vol_${key}_l`, band.data.map((p) => ({ time:p.time, value:p.lower })), color, 1);
          });
        }
        if (state.toggles.stdevBands) {
          const colors = ["#22c55e", "#f59e0b", "#a78bfa", "#ef4444"];
          state.indicators.stdevBands.forEach((band, i) => {
            const key = String(band.multiplier).replace(".", "_");
            const color = colors[i] || "#a78bfa";
            addLine(`stdev_${key}_u`, band.data.map((p) => ({ time:p.time, value:p.upper })), color, 1);
            addLine(`stdev_${key}_l`, band.data.map((p) => ({ time:p.time, value:p.lower })), color, 1);
          });
        }
        if (state.toggles.ma) state.indicators.ma.forEach((m) => addLine(m.id, m.data, m.color, m.period >= 200 ? 2 : 1));
        if (state.toggles.refs) {
          const refs = state.indicators.refs;
          addPriceLine(candleSeries, "DIA MAX", refs.day?.high, "#22c55e", 0, 2);
          addPriceLine(candleSeries, "DIA MIN", refs.day?.low, "#ef4444", 0, 2);
          addPriceLine(candleSeries, "DIA ANT MAX", refs.prevDay?.high, "#60a5fa", 2, 2);
          addPriceLine(candleSeries, "DIA ANT MIN", refs.prevDay?.low, "#f97316", 2, 2);
          addPriceLine(candleSeries, "SEM ANT MAX", refs.prevWeek?.high, "#a78bfa", 3, 2);
          addPriceLine(candleSeries, "SEM ANT MIN", refs.prevWeek?.low, "#c084fc", 3, 2);
          addPriceLine(candleSeries, "MES ANT MAX", refs.prevMonth?.high, "#f472b6", 1, 2);
          addPriceLine(candleSeries, "MES ANT MIN", refs.prevMonth?.low, "#fb7185", 1, 2);
          addPriceLine(candleSeries, "ATUAL", refs.current, "#f8fafc", 0, 1);
        }
        if (state.toggles.volumeProfile) {
          addPriceLine(candleSeries, "VAH", state.indicators.volumeProfile?.vah?.high, "#22c55e");
          addPriceLine(candleSeries, "VAL", state.indicators.volumeProfile?.val?.low, "#ef4444");
        }
        if (state.toggles.hv252 && intradayTimeframes.includes(state.timeframe) && state.indicators.hv252.ok) {
          const hvColors = { 0:"#f59e0b", 1:"#60a5fa", 1.5:"#a78bfa", 2:"#f472b6" };
          state.indicators.hv252.levels.forEach((level) => {
            const key = `hv252_${String(level.multiplier).replace("-", "m").replace(".", "_")}`;
            const color = hvColors[Math.abs(level.multiplier)] || "#a78bfa";
            addLine(key, horizontalSessionLine(state.candles, level.price), color, level.multiplier === 0 ? 2 : 1);
            addPriceLine(candleSeries, level.label, level.price, color, level.multiplier === 0 ? 0 : 2);
          });
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
        const lastVol = indicators.volumeStats[indicators.volumeStats.length - 1] || {};
        document.getElementById("lw-last").textContent = last ? fmt(last.close, 2) : "---";
        document.getElementById("lw-vwap").textContent = lastVwap ? fmt(lastVwap, 2) : "---";
        document.getElementById("lw-vwap-extra").textContent = last && lastVwap ? `Dist ${(((last.close - lastVwap) / lastVwap) * 100).toFixed(2)}%` : "Dist ---";
        document.getElementById("lw-volume").textContent = last ? fmt(last.volume, 4) : "---";
        document.getElementById("lw-rvol").textContent = `RVOL ${fmt(lastVol.rvol, 2)}x | Leg ${fmt(lastVol.legRelativeVolume, 2)}x | M20 ${fmt(lastVol.avg, 2)}`;
        document.getElementById("lw-vp-poc").textContent = `POC ${fmt(indicators.volumeProfile?.poc?.mid, 2)}`;
        document.getElementById("lw-vp-value-area").textContent = `VAH ${fmt(indicators.volumeProfile?.vah?.high, 2)} | VAL ${fmt(indicators.volumeProfile?.val?.low, 2)}`;
        const hv = indicators.hv252 || {};
        const level = (mult) => (hv.levels || []).find((item) => item.multiplier === mult)?.price;
        const nearest = last && hv.ok ? hv.levels.filter((item) => item.multiplier !== 0).reduce((best, item) => {
          const distance = Math.abs(last.close - item.price);
          return !best || distance < best.distance ? { ...item, distance } : best;
        }, null) : null;
        document.getElementById("lw-hv252").textContent = hv.ok ? `Fech. ant. ${fmt(hv.prevClose, 2)}` : (hv.warning || "Historico insuficiente para HV 252");
        document.getElementById("lw-hv30").textContent = hv.ok ? `HV diaria ${(hv.dailyVol * 100).toFixed(2)}% | anual ${(hv.annualVol * 100).toFixed(2)}%` : "Use candles diarios suficientes";
        document.getElementById("lw-hv-levels").textContent = hv.ok
          ? `1σ ${fmt(level(-1),2)} / ${fmt(level(1),2)} | 2σ ${fmt(level(-2),2)} / ${fmt(level(2),2)} | prox ${nearest ? `${nearest.label} (${fmt(nearest.distance,2)})` : "---"}`
          : "Historico insuficiente para HV 252";
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
          const buySignal = recent.find((s) => allowedSignalTypes.includes(s.type) && s.type.includes("BUY"));
          const sellSignal = recent.find((s) => allowedSignalTypes.includes(s.type) && s.type.includes("SELL"));
        if (buySignal) alerts.push([`${buySignal.type} score ${buySignal.score}`, "buy"]);
        if (sellSignal) alerts.push([`${sellSignal.type} score ${sellSignal.score}`, "sell"]);
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
      function signalByTime(time) {
        return (state.indicators?.signals || []).find((s) => s.time === time);
      }
      function vwapAt(time) {
        return (state.indicators?.vwapDay || []).find((v) => v.time === time)?.value;
      }
      function renderHover(c, x=12, y=12) {
        if (!c) return;
        const v = vwapAt(c.time);
        const signal = signalByTime(c.time);
        const change = ((c.close - c.open) / c.open) * 100;
        const dist = v ? ((c.close - v) / v) * 100 : NaN;
        const signalHtml = signal ? `
            <div style="grid-column:1 / -1; border-top:1px solid #334155; margin-top:6px; padding-top:6px;">
              <div style="color:#f8fafc; font-weight:900;">${escapeHtml(signal.type)} | Score ${signal.score} | ${escapeHtml(signal.regime)}</div>
              <div><span>Entrada</span> ${fmt(signal.price,2)} | <span>Stop</span> ${fmt(signal.suggestedStop,2)}</div>
              <div><span>Alvo 1</span> ${fmt(signal.suggestedTarget1,2)} | <span>Alvo 2</span> ${fmt(signal.suggestedTarget2,2)}</div>
              <div><span>RSI</span> ${fmt(signal.rsi,1)} | <span>Dist VWAP</span> ${Number.isFinite(signal.vwapDistancePercent) ? signal.vwapDistancePercent.toFixed(2) : "---"}%</div>
              <div><span>Vol</span> ${fmt(signal.volume,2)} | <span>M20</span> ${fmt(signal.volumeMA,2)} | <span>RVOL</span> ${fmt(signal.relativeVolume,2)}x</div>
              <div><span>Pernada</span> ${fmt(signal.legVolume,2)} | <span>Leg RVOL</span> ${fmt(signal.legRelativeVolume,2)}x</div>
              <div style="color:#cbd5e1; margin-top:3px;">${escapeHtml(signal.reasons.slice(0, 5).join(" | "))}</div>
              <div style="color:#94a3b8; margin-top:3px;">${escapeHtml((signal.locationTags || []).slice(0, 6).join(" | "))}</div>
            </div>` : "";
        const html = `
          <strong>${state.symbol} | ${fmtTime(c.time)}</strong>
          <div class="lw-crosshair-grid">
            <div><span>Open</span> ${fmt(c.open,2)}</div><div><span>High</span> ${fmt(c.high,2)}</div>
            <div><span>Low</span> ${fmt(c.low,2)}</div><div><span>Close</span> ${fmt(c.close,2)}</div>
            <div><span>Volume</span> ${fmt(c.volume,2)}</div><div><span>Var</span> ${Number.isFinite(change) ? change.toFixed(2) : "---"}%</div>
            <div><span>VWAP</span> ${fmt(v,2)}</div><div><span>Dist VWAP</span> ${Number.isFinite(dist) ? dist.toFixed(2) : "---"}%</div>
            ${signalHtml}
          </div>`;
        crosshairCard.innerHTML = html;
        crosshairCard.style.display = "block";
        crosshairCard.style.left = `${Math.min(x + 16, Math.max(12, chartEl.clientWidth - 280))}px`;
        crosshairCard.style.top = `${Math.min(y + 16, Math.max(12, chartEl.clientHeight - 160))}px`;
        document.getElementById("lw-hover-title").textContent = `${fmtTime(c.time)}`;
        document.getElementById("lw-hover-data").textContent = signal
          ? `${signal.type} score ${signal.score} | Stop ${fmt(signal.suggestedStop,2)} | Alvos ${fmt(signal.suggestedTarget1,2)} / ${fmt(signal.suggestedTarget2,2)}`
          : `O ${fmt(c.open,2)} H ${fmt(c.high,2)} L ${fmt(c.low,2)} C ${fmt(c.close,2)} | Vol ${fmt(c.volume,2)} | Dist VWAP ${Number.isFinite(dist) ? dist.toFixed(2) : "---"}%`;
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
        const nowMs = Date.now();
        if (nowMs - state.lastFullRefresh < 1000) {
          const lastQuick = state.candles[state.candles.length - 1];
          state.series.candle.update(lastQuick);
          if (state.series.volume) state.series.volume.update({ time:lastQuick.time, value:lastQuick.volume, color:lastQuick.close >= lastQuick.open ? "rgba(0,192,135,.32)" : "rgba(255,75,75,.32)" });
          if (!state.liveUpdateQueued) {
            state.liveUpdateQueued = true;
            setTimeout(() => { state.liveUpdateQueued = false; refreshLiveSeries(); }, 1000);
          }
          return;
        }
        state.lastFullRefresh = nowMs;
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
        updateVWAPPercentBands("vwap", state.indicators.vwapDay);
        updateVWAPPercentBands("vwapWeek", state.indicators.vwapWeek);
        state.indicators.weekVolBands.forEach((band) => {
          const key = String(band.multiplier).replace(".", "_");
          state.series[`week_vol_${key}_u`]?.setData(band.data.map((p) => ({ time:p.time, value:p.upper })));
          state.series[`week_vol_${key}_l`]?.setData(band.data.map((p) => ({ time:p.time, value:p.lower })));
        });
        state.indicators.stdevBands.forEach((band) => {
          const key = String(band.multiplier).replace(".", "_");
          state.series[`stdev_${key}_u`]?.setData(band.data.map((p) => ({ time:p.time, value:p.upper })));
          state.series[`stdev_${key}_l`]?.setData(band.data.map((p) => ({ time:p.time, value:p.lower })));
        });
        if (state.indicators.hv252?.ok) {
          state.indicators.hv252.levels.forEach((level) => {
            const key = `hv252_${String(level.multiplier).replace("-", "m").replace(".", "_")}`;
            state.series[key]?.setData(horizontalSessionLine(state.candles, level.price));
          });
        }
        state.indicators.ma.forEach((m) => state.series[m.id]?.setData(m.data));
        applyMarkers(state.series.candle, state.indicators.signals);
        updateStats();
        requestAnimationFrame(renderVolumeProfile);
      }
      function startSocket() {
        if (state.socket) state.socket.close();
        const asset = assetRegistry[state.symbol] || { source: "binance" };
        if (asset.source !== "binance") {
          state.socket = null;
          const loadedSeries = asset.source === "fred" ? fredPayload.series?.[state.symbol] : yahooPayload.series?.[state.symbol];
          const sourceName = loadedSeries?.sourceLabel || (asset.source === "fred" ? "FRED" : "yfinance");
          const code = asset.ticker || asset.seriesId || state.symbol;
          setStatus(`Dados ${sourceName} carregados: ${asset.label} (${code}). Sem WebSocket no browser; use Recarregar para atualizar.`);
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
        const nextAsset = assetRegistry[symbol] || { source: "binance", label: symbol };
        state.symbol = symbol;
        state.timeframe = nextAsset.source === "fred" && intradayTimeframes.includes(timeframe) ? "1d" : timeframe;
        renderControls();
        savePrefs();
        const asset = nextAsset;
        setLoading(true);
        if (asset.source === "yahoo" && state.timeframe === "30s") {
          setStatus(`${asset.label}: yfinance nao possui 30s; usando candles de 1m.`);
        } else if (asset.source === "fred" && state.timeframe !== timeframe) {
          setStatus(`${asset.label}: FRED entrega serie diaria. Ajustei automaticamente para 1d.`);
        } else {
          const sourceName = asset.source === "yahoo" ? "yfinance" : asset.source === "fred" ? "FRED" : "Binance";
          setStatus(`Carregando historico ${sourceName}: ${asset.label || symbol} ${state.timeframe}...`);
        }
        try {
          const [candles, dailyCandles] = await Promise.all([
            fetchHistorical(symbol, state.timeframe),
            fetchDailyCandles(symbol).catch((err) => { console.warn("Daily candles indisponiveis", err); return []; }),
          ]);
          state.candles = candles;
          state.dailyCandles = dailyCandles;
          if (!state.candles.length) throw new Error(`Ativo ${asset.label || symbol} sem candles para ${state.timeframe}.`);
          renderCharts();
          startSocket();
          if (asset.source === "binance") setStatus("Historico carregado. Atualizacao em tempo real via Binance WebSocket.");
        }
        catch (err) {
          console.error(err);
          renderChartMessage("Sem dados para este ativo/timeframe.", err.message || "Verifique a fonte de dados e tente novamente.");
          setStatus(`Erro ao carregar dados: ${err.message}`);
        }
        finally { setLoading(false); }
      }
      window.addEventListener("resize", () => {
        if (state.chart) state.chart.applyOptions({ width:chartEl.clientWidth });
        requestAnimationFrame(renderVolumeProfile);
      });
      renderControls(); loadSymbol(state.symbol, state.timeframe);
      if (providerNotes) setTimeout(() => { if (statusEl.textContent.includes("Inicializando")) setStatus(providerNotes); }, 400);
    })();
    </script>
    """
    return (
        html
        .replace("__YAHOO_PAYLOAD__", yahoo_json)
        .replace("__FRED_PAYLOAD__", fred_json)
        .replace("__SIGNAL_MODE__", signal_mode_json)
        .replace("__CHART_TITLE__", chart_title_json)
        .replace("__INSTANCE_ID__", instance_id_json)
    )
