"""Deterministic crypto market regime engine."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

try:
    from execution.crypto_common import CACHE_DIR, safe_float, save_cache, utc_now_iso
except ModuleNotFoundError:
    from crypto_common import CACHE_DIR, safe_float, save_cache, utc_now_iso

HISTORY_FILE = os.path.join(CACHE_DIR, "crypto_regime_history.json")


def _asset_map(binance_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = ((binance_payload or {}).get("data") or {}).get("assets") or []
    return {str(item.get("symbol")): item for item in assets if item.get("symbol")}


def _market_map(coingecko_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = ((coingecko_payload or {}).get("data") or {}).get("markets") or []
    out = {}
    for item in rows:
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            out[symbol] = item
    return out


def _trend_score(asset: dict[str, Any]) -> tuple[float, str]:
    change = safe_float(asset.get("change_pct_24h"))
    trend = safe_float(asset.get("trend_80h_pct"))
    score = 0
    if change > 2:
        score += 8
    elif change < -2:
        score -= 8
    if trend > 3:
        score += 8
    elif trend < -3:
        score -= 8
    label = f"{asset.get('symbol', '')}: 24h {change:+.2f}%, 80h {trend:+.2f}%"
    return score, label


def _funding_score(asset: dict[str, Any]) -> tuple[float, str | None]:
    funding = safe_float(asset.get("funding_rate"))
    if not funding:
        return 0, None
    annualized = funding * 3 * 365 * 100
    if annualized > 45:
        return -10, f"Funding muito positivo em {asset.get('symbol')} ({annualized:.1f}% a.a.)"
    if annualized < -10:
        return 8, f"Funding negativo em {asset.get('symbol')} ({annualized:.1f}% a.a.)"
    return 2, f"Funding controlado em {asset.get('symbol')} ({annualized:.1f}% a.a.)"


def _breadth_score(assets: list[dict[str, Any]]) -> tuple[float, str]:
    valid = [safe_float(a.get("change_pct_24h")) for a in assets if a.get("price")]
    if not valid:
        return 0, "Breadth indisponivel"
    positive = sum(1 for v in valid if v > 0)
    ratio = positive / len(valid)
    if ratio >= 0.7:
        return 12, f"breadth positiva ({positive}/{len(valid)} ativos em alta)"
    if ratio <= 0.3:
        return -12, f"breadth negativa ({positive}/{len(valid)} ativos em alta)"
    return 0, f"breadth neutra ({positive}/{len(valid)} ativos em alta)"


def _classify(score: float, fear_value: float, funding_pressure: bool) -> str:
    if fear_value <= 18 and score < -10:
        return "Capitulacao"
    if funding_pressure and score < -5:
        return "Desalavancagem"
    if fear_value >= 80 and score > 15:
        return "Euforia"
    if score >= 35:
        return "Risk-on forte"
    if score >= 15:
        return "Risk-on moderado"
    if score <= -35:
        return "Risk-off forte"
    if score <= -15:
        return "Risk-off moderado"
    return "Neutro"


def _append_history(result: dict[str, Any]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
        if not isinstance(history, list):
            history = []
        history.append({
            "updated_at": result.get("updated_at"),
            "regime": result.get("regime"),
            "score": result.get("score"),
            "confidence": result.get("confidence"),
        })
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-20:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def calculate_crypto_regime(
    binance_payload: dict[str, Any],
    coingecko_payload: dict[str, Any],
    fear_payload: dict[str, Any],
    defillama_payload: dict[str, Any],
    save_file: bool = True,
) -> dict[str, Any]:
    assets = list(_asset_map(binance_payload).values())
    asset_by_symbol = _asset_map(binance_payload)
    gecko = (coingecko_payload or {}).get("data") or {}
    fear = ((fear_payload or {}).get("data") or {}).get("current") or {}
    defi = (defillama_payload or {}).get("data") or {}

    score = 50.0
    positive: list[str] = []
    negative: list[str] = []
    missing: list[str] = []
    alerts: list[str] = []

    for symbol in ("BTCUSDT", "ETHUSDT"):
        if symbol in asset_by_symbol:
            delta, label = _trend_score(asset_by_symbol[symbol])
            score += delta
            (positive if delta >= 0 else negative).append(label)
        else:
            missing.append(symbol)

    breadth_delta, breadth_label = _breadth_score(assets)
    score += breadth_delta
    (positive if breadth_delta >= 0 else negative).append(breadth_label)

    btc_dom = safe_float(gecko.get("btc_dominance"))
    eth_dom = safe_float(gecko.get("eth_dominance"))
    if btc_dom and eth_dom:
        if btc_dom > 55 and eth_dom < 18:
            score -= 4
            negative.append(f"BTC dominance elevada ({btc_dom:.1f}%) limita altcoins")
        elif eth_dom > 18:
            score += 4
            positive.append(f"ETH dominance firme ({eth_dom:.1f}%) sugere rotacao de risco")
    else:
        missing.append("dominancia CoinGecko")

    fear_value = safe_float(fear.get("value"))
    if fear_value:
        if fear_value >= 75:
            score += 4
            alerts.append(f"Ganancia elevada no Fear & Greed ({fear_value:.0f})")
        elif fear_value <= 25:
            score -= 8
            alerts.append(f"Medo extremo no Fear & Greed ({fear_value:.0f})")
        else:
            positive.append(f"Fear & Greed em zona intermediaria ({fear_value:.0f})")
    else:
        missing.append("Fear & Greed")

    funding_pressure = False
    for symbol in ("BTCUSDT", "ETHUSDT"):
        asset = asset_by_symbol.get(symbol)
        if not asset:
            continue
        delta, msg = _funding_score(asset)
        score += delta
        if msg:
            if delta < 0:
                negative.append(msg)
                funding_pressure = True
            else:
                positive.append(msg)

    stable_mcap = safe_float(defi.get("stablecoin_market_cap_usd"))
    total_mcap = safe_float(gecko.get("total_market_cap_usd"))
    if stable_mcap and total_mcap:
        stable_dom = stable_mcap / total_mcap * 100
        if stable_dom > 9:
            score -= 5
            negative.append(f"Stablecoin dominance alta ({stable_dom:.1f}%) indica defensividade")
        else:
            positive.append(f"Stablecoin dominance controlada ({stable_dom:.1f}%)")
    else:
        missing.append("stablecoin dominance")

    total_tvl = safe_float(defi.get("total_tvl_usd"))
    if total_tvl:
        positive.append(f"TVL DeFi monitorado em US$ {total_tvl/1e9:.1f} bi")
    else:
        missing.append("TVL DeFi")

    score = max(0, min(100, score))
    confidence = max(25, min(95, 100 - len(missing) * 10))
    regime = _classify(score, fear_value, funding_pressure)
    result = {
        "source": "TTS Crypto Regime Engine",
        "status": "ok",
        "updated_at": utc_now_iso(),
        "updated_ts": time.time(),
        "score": round(score, 1),
        "confidence": confidence,
        "regime": regime,
        "drivers_positive": positive[:8],
        "drivers_negative": negative[:8],
        "alerts": alerts[:8],
        "missing_data": missing,
    }
    if save_file:
        save_cache("crypto_regime.json", result)
        _append_history(result)
    return result


if __name__ == "__main__":
    try:
        from execution.crypto_binance import fetch_binance_crypto_snapshot
        from execution.crypto_coingecko import fetch_coingecko_crypto_snapshot
        from execution.crypto_defillama import fetch_defillama_crypto_snapshot
        from execution.crypto_fear_greed import fetch_fear_greed_snapshot
    except ModuleNotFoundError:
        from crypto_binance import fetch_binance_crypto_snapshot
        from crypto_coingecko import fetch_coingecko_crypto_snapshot
        from crypto_defillama import fetch_defillama_crypto_snapshot
        from crypto_fear_greed import fetch_fear_greed_snapshot

    print(calculate_crypto_regime(
        fetch_binance_crypto_snapshot(),
        fetch_coingecko_crypto_snapshot(),
        fetch_fear_greed_snapshot(),
        fetch_defillama_crypto_snapshot(),
    ))
