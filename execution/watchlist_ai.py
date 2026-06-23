"""Deterministic Watchlist IA TTS for swing and position radar.

This first version avoids external LLM calls. It builds a structured radar from
yfinance prices plus the dashboard macro snapshot, keeping Brazil stocks and US
sector ETFs separated.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
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


def _safe_float(value, default=0.0) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def _download_prices(tickers: list[str]) -> pd.DataFrame:
    for attempt in range(2):
        try:
            data = yf.download(
                sorted(set(tickers)),
                period="1y",
                interval="1d",
                group_by="ticker",
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=18,
            )
            if data is not None and not data.empty:
                return data
        except Exception:
            time.sleep(1 + attempt)
    return pd.DataFrame()


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
    if regime == "Risk-on forte":
        if block == "Brasil":
            return 85 if any(x in sector_l for x in ["mineracao", "petroleo", "bancos", "industria"]) else 65
        return 85 if sector in {"Technology", "Industrials", "Materials"} else 60
    if regime == "Risk-on moderado":
        if block == "Brasil":
            return 75 if any(x in sector_l for x in ["bancos", "papel", "mineracao"]) else 60
        return 75 if sector in {"Technology", "Industrials"} else 58
    if regime == "Risk-off moderado":
        if block == "Brasil":
            return 72 if any(x in sector_l for x in ["eletricas", "defensivo"]) else 45
        return 78 if sector == "Consumer Staples" else 45
    if regime == "Risk-off forte":
        if block == "Brasil":
            return 62 if any(x in sector_l for x in ["eletricas", "defensivo"]) else 30
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


def _score_snapshot(s: AssetSnapshot, macro: dict, style: str) -> float:
    regime = _regime_component(s.block, s.sector, macro["regime"])
    if s.block == "Brasil":
        score = regime * 0.25 + s.trend_score * 0.20 + s.relative_score * 0.15 + 58 * 0.15 + 50 * 0.10 + s.volatility_score * 0.10 + 50 * 0.05
    else:
        score = regime * 0.25 + s.relative_score * 0.20 + s.trend_score * 0.15 + 58 * 0.15 + s.volatility_score * 0.10 + 52 * 0.10 + 50 * 0.05
    if style == "Position":
        score = score * 0.72 + s.trend_score * 0.18 + regime * 0.10
    return max(0, min(100, score))


def _recommendation(s: AssetSnapshot, macro: dict, style: str) -> dict[str, Any]:
    score = _score_snapshot(s, macro, style)
    atr = s.atr14 if s.atr14 > 0 else max(s.price * 0.025, 0.01)
    stop_mult = 1.8 if style == "Swing" else 2.8
    target_mults = (1.4, 2.4, 3.6) if style == "Swing" else (2.0, 3.5, 5.0)
    entry_ideal = min(s.price, s.ma20) if s.ma20 > 0 else s.price * 0.99
    entry_partial = s.price
    loss = entry_ideal - atr * stop_mult
    gain1 = entry_ideal + atr * target_mults[0]
    gain2 = entry_ideal + atr * target_mults[1]
    gain_final = entry_ideal + atr * target_mults[2]
    rr = (gain2 - entry_ideal) / max(entry_ideal - loss, 0.01)
    if score >= 72 and s.price <= gain1:
        action = "comprar parcial" if s.price > entry_ideal * 1.015 else "comprar"
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
    carteira = f"Carteira {style} {'Brasil - Acoes' if s.block == 'Brasil' else 'EUA - ETFs Setoriais'}"
    return {
        "bloco": f"{s.block} {'Acoes' if s.block == 'Brasil' else 'ETFs Setoriais'}",
        "ativo": s.symbol,
        "classe": "Acao" if s.block == "Brasil" else "ETF Setorial",
        "setor": s.sector,
        "tipo": style,
        "direcao": "compra",
        "score_inicial": round(score, 1),
        "score_atual": round(score, 1),
        "preco_atual": round(s.price, 2),
        "entrada_ideal": round(entry_ideal, 2),
        "entrada_parcial": round(entry_partial, 2),
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
    }


def _commentary(recs: list[dict[str, Any]], block: str, macro: dict) -> str:
    subset = [r for r in recs if r["bloco"].startswith(block)]
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
    return f"Rotacao setorial EUA em regime {macro['regime']}. Destaques: {names}. A leitura compara cada setor contra SPY; risco principal vem de US10Y, DXY, VIX e mudanca de apetite por risco."


def generate_watchlist(global_data: dict | None = None) -> dict[str, Any]:
    tickers = [m["ticker"] for m in BRAZIL_ASSETS.values()] + [m["ticker"] for m in US_SECTOR_ETFS.values()] + ["^BVSP", "BOVA11.SA", "SPY"]
    data = _download_prices(tickers)
    macro = _macro_regime(global_data)
    benchmark_br = _ticker_frame(data, "BOVA11.SA")
    if benchmark_br.empty:
        benchmark_br = _ticker_frame(data, "^BVSP")
    benchmark_us = _ticker_frame(data, "SPY")
    br_close = benchmark_br["Close"].astype(float) if not benchmark_br.empty else pd.Series(dtype=float)
    us_close = benchmark_us["Close"].astype(float) if not benchmark_us.empty else pd.Series(dtype=float)

    snapshots: list[AssetSnapshot] = []
    for symbol, meta in BRAZIL_ASSETS.items():
        snap = _build_snapshot(symbol, meta, "Brasil", data, br_close)
        if snap:
            snapshots.append(snap)
    for symbol, meta in US_SECTOR_ETFS.items():
        snap = _build_snapshot(symbol, meta, "EUA", data, us_close)
        if snap:
            snapshots.append(snap)

    recommendations = []
    for snap in snapshots:
        recommendations.append(_recommendation(snap, macro, "Swing"))
        recommendations.append(_recommendation(snap, macro, "Position"))

    recommendations.sort(key=lambda r: (r["tipo"], r["bloco"], -r["score_atual"]))
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "macro": macro,
        "recommendations": recommendations,
        "commentary": {
            "brasil": _commentary(recommendations, "Brasil", macro),
            "eua": _commentary(recommendations, "EUA", macro),
        },
        "data_quality": {
            "assets_loaded": len(snapshots),
            "recommendations": len(recommendations),
            "source": "yfinance + mercados_globais/cache",
        },
    }
