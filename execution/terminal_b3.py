"""Deterministic sector and asset-class analysis for Brazilian-listed assets."""

from __future__ import annotations

import math
import time
from typing import Any

import pandas as pd
import yfinance as yf


ASSET_UNIVERSE: list[dict[str, str]] = [
    {"symbol": "PETR4", "ticker": "PETR4.SA", "name": "Petrobras PN", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "PRIO3", "ticker": "PRIO3.SA", "name": "PRIO", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "RECV3", "ticker": "RECV3.SA", "name": "PetroReconcavo", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "VALE3", "ticker": "VALE3.SA", "name": "Vale", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "GGBR4", "ticker": "GGBR4.SA", "name": "Gerdau PN", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "CSNA3", "ticker": "CSNA3.SA", "name": "CSN", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "ITUB4", "ticker": "ITUB4.SA", "name": "Itaú Unibanco PN", "class": "Ação", "sector": "Bancos"},
    {"symbol": "BBDC4", "ticker": "BBDC4.SA", "name": "Bradesco PN", "class": "Ação", "sector": "Bancos"},
    {"symbol": "BBAS3", "ticker": "BBAS3.SA", "name": "Banco do Brasil", "class": "Ação", "sector": "Bancos"},
    {"symbol": "SANB11", "ticker": "SANB11.SA", "name": "Santander Brasil Unit", "class": "Ação", "sector": "Bancos"},
    {"symbol": "BPAC11", "ticker": "BPAC11.SA", "name": "BTG Pactual Unit", "class": "Ação", "sector": "Bancos"},
    {"symbol": "B3SA3", "ticker": "B3SA3.SA", "name": "B3", "class": "Ação", "sector": "Serviços financeiros"},
    {"symbol": "ELET3", "ticker": "ELET3.SA", "name": "Axia Energia ON", "class": "Ação", "sector": "Energia elétrica"},
    {"symbol": "EQTL3", "ticker": "EQTL3.SA", "name": "Equatorial", "class": "Ação", "sector": "Energia elétrica"},
    {"symbol": "CPFE3", "ticker": "CPFE3.SA", "name": "CPFL Energia", "class": "Ação", "sector": "Energia elétrica"},
    {"symbol": "CMIG4", "ticker": "CMIG4.SA", "name": "Cemig PN", "class": "Ação", "sector": "Energia elétrica"},
    {"symbol": "WEGE3", "ticker": "WEGE3.SA", "name": "WEG", "class": "Ação", "sector": "Indústria"},
    {"symbol": "EMBR3", "ticker": "EMBR3.SA", "name": "Embraer", "class": "Ação", "sector": "Indústria"},
    {"symbol": "RENT3", "ticker": "RENT3.SA", "name": "Localiza", "class": "Ação", "sector": "Consumo cíclico"},
    {"symbol": "LREN3", "ticker": "LREN3.SA", "name": "Lojas Renner", "class": "Ação", "sector": "Consumo cíclico"},
    {"symbol": "RADL3", "ticker": "RADL3.SA", "name": "Raia Drogasil", "class": "Ação", "sector": "Consumo defensivo"},
    {"symbol": "ABEV3", "ticker": "ABEV3.SA", "name": "Ambev", "class": "Ação", "sector": "Consumo defensivo"},
    {"symbol": "SUZB3", "ticker": "SUZB3.SA", "name": "Suzano", "class": "Ação", "sector": "Papel e celulose"},
    {"symbol": "KLBN11", "ticker": "KLBN11.SA", "name": "Klabin Unit", "class": "Ação", "sector": "Papel e celulose"},
    {"symbol": "HAPV3", "ticker": "HAPV3.SA", "name": "Hapvida", "class": "Ação", "sector": "Saúde"},
    {"symbol": "FLRY3", "ticker": "FLRY3.SA", "name": "Fleury", "class": "Ação", "sector": "Saúde"},
    {"symbol": "CYRE3", "ticker": "CYRE3.SA", "name": "Cyrela", "class": "Ação", "sector": "Imobiliário"},
    {"symbol": "MULT3", "ticker": "MULT3.SA", "name": "Multiplan", "class": "Ação", "sector": "Imobiliário"},
    {"symbol": "BOVA11", "ticker": "BOVA11.SA", "name": "Ibovespa ETF", "class": "ETF", "sector": "Índice amplo"},
    {"symbol": "SMAL11", "ticker": "SMAL11.SA", "name": "Small Caps ETF", "class": "ETF", "sector": "Small caps"},
    {"symbol": "DIVO11", "ticker": "DIVO11.SA", "name": "Dividendos ETF", "class": "ETF", "sector": "Dividendos"},
    {"symbol": "IVVB11", "ticker": "IVVB11.SA", "name": "S&P 500 ETF", "class": "ETF", "sector": "Exterior"},
    {"symbol": "GOLD11", "ticker": "GOLD11.SA", "name": "Ouro ETF", "class": "ETF", "sector": "Ouro"},
    {"symbol": "HASH11", "ticker": "HASH11.SA", "name": "Cripto ETF", "class": "ETF", "sector": "Criptoativos"},
    {"symbol": "AAPL34", "ticker": "AAPL34.SA", "name": "Apple BDR", "class": "BDR", "sector": "Tecnologia global"},
    {"symbol": "MSFT34", "ticker": "MSFT34.SA", "name": "Microsoft BDR", "class": "BDR", "sector": "Tecnologia global"},
    {"symbol": "NVDC34", "ticker": "NVDC34.SA", "name": "NVIDIA BDR", "class": "BDR", "sector": "Tecnologia global"},
    {"symbol": "AMZO34", "ticker": "AMZO34.SA", "name": "Amazon BDR", "class": "BDR", "sector": "Consumo global"},
]
BENCHMARK_TICKER = "BOVA11.SA"


