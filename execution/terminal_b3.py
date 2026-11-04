"""Deterministic sector and asset-class analysis for Brazilian-listed assets."""

from __future__ import annotations

import math
import time
from typing import Any

import pandas as pd
import requests
import yfinance as yf


ASSET_UNIVERSE: list[dict[str, str]] = [
    {"symbol": "PETR4", "ticker": "PETR4.SA", "name": "Petrobras PN", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "PRIO3", "ticker": "PRIO3.SA", "name": "PRIO", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "RECV3", "ticker": "RECV3.SA", "name": "PetroReconcavo", "class": "Ação", "sector": "Petróleo e gás"},
    {"symbol": "VALE3", "ticker": "VALE3.SA", "name": "Vale", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "GGBR4", "ticker": "GGBR4.SA", "name": "Gerdau PN", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "CSNA3", "ticker": "CSNA3.SA", "name": "CSN", "class": "Ação", "sector": "Mineração e siderurgia"},
    {"symbol": "ITUB4", "ticker": "ITUB4.SA", "name": "Itaú Unibanco PN", "class": "Ação", "sector": "Bancos"},
    {"symbol": "BBDC3", "ticker": "BBDC3.SA", "name": "Bradesco ON", "class": "Ação", "sector": "Bancos"},
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


def _income_statement_rows_from_yahoo(ticker: str, period: str) -> list[dict[str, Any]]:
    statement = getattr(yf.Ticker(ticker), "income_stmt" if period == "annual" else "quarterly_income_stmt", None)
    if statement is None or statement.empty:
        return []

    def row_for(candidates: tuple[str, ...]) -> pd.Series | None:
        normalized = {str(index).strip().lower(): index for index in statement.index}
        for candidate in candidates:
            original = normalized.get(candidate.lower())
            if original is not None:
                return statement.loc[original]
        return None

    net_income = row_for((
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
        "Net Income Continuous Operations",
        "Net Income Including Noncontrolling Interests",
    ))
    if net_income is None:
        return []
    revenue = row_for(("Total Revenue",))
    rows = []
    for date, value in net_income.items():
        if pd.isna(value):
            continue
        revenue_value = revenue.get(date) if revenue is not None else None
        rows.append({
            "endDate": pd.Timestamp(date).date().isoformat(),
            "netIncome": float(value),
            "totalRevenue": float(revenue_value) if revenue_value is not None and pd.notna(revenue_value) else None,
            "consolidationType": None,
        })
    return rows


def fetch_income_statement(symbol: str, ticker: str, period: str, api_key: str = "") -> tuple[list[dict[str, Any]], str, str | None]:
    """Prefer Brapi's reported DRE; fall back to Yahoo statements when available."""
    source_note = None
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = requests.get(
            "https://brapi.dev/api/v2/stocks/income-statement",
            params={"symbols": symbol, "period": period},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        result = next((
            item for item in payload.get("results", [])
            if str(item.get("requestedSymbol") or item.get("symbol") or "").upper() == symbol.upper()
        ), None)
        rows = result.get("data", []) if isinstance(result, dict) else []
        rows = [row for row in rows if isinstance(row, dict) and row.get("endDate") and row.get("netIncome") is not None]
        if rows:
            return rows, "Brapi · DRE", None
        source_note = "A Brapi não retornou DRE para este ativo/período."
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        source_note = f"Brapi indisponível{f' (HTTP {status})' if status else ''}; tentando Yahoo Finance."
    except (AttributeError, TypeError, ValueError, KeyError):
        source_note = "Resposta da Brapi sem formato de DRE esperado; tentando Yahoo Finance."

    try:
        rows = _income_statement_rows_from_yahoo(ticker, period)
        if rows:
            return rows, "Yahoo Finance · demonstração anual" if period == "annual" else "Yahoo Finance · demonstração trimestral", source_note
    except Exception:
        pass
    return [], "", source_note or "DRE não disponível nas fontes consultadas."


def build_profit_price_series(
    income_rows: list[dict[str, Any]],
    price_history: pd.DataFrame,
    *,
    period: str,
) -> dict[str, Any]:
    """Align each reported net income with the last market close on/before period end."""
    if not income_rows:
        return {"rows": [], "consolidation": None}

    valid_rows = []
    for raw in income_rows:
        if not isinstance(raw, dict):
            continue
        try:
            end_date = pd.Timestamp(raw.get("endDate")).normalize().tz_localize(None)
            net_income = float(raw.get("netIncome"))
            if not math.isfinite(net_income):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        revenue = _finite(raw.get("totalRevenue"))
        consolidation = str(raw.get("consolidationType") or "").strip().lower() or None
        valid_rows.append({
            "date": end_date,
            "net_income": net_income,
            "revenue": revenue,
            "consolidation": consolidation,
        })

    types = {row["consolidation"] for row in valid_rows if row["consolidation"]}
    selected_type = "consolidated" if "consolidated" in types else ("individual" if "individual" in types else None)
    if selected_type:
        valid_rows = [row for row in valid_rows if row["consolidation"] == selected_type]

    close = pd.Series(dtype=float)
    if isinstance(price_history, pd.DataFrame) and "Close" in price_history.columns:
        close = pd.to_numeric(price_history["Close"], errors="coerce").dropna()
        index = pd.DatetimeIndex(pd.to_datetime(close.index))
        if index.tz is not None:
            index = index.tz_localize(None)
        close.index = index.normalize()
        close = close[~close.index.duplicated(keep="last")].sort_index()

    rows = []
    for item in sorted(valid_rows, key=lambda row: row["date"]):
        price = None
        price_date = None
        if not close.empty:
            position = close.index.searchsorted(item["date"], side="right") - 1
            if position >= 0:
                price_date = close.index[position]
                price = float(close.iloc[position])
        rows.append({
            "period_end": item["date"].date().isoformat(),
            "period_label": item["date"].strftime("%Y" if period == "annual" else "%Y-%m"),
            "net_income": item["net_income"],
            "revenue": item["revenue"],
            "net_margin": item["net_income"] / item["revenue"] * 100 if item["revenue"] else None,
            "price": price,
            "price_date": price_date.date().isoformat() if price_date is not None else None,
        })

    previous_by_comparable_period: dict[tuple[int, int | None], float] = {}
    for row in rows:
        date = pd.Timestamp(row["period_end"])
        quarter = date.quarter if period == "quarterly" else None
        prior = previous_by_comparable_period.get((date.year - 1, quarter))
        row["net_income_yoy"] = (row["net_income"] / prior - 1) * 100 if prior not in (None, 0) else None
        previous_by_comparable_period[(date.year, quarter)] = row["net_income"]

    return {"rows": rows, "consolidation": selected_type}


def download_profit_vs_price(symbol: str, ticker: str, period: str = "annual", api_key: str = "") -> dict[str, Any]:
    if period not in {"annual", "quarterly"}:
        raise ValueError("period deve ser annual ou quarterly")
    income_rows, income_source, source_note = fetch_income_statement(symbol, ticker, period, api_key)
    if not income_rows:
        raise RuntimeError(source_note or "DRE indisponível para este ativo.")
    price_history = yf.download(
        ticker,
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        timeout=18,
    )
    if price_history is None or price_history.empty:
        raise RuntimeError("Histórico de preços do Yahoo Finance indisponível.")
    if isinstance(price_history.columns, pd.MultiIndex):
        price_history.columns = price_history.columns.get_level_values(0)
    series = build_profit_price_series(income_rows, price_history, period=period)
    if not series["rows"]:
        raise RuntimeError("Não foi possível alinhar os períodos da DRE.")
    return {
        **series,
        "period": period,
        "income_source": income_source,
        "price_source": "Yahoo Finance · fechamento diário",
        "source_note": source_note,
    }


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


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _positive_breadth(values: list[float]) -> float | None:
    return sum(value > 0 for value in values) / len(values) * 100 if values else None


def _positive_leader_share(values: list[float]) -> float | None:
    positive = sorted((value for value in values if value > 0), reverse=True)
    total = sum(positive)
    return sum(positive[:2]) / total * 100 if total > 0 else None


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
        ret1 = _return(close, 1)
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None
        ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
        price = float(close.iloc[-1])
        if ma20 is not None and ma50 is not None and price > ma20 > ma50:
            trend = "Alta alinhada"
        elif ma20 is not None and ma50 is not None and price < ma20 < ma50:
            trend = "Baixa alinhada"
        elif ma20 is None or ma50 is None:
            trend = "Histórico insuficiente"
        else:
            trend = "Misto"
        if volume_ratio is not None and volume_ratio >= 1.5 and ret1 is not None and ret1 > 0:
            volume_signal = "Confirma alta"
        elif volume_ratio is not None and volume_ratio >= 1.5 and ret1 is not None and ret1 < 0:
            volume_signal = "Confirma queda"
        else:
            volume_signal = "Sem confirmação"
        rows.append({
            **asset,
            "price": price,
            "date": last_date,
            "return_1d": ret1,
            "return_5d": ret5,
            "return_21d": ret21,
            "relative_5d": ret5 - benchmark_5d if ret5 is not None and benchmark_5d is not None else None,
            "relative_21d": ret21 - benchmark_21d if ret21 is not None and benchmark_21d is not None else None,
            "volume_ratio": volume_ratio,
            "volume_signal": volume_signal,
            "ma20": ma20,
            "ma50": ma50,
            "trend": trend,
        })

    sectors = []
    sector_names = sorted({r["sector"] for r in rows if r["class"] == "Ação"})
    for sector in sector_names:
        members = [r for r in rows if r["sector"] == sector and r["class"] == "Ação"]
        weekly = [r["return_5d"] for r in members if r["return_5d"] is not None]
        monthly = [r["return_21d"] for r in members if r["return_21d"] is not None]
        weekly_relative = [r["relative_5d"] for r in members if r["relative_5d"] is not None]
        monthly_relative = [r["relative_21d"] for r in members if r["relative_21d"] is not None]
        if weekly and monthly:
            weekly_avg, monthly_avg = _mean(weekly), _mean(monthly)
            if weekly_avg > 0 and monthly_avg > 0:
                regime = "Força persistente"
            elif weekly_avg < 0 and monthly_avg < 0:
                regime = "Fraqueza persistente"
            elif weekly_avg > 0 > monthly_avg:
                regime = "Recuperação de curto prazo"
            elif weekly_avg < 0 < monthly_avg:
                regime = "Perda de força"
            else:
                regime = "Misto"
        else:
            regime = "Histórico insuficiente"
        sectors.append({
            "sector": sector,
            "assets": len(members),
            "observations_5d": len(weekly),
            "observations_21d": len(monthly),
            "weekly": _mean(weekly),
            "monthly": _mean(monthly),
            "weekly_relative": _mean(weekly_relative),
            "monthly_relative": _mean(monthly_relative),
            "weekly_breadth": _positive_breadth(weekly),
            "monthly_breadth": _positive_breadth(monthly),
            "weekly_leader_share": _positive_leader_share(weekly),
            "monthly_leader_share": _positive_leader_share(monthly),
            "weekly_participation": (
                "Ampla" if _positive_breadth(weekly) is not None and _positive_breadth(weekly) >= 60
                else "Estreita" if _positive_breadth(weekly) is not None and _positive_breadth(weekly) <= 40
                else "Mista" if weekly else "Sem dados"
            ),
            "regime": regime,
        })
    sectors.sort(key=lambda row: row["weekly"] if row["weekly"] is not None else -math.inf, reverse=True)
    dates = [r["date"] for r in rows]
    available_tickers = {r["ticker"] for r in rows}
    missing_assets = [item["symbol"] for item in ASSET_UNIVERSE if item["ticker"] not in available_tickers]
    stocks = [row for row in rows if row["class"] == "Ação"]
    weekly_stock_returns = [row["return_5d"] for row in stocks if row["return_5d"] is not None]
    monthly_stock_returns = [row["return_21d"] for row in stocks if row["return_21d"] is not None]
    return {
        "rows": rows,
        "sectors": sectors,
        "updated_at": pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%d/%m/%Y %H:%M:%S"),
        "latest_session": max(dates) if dates else None,
        "benchmark": {"symbol": "BOVA11", "weekly": benchmark_5d, "monthly": benchmark_21d},
        "coverage": {"available": len(rows), "universe": len(ASSET_UNIVERSE)},
        "missing_assets": missing_assets,
        "market_breadth": {
            "weekly": _positive_breadth(weekly_stock_returns),
            "monthly": _positive_breadth(monthly_stock_returns),
            "weekly_leader_share": _positive_leader_share(weekly_stock_returns),
            "monthly_leader_share": _positive_leader_share(monthly_stock_returns),
            "stocks_weekly": len(weekly_stock_returns),
            "stocks_monthly": len(monthly_stock_returns),
        },
    }


def _global_quote(global_data: Any, names: set[str]) -> dict[str, Any] | None:
    if not isinstance(global_data, dict):
        return None
    categories = global_data.get("categories", global_data)
    for items in categories.values() if isinstance(categories, dict) else []:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            symbols = {str(item.get(key) or "").upper() for key in ("symbol", "name", "source_symbol", "fallback_for")}
            if symbols & names:
                try:
                    item = dict(item)
                    item["change"] = float(item.get("change"))
                    return item
                except (TypeError, ValueError):
                    continue
    return None


def build_macro_context(global_data: Any, di_regime: Any, flow_data: Any) -> dict[str, Any]:
    """Expose existing macro and flow observations as context, never as causality."""
    quotes = {
        "DXY": _global_quote(global_data, {"DXY", "DX-Y.NYB", "DXY (DÓLAR INDEX)"}),
        "USD/BRL": _global_quote(global_data, {"USDBRL", "BRL=X", "USDBRL (COMERCIAL)"}),
        "Brent": _global_quote(global_data, {"BRENT", "BZ=F", "BRENT CRUDE OIL"}),
    }
    flow_records = flow_data.get("records", []) if isinstance(flow_data, dict) else []
    flow_records = [row for row in flow_records if isinstance(row, dict) and _finite(row.get("foreigners")) is not None]
    flow_records.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    flow_5d_thousands = sum(_finite(row.get("foreigners")) for row in flow_records[:5]) if flow_records else None
    return {
        "quotes": quotes,
        "di_regime": di_regime.get("regime") if isinstance(di_regime, dict) else None,
        "di_average_change": di_regime.get("avg_change") if isinstance(di_regime, dict) else None,
        "flow_5d_millions": flow_5d_thousands / 1000 if flow_5d_thousands is not None else None,
        "flow_latest_date": flow_records[0].get("date") if flow_records else None,
        "flow_observations": min(len(flow_records), 5),
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


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
    breadth_data = report.get("market_breadth") or {}
    breadth = breadth_data.get("weekly")
    if breadth is not None:
        reads.append(f"A amplitude semanal está em {breadth:.0f}% de ações da amostra em alta; o movimento {'é amplo' if breadth >= 60 else 'é estreito' if breadth <= 40 else 'está dividido'}.")
    concentration = breadth_data.get("weekly_leader_share")
    if concentration is not None and concentration >= 60 and breadth is not None and breadth < 50:
        reads.append(f"Os ganhos semanais estão concentrados: as duas maiores variações positivas representam {concentration:.0f}% da soma dos ganhos da amostra.")
    trend_rows = [row for row in rows if row["class"] == "Ação" and row.get("trend") in {"Alta alinhada", "Baixa alinhada"}]
    if trend_rows:
        aligned = sum(row["trend"] == "Alta alinhada" for row in trend_rows) / len(trend_rows) * 100
        reads.append(f"Entre as ações com médias de 20/50 pregões disponíveis, {aligned:.0f}% está em tendência alinhada de alta; as demais estão alinhadas em baixa.")
    benchmark = report.get("benchmark") or {}
    if benchmark.get("weekly") is not None:
        reads.append(f"BOVA11, usado como referência do Ibovespa, variou {benchmark['weekly']:+.2f}% em 5 pregões.")
    if not reads:
        reads.append("A amostra carregou, mas ainda não há pregões suficientes para calcular as janelas de 5 e 21 sessões.")
    return reads
