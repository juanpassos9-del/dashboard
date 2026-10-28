"""Deterministic FX cross-market correlation context."""

from __future__ import annotations

import math

import pandas as pd


FX_MACRO_RELATIONSHIPS = (
    ("EURUSD", "DXY", "inversa", "Dólar amplo; diferencial Fed/BCE não calculado neste painel"),
    ("GBPUSD", "DXY", "inversa", "Dólar amplo; diferencial Fed/BoE não calculado neste painel"),
    ("USDJPY", "US02Y", "direta", "Juros curtos dos EUA versus BoJ"),
    ("USDJPY", "VIX", "inversa", "Iene como moeda defensiva em episódios de aversão a risco"),
    ("USDCHF", "EURUSD", "inversa", "Relação entre duas cotações com USD em lados opostos"),
    ("USDCHF", "VIX", "direta", "Franco suíço como moeda defensiva; relação pode variar por regime"),
    ("AUDUSD", "COPPER", "direta", "Ciclo de commodities e demanda global/China"),
    ("AUDUSD", "SPX", "direta", "Apetite por risco global"),
    ("NZDUSD", "SPX", "direta", "Apetite por risco global"),
    ("USDCAD", "WTI", "inversa", "Petróleo e termos de troca do Canadá"),
)


def build_fx_macro_correlation_rows(
    prices: pd.DataFrame,
    *,
    window: int = 60,
    short_window: int = 20,
    min_observations: int = 30,
) -> list[dict]:
    """Correlate aligned daily percentage returns; omit pairs with short samples."""
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return []

    returns = prices.apply(pd.to_numeric, errors="coerce").pct_change(fill_method=None)
    rows = []
    for pair, driver, expected, context in FX_MACRO_RELATIONSHIPS:
        if pair not in returns.columns or driver not in returns.columns:
            continue
        history = returns[[pair, driver]].dropna()
        sample = history.tail(max(1, int(window)))
        observations = len(sample)
        if observations < min_observations:
            continue
        corr_60 = sample[pair].corr(sample[driver])
        short_sample = sample.tail(max(1, int(short_window)))
        corr_20 = short_sample[pair].corr(short_sample[driver]) if len(short_sample) >= 15 else float("nan")
        if pd.isna(corr_60):
            continue

        risk_corr = {"risk_on": None, "risk_on_n": 0, "risk_off": None, "risk_off_n": 0}
        if "SPX" in returns.columns and "VIX" in returns.columns:
            regime_history = returns[[pair, driver, "SPX", "VIX"]].dropna().tail(max(1, int(window)))
            risk_on = regime_history[(regime_history["SPX"] > 0) & (regime_history["VIX"] <= 0)]
            risk_off = regime_history[(regime_history["SPX"] < 0) & (regime_history["VIX"] > 0)]
            for name, regime_sample in (("risk_on", risk_on), ("risk_off", risk_off)):
                risk_corr[f"{name}_n"] = len(regime_sample)
                if len(regime_sample) >= 10:
                    regime_value = regime_sample[pair].corr(regime_sample[driver])
                    if pd.notna(regime_value):
                        risk_corr[name] = round(float(regime_value), 2)
        value = float(corr_60)
        if abs(value) < 0.15:
            reading = "Fraca/indefinida"
        else:
            aligned = (expected == "direta" and value > 0) or (expected == "inversa" and value < 0)
            reading = "Alinhada" if aligned else "Divergente"
        rows.append({
            "Par": pair,
            "Driver": driver,
            "Correlação 20d": round(float(corr_20), 2) if pd.notna(corr_20) else None,
            "Correlação 60d": round(value, 2),
            "Relação de referência": expected,
            "Leitura": reading,
            "Pregões": observations,
            "Último pregão": sample.index[-1].strftime("%Y-%m-%d"),
            "Corr. risk-on": risk_corr["risk_on"],
            "N risk-on": risk_corr["risk_on_n"],
            "Corr. risk-off": risk_corr["risk_off"],
            "N risk-off": risk_corr["risk_off_n"],
            "Contexto": context,
        })
    return rows


