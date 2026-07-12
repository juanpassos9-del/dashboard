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


def _bias_from_regime(regime: str, score: float) -> str:
    text = str(regime or "").lower()
    if "capitulacao" in text:
        return "Stress / possivel acumulacao"
    if "desalavancagem" in text:
        return "Defensivo"
    if "euforia" in text:
        return "Risk-on esticado"
    if "risk-on forte" in text:
        return "Comprador seletivo"
    if "risk-on" in text:
        return "Comprador moderado"
    if "risk-off forte" in text:
        return "Defensivo forte"
    if "risk-off" in text:
        return "Defensivo moderado"
    if score >= 58:
        return "Levemente comprador"
    if score <= 42:
        return "Levemente defensivo"
    return "Neutro"


def _build_summary(
    regime: str,
    score: float,
    positive: list[str],
    negative: list[str],
    alerts: list[str],
    stable_dom: float | None,
    btc_dom: float,
    eth_dom: float,
) -> str:
    primary = positive[0] if positive else "sem driver positivo dominante"
    risk = negative[0] if negative else (alerts[0] if alerts else "sem alerta critico")
    dom = ""
    if btc_dom and eth_dom:
        dom = f" Dominancia: BTC {btc_dom:.1f}%, ETH {eth_dom:.1f}%."
    stable = ""
    if stable_dom is not None:
        stable = f" Stables {stable_dom:.1f}% do market cap."
    return (
        f"{regime} ({score:.0f}/100). Driver principal: {primary}. "
        f"Risco monitorado: {risk}.{dom}{stable}"
    )


