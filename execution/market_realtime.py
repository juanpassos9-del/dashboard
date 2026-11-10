"""Free exchange WebSocket overlays for the shared global-market snapshot."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import time
from typing import Any


def _quote(asset: str, instrument: str, market_type: str, note: str = "") -> dict[str, str]:
    return {
        "asset": asset,
        "instrument": instrument,
        "market_type": market_type,
        "mapping_note": note,
    }


GLOBAL_REALTIME_MAP: dict[str, list[tuple[str, dict[str, str]]]] = {
    "BTC-USD": [(provider, _quote("BTC", instrument, "Spot")) for provider, instrument in (
        ("Binance", "BTCUSDT"), ("OKX", "BTC-USDT"), ("BingX", "BTC-USDT"),
    )],
    "ETH-USD": [(provider, _quote("ETH", instrument, "Spot")) for provider, instrument in (
        ("Binance", "ETHUSDT"), ("OKX", "ETH-USDT"), ("BingX", "ETH-USDT"),
    )],
    "SOL-USD": [(provider, _quote("SOL", instrument, "Spot")) for provider, instrument in (
        ("Binance", "SOLUSDT"), ("OKX", "SOL-USDT"), ("BingX", "SOL-USDT"),
    )],
    "^GSPC": [("BingX", _quote("BINGX_INDEX_SP500", "NCSISP5002USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao S&P 500."))],
    "^IXIC": [("BingX", _quote("BINGX_INDEX_NASDAQ100", "NCSINASDAQ1002USD-USDT", "Perpétuo", "Nasdaq 100 perpétuo; proxy do Nasdaq Composite."))],
    "^DJI": [("BingX", _quote("BINGX_INDEX_DOWJONES", "NCSIDOWJONES2USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao Dow Jones."))],
    "^RUT": [("BingX", _quote("BINGX_INDEX_RUSSELL2000", "NCSIRUSSELL20002USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao Russell 2000."))],
    "^N225": [("BingX", _quote("BINGX_INDEX_NIKKEI225", "NCSINIKKEI2252USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao Nikkei 225."))],
    "^GDAXI": [("BingX", _quote("BINGX_INDEX_GER", "NCSIGER2USD-USDT", "Perpétuo", "Índice alemão GER usado como proxy do DAX; equivalência não confirmada."))],
    "DX-Y.NYB": [("BingX", _quote("BINGX_INDEX_DXY", "NCSIDXY2USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao DXY."))],
    "BRL=X": [
        ("Binance", _quote("USDBRL", "USDBRLUSDT", "Perpétuo USDⓈ-M", "Perpétuo USD/BRL; preço cotado em USDT.")),
        ("BingX", _quote("USDBRL", "NCFXUSDBRL2USD-USDT", "Índice Forex perpétuo", "Índice Forex perpétuo de USD/BRL.")),
    ],
    "EURUSD=X": [("BingX", _quote("EURUSD", "NCFXEUR2USD-USDT", "Índice Forex perpétuo"))],
    "GBPUSD=X": [("BingX", _quote("GBPUSD", "NCFXGBP2USD-USDT", "Índice Forex perpétuo"))],
    "JPY=X": [("BingX", _quote("USDJPY", "NCFXUSD2JPY-USDT", "Índice Forex perpétuo"))],
    "AUDUSD=X": [("BingX", _quote("AUDUSD", "NCFXAUD2USD-USDT", "Índice Forex perpétuo"))],
    "CAD=X": [("BingX", _quote("USDCAD", "NCFXUSD2CAD-USDT", "Índice Forex perpétuo"))],
    "CHF=X": [("BingX", _quote("USDCHF", "NCFXUSD2CHF-USDT", "Índice Forex perpétuo"))],
    "EWZ": [(provider, _quote(asset, instrument, market_type)) for provider, asset, instrument, market_type in (
        ("Binance", "EWZ", "EWZUSDT", "Perpétuo USDⓈ-M"),
        ("OKX", "EWZ", "EWZ-USDT-SWAP", "Perpétuo"),
        ("BingX", "BINGX_STOCK_EWZ", "NCSKEWZ2USD-USDT", "Perpétuo"),
    )],
    "EWZS": [(provider, _quote(asset, instrument, market_type)) for provider, asset, instrument, market_type in (
        ("Binance", "EWZS", "EWZSUSDT", "Perpétuo USDⓈ-M"),
        ("OKX", "EWZS", "EWZS-USDT-SWAP", "Perpétuo"),
        ("BingX", "BINGX_STOCK_EWZS", "NCSKEWZS2USD-USDT", "Perpétuo"),
    )],
    "PBR": [("BingX", _quote("BINGX_STOCK_PBR", "NCSKPBR2USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao ADR PBR."))],
    "ITUB": [("BingX", _quote("BINGX_STOCK_ITUB", "NCSKITUB2USD-USDT", "Perpétuo", "Perpétuo sintético referenciado ao ADR ITUB."))],
}

for _symbol, _binance, _okx, _bingx in (
    ("AAPL", "AAPLUSDT", "AAPL-USDT-SWAP", "NCSKAAPL2USD-USDT"),
    ("MSFT", "MSFTUSDT", "MSFT-USDT-SWAP", "NCSKMSFT2USD-USDT"),
    ("GOOGL", "GOOGLUSDT", "GOOGL-USDT-SWAP", "NCSKGOOGL2USD-USDT"),
    ("AMZN", "AMZNUSDT", "AMZN-USDT-SWAP", "NCSKAMZN2USD-USDT"),
    ("META", "METAUSDT", "META-USDT-SWAP", "NCSKMETA2USD-USDT"),
    ("NVDA", "NVDAUSDT", "NVDA-USDT-SWAP", "NCSKNVDA2USD-USDT"),
    ("TSLA", "TSLAUSDT", "TSLA-USDT-SWAP", "NCSKTSLA2USD-USDT"),
):
    GLOBAL_REALTIME_MAP[_symbol] = [
        ("Binance", _quote(_symbol, _binance, "Perpétuo USDⓈ-M")),
        ("OKX", _quote(_symbol, _okx, "Perpétuo")),
        ("BingX", _quote(f"BINGX_STOCK_{_symbol}", _bingx, "Perpétuo")),
    ]

for _symbol, _binance, _okx, _bingx in (
    ("SPY", "SPYUSDT", "SPY-USDT-SWAP", "NCSKSPY2USD-USDT"),
    ("XLE", "XLEUSDT", "XLE-USDT-SWAP", "NCSKXLE2USD-USDT"),
    ("XBI", "XBIUSDT", "XBI-USDT-SWAP", "NCSKXBI2USD-USDT"),
):
    GLOBAL_REALTIME_MAP[_symbol] = [
        ("Binance", _quote(_symbol, _binance, "Perpétuo USDⓈ-M")),
        ("OKX", _quote(_symbol, _okx, "Perpétuo")),
        ("BingX", _quote(f"BINGX_STOCK_{_symbol}", _bingx, "Perpétuo")),
    ]

for _symbol, _instrument in (
    ("XLK", "NCSKXLK2USD-USDT"),
    ("XLP", "NCSKXLP2USD-USDT"),
    ("XLI", "NCSKXLI2USD-USDT"),
):
    GLOBAL_REALTIME_MAP[_symbol] = [("BingX", _quote(f"BINGX_STOCK_{_symbol}", _instrument, "Perpétuo"))]
GLOBAL_REALTIME_MAP["XLV"] = [
    ("OKX", _quote("XLV", "XLV-USDT-SWAP", "Perpétuo")),
    ("BingX", _quote("BINGX_STOCK_XLV", "NCSKXLV2USD-USDT", "Perpétuo")),
]

for _symbol, _aliases in (
    ("BZ=F", (("Binance", "BZ", "BZUSDT", "Perpétuo USDⓈ-M"), ("OKX", "BZ", "BZ-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_BRENT", "NCCO1OILBRENT2USD-USDT", "Perpétuo"))),
    ("CL=F", (("Binance", "CL", "CLUSDT", "Perpétuo USDⓈ-M"), ("OKX", "CL", "CL-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_WTI", "NCCO1OILWTI2USD-USDT", "Perpétuo"))),
    ("NG=F", (("Binance", "NATGAS", "NATGASUSDT", "Perpétuo USDⓈ-M"), ("OKX", "NG", "NG-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_NATGAS", "NCCO7241NATGAS2USD-USDT", "Perpétuo"))),
    ("HG=F", (("Binance", "COPPER", "COPPERUSDT", "Perpétuo USDⓈ-M"), ("BingX", "BINGX_COMMODITY_COPPER", "NCCO724COPPER2USD-USDT", "Perpétuo"))),
    ("GC=F", (("Binance", "XAU", "XAUUSDT", "Perpétuo USDⓈ-M"), ("OKX", "XAU", "XAU-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_GOLD", "NCCOGOLD2USD-USDT", "Perpétuo"))),
    ("SI=F", (("Binance", "XAG", "XAGUSDT", "Perpétuo USDⓈ-M"), ("OKX", "XAG", "XAG-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_SILVER", "NCCOXAG2USD-USDT", "Perpétuo"))),
    ("PL=F", (("Binance", "XPT", "XPTUSDT", "Perpétuo USDⓈ-M"), ("OKX", "XPT", "XPT-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_PLATINUM", "NCCOXPT2USD-USDT", "Perpétuo"))),
    ("PA=F", (("Binance", "XPD", "XPDUSDT", "Perpétuo USDⓈ-M"), ("OKX", "XPD", "XPD-USDT-SWAP", "Perpétuo"), ("BingX", "BINGX_COMMODITY_PALLADIUM", "NCCOPALLADIUM2USD-USDT", "Perpétuo"))),
):
    GLOBAL_REALTIME_MAP[_symbol] = [
        (provider, _quote(alias, instrument, market_type))
        for provider, alias, instrument, market_type in _aliases
    ]


def global_market_subscriptions() -> dict[str, list[dict[str, str]]]:
    subscriptions = {"Binance": [], "OKX": [], "BingX": []}
    for candidates in GLOBAL_REALTIME_MAP.values():
        for provider, row in candidates:
            subscriptions[provider].append(row)
    return subscriptions


def apply_global_realtime_overlay(
    snapshot: dict[str, Any],
    latest_quotes: dict[tuple[str, str, str], dict[str, Any]],
    *,
    now: float | None = None,
    max_age_seconds: int = 20,
) -> dict[str, Any]:
    """Overlay fresh ticks while keeping unsupported snapshot quotes untouched."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("categories"), dict):
        return snapshot
    now = time.time() if now is None else now
    data = deepcopy(snapshot)
    updated = []
    categories = data.get("categories") or {}

    for assets in categories.values():
        if not isinstance(assets, list):
            continue
        for item in assets:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            candidates = GLOBAL_REALTIME_MAP.get(symbol, ())
            for provider, mapping in candidates:
                live = latest_quotes.get((provider, mapping["asset"], mapping["market_type"]))
                if not live:
                    continue
                received_at = float(live.get("received_at") or 0)
                age = max(0.0, now - received_at) if received_at else float("inf")
                try:
                    price = float(live.get("price"))
                except (TypeError, ValueError, OverflowError):
                    continue
                if age > max_age_seconds or price <= 0:
                    continue

                timestamp_ms = int(live.get("timestamp_ms") or 0)
                source_timestamp = (
                    datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
                    if timestamp_ms > 0 else datetime.fromtimestamp(received_at, tz=timezone.utc).isoformat()
                )
                item.update({
                    "price": price,
                    "high": float(live.get("high_24h") or item.get("high") or price),
                    "low": float(live.get("low_24h") or item.get("low") or price),
                    "high_low_basis": "exchange_rolling_24h",
                    "change": float(live.get("change_pct_24h") or 0),
                    "change_24h": float(live.get("change_pct_24h") or 0),
                    "change_basis": "exchange_rolling_24h",
                    "change_5m": item.get("change_5m"),
                    "source": f"{provider} WebSocket",
                    "source_symbol": mapping["instrument"],
                    "source_timestamp": source_timestamp,
                    "timestamp_type": "exchange" if timestamp_ms > 0 else "retrieved_at",
                    "market_delay_seconds": max(0, round(age)),
                    "age_seconds": max(0, round(age)),
                    "updated_at": source_timestamp,
                    "exchange": provider,
                    "market_type": mapping["market_type"],
                    "instrument_type": "spot" if mapping["market_type"] == "Spot" else "synthetic_perpetual",
                    "reference_type": (
                        "proxy"
                        if "proxy" in str(mapping.get("mapping_note") or "").lower()
                        or "equivalência não confirmada" in str(mapping.get("mapping_note") or "").lower()
                        else "synthetic_reference"
                        if mapping["market_type"] != "Spot"
                        else "exchange_reference"
                    ),
                    "mapping_note": mapping.get("mapping_note") or "",
                    "is_realtime": True,
                    "data_status": "fresh",
                })
                updated.append(symbol)
                break

    unique_updated = sorted(set(updated))
    if not isinstance(data.get("metadata"), dict):
        data["metadata"] = {}
    data["metadata"]["realtime_overlay"] = {
        "source": "Binance/OKX/BingX public WebSocket",
        "updated_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "quotes_updated": len(unique_updated),
        "symbols": unique_updated,
        "max_tick_age_seconds": max_age_seconds,
    }
    return data