def build_fx_intraday_correlation_rows(
    pair_performance: pd.DataFrame,
    driver_performance: pd.DataFrame,
    *,
    pairs: list[str],
    inverse_pairs: set[str],
    inverse_drivers: set[str],
    min_observations: int = 30,
) -> list[dict]:
    """Correlate synchronized intraday changes, not rebased performance levels."""
    if not isinstance(pair_performance, pd.DataFrame) or pair_performance.empty:
        return []
    if not isinstance(driver_performance, pd.DataFrame) or driver_performance.empty:
        return []
    synchronized = pair_performance.join(driver_performance, how="inner", rsuffix="_driver")
    changes = synchronized.diff().dropna(how="all")
    rows = []
    for pair in pairs:
        if pair not in changes.columns:
            continue
        for driver in driver_performance.columns:
            if driver not in changes.columns:
                continue
            sample = changes[[pair, driver]].dropna()
            if len(sample) < min_observations:
                continue
            correlation = sample[pair].corr(sample[driver])
            if pd.isna(correlation):
                continue
            expected = "inversa" if pair in inverse_pairs and driver in inverse_drivers else "direta"
            value = float(correlation)
            reading = "fraca/indefinida" if abs(value) < 0.15 else (
                "confirma" if (expected == "direta" and value > 0) or (expected == "inversa" and value < 0) else "diverge"
            )
            rows.append({
                "Par": pair,
                "Driver": driver,
                "Correlação": round(value, 2),
                "Relação esperada": expected,
                "Leitura": reading,
                "Observações": len(sample),
            })
    return sorted(rows, key=lambda item: abs(item["Correlação"]), reverse=True)


def currency_strength_from_pair_returns(
    pair_returns: dict[str, float],
    pair_currencies: dict[str, tuple[str, str]],
) -> tuple[dict[str, float], dict[str, int]]:
    """Normalize average currency contributions and retain observed-pair coverage."""
    contributions: dict[str, list[float]] = {}
    for pair, raw_value in pair_returns.items():
        currencies = pair_currencies.get(pair)
        if not currencies:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        base, quote = currencies
        contributions.setdefault(base, []).append(value)
        contributions.setdefault(quote, []).append(-value)

    raw_scores = {currency: sum(values) / len(values) for currency, values in contributions.items() if values}
    max_abs = max((abs(value) for value in raw_scores.values()), default=0.0)
    strength = {
        currency: round((value / max_abs) * 100.0, 1) if max_abs else 0.0
        for currency, value in raw_scores.items()
    }
    coverage = {currency: len(values) for currency, values in contributions.items()}
    return strength, coverage


def build_fx_market_brief(
    strength: dict[str, float],
    coverage: dict[str, int],
    *,
    dxy_change: float | None = None,
    spx_change: float | None = None,
    vix_change: float | None = None,
    best_pair: dict | None = None,
    divergent_pairs: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Summarize observed confirmations and divergences without filling missing data."""
    confirms: list[str] = []
    divergences: list[str] = []
    notes: list[str] = []

    usd_coverage = int(coverage.get("USD", 0) or 0)
    if dxy_change is not None and usd_coverage:
        usd_score = float(strength.get("USD", 0.0))
        if abs(usd_score) < 10 or abs(dxy_change) < 0.03:
            notes.append("USD/DXY sem deslocamento direcional relevante neste recorte.")
        elif (usd_score > 0) == (dxy_change > 0):
            confirms.append("Força relativa do USD e DXY apontam na mesma direção.")
        else:
            divergences.append("Força relativa do USD diverge do DXY.")
    else:
        notes.append("Confirmação USD/DXY indisponível por cobertura insuficiente.")

    if spx_change is not None and vix_change is not None:
        if spx_change > 0 and vix_change < 0:
            confirms.append("S&P em alta e VIX em queda: leitura de risco mais construtiva.")
        elif spx_change < 0 and vix_change > 0:
            confirms.append("S&P em queda e VIX em alta: leitura de risco mais defensiva.")
        else:
            notes.append("S&P/VIX sem confirmação direcional conjunta.")
    else:
        notes.append("Regime de risco não classificado: falta S&P 500 ou VIX.")

    if best_pair and best_pair.get("Par"):
        statement = (
            f"Scanner ranqueia {best_pair.get('Direcao', '—')} {best_pair['Par']} "
            f"(score relativo {best_pair.get('Score', '—')}; não é probabilidade)."
        )
        if best_pair.get("Alinhado") == "Sim":
            confirms.append(statement)
        elif best_pair.get("Alinhado") == "Divergente":
            divergences.append(statement)
        else:
            notes.append(statement)
    else:
        notes.append("Scanner sem par com força relativa coberta.")

    for row in (divergent_pairs or [])[:3]:
        pair = row.get("Par")
        if pair:
            divergences.append(f"{pair}: momentum não acompanha a direção indicada pelo spread de força.")

    if not confirms:
        confirms.append("Nenhuma confirmação conjunta suficiente nos dados disponíveis.")
    if not divergences:
        divergences.append("Nenhuma divergência identificada; isso não equivale a confirmação.")
    return {"confirms": confirms, "divergences": divergences, "notes": notes}
