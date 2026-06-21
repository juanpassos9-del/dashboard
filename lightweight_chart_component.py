import json
import os
import time
from datetime import datetime, timedelta

import requests
import streamlit as st
import yfinance as yf


YAHOO_LIGHTWEIGHT_ASSETS = [
    {"symbol": "SP500", "label": "S&P 500", "ticker": "^GSPC"},
    {"symbol": "NASDAQ", "label": "NASDAQ", "ticker": "^IXIC"},
    {"symbol": "RUSSELL", "label": "RUSSELL", "ticker": "^RUT"},
    {"symbol": "DXY", "label": "DXY", "ticker": "DX-Y.NYB"},
    {"symbol": "EURUSD", "label": "EURUSD", "ticker": "EURUSD=X"},
    {"symbol": "6L1", "label": "6L1", "ticker": "6L=F"},
    {"symbol": "BRENT", "label": "BRENT", "ticker": "BZ=F"},
    {"symbol": "WTI", "label": "WTI", "ticker": "CL=F"},
    {"symbol": "XAUUSD", "label": "XAUUSD", "ticker": "GC=F"},
    {"symbol": "EEM", "label": "EEM", "ticker": "EEM"},
    {"symbol": "EWZ", "label": "EWZ", "ticker": "EWZ"},
    {"symbol": "IBOV", "label": "IBOV", "ticker": "^BVSP"},
    {"symbol": "BOVA11", "label": "BOVA11", "ticker": "BOVA11.SA"},
    {"symbol": "SMAL11", "label": "SMAL11", "ticker": "SMAL11.SA"},
    {"symbol": "IVVB11", "label": "IVVB11", "ticker": "IVVB11.SA"},
    {"symbol": "PETR4", "label": "PETR4", "ticker": "PETR4.SA"},
    {"symbol": "PETR3", "label": "PETR3", "ticker": "PETR3.SA"},
    {"symbol": "VALE3", "label": "VALE3", "ticker": "VALE3.SA"},
    {"symbol": "ITUB4", "label": "ITUB4", "ticker": "ITUB4.SA"},
    {"symbol": "BBDC4", "label": "BBDC4", "ticker": "BBDC4.SA"},
    {"symbol": "BBAS3", "label": "BBAS3", "ticker": "BBAS3.SA"},
    {"symbol": "B3SA3", "label": "B3SA3", "ticker": "B3SA3.SA"},
    {"symbol": "WEGE3", "label": "WEGE3", "ticker": "WEGE3.SA"},
    {"symbol": "ABEV3", "label": "ABEV3", "ticker": "ABEV3.SA"},
    {"symbol": "MGLU3", "label": "MGLU3", "ticker": "MGLU3.SA"},
    {"symbol": "RENT3", "label": "RENT3", "ticker": "RENT3.SA"},
    {"symbol": "PRIO3", "label": "PRIO3", "ticker": "PRIO3.SA"},
    {"symbol": "SUZB3", "label": "SUZB3", "ticker": "SUZB3.SA"},
    {"symbol": "BPAC11", "label": "BPAC11", "ticker": "BPAC11.SA"},
    {"symbol": "RADL3", "label": "RADL3", "ticker": "RADL3.SA"},
    {"symbol": "LREN3", "label": "LREN3", "ticker": "LREN3.SA"},
    {"symbol": "GGBR4", "label": "GGBR4", "ticker": "GGBR4.SA"},
    {"symbol": "CSNA3", "label": "CSNA3", "ticker": "CSNA3.SA"},
]

BCB_LIGHTWEIGHT_ASSETS = [
    {"symbol": "BCB_USDBRL", "label": "USD/BRL BCB", "series_id": 1},
    {"symbol": "BCB_EURBRL", "label": "EUR/BRL BCB", "series_id": 21619},
    {"symbol": "BCB_GBPBRL", "label": "GBP/BRL BCB", "series_id": 21623},
    {"symbol": "BCB_JPYBRL", "label": "JPY/BRL BCB", "series_id": 21621},
    {"symbol": "BCB_CHFBRL", "label": "CHF/BRL BCB", "series_id": 21625},
]

FRED_LIGHTWEIGHT_ASSETS = [
    {"symbol": "FRED_DGS10", "label": "US10Y FRED", "series_id": "DGS10"},
    {"symbol": "FRED_DGS30", "label": "US30Y FRED", "series_id": "DGS30"},
]

LIGHTWEIGHT_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".tmp")
YAHOO_PAYLOAD_CACHE = os.path.join(LIGHTWEIGHT_CACHE_DIR, "lightweight_yahoo_payload.json")


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


def _read_json_cache(path: str, max_age_seconds: int):
    try:
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > max_age_seconds:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json_cache(path: str, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


@st.cache_data(ttl=60, show_spinner=False)
def load_yahoo_lightweight_payload():
    cached_payload = _read_json_cache(YAHOO_PAYLOAD_CACHE, max_age_seconds=900)
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
            timeout=12,
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
            timeout=12,
        )
    except Exception as e:
        daily_data = None
        errors.append(f"daily: {e}")

    if (intraday_data is None or intraday_data.empty) and (daily_data is None or daily_data.empty):
        if cached_payload:
            cached_payload["stale"] = True
            cached_payload["error"] = "; ".join(errors) or "Yahoo Finance retornou vazio; usando cache local."
            return cached_payload
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
    result = {"assets": YAHOO_LIGHTWEIGHT_ASSETS, "series": payload, "error": "; ".join(errors) or None}
    if payload:
        _write_json_cache(YAHOO_PAYLOAD_CACHE, result)
    elif cached_payload:
        cached_payload["stale"] = True
        cached_payload["error"] = "; ".join(errors) or "Yahoo Finance retornou vazio; usando cache local."
        return cached_payload
    return result


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


@st.cache_data(ttl=900, show_spinner=False)
def load_bcb_lightweight_payload():
    payload = {}
    errors = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 3)
    date_params = {
        "dataInicial": start_date.strftime("%d/%m/%Y"),
        "dataFinal": end_date.strftime("%d/%m/%Y"),
    }
    for asset in BCB_LIGHTWEIGHT_ASSETS:
        series_id = asset["series_id"]
        try:
            res = requests.get(
                f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados",
                params={"formato": "json", **date_params},
                timeout=12,
            )
            res.raise_for_status()
            rows = res.json()
            candles = []
            previous = None
            for item in rows[-750:]:
                value = item.get("valor")
                date_text = item.get("data")
                if value in (None, "") or not date_text:
                    continue
                close = float(str(value).replace(",", "."))
                open_ = previous if previous is not None else close
                ts = int(time.mktime(time.strptime(date_text, "%d/%m/%Y")))
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
                    "sourceLabel": "BCB SGS",
                }
        except Exception as e:
            errors.append(f"{series_id}: {e}")
    return {"enabled": True, "assets": BCB_LIGHTWEIGHT_ASSETS, "series": payload, "error": "; ".join(errors) or None}