def _cycle_allocation_decision(
    score: float,
    fear_value: float,
    mvrv_z: float,
    mvrv: float,
    mayer: float,
    puell: float,
    aviv: float,
    stable_dom: float | None,
    breadth_delta: float,
    btc_asset: dict[str, Any] | None,
    eth_asset: dict[str, Any] | None,
    funding_pressure: bool,
) -> dict[str, Any]:
    """Contrarian cycle allocation with momentum confirmation."""
    cycle_score = 50.0
    reasons: list[str] = []
    risks: list[str] = []

    if fear_value:
        if fear_value <= 20:
            cycle_score += 18
            reasons.append(f"medo extremo no Fear & Greed ({fear_value:.0f})")
        elif fear_value <= 35:
            cycle_score += 10
            reasons.append(f"medo ainda elevado ({fear_value:.0f})")
        elif fear_value >= 80:
            cycle_score -= 20
            risks.append(f"ganancia extrema ({fear_value:.0f})")
        elif fear_value >= 70:
            cycle_score -= 10
            risks.append(f"sentimento aquecido ({fear_value:.0f})")

    if mvrv_z:
        if mvrv_z <= 0:
            cycle_score += 22
            reasons.append(f"MVRV Z em desconto/capitulacao ({mvrv_z:.2f})")
        elif mvrv_z <= 2:
            cycle_score += 10
            reasons.append(f"MVRV Z saudavel ({mvrv_z:.2f})")
        elif mvrv_z >= 7:
            cycle_score -= 26
            risks.append(f"MVRV Z em euforia de ciclo ({mvrv_z:.2f})")
        elif mvrv_z >= 4:
            cycle_score -= 14
            risks.append(f"MVRV Z aquecido ({mvrv_z:.2f})")

    if mvrv:
        if mvrv < 1:
            cycle_score += 16
            reasons.append(f"BTC abaixo do realized price agregado ({mvrv:.2f}x)")
        elif mvrv < 1.8:
            cycle_score += 6
            reasons.append(f"MVRV sem euforia ({mvrv:.2f}x)")
        elif mvrv >= 3:
            cycle_score -= 13
            risks.append(f"MVRV esticado ({mvrv:.2f}x)")

    if mayer:
        if mayer < 0.8:
            cycle_score += 9
            reasons.append(f"Mayer descontado ({mayer:.2f}x)")
        elif mayer > 2.4:
            cycle_score -= 12
            risks.append(f"Mayer em zona historicamente esticada ({mayer:.2f}x)")
        elif mayer > 1.7:
            cycle_score -= 6
            risks.append(f"Mayer aquecendo ({mayer:.2f}x)")

    if puell:
        if puell < 0.6:
            cycle_score += 7
            reasons.append(f"Puell em miner stress/acumulacao ({puell:.2f})")
        elif puell > 3:
            cycle_score -= 10
            risks.append(f"Puell em euforia mineradora ({puell:.2f})")
        elif puell > 2:
            cycle_score -= 5
            risks.append(f"Puell aquecendo ({puell:.2f})")

    if aviv:
        if aviv < 0.75:
            cycle_score += 6
            reasons.append(f"AVIV em desconto ({aviv:.2f})")
        elif aviv > 2:
            cycle_score -= 8
            risks.append(f"AVIV esticado ({aviv:.2f})")

    if stable_dom is not None:
        if stable_dom >= 10:
            cycle_score += 5
            reasons.append(f"muito caixa em stablecoins ({stable_dom:.1f}%)")
        elif stable_dom <= 6:
            cycle_score -= 5
            risks.append(f"stable dominance baixa, pouco caixa defensivo ({stable_dom:.1f}%)")

    btc_change = safe_float((btc_asset or {}).get("change_pct_24h"))
    btc_trend = safe_float((btc_asset or {}).get("trend_80h_pct"))
    eth_change = safe_float((eth_asset or {}).get("change_pct_24h"))
    momentum_score = 0.0
    if btc_change > 0 and btc_trend > 0:
        momentum_score += 8
        reasons.append(f"momentum BTC confirma ({btc_change:+.2f}% 24h, {btc_trend:+.2f}% 80h)")
    elif btc_change < -2 and btc_trend < -3:
        momentum_score -= 8
        risks.append(f"momentum BTC ainda negativo ({btc_change:+.2f}% 24h)")
    if eth_change > btc_change:
        momentum_score += 4
        reasons.append("ETH lidera BTC no curto prazo, sinal de apetite por beta")
    if breadth_delta > 0:
        momentum_score += 5
        reasons.append("breadth cripto positiva")
    elif breadth_delta < 0:
        momentum_score -= 5
        risks.append("breadth cripto negativa")
    if funding_pressure:
        momentum_score -= 8
        risks.append("funding esticado aumenta risco de desalavancagem")

    final_score = max(0.0, min(100.0, cycle_score + momentum_score))
    if final_score >= 72:
        action = "ACUMULAR"
        bias = "Acumular medo/desconto"
        crypto_pct, usdt_pct = 75, 25
        risk = "Baixo/medio"
        condition = "Reduzir se MVRV/Fear & Greed aquecerem ou USDT.D cair demais."
    elif final_score >= 58:
        action = "ACUMULAR SELETIVO"
        bias = "Seguir tendencia saudavel"
        crypto_pct, usdt_pct = 60, 40
        risk = "Medio"
        condition = "Aumentar apenas em pullbacks ou com USDT.D caindo sem euforia."
    elif final_score >= 43:
        action = "NEUTRO"
        bias = "Aguardar assimetria"
        crypto_pct, usdt_pct = 45, 55
        risk = "Medio"
        condition = "Comprar medo/desconto; vender se euforia/on-chain esticar."
    elif final_score >= 28:
        action = "REALIZAR PARCIAL"
        bias = "Reduzir beta"
        crypto_pct, usdt_pct = 30, 70
        risk = "Medio/alto"
        condition = "Voltar a acumular se medo aumentar e MVRV voltar a zona saudavel."
    else:
        action = "FAZER CAIXA USDT"
        bias = "Vender caro / proteger lucro"
        crypto_pct, usdt_pct = 15, 85
        risk = "Alto"
        condition = "Priorizar caixa ate euforia aliviar e aparecer desconto de ciclo."

    btc_pct = round(crypto_pct * 0.55)
    eth_pct = round(crypto_pct * 0.20)
    alts_pct = max(0, crypto_pct - btc_pct - eth_pct)
    return {
        "action": action,
        "bias": bias,
        "score": round(final_score, 1),
        "cycle_score": round(cycle_score, 1),
        "momentum_score": round(momentum_score, 1),
        "crypto_pct": crypto_pct,
        "usdt_pct": usdt_pct,
        "btc_pct": btc_pct,
        "eth_pct": eth_pct,
        "alts_pct": alts_pct,
        "risk": risk,
        "reason": "; ".join(reasons[:3]) or "sem assimetria clara de ciclo",
        "risk_note": "; ".join(risks[:3]) or "sem risco extremo dominante",
        "condition": condition,
    }


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
    bgeometrics_payload: dict[str, Any] | None = None,
    save_file: bool = True,
) -> dict[str, Any]:
    assets = list(_asset_map(binance_payload).values())
    asset_by_symbol = _asset_map(binance_payload)
    gecko = (coingecko_payload or {}).get("data") or {}
    fear = ((fear_payload or {}).get("data") or {}).get("current") or {}
    defi = (defillama_payload or {}).get("data") or {}
    onchain = (bgeometrics_payload or {}).get("data") or {}

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
    stable_dom = None
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

    mvrv_z = safe_float(onchain.get("mvrv_z_score"))
    mvrv = safe_float(onchain.get("mvrv"))
    mayer = safe_float(onchain.get("mayer_multiple"))
    puell = safe_float(onchain.get("puell_multiple"))
    aviv = safe_float(onchain.get("aviv"))
    fear_onchain = safe_float(onchain.get("fear_greed"))
    active_addresses = safe_float(onchain.get("active_addresses"))
    hashrate = safe_float(onchain.get("hashrate"))
    if mvrv_z:
        if mvrv_z >= 7:
            score -= 14
            alerts.append(f"MVRV Z-Score em euforia de ciclo ({mvrv_z:.2f})")
            negative.append("On-chain sugere risco assimetrico de topo no Bitcoin")
        elif mvrv_z >= 4:
            score -= 7
            negative.append(f"MVRV Z-Score aquecido ({mvrv_z:.2f})")
        elif mvrv_z <= 0:
            score += 8
            positive.append(f"MVRV Z-Score em zona de acumulacao ({mvrv_z:.2f})")
        elif mvrv_z <= 2:
            score += 3
            positive.append(f"MVRV Z-Score saudavel para ciclo ({mvrv_z:.2f})")
        else:
            positive.append(f"MVRV Z-Score neutro/aquecendo ({mvrv_z:.2f})")
        if mvrv:
            positive.append(f"MVRV BTC {mvrv:.2f}x")
    else:
        missing.append("MVRV Z-Score BGeometrics")

    if mayer:
        if mayer < 0.8:
            score += 5
            positive.append(f"Mayer Multiple descontado ({mayer:.2f}x)")
        elif mayer > 2.4:
            score -= 8
            negative.append(f"Mayer Multiple esticado ({mayer:.2f}x)")
        elif mayer > 1.7:
            score -= 3
            negative.append(f"Mayer Multiple aquecendo ({mayer:.2f}x)")
        else:
            positive.append(f"Mayer Multiple controlado ({mayer:.2f}x)")
    else:
        missing.append("Mayer Multiple")

    if puell:
        if puell < 0.6:
            score += 5
            positive.append(f"Puell Multiple em zona de miner stress/acumulacao ({puell:.2f})")
        elif puell > 3.0:
            score -= 8
            negative.append(f"Puell Multiple em zona de euforia mineradora ({puell:.2f})")
        elif puell > 2.0:
            score -= 3
            negative.append(f"Puell Multiple aquecendo ({puell:.2f})")
        else:
            positive.append(f"Puell Multiple sem estresse de topo ({puell:.2f})")
    else:
        missing.append("Puell Multiple")

    if aviv:
        if aviv < 0.75:
            score += 4
            positive.append(f"AVIV descontado ({aviv:.2f})")
        elif aviv > 2.0:
            score -= 6
            negative.append(f"AVIV esticado ({aviv:.2f})")
        else:
            positive.append(f"AVIV neutro/saudavel ({aviv:.2f})")
    else:
        missing.append("AVIV")

    if fear_onchain and not fear_value:
        if fear_onchain <= 25:
            score -= 5
            alerts.append(f"Fear & Greed BGeometrics em medo ({fear_onchain:.0f})")
        elif fear_onchain >= 75:
            score += 3
            alerts.append(f"Fear & Greed BGeometrics em ganancia ({fear_onchain:.0f})")

    if active_addresses:
        positive.append(f"Enderecos ativos BTC: {active_addresses/1000:.0f} mil")
    if hashrate:
        positive.append(f"Hashrate BTC monitorado: {hashrate/1_000_000:.0f} EH/s")

    score = max(0, min(100, score))
    confidence = max(25, min(95, 100 - len(missing) * 10))
    regime = _classify(score, fear_value, funding_pressure)
    bias = _bias_from_regime(regime, score)
    summary = _build_summary(regime, score, positive, negative, alerts, stable_dom, btc_dom, eth_dom)
    allocation = _cycle_allocation_decision(
        score=score,
        fear_value=fear_value,
        mvrv_z=mvrv_z,
        mvrv=mvrv,
        mayer=mayer,
        puell=puell,
        aviv=aviv,
        stable_dom=stable_dom,
        breadth_delta=breadth_delta,
        btc_asset=asset_by_symbol.get("BTCUSDT"),
        eth_asset=asset_by_symbol.get("ETHUSDT"),
        funding_pressure=funding_pressure,
    )
    result = {
        "source": "TTS Crypto Regime Engine",
        "status": "ok",
        "updated_at": utc_now_iso(),
        "updated_ts": time.time(),
        "score": round(score, 1),
        "confidence": confidence,
        "regime": regime,
        "bias": bias,
        "summary": summary,
        "allocation": allocation,
        "drivers_positive": positive[:8],
        "drivers_negative": negative[:8],
        "alerts": alerts[:8],
        "missing_data": missing,
        "onchain": {
            "mvrv": round(mvrv, 4) if mvrv else None,
            "mvrv_z_score": round(mvrv_z, 4) if mvrv_z else None,
            "mayer_multiple": round(mayer, 4) if mayer else None,
            "puell_multiple": round(puell, 4) if puell else None,
            "aviv": round(aviv, 4) if aviv else None,
            "fear_greed": round(fear_onchain, 2) if fear_onchain else None,
            "active_addresses": round(active_addresses, 2) if active_addresses else None,
            "hashrate": round(hashrate, 2) if hashrate else None,
            "date": onchain.get("date"),
        },
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
