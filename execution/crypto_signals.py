"""Operational signal helpers for the TTS Crypto Terminal."""

from __future__ import annotations

import math
from typing import Any

try:
    from execution.crypto_common import safe_float
except ModuleNotFoundError:
    from crypto_common import safe_float


def _asset_rows(binance_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return ((binance_payload or {}).get("data") or {}).get("assets") or []


def _coingecko_rows(coingecko_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return ((coingecko_payload or {}).get("data") or {}).get("markets") or []


def _normalized_rows(
    binance_payload: dict[str, Any],
    coingecko_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = [row for row in _asset_rows(binance_payload) if isinstance(row, dict) and row.get("price")]
    if rows:
        return rows

    out = []
    for item in _coingecko_rows(coingecko_payload or {})[:20]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        sparkline = ((item.get("sparkline_in_7d") or {}).get("price") or [])
        candles = []
        start_time = int(safe_float(item.get("last_updated_ts")) or 0)
        if not start_time:
            import time
            start_time = int(time.time())
        if isinstance(sparkline, list):
            for idx, price in enumerate(sparkline[-80:]):
                px = safe_float(price)
                if px <= 0:
                    continue
                candles.append({
                    "time": start_time - (len(sparkline[-80:]) - idx) * 3600,
                    "open": px,
                    "high": px,
                    "low": px,
                    "close": px,
                    "volume": 0,
                })
        out.append({
            "symbol": f"{symbol}USDT",
            "price": safe_float(item.get("current_price")),
            "change_pct_24h": safe_float(item.get("price_change_percentage_24h")),
            "quote_volume": safe_float(item.get("total_volume")),
            "high_24h": safe_float(item.get("high_24h")),
            "low_24h": safe_float(item.get("low_24h")),
            "funding_rate": 0,
            "candles_1h": candles,
            "trend_80h_pct": safe_float(item.get("price_change_percentage_7d_in_currency")),
            "source": "CoinGecko fallback",
        })
    return out


def _returns(candles: list[dict[str, Any]]) -> list[float]:
    closes = [safe_float(row.get("close")) for row in candles if safe_float(row.get("close")) > 0]
    out: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            out.append((closes[i] / closes[i - 1]) - 1)
    return out


def _realized_vol_pct(candles: list[dict[str, Any]]) -> float:
    returns = _returns(candles[-48:])
    if len(returns) < 5:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((ret - mean) ** 2 for ret in returns) / max(1, len(returns) - 1)
    hourly_vol = math.sqrt(max(variance, 0))
    return hourly_vol * math.sqrt(24) * 100


def _range_position(asset: dict[str, Any]) -> float:
    price = safe_float(asset.get("price"))
    high = safe_float(asset.get("high_24h"))
    low = safe_float(asset.get("low_24h"))
    if not price or not high or not low or high <= low:
        return 50.0
    return max(0.0, min(100.0, (price - low) / (high - low) * 100))


def _funding_annual_pct(asset: dict[str, Any]) -> float:
    return safe_float(asset.get("funding_rate")) * 3 * 365 * 100


def build_crypto_operational_dashboard(
    binance_payload: dict[str, Any],
    regime: dict[str, Any],
    coingecko_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = []
    alerts = []
    regime_name = str((regime or {}).get("regime") or "Neutro")
    risk_on = "Risk-on" in regime_name or regime_name == "Euforia"
    risk_off = "Risk-off" in regime_name or regime_name in {"Capitulacao", "Desalavancagem"}

    for asset in _normalized_rows(binance_payload, coingecko_payload):
        symbol = str(asset.get("symbol") or "")
        if not symbol:
            continue
        price = safe_float(asset.get("price"))
        change_24h = safe_float(asset.get("change_pct_24h"))
        trend_80h = safe_float(asset.get("trend_80h_pct"))
        quote_volume = safe_float(asset.get("quote_volume"))
        funding = _funding_annual_pct(asset)
        range_pos = _range_position(asset)
        realized_vol = _realized_vol_pct(asset.get("candles_1h") or [])

        score = 50.0
        score += max(-18, min(18, change_24h * 3))
        score += max(-18, min(18, trend_80h * 2))
        if quote_volume > 1_000_000_000:
            score += 5
        elif quote_volume < 50_000_000:
            score -= 4
        if 0 <= funding <= 25:
            score += 4
        elif funding > 45:
            score -= 8
        elif funding < -10:
            score += 3
        if risk_on:
            score += 5
        if risk_off:
            score -= 5
        score = max(0, min(100, score))

        if score >= 68 and trend_80h > 0 and change_24h > 0:
            bias = "Momentum comprador"
        elif score <= 35 and trend_80h < 0 and change_24h < 0:
            bias = "Pressao vendedora"
        elif range_pos >= 85 and funding > 45:
            bias = "Risco de alavancagem"
        elif range_pos <= 15 and change_24h < 0:
            bias = "Zona de estresse"
        else:
            bias = "Neutro"

        if funding > 60:
            alerts.append(f"{symbol}: funding anualizado muito alto ({funding:.1f}%).")
        if range_pos >= 92:
            alerts.append(f"{symbol}: negociando perto da maxima de 24h.")
        if range_pos <= 8:
            alerts.append(f"{symbol}: negociando perto da minima de 24h.")
        if realized_vol >= 8:
            alerts.append(f"{symbol}: volatilidade realizada elevada ({realized_vol:.1f}%).")

        rows.append({
            "symbol": symbol,
            "price": price,
            "change_24h": round(change_24h, 2),
            "trend_80h": round(trend_80h, 2),
            "quote_volume": quote_volume,
            "funding_annual_pct": round(funding, 2),
            "range_position": round(range_pos, 1),
            "realized_vol_48h_pct": round(realized_vol, 2),
            "score": round(score, 1),
            "bias": bias,
        })

    rows.sort(key=lambda row: row["score"], reverse=True)
    return {
        "leaders": rows[:5],
        "laggards": sorted(rows, key=lambda row: row["score"])[:5],
        "ranking": rows,
        "alerts": alerts[:10],
    }