def render_lightweight_chart_html(signal_mode="all", chart_title=None, instance_id="main"):
    signal_mode = signal_mode if signal_mode in {"all", "reversal"} else "reversal"
    instance_id = "".join(ch for ch in str(instance_id or "main") if ch.isalnum() or ch in ("_", "-")) or "main"
    chart_title = chart_title or {
        "all": "Grafico operacional - Reversao",
        "reversal": "Grafico operacional - Reversao",
    }[signal_mode]
    yahoo_payload = load_yahoo_lightweight_payload()
    bcb_payload = load_bcb_lightweight_payload()
    fred_payload = load_fred_lightweight_payload()
    yahoo_json = json.dumps(yahoo_payload, ensure_ascii=False)
    bcb_json = json.dumps(bcb_payload, ensure_ascii=False)
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
        #lw-chart { height:1320px; min-width:0; }
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
        .lw-volume-profile { position:absolute; top:0; right:56px; width:150px; height:1320px; z-index:3; pointer-events:none; opacity:.82; }
        .lw-vp-bar { position:absolute; right:0; height:3px; min-width:2px; border-radius:999px 0 0 999px; background:rgba(56,189,248,.32); }
        .lw-vp-bar.value-area { background:rgba(34,197,94,.38); }
        .lw-vp-bar.poc { height:5px; background:rgba(245,158,11,.9); box-shadow:0 0 8px rgba(245,158,11,.55); }
        .lw-vp-label { position:absolute; right:0; top:6px; color:#94a3b8; font-size:.66rem; font-weight:900; text-transform:uppercase; background:rgba(8,13,20,.72); padding:2px 5px; border:1px solid #334155; border-radius:4px; }
        .lw-skeleton { position:absolute; inset:0; z-index:4; display:none; background:linear-gradient(90deg,#0b1220 0%,#111827 50%,#0b1220 100%); background-size:220% 100%; animation:lwPulse 1.2s ease-in-out infinite; }
        .lw-skeleton.show { display:block; }
        @keyframes lwPulse { from{background-position:220% 0;} to{background-position:-220% 0;} }
        .lw-status { color:#94a3b8; font-size:.75rem; padding:8px 12px 10px; border-top:1px solid #1f2937; background:#0d1420; }
        @media (max-width:900px){ .lw-main{grid-template-columns:1fr;} .lw-side{border-left:0; border-top:1px solid #1f2937; grid-template-columns:repeat(2,minmax(0,1fr));} #lw-chart{height:860px;} }
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
      const bcbPayload = __BCB_PAYLOAD__;
      const fredPayload = __FRED_PAYLOAD__;
      const signalMode = __SIGNAL_MODE__;
      const chartTitle = __CHART_TITLE__;
      const instanceId = __INSTANCE_ID__;
      const binanceAssets = [
        { symbol: "BTCUSDT", label: "BTC", source: "binance" },
        { symbol: "ETHUSDT", label: "ETH", source: "binance" },
        { symbol: "SOLUSDT", label: "SOL", source: "binance" },
        { symbol: "LINKUSDT", label: "LINK", source: "binance" },
        { symbol: "BNBUSDT", label: "BNB", source: "binance" },
        { symbol: "DYDXUSDT", label: "DYDX", source: "binance" },
        { symbol: "ENAUSDT", label: "ENA", source: "binance" },
        { symbol: "LDOUSDT", label: "LDO", source: "binance" },
        { symbol: "ARKMUSDT", label: "ARKM", source: "binance" },
        { symbol: "PENDLEUSDT", label: "PENDLE", source: "binance" },
        { symbol: "AAVEUSDT", label: "AAVE", source: "binance" },
        { symbol: "XAUTUSDT", label: "XAUT", source: "binance" },
        { symbol: "PAXGUSDT", label: "PAXG", source: "binance" },
        { symbol: "ONDOUSDT", label: "ONDO", source: "binance" },
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
      const bcbAssets = (bcbPayload.assets || []).map((asset) => ({
        symbol: asset.symbol,
        label: asset.label,
        source: "bcb",
        seriesId: asset.series_id,
      }));
      const assets = [...binanceAssets, ...yahooAssets, ...bcbAssets, ...fredAssets];
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
        enabledSignals:{ REV_BUY:true, REV_SELL:true, TREND_BUY:false, TREND_SELL:false },
        minScore:50,
        cooldownCandles:10,
        volume:{ enabled:true, lookback:20, minVolumeMultiplier:1.2, minRelativeVolume:1.2, strongRelativeVolume:1.5, blockLowVolumeSignals:true, requireBarVolumeAboveAverage:true, requireVolumeExpansion:true, legLookback:5, minLegRelativeVolume:1.1, requireReversalVolumeClimaxOrRejection:true, requireTrendVolumeResumption:true, blockFallingVolume:true, fallingVolumeLookback:3 },
        garch:{ enabled:true, omega:0.000001, alpha:0.08, beta:0.90, garchTimeframe:"D", referenceMode:"previousClose", adjustment:null, minSigmaForSignal:1.5 },
        signalEngine:{
          enabled:true,
          minSigmaForSignal:1.5,
          preferredSigmaForStrongSignal:2.0,
          allowedSources:{ garch:true, hv252:true },
          bandRegion:{ enabled:true, mode:"percent", percentTolerance:0.001, atrMultiplier:0.15, ticksTolerance:20, minRegionWidthTicks:5, closeBackRule:"aboveCenter" },
          rejection:{ minWickToBodyRatio:1.8, minCloseBackInsidePercent:0.4, requireCloseBackInsideZone:true, allowPinBar:true, allowEngulfing:true, allowFailedBreakout:true, allowCloseBackInside:true, allowImpulseReversal:true },
          volumeFilter:{ enabled:true, lookback:20, multiplier:1.2 },
          candleFilter:{ minBodyPercentOfRange:0.15, maxBodyPercentForPinBar:0.45 },
          cooldown:{ enabled:true, bars:10 },
          signalSide:{ buy:true, sell:true },
          visual:{ plotRegionLines:true, plotSignals:true, preserveExistingMarkers:true },
        },
        sessionFilter:{ enabled:false, blockedTimes:[] },
      };
      const defaultPrefs = {
        symbol:"BTCUSDT",
        timeframe:"1m",
        toggles:{ ma:true, vwap:true, bandsDay:true, bandsWeek:false, bandsWeekVol:false, bands:false, stdevBands:false, volume:true, weisWave:true, volatilityBands:true, garch:true, volumeProfile:true, hv252:true, refs:true, signals:true },
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
          reversal:{ ...defaultSignalConfig.reversal, ...((storedPrefs.signalConfig || {}).reversal || {}) },
          trend:{ ...defaultSignalConfig.trend, ...((storedPrefs.signalConfig || {}).trend || {}) },
          volume:{ ...defaultSignalConfig.volume, ...((storedPrefs.signalConfig || {}).volume || {}) },
          garch:{ ...defaultSignalConfig.garch, ...((storedPrefs.signalConfig || {}).garch || {}) },
          signalEngine:{
            ...defaultSignalConfig.signalEngine,
            ...((storedPrefs.signalConfig || {}).signalEngine || {}),
            allowedSources:{ ...defaultSignalConfig.signalEngine.allowedSources, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).allowedSources || {}) },
            bandRegion:{ ...defaultSignalConfig.signalEngine.bandRegion, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).bandRegion || {}) },
            rejection:{ ...defaultSignalConfig.signalEngine.rejection, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).rejection || {}) },
            volumeFilter:{ ...defaultSignalConfig.signalEngine.volumeFilter, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).volumeFilter || {}) },
            candleFilter:{ ...defaultSignalConfig.signalEngine.candleFilter, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).candleFilter || {}) },
            cooldown:{ ...defaultSignalConfig.signalEngine.cooldown, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).cooldown || {}) },
            signalSide:{ ...defaultSignalConfig.signalEngine.signalSide, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).signalSide || {}) },
            visual:{ ...defaultSignalConfig.signalEngine.visual, ...(((storedPrefs.signalConfig || {}).signalEngine || {}).visual || {}) },
          },
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
      if (assetRegistry[state.symbol]?.source === "bcb" && !bcbPayload.enabled) state.symbol = "BTCUSDT";
      if (!timeframes.includes(state.timeframe)) state.timeframe = "1m";
      if (assetRegistry[state.symbol]?.source === "fred" && intradayTimeframes.includes(state.timeframe)) state.timeframe = "1d";
      if (assetRegistry[state.symbol]?.source === "bcb" && intradayTimeframes.includes(state.timeframe)) state.timeframe = "1d";
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
        [["ma","Medias"],["vwap","VWAP"],["bandsDay","Bandas D"],["bandsWeek","Bandas W %"],["bandsWeekVol","Bandas W Vol"],["stdevBands","Desvios"],["refs","Refs"],["signals","Sinais"],["volume","Volume"],["weisWave","Weis Vol"],["volatilityBands","Bandas Vol"],["volumeProfile","Vol Profile"]].forEach(([key,label]) => {
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
        const engine = cfg.signalEngine;
        const title = document.createElement("div");
        title.className = "lw-settings-title";
        title.style.marginTop = "6px";
        title.textContent = "Motor de sinais - zonas";
        box.appendChild(title);
        const checks = [["enabled", "Motor"], ["engine", "Zonas volatilidade"], ["buy", "BUY"], ["sell", "SELL"], ["volFilter", "Filtro volume"], ["regionLines", "Linhas regiao"], ["garchSrc", "Fonte GARCH"], ["hvSrc", "Fonte HV252"]];
        checks.forEach(([key, label]) => {
          const row = document.createElement("div");
          row.className = "lw-setting-row";
          const checked =
            key === "enabled" ? cfg.enabled :
            key === "engine" ? engine.enabled :
            key === "buy" ? engine.signalSide.buy :
            key === "sell" ? engine.signalSide.sell :
            key === "volFilter" ? engine.volumeFilter.enabled :
            key === "regionLines" ? engine.visual.plotRegionLines :
            key === "garchSrc" ? engine.allowedSources.garch :
            key === "hvSrc" ? engine.allowedSources.hv252 :
            false;
          row.innerHTML = `<label style="grid-column:1 / 3;"><input type="checkbox" ${checked ? "checked" : ""}> ${label}</label><span></span>`;
          row.querySelector("input").onchange = (e) => {
            if (key === "enabled") cfg.enabled = e.target.checked;
            else if (key === "engine") engine.enabled = e.target.checked;
            else if (key === "buy") engine.signalSide.buy = e.target.checked;
            else if (key === "sell") engine.signalSide.sell = e.target.checked;
            else if (key === "volFilter") engine.volumeFilter.enabled = e.target.checked;
            else if (key === "regionLines") engine.visual.plotRegionLines = e.target.checked;
            else if (key === "garchSrc") engine.allowedSources.garch = e.target.checked;
            else if (key === "hvSrc") engine.allowedSources.hv252 = e.target.checked;
            savePrefs(); renderCharts(false);
          };
          box.appendChild(row);
        });
        [
          ["minScore", "Score", 1, 100, 1, cfg.minScore, (v) => { cfg.minScore = v; }],
          ["minSigma", "Sigma min", 0.5, 3, 0.25, engine.minSigmaForSignal, (v) => { engine.minSigmaForSignal = v; cfg.garch.minSigmaForSignal = v; }],
          ["strongSigma", "Sigma forte", 1, 4, 0.25, engine.preferredSigmaForStrongSignal, (v) => { engine.preferredSigmaForStrongSignal = v; }],
          ["regionPct", "Regiao %", 0.02, 0.5, 0.01, (engine.bandRegion.percentTolerance || 0.001) * 100, (v) => { engine.bandRegion.percentTolerance = v / 100; }],
          ["wickRatio", "Pavio/body", 0.5, 5, 0.1, engine.rejection.minWickToBodyRatio, (v) => { engine.rejection.minWickToBodyRatio = v; }],
          ["cooldown", "Cooldown", 0, 80, 1, engine.cooldown.bars, (v) => { engine.cooldown.bars = v; cfg.cooldownCandles = v; }],
          ["volLook", "Vol M", 5, 80, 1, engine.volumeFilter.lookback, (v) => { engine.volumeFilter.lookback = v; }],
          ["volMult", "Vol x", 0.5, 5, 0.05, engine.volumeFilter.multiplier, (v) => { engine.volumeFilter.multiplier = v; }],
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
        const garchRefRow = document.createElement("div");
        garchRefRow.className = "lw-setting-row";
        garchRefRow.innerHTML = `
          <span>Ref GARCH</span>
          <select id="lw-garch-ref">
            <option value="previousClose">Fech. ant.</option>
            <option value="sessionOpen">Abertura</option>
            <option value="vwap">VWAP</option>
            <option value="lastClose">Ultimo</option>
            <option value="adjustment">Manual</option>
          </select>
          <span></span>`;
        box.appendChild(garchRefRow);
        garchRefRow.querySelector("select").value = cfg.garch.referenceMode || "previousClose";
        garchRefRow.querySelector("select").onchange = (e) => {
          cfg.garch.referenceMode = e.target.value;
          savePrefs();
          renderCharts(false);
        };
        const garchTfRow = document.createElement("div");
        garchTfRow.className = "lw-setting-row";
        garchTfRow.innerHTML = `
          <span>TF GARCH</span>
          <select id="lw-garch-tf">
            <option value="D">Diario</option>
            <option value="intraday">Intraday</option>
          </select>
          <span></span>`;
        box.appendChild(garchTfRow);
        garchTfRow.querySelector("select").value = cfg.garch.garchTimeframe || "D";
        garchTfRow.querySelector("select").onchange = (e) => {
          cfg.garch.garchTimeframe = e.target.value;
          savePrefs();
          renderCharts(false);
        };
        const garchAdjustmentRow = document.createElement("div");
        garchAdjustmentRow.className = "lw-setting-row";
        garchAdjustmentRow.innerHTML = `<span>Ajuste GARCH</span><input type="number" min="0" step="0.01" value="${Number.isFinite(Number(cfg.garch.adjustment)) ? cfg.garch.adjustment : ""}" placeholder="preco"><span></span>`;
        box.appendChild(garchAdjustmentRow);
        garchAdjustmentRow.querySelector("input").onchange = (e) => {
          const value = Number(e.target.value);
          cfg.garch.adjustment = Number.isFinite(value) && value > 0 ? value : null;
          savePrefs();
          renderCharts(false);
        };
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
        if (asset.source === "bcb") return fetchBcbHistorical(symbol, timeframe);
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
        if (asset.source === "bcb") {
          const series = (bcbPayload.series && bcbPayload.series[symbol]) || {};
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
      function fetchBcbHistorical(symbol, timeframe) {
        if (!bcbPayload.enabled) throw new Error(bcbPayload.error || "BCB SGS indisponivel.");
        const series = (bcbPayload.series && bcbPayload.series[symbol]) || {};
        const daily = series.daily || [];
        if (!daily.length) throw new Error(`Sem dados BCB para ${symbol}`);
        if (["30s", "1m", "5m", "h1"].includes(timeframe)) {
          throw new Error("BCB entrega series diarias. Use 1d, 1w ou 1month.");
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
      function computeWeisWaveVolume(candles, reversalPercent=0.2) {
        if (!candles.length) return { points:[], waves:[], current:null };
        const threshold = Math.max(0.01, reversalPercent) / 100;
        const points = [];
        const waves = [];
        let direction = 0;
        let waveStart = 0;
        let extreme = candles[0].close;
        let volume = 0;
        const finalizeWave = (endIndex) => {
          if (endIndex < waveStart) return;
          waves.push({
            start:waveStart,
            end:endIndex,
            direction,
            volume,
            startPrice:candles[waveStart]?.close,
            endPrice:candles[endIndex]?.close,
          });
        };
        candles.forEach((c, i) => {
          if (i === 0) {
            volume = Number(c.volume || 0);
            points.push({ time:c.time, value:volume, direction:0, waveIndex:0 });
            return;
          }
          const prev = candles[i - 1];
          if (direction === 0) {
            direction = c.close >= prev.close ? 1 : -1;
            extreme = c.close;
          }
          const reversalFromHigh = direction === 1 && c.close <= extreme * (1 - threshold);
          const reversalFromLow = direction === -1 && c.close >= extreme * (1 + threshold);
          if (reversalFromHigh || reversalFromLow) {
            finalizeWave(i - 1);
            direction = reversalFromHigh ? -1 : 1;
            waveStart = i;
            volume = Number(c.volume || 0);
            extreme = c.close;
          } else {
            volume += Number(c.volume || 0);
            if (direction === 1) extreme = Math.max(extreme, c.close);
            if (direction === -1) extreme = Math.min(extreme, c.close);
          }
          points.push({ time:c.time, value:volume, direction, waveIndex:waves.length });
        });
        finalizeWave(candles.length - 1);
        const current = points.length ? points[points.length - 1] : null;
        const previousSameDirection = [...waves].reverse().find((w) => w.direction === current?.direction && w.end < candles.length - 1);
        return { points, waves, current, previousSameDirection };
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
      function calculateVolatilityLevels(prevClose, dailyVol, multipliers=[1, 2, 3]) {
        if (!Number.isFinite(prevClose) || !Number.isFinite(dailyVol)) return [];
        const levels = [{ label:"Fech. Ant.", price:prevClose, multiplier:0 }];
        multipliers.forEach((m) => {
          levels.push({ label:`HV +${m}Ïƒ`, price:prevClose * Math.exp(m * dailyVol), multiplier:m });
          levels.push({ label:`HV -${m}Ïƒ`, price:prevClose * Math.exp(-m * dailyVol), multiplier:-m });
        });
        return levels;
      }
      function annualizationFactorForTimeframe(tf) {
        if (tf === "1d") return 252;
        if (tf === "1w") return 52;
        if (tf === "1month") return 12;
        if (tf === "h1") return 252 * 6;
        return 252 * 390;
      }
      function calculateGarch11Volatility(candles, options={}) {
        const omega = Number(options.omega ?? 0.000001);
        const alpha = Number(options.alpha ?? 0.08);
        const beta = Number(options.beta ?? 0.90);
        const annualizationFactor = Number(options.annualizationFactor ?? 252);
        if (alpha + beta >= 1) return { ok:false, warning:"GARCH instavel: alpha + beta precisa ser menor que 1.", conditionalVariance:[], conditionalVolatility:[], latestVolatility:NaN, annualizedVolatility:NaN };
        const closes = (candles || []).map((c) => c.close).filter((v) => Number.isFinite(v) && v > 0);
        const returns = calculateLogReturns(closes);
        if (returns.length < 30) return { ok:false, warning:"Historico insuficiente para GARCH.", conditionalVariance:[], conditionalVolatility:[], latestVolatility:NaN, annualizedVolatility:NaN };
        const mean = returns.reduce((a,b) => a + b, 0) / returns.length;
        const sampleVariance = returns.reduce((sum,r) => sum + Math.pow(r - mean, 2), 0) / Math.max(1, returns.length - 1);
        const conditionalVariance = [Math.max(sampleVariance, omega)];
        for (let i = 1; i < returns.length; i += 1) {
          const prevReturn = returns[i - 1];
          const prevVariance = conditionalVariance[i - 1];
          conditionalVariance.push(Math.max(0, omega + alpha * prevReturn * prevReturn + beta * prevVariance));
        }
        const conditionalVolatility = conditionalVariance.map((v) => Math.sqrt(v));
        const latestVolatility = conditionalVolatility[conditionalVolatility.length - 1];
        return { ok:true, warning:"", conditionalVariance, conditionalVolatility, latestVolatility, annualizedVolatility:latestVolatility * Math.sqrt(annualizationFactor) };
      }
      function getGarchReferencePrice(candles, mode, externalData={}) {
        const last = candles[candles.length - 1];
        if (mode === "vwap" && Number.isFinite(externalData.vwap)) return externalData.vwap;
        if (mode === "adjustment" && Number.isFinite(externalData.adjustment)) return externalData.adjustment;
        if (mode === "sessionOpen" && Number.isFinite(externalData.sessionOpen)) return externalData.sessionOpen;
        if (mode === "lastClose" && Number.isFinite(last?.close)) return last.close;
        if (mode === "previousClose" && Number.isFinite(externalData.previousClose)) return externalData.previousClose;
        return Number.isFinite(last?.close) ? last.close : NaN;
      }
      function calculateGarchVolatilityZones(referencePrice, volatility, multipliers=[0,0.5,1,1.5,2,2.5,3]) {
        if (!Number.isFinite(referencePrice) || !Number.isFinite(volatility) || volatility <= 0) return [];
        const zones = [];
        multipliers.forEach((m) => {
          if (m === 0) zones.push({ level:referencePrice, label:"GARCH 0", multiplier:0, side:"center" });
          else {
            zones.push({ level:referencePrice * Math.exp(volatility * m), label:`GARCH +${m}Ïƒ`, multiplier:m, side:"upper" });
            zones.push({ level:referencePrice * Math.exp(-volatility * m), label:`GARCH -${m}Ïƒ`, multiplier:-m, side:"lower" });
          }
        });
        return zones;
      }
      function classifyCurrentGarchZone(currentPrice, referencePrice, volatility) {
        if (!Number.isFinite(currentPrice) || !Number.isFinite(referencePrice) || !Number.isFinite(volatility) || volatility <= 0) {
          return { zone:"indisponivel", side:"center", sigmaDistance:NaN, message:"GARCH indisponivel." };
        }
        const sigmaDistance = Math.log(currentPrice / referencePrice) / volatility;
        const abs = Math.abs(sigmaDistance);
        const side = sigmaDistance > 0 ? "upper" : sigmaDistance < 0 ? "lower" : "center";
        if (abs < 0.5) return { zone:"neutral", side, sigmaDistance, message:"Zona neutra. Evitar reversao." };
        if (abs < 1) return { zone:"moderate", side, sigmaDistance, message:"Afastamento moderado. Aguardar confirmacao." };
        if (abs < 2) return { zone:"attention", side, sigmaDistance, message:"Zona operacional relevante." };
        if (abs < 3) return { zone:"extreme", side, sigmaDistance, message:"Zona estatisticamente esticada." };
        return { zone:"anomaly", side, sigmaDistance, message:"Movimento anormal. Exigir confirmacao forte." };
      }
      function calculateGarchOverlay(candles, dailyCandles, refs, vwapDay) {
        const cfg = state.signalConfig.garch || {};
        const referenceMode = cfg.referenceMode || "previousClose";
        const garchTimeframe = cfg.garchTimeframe || "D";
        const garchSource = garchTimeframe === "D" && Array.isArray(dailyCandles) && dailyCandles.length >= 31 ? dailyCandles : candles;
        const annualizationFactor = garchTimeframe === "D" ? 252 : annualizationFactorForTimeframe(state.timeframe);
        const garch = calculateGarch11Volatility(garchSource, { ...cfg, annualizationFactor });
        if (!garch.ok) return { ...garch, referencePrice:NaN, zones:[], classification:{ zone:"indisponivel", side:"center", sigmaDistance:NaN, message:garch.warning } };
        const referencePrice = getGarchReferencePrice(candles, referenceMode, {
          previousClose:refs?.prevClose,
          sessionOpen:refs?.open,
          adjustment:Number(cfg.adjustment),
          vwap:vwapDay?.[vwapDay.length - 1]?.value,
        });
        const zones = calculateGarchVolatilityZones(referencePrice, garch.latestVolatility);
        const current = candles[candles.length - 1]?.close;
        const classification = classifyCurrentGarchZone(current, referencePrice, garch.latestVolatility);
        return { ...garch, referencePrice, referenceMode, garchTimeframe:garchSource === dailyCandles ? "D" : "intraday", zones, classification };
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
      function collectVolatilityBands(indicators) {
        const out = [];
        (indicators.garch?.zones || []).forEach((zone) => {
          const side = zone.side === "upper" ? "upper" : zone.side === "lower" ? "lower" : "center";
          out.push({ id:`GARCH_${zone.multiplier}`, label:zone.label, source:zone.multiplier === 0 ? "REFERENCE" : "GARCH", side, multiplier:Math.abs(zone.multiplier), signedMultiplier:zone.multiplier, price:zone.level });
        });
        (indicators.hv252?.levels || []).forEach((level) => {
          const side = level.multiplier > 0 ? "upper" : level.multiplier < 0 ? "lower" : "center";
          out.push({ id:`HV252_${level.multiplier}`, label:level.label, source:level.multiplier === 0 ? "REFERENCE" : "HV252", side, multiplier:Math.abs(level.multiplier), signedMultiplier:level.multiplier, price:level.price });
        });
        return out.filter((band) => Number.isFinite(band.price));
      }
      function createBandRegion(band, config, atr, tickSize) {
        if (!band || band.source === "REFERENCE" || band.side === "center") return null;
        let toleranceValue = 0;
        if (config.mode === "atr") toleranceValue = Number.isFinite(atr) && atr > 0 ? atr * config.atrMultiplier : 0;
        else if (config.mode === "ticks") toleranceValue = Number.isFinite(tickSize) && tickSize > 0 ? tickSize * config.ticksTolerance : 0;
        else toleranceValue = band.price * (config.percentTolerance || 0.001);
        if (config.minRegionWidthTicks && Number.isFinite(tickSize) && tickSize > 0) toleranceValue = Math.max(toleranceValue, tickSize * config.minRegionWidthTicks);
        if (!Number.isFinite(toleranceValue) || toleranceValue <= 0) return null;
        return { bandId:band.id, label:band.label, source:band.source, side:band.side, multiplier:band.multiplier, centerPrice:band.price, lowerBound:band.price - toleranceValue, upperBound:band.price + toleranceValue, toleranceValue, toleranceMode:config.mode };
      }
      function createBandRegions(bands, config, atr, tickSize) {
        if (!config.bandRegion.enabled) return [];
        return (bands || [])
          .filter((band) => band.source !== "REFERENCE" && band.side !== "center")
          .filter((band) => band.multiplier >= config.minSigmaForSignal)
          .filter((band) => band.source !== "GARCH" || config.allowedSources.garch)
          .filter((band) => band.source !== "HV252" || config.allowedSources.hv252)
          .map((band) => createBandRegion(band, config.bandRegion, atr, tickSize))
          .filter(Boolean);
      }
      function candleTouchesBandRegion(candle, region) {
        return candle.high >= region.lowerBound && candle.low <= region.upperBound;
      }
      function getCandleMetrics(candle) {
        const range = candle.high - candle.low;
        if (!(range > 0)) return null;
        const body = Math.abs(candle.close - candle.open);
        return {
          range,
          body,
          upperWick:candle.high - Math.max(candle.open, candle.close),
          lowerWick:Math.min(candle.open, candle.close) - candle.low,
          closePosition:(candle.close - candle.low) / range,
          bodyPercent:body / range,
          isBullish:candle.close > candle.open,
          isBearish:candle.close < candle.open,
        };
      }
      function isBullishRejectionAtLowerRegion(candle, region, config) {
        if (region.side !== "lower" || !candleTouchesBandRegion(candle, region)) return false;
        const m = getCandleMetrics(candle); if (!m) return false;
        const sweptBelow = candle.low < region.lowerBound;
        const closedAboveCenter = candle.close > region.centerPrice;
        const closedAboveRegion = candle.close > region.upperBound;
        const closeBackOk = config.bandRegion.closeBackRule === "outsideRegion" ? closedAboveRegion : config.bandRegion.closeBackRule === "anyRejection" ? (closedAboveCenter || closedAboveRegion || sweptBelow) : closedAboveCenter;
        return m.lowerWick >= m.body * config.rejection.minWickToBodyRatio && m.closePosition >= 0.6 && m.bodyPercent <= config.candleFilter.maxBodyPercentForPinBar && closeBackOk;
      }
      function isBearishRejectionAtUpperRegion(candle, region, config) {
        if (region.side !== "upper" || !candleTouchesBandRegion(candle, region)) return false;
        const m = getCandleMetrics(candle); if (!m) return false;
        const sweptAbove = candle.high > region.upperBound;
        const closedBelowCenter = candle.close < region.centerPrice;
        const closedBelowRegion = candle.close < region.lowerBound;
        const closeBackOk = config.bandRegion.closeBackRule === "outsideRegion" ? closedBelowRegion : config.bandRegion.closeBackRule === "anyRejection" ? (closedBelowCenter || closedBelowRegion || sweptAbove) : closedBelowCenter;
        return m.upperWick >= m.body * config.rejection.minWickToBodyRatio && m.closePosition <= 0.4 && m.bodyPercent <= config.candleFilter.maxBodyPercentForPinBar && closeBackOk;
      }
      function isBullishEngulfingAtLowerRegion(prev, current, region) {
        return region.side === "lower" && prev?.close < prev?.open && current.close > current.open && current.open <= prev.close && current.close >= prev.open && (candleTouchesBandRegion(prev, region) || candleTouchesBandRegion(current, region)) && current.close > region.centerPrice;
      }
      function isBearishEngulfingAtUpperRegion(prev, current, region) {
        return region.side === "upper" && prev?.close > prev?.open && current.close < current.open && current.open >= prev.close && current.close <= prev.open && (candleTouchesBandRegion(prev, region) || candleTouchesBandRegion(current, region)) && current.close < region.centerPrice;
      }
      function isBullishFailedBreakout(candle, region, config) {
        if (region.side !== "lower") return false;
        return candle.low < region.lowerBound && (config.bandRegion.closeBackRule === "outsideRegion" ? candle.close > region.upperBound : candle.close > region.centerPrice);
      }
      function isBearishFailedBreakout(candle, region, config) {
        if (region.side !== "upper") return false;
        return candle.high > region.upperBound && (config.bandRegion.closeBackRule === "outsideRegion" ? candle.close < region.lowerBound : candle.close < region.centerPrice);
      }
      function isBullishCloseBackInside(prev, current, region) {
        return region.side === "lower" && prev && prev.close < region.lowerBound && current.close > region.lowerBound;
      }
      function isBearishCloseBackInside(prev, current, region) {
        return region.side === "upper" && prev && prev.close > region.upperBound && current.close < region.upperBound;
      }
      function isBullishImpulseReversal(candle, region) {
        const m = getCandleMetrics(candle);
        return region.side === "lower" && m && m.isBullish && candleTouchesBandRegion(candle, region) && m.bodyPercent >= 0.55 && m.closePosition >= 0.75 && candle.close > region.centerPrice;
      }
      function isBearishImpulseReversal(candle, region) {
        const m = getCandleMetrics(candle);
        return region.side === "upper" && m && m.isBearish && candleTouchesBandRegion(candle, region) && m.bodyPercent >= 0.55 && m.closePosition <= 0.25 && candle.close < region.centerPrice;
      }
      function averageVolume(candles, index, lookback) {
        const slice = candles.slice(Math.max(0, index - lookback), index).filter((c) => typeof c.volume === "number");
        return slice.length ? slice.reduce((sum, c) => sum + (c.volume || 0), 0) / slice.length : null;
      }
      function isVolumeOk(candles, index, config) {
        if (!config.volumeFilter.enabled) return true;
        const volume = candles[index]?.volume;
        if (typeof volume !== "number") return true;
        const avg = averageVolume(candles, index, config.volumeFilter.lookback);
        return !avg || avg <= 0 ? true : volume >= avg * config.volumeFilter.multiplier;
      }
      function detectBullishPattern(prev, current, region, config) {
        if (region.side !== "lower") return null;
        if (config.rejection.allowFailedBreakout && isBullishFailedBreakout(current, region, config)) return "failedBreakout";
        if (config.rejection.allowPinBar && isBullishRejectionAtLowerRegion(current, region, config)) return "pinBar";
        if (prev && config.rejection.allowEngulfing && isBullishEngulfingAtLowerRegion(prev, current, region)) return "engulfing";
        if (prev && config.rejection.allowCloseBackInside && isBullishCloseBackInside(prev, current, region)) return "closeBackInside";
        if (config.rejection.allowImpulseReversal && isBullishImpulseReversal(current, region)) return "impulseReversal";
        return null;
      }
      function detectBearishPattern(prev, current, region, config) {
        if (region.side !== "upper") return null;
        if (config.rejection.allowFailedBreakout && isBearishFailedBreakout(current, region, config)) return "failedBreakout";
        if (config.rejection.allowPinBar && isBearishRejectionAtUpperRegion(current, region, config)) return "pinBar";
        if (prev && config.rejection.allowEngulfing && isBearishEngulfingAtUpperRegion(prev, current, region)) return "engulfing";
        if (prev && config.rejection.allowCloseBackInside && isBearishCloseBackInside(prev, current, region)) return "closeBackInside";
        if (config.rejection.allowImpulseReversal && isBearishImpulseReversal(current, region)) return "impulseReversal";
        return null;
      }
      function calculateSignalScore({ sigmaDistance, bandMultiplier, pattern, volumeOk, source, touchedRegion }) {
        let score = 40;
        const absSigma = Math.abs(sigmaDistance || bandMultiplier || 0);
        if (absSigma >= 1.5) score += 10;
        if (absSigma >= 2) score += 20;
        if (absSigma >= 3) score += 30;
        if (pattern === "failedBreakout" || pattern === "pinBar") score += 15;
        if (pattern === "engulfing" || pattern === "impulseReversal") score += 20;
        if (pattern === "closeBackInside") score += 10;
        if (volumeOk) score += 10;
        if (source === "GARCH") score += 5;
        if (touchedRegion) score += 5;
        return Math.min(100, score);
      }
      function classifySignalStrength(score) {
        return score >= 75 ? "strong" : score >= 50 ? "moderate" : "weak";
      }
      function generateSignals(candles, indicators) {
        const cfg = state.signalConfig;
        const engine = cfg.signalEngine;
        if (!cfg.enabled || !engine.enabled || candles.length < 2) return [];
        const regions = createBandRegions(collectVolatilityBands(indicators), engine, null, null);
        const signals = [];
        let lastSignalIndex = null;
        for (let i = 1; i < candles.length; i += 1) {
          if (engine.cooldown.enabled && lastSignalIndex !== null && i - lastSignalIndex < engine.cooldown.bars) continue;
          const prev = candles[i - 1];
          const current = candles[i];
          const volumeOk = isVolumeOk(candles, i, engine);
          if (!volumeOk && engine.volumeFilter.enabled) continue;
          const touched = regions.filter((region) => candleTouchesBandRegion(current, region));
          for (const region of touched) {
            let direction = null, pattern = null;
            if (region.side === "lower" && engine.signalSide.buy) { pattern = detectBullishPattern(prev, current, region, engine); if (pattern) direction = "buy"; }
            if (region.side === "upper" && engine.signalSide.sell) { pattern = detectBearishPattern(prev, current, region, engine); if (pattern) direction = "sell"; }
            if (!direction || !pattern) continue;
            const sigmaDistance = region.side === "upper" ? region.multiplier : -region.multiplier;
            const score = calculateSignalScore({ sigmaDistance, bandMultiplier:region.multiplier, pattern, volumeOk, source:region.source, touchedRegion:true });
            if (score < cfg.minScore) continue;
            signals.push({
              time:current.time,
              type:direction === "buy" ? "VOL_BUY" : "VOL_SELL",
              direction,
              price:current.close,
              score,
              strength:classifySignalStrength(score),
              regionLabel:region.label,
              zoneSource:region.source,
              sigmaDistance,
              pattern,
              reason:direction === "buy" ? `Compra em regiao inferior ${region.label}. Padrao: ${pattern}.` : `Venda em regiao superior ${region.label}. Padrao: ${pattern}.`,
            });
            lastSignalIndex = i;
            break;
          }
        }
        return signals;
      }
      function buildSignalMarkers(signals) {
        return (signals || []).map((signal) => ({
          time:signal.time,
          position:signal.direction === "buy" ? "belowBar" : "aboveBar",
          shape:signal.direction === "buy" ? "arrowUp" : "arrowDown",
          color:signal.direction === "buy" ? "#22c55e" : "#ef4444",
          text:`${signal.direction === "buy" ? "BUY" : "SELL"} ${signal.score}`,
        }));
      }
      function computeIndicators(candles) {
        const vwapDay = computeVWAP(candles, "day");
        const vwapWeek = computeVWAP(candles, "week");
        const vwapMonth = computeVWAP(candles, "month");
        const volumeStats = computeVolumeStats(candles, state.signalConfig.volume.lookback || 20);
        const ma = state.ma.filter((m) => m.enabled).map((m) => ({ ...m, data:computeMA(candles, m.period, state.maType) }));
        const signalMAs = computeSignalMAs(candles);
        const stdevBands = vwapStdevMultipliers.map((multiplier) => ({ multiplier, data:computeStdevBands(candles, vwapDay, multiplier) }));
        const weekVolBands = vwapStdevMultipliers.map((multiplier) => ({ multiplier, data:computeStdevBands(candles, vwapWeek, multiplier, "week") }));
        const refs = sessionRefs(candles);
        const volumeProfile = computeSessionVolumeProfile(candles);
        const weisWave = computeWeisWaveVolume(candles, 0.2);
        const garch = calculateGarchOverlay(candles, state.dailyCandles, refs, vwapDay);
        const hv252 = calculateHistoricalVolatility(state.dailyCandles, 252);
        const indicators = { vwapDay, vwapWeek, vwapMonth, volumeStats, ma, signalMAs, stdevBands, weekVolBands, refs, volumeProfile, weisWave, garch, hv252 };
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
      function candleVolumeStyle(c, rvol) {
        const up = c.close >= c.open;
        if (Number.isFinite(rvol) && rvol >= 2) {
          return { color:"#f59e0b", borderColor:"#fde68a", wickColor:"#fde68a" };
        }
        if (Number.isFinite(rvol) && rvol >= 1.5) {
          return up
            ? { color:"#00e676", borderColor:"#a7f3d0", wickColor:"#a7f3d0" }
            : { color:"#ff1744", borderColor:"#fecdd3", wickColor:"#fecdd3" };
        }
        if (Number.isFinite(rvol) && rvol >= 1.2) {
          return up
            ? { color:"#00c087", borderColor:"#34d399", wickColor:"#34d399" }
            : { color:"#ff4b4b", borderColor:"#fb7185", wickColor:"#fb7185" };
        }
        return up
          ? { color:"#00a878", borderColor:"#00a878", wickColor:"#00a878" }
          : { color:"#d63d3d", borderColor:"#d63d3d", wickColor:"#d63d3d" };
      }
      function candleWithVolumeColor(c, i) {
        const rvol = state.indicators?.volumeStats?.[i]?.rvol;
        return { ...c, ...candleVolumeStyle(c, rvol) };
      }
      function addPriceLine(series, title, price, color, style=2, width=1) {
        if (!Number.isFinite(price)) return;
        const line = series.createPriceLine({ price, color, lineWidth:width, lineStyle:style, axisLabelVisible:true, title });
        state.priceLines.push(line);
      }
      function volatilityBandKey(source, multiplier) {
        return `volband_${source}_${String(multiplier).replace("-", "m").replace(".", "_")}`;
      }
      function renderVolatilityBands(candleSeries) {
        if (!state.toggles.volatilityBands) return;
        const garch = state.indicators.garch || {};
        const hv = state.indicators.hv252 || {};
        if (garch.ok) {
          const allowedGarch = new Set([0, 0.5, 1, 1.5, 2, 3, -0.5, -1, -1.5, -2, -3]);
          garch.zones.filter((zone) => allowedGarch.has(zone.multiplier)).forEach((zone) => {
            const abs = Math.abs(zone.multiplier);
            const key = volatilityBandKey("garch", zone.multiplier);
            const color = zone.side === "upper"
              ? (abs >= 3 ? "#7f1d1d" : abs >= 2 ? "#ef4444" : "#fca5a5")
              : zone.side === "lower"
                ? (abs >= 3 ? "#14532d" : abs >= 2 ? "#22c55e" : "#86efac")
                : "#facc15";
            const width = abs >= 2 ? 2 : 1;
            const label = zone.multiplier === 0 ? "BV REF" : `BV ${zone.label}`;
            addLine(key, horizontalSessionLine(state.candles, zone.level), color, width);
            addPriceLine(candleSeries, label, zone.level, color, zone.multiplier === 0 ? 0 : 2, width);
          });
        }
        if (intradayTimeframes.includes(state.timeframe) && hv.ok) {
          const hvColors = { 1:"#3b82f6", 2:"#06b6d4", 3:"#0e7490" };
          hv.levels.filter((level) => [1,2,3,-1,-2,-3].includes(level.multiplier)).forEach((level) => {
            const abs = Math.abs(level.multiplier);
            const key = volatilityBandKey("hv252", level.multiplier);
            const color = hvColors[abs] || "#3b82f6";
            const width = abs >= 2 ? 2 : 1;
            addLine(key, horizontalSessionLine(state.candles, level.price), color, width);
            addPriceLine(candleSeries, `BV ${level.label}`, level.price, color, 2, width);
          });
        }
        const engine = state.signalConfig.signalEngine;
        if (engine?.enabled && engine.visual?.plotRegionLines) {
          createBandRegions(collectVolatilityBands(state.indicators), engine, null, null).forEach((region) => {
            const softColor = region.side === "upper" ? "#fca5a5" : "#86efac";
            addPriceLine(candleSeries, `${region.label} reg sup`, region.upperBound, softColor, 3, 1);
            addPriceLine(candleSeries, `${region.label} reg inf`, region.lowerBound, softColor, 3, 1);
          });
        }
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
        const chartHeight = chartEl.clientHeight || 1320;
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
        state.chart = makeChart(chartEl, chartEl.clientHeight || 1320);
        state.indicators = computeIndicators(state.candles);
        const candleSeries = state.chart.addSeries(CandlestickSeries, { upColor:"#00a878", downColor:"#d63d3d", borderVisible:true, wickUpColor:"#00a878", wickDownColor:"#d63d3d" });
        candleSeries.setData(state.candles.map((c, i) => candleWithVolumeColor(c, i))); state.series.candle = candleSeries;
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
        if (state.toggles.weisWave) {
          const weisSeries = state.chart.addSeries(HistogramSeries, { priceFormat:{ type:"volume" }, priceScaleId:"weis", color:"#14b8a6" });
          weisSeries.priceScale().applyOptions({ scaleMargins:{ top:0.72, bottom:0 } });
          weisSeries.setData((state.indicators.weisWave?.points || []).map((p) => ({
            time:p.time,
            value:p.value,
            color:p.direction >= 0 ? "rgba(20,184,166,.62)" : "rgba(244,63,94,.62)",
          })));
          state.series.weisWave = weisSeries;
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
        renderVolatilityBands(candleSeries);
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
        renderAlerts(last, lastVwap, lastVol.rvol, indicators.signals);
      }
      function renderAlerts(last, vwap, rvol, signals) {
        const box = document.getElementById("lw-alerts");
        box.innerHTML = "";
        const alerts = [];
        if (last && vwap) {
          const dist = (last.close - vwap) / vwap;
          if (dist >= .01) alerts.push(["PreÃ§o em banda +1%", "hot"]);
          if (dist <= -.01) alerts.push(["PreÃ§o em banda -1%", "hot"]);
        }
        if (Number.isFinite(rvol) && rvol >= 2) alerts.push(["Volume relativo extremo", "hot"]);
        else if (Number.isFinite(rvol) && rvol >= 1.5) alerts.push(["Volume relativo alto", "hot"]);
        const recent = (signals || []).filter((s) => last && s.time >= last.time - (tfSeconds[state.timeframe] || 60) * 3);
          const buySignal = recent.find((s) => s.direction === "buy");
          const sellSignal = recent.find((s) => s.direction === "sell");
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
              <div style="color:#f8fafc; font-weight:900;">${escapeHtml(signal.type)} | Score ${signal.score} | ${escapeHtml(signal.strength || "")}</div>
              <div><span>Entrada</span> ${fmt(signal.price,2)} | <span>Regiao</span> ${escapeHtml(signal.regionLabel || "---")}</div>
              <div><span>Fonte</span> ${escapeHtml(signal.zoneSource || "---")} | <span>Sigma</span> ${Number.isFinite(signal.sigmaDistance) ? signal.sigmaDistance.toFixed(2) : "---"}</div>
              <div><span>Padrao</span> ${escapeHtml(signal.pattern || "---")} | <span>Direcao</span> ${escapeHtml(signal.direction || "---")}</div>
              <div style="color:#cbd5e1; margin-top:3px;">${escapeHtml(signal.reason || "")}</div>
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
          ? `${signal.type} score ${signal.score} | ${signal.regionLabel || "---"} | ${signal.pattern || "---"}`
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
          state.series.candle.update(candleWithVolumeColor(lastQuick, state.candles.length - 1));
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
        state.series.candle.update(candleWithVolumeColor(last, state.candles.length - 1));
        if (state.series.volume) {
          const i = state.candles.length - 1;
          const rvol = state.indicators.volumeStats[i]?.rvol;
          const base = last.close >= last.open ? "0,192,135" : "255,75,75";
          const color = rvol >= 2 ? "rgba(245,158,11,.78)" : rvol >= 1.5 ? `rgba(${base},.75)` : `rgba(${base},.32)`;
          state.series.volume.update({ time:last.time, value:last.volume, color });
        }
        if (state.series.vol20) state.series.vol20.setData(state.indicators.volumeStats.filter((v) => Number.isFinite(v.avg)).map((v) => ({ time:v.time, value:v.avg })));
        if (state.series.weisWave) {
          state.series.weisWave.setData((state.indicators.weisWave?.points || []).map((p) => ({
            time:p.time,
            value:p.value,
            color:p.direction >= 0 ? "rgba(20,184,166,.62)" : "rgba(244,63,94,.62)",
          })));
        }
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
            const key = volatilityBandKey("hv252", level.multiplier);
            state.series[key]?.setData(horizontalSessionLine(state.candles, level.price));
          });
        }
        if (state.indicators.garch?.ok) {
          state.indicators.garch.zones.forEach((zone) => {
            const key = volatilityBandKey("garch", zone.multiplier);
            state.series[key]?.setData(horizontalSessionLine(state.candles, zone.level));
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
          const loadedSeries = asset.source === "fred" ? fredPayload.series?.[state.symbol] : asset.source === "bcb" ? bcbPayload.series?.[state.symbol] : yahooPayload.series?.[state.symbol];
          const sourceName = loadedSeries?.sourceLabel || (asset.source === "fred" ? "FRED" : asset.source === "bcb" ? "BCB SGS" : "yfinance");
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
        state.timeframe = ["fred", "bcb"].includes(nextAsset.source) && intradayTimeframes.includes(timeframe) ? "1d" : timeframe;
        renderControls();
        savePrefs();
        const asset = nextAsset;
        setLoading(true);
        if (asset.source === "yahoo" && state.timeframe === "30s") {
          setStatus(`${asset.label}: yfinance nao possui 30s; usando candles de 1m.`);
        } else if (asset.source === "fred" && state.timeframe !== timeframe) {
          setStatus(`${asset.label}: FRED entrega serie diaria. Ajustei automaticamente para 1d.`);
        } else if (asset.source === "bcb" && state.timeframe !== timeframe) {
          setStatus(`${asset.label}: BCB entrega serie diaria. Ajustei automaticamente para 1d.`);
        } else {
          const sourceName = asset.source === "yahoo" ? "yfinance" : asset.source === "fred" ? "FRED" : asset.source === "bcb" ? "BCB SGS" : "Binance";
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
        .replace("__BCB_PAYLOAD__", bcb_json)
        .replace("__FRED_PAYLOAD__", fred_json)
        .replace("__SIGNAL_MODE__", signal_mode_json)
        .replace("__CHART_TITLE__", chart_title_json)
        .replace("__INSTANCE_ID__", instance_id_json)
    )