def download_terminal_b3_history() -> dict[str, Any]:
    """Download adjusted daily bars in small batches, preserving partial coverage."""
    tickers = sorted({item["ticker"] for item in ASSET_UNIVERSE} | {BENCHMARK_TICKER})
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for start in range(0, len(tickers), 8):
        batch = tickers[start:start + 8]
        data = pd.DataFrame()
        for attempt in range(2):
            try:
                data = yf.download(batch, period="4mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=False, timeout=18)
                if data is not None and not data.empty:
                    break
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                time.sleep(0.4 * (attempt + 1))
        if data is None or data.empty:
            continue
        for ticker in batch:
            try:
                frame = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
                frame = frame.dropna(subset=["Close"]).copy()
                if not frame.empty:
                    frames[ticker] = frame
            except (KeyError, TypeError, ValueError):
                continue
    report = build_terminal_b3_report(frames)
    report["errors"] = errors[-8:]
    return report


def _valid_closes(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty or "Close" not in frame:
        return pd.Series(dtype=float)
    close = pd.to_numeric(frame["Close"], errors="coerce")
    return close[close > 0].dropna()


def _return(close: pd.Series, sessions: int) -> float | None:
    if len(close) <= sessions:
        return None
    base, latest = float(close.iloc[-sessions - 1]), float(close.iloc[-1])
    return (latest / base - 1) * 100 if base > 0 else None


def build_terminal_b3_report(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Calculate comparable 5/21-session returns, sector breadth and relative strength."""
    benchmark_close = _valid_closes(frames.get(BENCHMARK_TICKER))
    benchmark_5d, benchmark_21d = _return(benchmark_close, 5), _return(benchmark_close, 21)
    rows: list[dict[str, Any]] = []
    for asset in ASSET_UNIVERSE:
        frame = frames.get(asset["ticker"])
        close = _valid_closes(frame)
        if close.empty:
            continue
        last_date = pd.Timestamp(close.index[-1]).date().isoformat()
        volume = pd.to_numeric(frame.get("Volume", pd.Series(dtype=float)), errors="coerce").dropna()
        volume_ratio = None
        if len(volume) >= 21:
            baseline = float(volume.iloc[-21:-1].median())
            if baseline > 0:
                volume_ratio = float(volume.iloc[-1]) / baseline
        ret5, ret21 = _return(close, 5), _return(close, 21)
        rows.append({
            **asset,
            "price": float(close.iloc[-1]),
            "date": last_date,
            "return_5d": ret5,
            "return_21d": ret21,
            "relative_5d": ret5 - benchmark_5d if ret5 is not None and benchmark_5d is not None else None,
            "relative_21d": ret21 - benchmark_21d if ret21 is not None and benchmark_21d is not None else None,
            "volume_ratio": volume_ratio,
        })

    sectors = []
    sector_names = sorted({r["sector"] for r in rows if r["class"] == "Ação"})
    for sector in sector_names:
        members = [r for r in rows if r["sector"] == sector and r["class"] == "Ação"]
        weekly = [r["return_5d"] for r in members if r["return_5d"] is not None]
        monthly = [r["return_21d"] for r in members if r["return_21d"] is not None]
        sectors.append({
            "sector": sector,
            "assets": len(members),
            "weekly": sum(weekly) / len(weekly) if weekly else None,
            "monthly": sum(monthly) / len(monthly) if monthly else None,
            "weekly_breadth": sum(value > 0 for value in weekly) / len(weekly) * 100 if weekly else None,
            "monthly_breadth": sum(value > 0 for value in monthly) / len(monthly) * 100 if monthly else None,
        })
    sectors.sort(key=lambda row: row["weekly"] if row["weekly"] is not None else -math.inf, reverse=True)
    dates = [r["date"] for r in rows]
    available_tickers = {r["ticker"] for r in rows}
    missing_assets = [item["symbol"] for item in ASSET_UNIVERSE if item["ticker"] not in available_tickers]
    return {
        "rows": rows,
        "sectors": sectors,
        "updated_at": pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%d/%m/%Y %H:%M:%S"),
        "latest_session": max(dates) if dates else None,
        "benchmark": {"symbol": "BOVA11", "weekly": benchmark_5d, "monthly": benchmark_21d},
        "coverage": {"available": len(rows), "universe": len(ASSET_UNIVERSE)},
        "missing_assets": missing_assets,
    }


def market_read(report: dict[str, Any]) -> list[str]:
    sectors = report.get("sectors") or []
    rows = report.get("rows") or []
    if not rows:
        return ["Sem histórico suficiente para montar a leitura. Tente atualizar os dados mais tarde."]
    reads = []
    weekly = [s for s in sectors if s["weekly"] is not None]
    monthly = [s for s in sectors if s["monthly"] is not None]
    if weekly:
        leader, laggard = weekly[0], weekly[-1]
        reads.append(f"Na semana, {leader['sector']} lidera ({leader['weekly']:+.2f}%) e {laggard['sector']} fica atrás ({laggard['weekly']:+.2f}%).")
    if monthly:
        leader = max(monthly, key=lambda s: s["monthly"])
        reads.append(f"No mês (21 pregões), {leader['sector']} apresenta o melhor retorno médio ({leader['monthly']:+.2f}%).")
    liquid = [r for r in rows if r["class"] == "Ação" and r["return_5d"] is not None]
    if liquid:
        breadth = sum(r["return_5d"] > 0 for r in liquid) / len(liquid) * 100
        reads.append(f"A amplitude semanal está em {breadth:.0f}% de ações da amostra em alta; o movimento {'é amplo' if breadth >= 60 else 'é estreito' if breadth <= 40 else 'está dividido'}.")
    benchmark = report.get("benchmark") or {}
    if benchmark.get("weekly") is not None:
        reads.append(f"BOVA11, usado como referência do Ibovespa, variou {benchmark['weekly']:+.2f}% em 5 pregões.")
    if not reads:
        reads.append("A amostra carregou, mas ainda não há pregões suficientes para calcular as janelas de 5 e 21 sessões.")
    return reads
