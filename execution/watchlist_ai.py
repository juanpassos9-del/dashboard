"""Deterministic Watchlist IA TTS for swing and position radar.

This first version avoids external LLM calls. It builds a structured radar from
yfinance prices plus the dashboard macro snapshot, keeping Brazil stocks and US
sector ETFs separated.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


BRAZIL_ASSETS = {
    "VALE3": {"ticker": "VALE3.SA", "sector": "Mineracao", "driver": "minerio, China, dolar, ciclo industrial"},
    "PETR4": {"ticker": "PETR4.SA", "sector": "Petroleo", "driver": "petroleo, dividendos, risco estatal"},
    "PRIO3": {"ticker": "PRIO3.SA", "sector": "Petroleo", "driver": "petroleo, crescimento, execucao operacional"},
    "ITUB4": {"ticker": "ITUB4.SA", "sector": "Bancos", "driver": "juros, credito, inadimplencia, curva DI"},
    "BBDC4": {"ticker": "BBDC4.SA", "sector": "Bancos", "driver": "juros, credito, inadimplencia, curva DI"},
    "BBAS3": {"ticker": "BBAS3.SA", "sector": "Bancos", "driver": "juros, credito, inadimplencia, curva DI"},
    "WEGE3": {"ticker": "WEGE3.SA", "sector": "Industria global", "driver": "dolar, industria global, valuation"},
    "POMO4": {"ticker": "POMO4.SA", "sector": "Industria", "driver": "ciclo industrial, exportacao, juros"},
    "CMIG4": {"ticker": "CMIG4.SA", "sector": "Eletricas", "driver": "juros, dividendos, regulacao"},
    "KLBN11": {"ticker": "KLBN11.SA", "sector": "Papel e celulose", "driver": "celulose, dolar, China"},
    "SUZB3": {"ticker": "SUZB3.SA", "sector": "Papel e celulose", "driver": "celulose, dolar, China"},
    "RENT3": {"ticker": "RENT3.SA", "sector": "Consumo", "driver": "juros Brasil, consumo, credito"},
    "LREN3": {"ticker": "LREN3.SA", "sector": "Varejo", "driver": "juros Brasil, consumo, credito"},
    "ABEV3": {"ticker": "ABEV3.SA", "sector": "Consumo defensivo", "driver": "consumo defensivo, margem, baixa volatilidade"},
    "B3SA3": {"ticker": "B3SA3.SA", "sector": "Financeiro/bolsa", "driver": "volume financeiro, bolsa, juros"},
    "ELET3": {"ticker": "ELET3.SA", "sector": "Eletricas", "driver": "juros, dividendos, regulacao"},
}

US_SECTOR_ETFS = {
    "XLE": {"ticker": "XLE", "sector": "Energy", "driver": "petroleo, inflacao, commodities, energia"},
    "XLK": {"ticker": "XLK", "sector": "Technology", "driver": "US10Y, juros reais, Nasdaq, liquidez, crescimento"},
    "XLP": {"ticker": "XLP", "sector": "Consumer Staples", "driver": "defesa, recessao, volatilidade, consumo basico"},
    "XLB": {"ticker": "XLB", "sector": "Materials", "driver": "commodities, China, dolar, ciclo industrial"},
    "XLI": {"ticker": "XLI", "sector": "Industrials", "driver": "crescimento, PMIs, infraestrutura, ciclo economico"},
}

CRYPTO_ASSETS = {
    "BTC": {"ticker": "BTC-USD", "sector": "Crypto major", "driver": "liquidez global, DXY, Nasdaq, apetite por risco"},
    "ETH": {"ticker": "ETH-USD", "sector": "Crypto beta", "driver": "liquidez, tecnologia, fluxo em altcoins"},
    "SOL": {"ticker": "SOL-USD", "sector": "Crypto beta", "driver": "beta cripto, fluxo de risco, momentum"},
    "BNB": {"ticker": "BNB-USD", "sector": "Crypto exchange", "driver": "cripto beta, fluxo em exchanges"},
    "LINK": {"ticker": "LINK-USD", "sector": "Crypto infra", "driver": "infra cripto, altseason, apetite por risco"},
}

FX_ASSETS = {
    "EURUSD": {"ticker": "EURUSD=X", "sector": "G10 FX", "driver": "diferencial de juros EUA/Europa, DXY, BCE/Fed"},
    "GBPUSD": {"ticker": "GBPUSD=X", "sector": "G10 FX", "driver": "BoE, DXY, apetite por risco"},
    "USDJPY": {"ticker": "JPY=X", "sector": "Carry FX", "driver": "US10Y, BoJ, diferencial de juros, carry trade"},
    "USDBRL": {"ticker": "BRL=X", "sector": "Emerging FX", "driver": "DXY, fiscal Brasil, commodities, fluxo estrangeiro"},
    "AUDUSD": {"ticker": "AUDUSD=X", "sector": "Commodity FX", "driver": "China, commodities, DXY, risco global"},
    "USDCAD": {"ticker": "CAD=X", "sector": "Commodity FX", "driver": "petroleo, BoC, DXY"},
}

COMMODITY_ASSETS = {
    "WTI": {"ticker": "CL=F", "sector": "Energia", "driver": "estoques, OPEP, geopolitica, crescimento global"},
    "BRENT": {"ticker": "BZ=F", "sector": "Energia", "driver": "petroleo global, geopolitica, oferta/demanda"},
    "NATGAS": {"ticker": "NG=F", "sector": "Energia", "driver": "clima, estoques, demanda industrial"},
    "CORN": {"ticker": "ZC=F", "sector": "Graos", "driver": "clima, safra, dolar, demanda global"},
    "SOYBEAN": {"ticker": "ZS=F", "sector": "Graos", "driver": "China, clima, safra EUA/Brasil"},
    "WHEAT": {"ticker": "ZW=F", "sector": "Graos", "driver": "clima, Mar Negro, oferta global"},
}

METAL_ASSETS = {
    "GOLD": {"ticker": "GC=F", "sector": "Metal precioso", "driver": "juros reais, DXY, risco geopolitico, inflacao"},
    "SILVER": {"ticker": "SI=F", "sector": "Metal precioso/industrial", "driver": "ouro, demanda industrial, DXY"},
    "COPPER": {"ticker": "HG=F", "sector": "Metal industrial", "driver": "China, ciclo industrial, dolar"},
    "PLATINUM": {"ticker": "PL=F", "sector": "Metal precioso/industrial", "driver": "industria, automotivo, dolar"},
    "PALLADIUM": {"ticker": "PA=F", "sector": "Metal industrial", "driver": "automotivo, oferta, ciclo industrial"},
}

ASSET_GROUPS = {
    "Brasil": {"assets": BRAZIL_ASSETS, "benchmarks": ["BOVA11.SA", "^BVSP"], "label": "Brasil Acoes", "class": "Acao"},
    "EUA": {"assets": US_SECTOR_ETFS, "benchmarks": ["SPY"], "label": "EUA ETFs Setoriais", "class": "ETF Setorial"},
    "Cripto": {"assets": CRYPTO_ASSETS, "benchmarks": ["BTC-USD"], "label": "Cripto", "class": "Cripto"},
    "Moedas": {"assets": FX_ASSETS, "benchmarks": ["DX-Y.NYB"], "label": "Moedas Forex", "class": "Moeda"},
    "Commodities": {"assets": COMMODITY_ASSETS, "benchmarks": ["DBC"], "label": "Commodities", "class": "Commodity"},
    "Metais": {"assets": METAL_ASSETS, "benchmarks": ["GC=F"], "label": "Metais", "class": "Metal"},
}

WATCHLIST_RESULTS_PATH = Path(".tmp") / "watchlist_results.json"
WATCHLIST_PAYLOAD_PATH = Path(".tmp") / "watchlist_payload.json"


@dataclass
class AssetSnapshot:
    symbol: str
    ticker: str
    block: str
    sector: str
    driver: str
    price: float
    trend_score: float
    relative_score: float
    volatility_score: float
    momentum_20d: float
    momentum_60d: float
    relative_60d: float
    annual_vol: float
    atr14: float
    ma20: float
    ma50: float
    ma200: float
    avg_volume_20d: float
    source: str = "historico"


def _safe_float(value, default=0.0) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def _download_prices(tickers: list[str]) -> pd.DataFrame:
    unique = sorted(set(tickers))
    frames: dict[str, pd.DataFrame] = {}
    chunk_size = 5
    for start in range(0, len(unique), chunk_size):
        chunk = unique[start:start + chunk_size]
        data = pd.DataFrame()
        for attempt in range(2):
            try:
                data = yf.download(
                    chunk,
                    period="1y",
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    auto_adjust=False,
                    threads=False,
                    timeout=15,
                )
                if data is not None and not data.empty:
                    break
            except Exception:
                time.sleep(1 + attempt)
        if data is None or data.empty:
            continue
        for ticker in chunk:
            df = _ticker_frame(data, ticker)
            if not df.empty:
                frames[ticker] = df
        time.sleep(0.4)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def _ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker not in set(data.columns.get_level_values(0)):
                return pd.DataFrame()
            df = data[ticker].copy()
        else:
            df = data.copy()
        df = df.dropna(subset=["Close"])
        return df
    except Exception:
        return pd.DataFrame()


def _series_return(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    prev = _safe_float(close.iloc[-periods - 1], 0.0)
    last = _safe_float(close.iloc[-1], 0.0)
    return ((last / prev) - 1) * 100 if prev > 0 else 0.0


def _atr14(df: pd.DataFrame) -> float:
    if len(df) < 15:
        return 0.0
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return _safe_float(tr.rolling(14).mean().iloc[-1], 0.0)


def _extract_change(global_data: dict | None, aliases: list[str]) -> float | None:
    if not global_data:
        return None
    categories = global_data.get("categories", global_data)
    for assets in categories.values():
        if not isinstance(assets, list):
            continue
        for item in assets:
            name = str(item.get("name", "")).lower()
            if any(alias.lower() in name for alias in aliases):
                return _safe_float(item.get("change"), None)
    return None


def _macro_regime(global_data: dict | None) -> dict[str, Any]:
    spx = _extract_change(global_data, ["S&P 500", "SPY"])
    nasdaq = _extract_change(global_data, ["NASDAQ"])
    vix = _extract_change(global_data, ["VIX"])
    dxy = _extract_change(global_data, ["DXY"])
    ewz = _extract_change(global_data, ["EWZ"])
    ibov = _extract_change(global_data, ["IBOV"])
    score = 0
    for value in [spx, nasdaq, ewz, ibov]:
        if value is not None:
            score += 1 if value > 0.25 else -1 if value < -0.25 else 0
    if vix is not None:
        score += 1 if vix < -1 else -1 if vix > 1 else 0
    if dxy is not None:
        score += 1 if dxy < -0.15 else -1 if dxy > 0.15 else 0
    if score >= 3:
        regime = "Risk-on forte"
    elif score >= 1:
        regime = "Risk-on moderado"
    elif score <= -3:
        regime = "Risk-off forte"
    elif score <= -1:
        regime = "Risk-off moderado"
    else:
        regime = "Neutro/seletivo"
    return {"regime": regime, "score": score, "spx": spx, "nasdaq": nasdaq, "vix": vix, "dxy": dxy, "ewz": ewz, "ibov": ibov}


def _regime_component(block: str, sector: str, regime: str) -> float:
    sector_l = sector.lower()
    risk_sensitive = block in {"Cripto", "Commodities", "Metais"}
    if regime == "Risk-on forte":
        if block == "Brasil":
            return 85 if any(x in sector_l for x in ["mineracao", "petroleo", "bancos", "industria"]) else 65
        if block == "Cripto":
            return 82
        if block == "Moedas":
            return 72 if "commodity" in sector_l or "emerging" in sector_l else 55
        if block == "Commodities":
            return 75
        if block == "Metais":
            return 76 if "industrial" in sector_l else 58
        return 85 if sector in {"Technology", "Industrials", "Materials"} else 60
    if regime == "Risk-on moderado":
        if block == "Brasil":
            return 75 if any(x in sector_l for x in ["bancos", "papel", "mineracao"]) else 60
        if block == "Cripto":
            return 72
        if block == "Moedas":
            return 68 if "commodity" in sector_l or "emerging" in sector_l else 55
        if risk_sensitive:
            return 66
        return 75 if sector in {"Technology", "Industrials"} else 58
    if regime == "Risk-off moderado":
        if block == "Brasil":
            return 72 if any(x in sector_l for x in ["eletricas", "defensivo"]) else 45
        if block == "Cripto":
            return 35
        if block == "Moedas":
            return 70 if "g10" in sector_l or "carry" in sector_l else 42
        if block == "Commodities":
            return 48
        if block == "Metais":
            return 70 if "precioso" in sector_l else 45
        return 78 if sector == "Consumer Staples" else 45
    if regime == "Risk-off forte":
        if block == "Brasil":
            return 62 if any(x in sector_l for x in ["eletricas", "defensivo"]) else 30
        if block == "Cripto":
            return 25
        if block == "Moedas":
            return 68 if "g10" in sector_l or "carry" in sector_l else 35
        if block == "Commodities":
            return 35
        if block == "Metais":
            return 78 if "precioso" in sector_l else 35
        return 70 if sector == "Consumer Staples" else 30
    return 55


def _build_snapshot(symbol: str, meta: dict, block: str, data: pd.DataFrame, benchmark_close: pd.Series) -> AssetSnapshot | None:
    df = _ticker_frame(data, meta["ticker"])
    if df.empty or len(df) < 70:
        return None
    close = df["Close"].astype(float)
    price = _safe_float(close.iloc[-1])
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1])
    ma50 = _safe_float(close.rolling(50).mean().iloc[-1])
    ma200 = _safe_float(close.rolling(200).mean().iloc[-1], ma50)
    mom20 = _series_return(close, 20)
    mom60 = _series_return(close, 60)
    bench60 = _series_return(benchmark_close, 60) if benchmark_close is not None and not benchmark_close.empty else 0.0
    rel60 = mom60 - bench60
    ret = close.pct_change().dropna()
    annual_vol = _safe_float(ret.tail(63).std() * math.sqrt(252) * 100, 0.0)
    trend = 35
    trend += 20 if price > ma20 else -8
    trend += 20 if ma20 > ma50 else -6
    trend += 15 if ma50 > ma200 else -5
    trend += max(-10, min(10, mom20 / 2))
    relative = max(0, min(100, 50 + rel60 * 2))
    vol_score = max(20, min(85, 85 - annual_vol))
    volume = _safe_float(df.get("Volume", pd.Series(dtype=float)).tail(20).mean(), 0.0)
    return AssetSnapshot(
        symbol=symbol, ticker=meta["ticker"], block=block, sector=meta["sector"], driver=meta["driver"],
        price=price, trend_score=max(0, min(100, trend)), relative_score=relative, volatility_score=vol_score,
        momentum_20d=mom20, momentum_60d=mom60, relative_60d=rel60, annual_vol=annual_vol,
        atr14=_atr14(df), ma20=ma20, ma50=ma50, ma200=ma200, avg_volume_20d=volume,
    )


def _flatten_global_assets(global_data: dict | None) -> list[dict[str, Any]]:
    if not global_data:
        return []
    categories = global_data.get("categories", global_data)
    rows: list[dict[str, Any]] = []
    if not isinstance(categories, dict):
        return rows
    for assets in categories.values():
        if not isinstance(assets, list):
            continue
        for item in assets:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _global_asset_map(global_data: dict | None) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in _flatten_global_assets(global_data):
        for key in [item.get("symbol"), item.get("name")]:
            if key:
                mapped[str(key).upper()] = item
    return mapped


def _quick_snapshot_from_dashboard(
    symbol: str,
    meta: dict,
    block: str,
    item: dict[str, Any],
    benchmark_change: float = 0.0,
) -> AssetSnapshot | None:
    price = _safe_float(item.get("price"), 0.0)
    if price <= 0:
        return None
    change = _safe_float(item.get("change"), 0.0)
    high = _safe_float(item.get("high"), price)
    low = _safe_float(item.get("low"), price)
    day_range = max(abs(high - low), price * 0.01)
    rel = change - benchmark_change
    trend = max(0, min(100, 52 + change * 6 + rel * 2))
    relative = max(0, min(100, 50 + rel * 6))
    annual_vol_defaults = {
        "Cripto": 72,
        "Moedas": 13,
        "Commodities": 36,
        "Metais": 28,
        "Brasil": 32,
        "EUA": 22,
    }
    annual_vol = annual_vol_defaults.get(block, 30)
    vol_score = max(20, min(85, 85 - annual_vol * 0.55))
    synthetic_ma20 = price / (1 + change / 100) if abs(change) < 45 else price
    return AssetSnapshot(
        symbol=symbol,
        ticker=meta["ticker"],
        block=block,
        sector=meta["sector"],
        driver=meta["driver"],
        price=price,
        trend_score=trend,
        relative_score=relative,
        volatility_score=vol_score,
        momentum_20d=change,
        momentum_60d=rel,
        relative_60d=rel,
        annual_vol=annual_vol,
        atr14=day_range,
        ma20=synthetic_ma20,
        ma50=synthetic_ma20,
        ma200=synthetic_ma20,
        avg_volume_20d=0.0,
        source="dashboard",
    )


def _score_snapshot(s: AssetSnapshot, macro: dict, style: str) -> float:
    regime = _regime_component(s.block, s.sector, macro["regime"])
    if s.block == "Brasil":
        score = regime * 0.25 + s.trend_score * 0.20 + s.relative_score * 0.15 + 58 * 0.15 + 50 * 0.10 + s.volatility_score * 0.10 + 50 * 0.05
    elif s.block == "EUA":
        score = regime * 0.25 + s.relative_score * 0.20 + s.trend_score * 0.15 + 58 * 0.15 + s.volatility_score * 0.10 + 52 * 0.10 + 50 * 0.05
    elif s.block == "Cripto":
        score = regime * 0.30 + s.trend_score * 0.24 + s.relative_score * 0.18 + s.volatility_score * 0.08 + 55 * 0.12 + 50 * 0.08
    elif s.block == "Moedas":
        score = regime * 0.18 + s.trend_score * 0.25 + s.relative_score * 0.18 + s.volatility_score * 0.16 + 58 * 0.13 + 50 * 0.10
    elif s.block == "Commodities":
        score = regime * 0.22 + s.trend_score * 0.24 + s.relative_score * 0.16 + s.volatility_score * 0.10 + 60 * 0.18 + 50 * 0.10
    else:
        score = regime * 0.24 + s.trend_score * 0.22 + s.relative_score * 0.16 + s.volatility_score * 0.12 + 62 * 0.16 + 50 * 0.10
    if style == "Position":
        score = score * 0.72 + s.trend_score * 0.18 + regime * 0.10
    return max(0, min(100, score))


def _recommendation(s: AssetSnapshot, macro: dict, style: str) -> dict[str, Any]:
    score = _score_snapshot(s, macro, style)
    atr = s.atr14 if s.atr14 > 0 else max(s.price * 0.025, 0.01)
    stop_mult = 1.8 if style == "Swing" else 2.8
    target_mults = (1.4, 2.4, 3.6) if style == "Swing" else (2.0, 3.5, 5.0)
    entry_ideal = min(s.price, s.ma20) if s.ma20 > 0 else s.price * 0.99
    loss = entry_ideal - atr * stop_mult
    gain1 = entry_ideal + atr * target_mults[0]
    gain2 = entry_ideal + atr * target_mults[1]
    gain_final = entry_ideal + atr * target_mults[2]
    rr = (gain2 - entry_ideal) / max(entry_ideal - loss, 0.01)
    if score >= 72 and s.price <= gain1:
        action = "comprar"
        status = "ativo"
    elif score >= 62:
        action = "aguardar entrada"
        status = "watch"
    elif score >= 52:
        action = "manter radar"
        status = "neutro"
    else:
        action = "evitar/reduzir"
        status = "fraco"
    position = "1.0x" if score >= 75 else "0.5x" if score >= 62 else "0.25x"
    group = ASSET_GROUPS.get(s.block, {})
    block_label = group.get("label", s.block)
    asset_class = group.get("class", s.block)
    carteira = f"Carteira {style} {block_label}"
    source_label = "historico yfinance" if s.source == "historico" else "radar rapido dashboard"
    return {
        "bloco": block_label,
        "ativo": s.symbol,
        "classe": asset_class,
        "setor": s.sector,
        "tipo": style,
        "direcao": "compra",
        "score_inicial": round(score, 1),
        "score_atual": round(score, 1),
        "preco_atual": round(s.price, 2),
        "entrada": round(entry_ideal, 2),
        "entrada_ideal": round(entry_ideal, 2),
        "entrada_executada": None,
        "gain_1": round(gain1, 2),
        "gain_2": round(gain2, 2),
        "gain_final": round(gain_final, 2),
        "loss": round(loss, 2),
        "risco_retorno": round(rr, 2),
        "horizonte": "2 a 15 dias" if style == "Swing" else "1 a 6 meses",
        "tamanho_sugerido": position,
        "tese_principal": f"{s.symbol} depende de {s.driver}. Score combina regime {macro['regime']}, tendencia e forca relativa.",
        "confirmacoes": "Preco respeitar entrada/invalidação, forca relativa positiva e regime macro sem deterioracao.",
        "riscos": "Deterioracao do regime, gap de noticia, alta de volatilidade ou perda do suporte tecnico.",
        "status": status,
        "carteira": carteira,
        "resultado": "sem posicao executada",
        "acao": action,
        "momento_20d": round(s.momentum_20d, 2),
        "forca_relativa_60d": round(s.relative_60d, 2),
        "volatilidade_anual": round(s.annual_vol, 2),
        "driver": s.driver,
        "fonte_sinal": s.source,
        "fonte_descricao": source_label,
    }


def _commentary(recs: list[dict[str, Any]], block: str, macro: dict) -> str:
    label = ASSET_GROUPS.get(block, {}).get("label", block)
    subset = [r for r in recs if r["bloco"].startswith(label)]
    top = []
    seen = set()
    for item in sorted(subset, key=lambda r: r["score_atual"], reverse=True):
        if item["ativo"] in seen:
            continue
        seen.add(item["ativo"])
        top.append(item)
        if len(top) >= 3:
            break
    if not top:
        return f"Radar {block} sem dados suficientes no momento."
    names = ", ".join(r["ativo"] for r in top)
    if block == "Brasil":
        return f"Radar Brasil em regime {macro['regime']}. Destaques: {names}. A leitura favorece nomes com melhor tendencia e forca relativa contra Ibovespa; risco principal vem de DXY/juros locais e commodities."
    if block == "EUA":
        return f"Rotacao setorial EUA em regime {macro['regime']}. Destaques: {names}. A leitura compara cada setor contra SPY; risco principal vem de US10Y, DXY, VIX e mudanca de apetite por risco."
    if block == "Cripto":
        return f"Radar Cripto em regime {macro['regime']}. Destaques: {names}. Prioriza tendencia, forca contra BTC e sensibilidade a liquidez, Nasdaq e DXY."
    if block == "Moedas":
        return f"Radar Moedas em regime {macro['regime']}. Destaques: {names}. A leitura observa momentum contra DXY/cesta FX, diferencial de juros e apetite por risco."
    if block == "Commodities":
        return f"Radar Commodities em regime {macro['regime']}. Destaques: {names}. Foco em tendencia, pressao inflacionaria, China, geopolitica e dolar."
    return f"Radar Metais em regime {macro['regime']}. Destaques: {names}. Foco em juros reais, DXY, ciclo industrial e demanda por protecao."


def generate_watchlist(global_data: dict | None = None) -> dict[str, Any]:
    tickers = []
    for group in ASSET_GROUPS.values():
        tickers.extend(m["ticker"] for m in group["assets"].values())
        tickers.extend(group.get("benchmarks", []))
    data = _download_prices(tickers)
    macro = _macro_regime(global_data)
    dashboard_assets = _global_asset_map(global_data)

    snapshots: list[AssetSnapshot] = []
    for block, group in ASSET_GROUPS.items():
        benchmark = pd.DataFrame()
        for benchmark_ticker in group.get("benchmarks", []):
            benchmark = _ticker_frame(data, benchmark_ticker)
            if not benchmark.empty:
                break
        benchmark_close = benchmark["Close"].astype(float) if not benchmark.empty else pd.Series(dtype=float)
        benchmark_change = 0.0
        for benchmark_ticker in group.get("benchmarks", []):
            dashboard_benchmark = dashboard_assets.get(str(benchmark_ticker).upper())
            if dashboard_benchmark:
                benchmark_change = _safe_float(dashboard_benchmark.get("change"), 0.0)
                break
        for symbol, meta in group["assets"].items():
            snap = _build_snapshot(symbol, meta, block, data, benchmark_close)
            if not snap:
                dashboard_item = dashboard_assets.get(str(meta["ticker"]).upper()) or dashboard_assets.get(symbol.upper())
                if dashboard_item:
                    snap = _quick_snapshot_from_dashboard(symbol, meta, block, dashboard_item, benchmark_change)
            if snap:
                snapshots.append(snap)

    recommendations = []
    for snap in snapshots:
        recommendations.append(_recommendation(snap, macro, "Swing"))
        recommendations.append(_recommendation(snap, macro, "Position"))

    recommendations.sort(key=lambda r: (r["tipo"], r["bloco"], -r["score_atual"]))
    dashboard_count = sum(1 for snap in snapshots if snap.source == "dashboard")
    historical_count = sum(1 for snap in snapshots if snap.source == "historico")
    payload = {
        "schema_version": "watchlist_v3_multi_asset",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "macro": macro,
        "recommendations": recommendations,
        "commentary": {
            block.lower(): _commentary(recommendations, block, macro)
            for block in ASSET_GROUPS
        },
        "data_quality": {
            "assets_loaded": len(snapshots),
            "historical_assets": historical_count,
            "dashboard_assets": dashboard_count,
            "recommendations": len(recommendations),
            "source": "yfinance + mercados_globais/cache",
        },
    }
    if recommendations:
        _save_watchlist_payload(payload)
        return payload
    cached_payload = _load_watchlist_payload()
    if cached_payload:
        cached_payload["data_quality"] = {
            **cached_payload.get("data_quality", {}),
            "source": "ultimo payload valido da WATCHLIST",
            "stale": True,
        }
        return cached_payload
    return payload


def _safe_number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _load_watchlist_payload() -> dict[str, Any] | None:
    try:
        if not WATCHLIST_PAYLOAD_PATH.exists():
            return None
        data = json.loads(WATCHLIST_PAYLOAD_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_watchlist_payload(payload: dict[str, Any]) -> None:
    try:
        WATCHLIST_PAYLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_PAYLOAD_PATH.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        return None


def _load_watchlist_results() -> list[dict[str, Any]]:
    try:
        if not WATCHLIST_RESULTS_PATH.exists():
            return []
        data = json.loads(WATCHLIST_RESULTS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_watchlist_results(rows: list[dict[str, Any]]) -> None:
    WATCHLIST_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_RESULTS_PATH.write_text(
        json.dumps(rows[-500:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _hit_event(rec: dict[str, Any]) -> dict[str, Any] | None:
    if str(rec.get("acao", "")).lower() != "comprar":
        return None

    price = _safe_number(rec.get("preco_atual"))
    entry = _safe_number(rec.get("entrada") or rec.get("entrada_ideal"))
    loss = _safe_number(rec.get("loss"))
    gain1 = _safe_number(rec.get("gain_1"))
    gain2 = _safe_number(rec.get("gain_2"))
    gain_final = _safe_number(rec.get("gain_final"))
    if price is None or entry is None or entry <= 0:
        return None

    event = None
    exit_price = None
    if loss is not None and price <= loss:
        event = "STOP"
        exit_price = loss
    elif gain_final is not None and price >= gain_final:
        event = "TAKE FINAL"
        exit_price = gain_final
    elif gain2 is not None and price >= gain2:
        event = "TAKE 2"
        exit_price = gain2
    elif gain1 is not None and price >= gain1:
        event = "TAKE 1"
        exit_price = gain1

    if not event or exit_price is None:
        return None

    result_pct = ((exit_price / entry) - 1) * 100
    return {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ativo": rec.get("ativo", "---"),
        "tipo": rec.get("tipo", "---"),
        "bloco": rec.get("bloco", "---"),
        "evento": event,
        "entrada": round(entry, 4),
        "saida": round(exit_price, 4),
        "preco_atual": round(price, 4),
        "resultado_pct": round(result_pct, 2),
        "score": rec.get("score_atual", "---"),
        "acao_origem": rec.get("acao", "---"),
    }


def update_watchlist_results(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Register take/stop hits for actionable watchlist recommendations."""
    rows = _load_watchlist_results()
    seen = {
        f"{r.get('ativo')}|{r.get('tipo')}|{r.get('bloco')}|{r.get('evento')}|{r.get('entrada')}|{r.get('saida')}"
        for r in rows
    }
    changed = False
    for rec in recommendations:
        hit = _hit_event(rec)
        if not hit:
            continue
        key = f"{hit.get('ativo')}|{hit.get('tipo')}|{hit.get('bloco')}|{hit.get('evento')}|{hit.get('entrada')}|{hit.get('saida')}"
        if key in seen:
            continue
        rows.append(hit)
        seen.add(key)
        changed = True
    if changed:
        _save_watchlist_results(rows)
    return rows
