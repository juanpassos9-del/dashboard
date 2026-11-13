"""Free exchange WebSocket overlays for the shared global-market snapshot."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import time
from typing import Any


def _quote(
    asset: str,
    instrument: str,
    market_type: str,
    note: str = "",
    dex: str | None = None,
    quote_unit: str | None = None,
) -> dict[str, str | None]:
    return {
        "asset": asset,
        "instrument": instrument,
        "market_type": market_type,
        "mapping_note": note,
        "dex": dex,
        "quote_unit": quote_unit,
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


def _add_hyperliquid_candidate(
    yahoo_symbol: str,
    instrument: str,
    *,
    dex: str = "",
    note: str,
) -> None:
    candidates = GLOBAL_REALTIME_MAP.setdefault(yahoo_symbol, [])
    candidates.append((
        "Hyperliquid",
        _quote(
            f"HYPERLIQUID:{instrument}",
            instrument,
            f"Perpétuo Hyperliquid{f' · {dex.upper()}' if dex else ''}",
            note,
            dex=dex,
        ),
    ))


for _ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"):
    _add_hyperliquid_candidate(
        _ticker,
        f"xyz:{_ticker}",
        dex="xyz",
        note="Perpétuo sintético HIP-3 referenciado à ação; não é ação à vista.",
    )

for _yahoo_symbol, _coin, _note in (
    ("^GSPC", "xyz:SP500", "Perpétuo sintético referenciado ao S&P 500."),
    ("DX-Y.NYB", "xyz:DXY", "Perpétuo sintético referenciado ao índice DXY."),
    ("EURUSD=X", "xyz:EUR", "Perpétuo sintético EUR; proxy de EUR/USD, não cotação spot."),
    ("GBPUSD=X", "xyz:GBP", "Perpétuo sintético GBP; proxy de GBP/USD, não cotação spot."),
    ("EWZ", "xyz:EWZ", "Perpétuo sintético referenciado ao ETF EWZ."),
    ("XLE", "xyz:XLE", "Perpétuo sintético referenciado ao ETF setorial XLE."),
    ("XBI", "xyz:XBI", "Perpétuo sintético referenciado ao ETF setorial XBI."),
    ("BZ=F", "xyz:BRENTOIL", "Perpétuo sintético de Brent; não é o contrato futuro BZ da CME."),
    ("CL=F", "xyz:CL", "Perpétuo sintético de WTI; instrumento e referência podem divergir do futuro CL."),
    ("NG=F", "xyz:NATGAS", "Perpétuo sintético de gás natural; não é o contrato futuro NG."),
    ("HG=F", "xyz:COPPER", "Perpétuo sintético de cobre; referência não idêntica ao futuro HG."),
    ("GC=F", "xyz:GOLD", "Perpétuo sintético de ouro; não é o contrato futuro GC."),
    ("SI=F", "xyz:SILVER", "Perpétuo sintético de prata; não é o contrato futuro SI."),
    ("PL=F", "xyz:PLATINUM", "Perpétuo sintético de platina; referência não idêntica ao futuro PL."),
    ("PA=F", "xyz:PALLADIUM", "Perpétuo sintético de paládio; referência não idêntica ao futuro PA."),
):
    _add_hyperliquid_candidate(_yahoo_symbol, _coin, dex="xyz", note=_note)

for _symbol, _tenor in (
    ("FRED:DGS2", "2Y"),
    ("^TNX", "10Y"),
    ("^TYX", "30Y"),
    ("US02Y", "2Y"),
    ("US10Y", "10Y"),
    ("US30Y", "30Y"),
):
    GLOBAL_REALTIME_MAP[_symbol] = [("Hyperliquid", _quote(
        f"US{_tenor}",
        f"para:{_tenor}",
        "Perpétuo de yield Hyperliquid · Paragon",
        f"Yield do Treasury dos EUA de {_tenor}, cotado em % ao ano; perpétuo sintético, não preço do título à vista.",
        dex="para",
        quote_unit="yield_percent",
    ))]

for _yahoo_symbol, _coin, _note in (
    ("BTC-USD", "BTC", "Perpétuo cripto Hyperliquid; preço de venue, não índice composto."),
    ("ETH-USD", "ETH", "Perpétuo cripto Hyperliquid; preço de venue, não índice composto."),
    ("SOL-USD", "SOL", "Perpétuo cripto Hyperliquid; preço de venue, não índice composto."),
):
    _add_hyperliquid_candidate(_yahoo_symbol, _coin, note=_note)

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
    ] + [candidate for candidate in GLOBAL_REALTIME_MAP.get(_symbol, ()) if candidate[0] == "Hyperliquid"]


for _asset, _instrument, _market_type in (
    ("ZEC", "ZECUSDT", "Spot"),
    ("JCT", "JCTUSDT", "Perpétuo USDⓈ-M"),
    ("XRP", "XRPUSDT", "Spot"),
    ("HYPE", "HYPEUSDT", "Spot"),
    ("1000PEPE", "1000PEPEUSDT", "Perpétuo USDⓈ-M"),
    ("DOGE", "DOGEUSDT", "Spot"),
    ("NEAR", "NEARUSDT", "Spot"),
    ("BNB", "BNBUSDT", "Spot"),
    ("AVAX", "AVAXUSDT", "Spot"),
    ("ENA", "ENAUSDT", "Spot"),
    ("SUI", "SUIUSDT", "Spot"),
    ("UNI", "UNIUSDT", "Spot"),
    ("WLD", "WLDUSDT", "Spot"),
    ("PUMP", "PUMPUSDT", "Spot"),
    ("AIOT", "AIOTUSDT", "Perpétuo USDⓈ-M"),
    ("HOT", "HOTUSDT", "Spot"),
):
    GLOBAL_REALTIME_MAP[f"TOKENIZED_CRYPTO:{_asset}"] = [
        ("Binance", _quote(_asset, _instrument, _market_type, "Cotação cripto via WebSocket Binance."))
    ]

for _ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"):
    GLOBAL_REALTIME_MAP[f"TOKENIZED_STOCK:{_ticker}"] = GLOBAL_REALTIME_MAP[_ticker]

for _asset, _instrument, _name, _note in (
    ("BINGX_INDEX_H100", "NCSIH1002USD-USDT", "Hang Seng Tech (H100)", "Índice tokenizado da BingX; referência H100, não o Hang Seng amplo."),
    ("BINGX_INDEX_KOSPI", "NCSIKOSPI2USD-USDT", "KOSPI", "Índice tokenizado da BingX."),
    ("BINGX_INDEX_KOSPI1", "NCSIKOSPI12USD-USDT", "KOSPI 200", "Índice tokenizado da BingX."),
):
    GLOBAL_REALTIME_MAP[f"TOKENIZED_INDEX:{_asset}"] = [
        ("BingX", _quote(_asset, _instrument, "Perpétuo", _note))
    ]


TOKENIZED_GLOBAL_INDEX_SYMBOLS = {"^GSPC", "^IXIC", "^DJI", "^RUT", "^N225", "^GDAXI"}
TOKENIZED_SUPPLEMENTAL_QUOTES = [
    ("🪙 CRIPTOMOEDAS · WEBSOCKET", asset, f"TOKENIZED_CRYPTO:{asset}", f"TOKENIZED_CRYPTO:{asset}")
    for asset in ("ZEC", "JCT", "XRP", "HYPE", "1000PEPE", "DOGE", "NEAR", "BNB", "AVAX", "ENA", "SUI", "UNI", "WLD", "PUMP", "AIOT", "HOT")
]
TOKENIZED_SUPPLEMENTAL_QUOTES.extend([
    ("🇺🇸 7 MAGNÍFICAS · TOKENIZADAS", ticker, f"TOKENIZED_STOCK:{ticker}", f"TOKENIZED_STOCK:{ticker}")
    for ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA")
])
TOKENIZED_SUPPLEMENTAL_QUOTES.extend([
    ("🌍 ÍNDICES TOKENIZADOS", name, f"TOKENIZED_INDEX:{asset}", f"TOKENIZED_INDEX:{asset}")
    for asset, _instrument, name, _note in (
        ("BINGX_INDEX_H100", "NCSIH1002USD-USDT", "Hang Seng Tech (H100)", ""),
        ("BINGX_INDEX_KOSPI", "NCSIKOSPI2USD-USDT", "KOSPI", ""),
        ("BINGX_INDEX_KOSPI1", "NCSIKOSPI12USD-USDT", "KOSPI 200", ""),
    )
])


def global_market_subscriptions() -> dict[str, list[dict[str, str | None]]]:
    subscriptions = {"Binance": [], "OKX": [], "BingX": [], "Hyperliquid": []}
    for candidates in GLOBAL_REALTIME_MAP.values():
        for provider, row in candidates:
            subscriptions[provider].append(row)
    return subscriptions


def _apply_live_quote(
    item: dict[str, Any],
    lookup_symbol: str,
    latest_quotes: dict[tuple[str, str, str], dict[str, Any]],
    now: float,
    max_age_seconds: int,
) -> bool:
    for provider, mapping in GLOBAL_REALTIME_MAP.get(lookup_symbol, ()):
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
        mapping_note = mapping.get("mapping_note") or ""
        previous_source = item.get("source")
        live_change = live.get("change_pct_24h")
        live_high = live.get("high_24h")
        live_low = live.get("low_24h")
        item.update({
            "price": price,
            "high": float(live_high) if live_high is not None else item.get("high"),
            "low": float(live_low) if live_low is not None else item.get("low"),
            "high_low_basis": "exchange_rolling_24h" if live_high is not None and live_low is not None else item.get("high_low_basis"),
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
                if "proxy" in str(mapping_note).lower()
                or "equivalência não confirmada" in str(mapping_note).lower()
                else "synthetic_reference"
                if mapping["market_type"] != "Spot"
                else "exchange_reference"
            ),
            "mapping_note": mapping_note,
            "is_realtime": True,
            "data_status": "fresh",
        })
        if live_change is not None:
            item.update({
                "change": float(live_change),
                "change_24h": float(live_change),
                "change_basis": live.get("change_basis") or "exchange_rolling_24h",
            })
        elif previous_source:
            item["change_source"] = previous_source
        if (live_high is None or live_low is None) and previous_source:
            item["high_low_source"] = previous_source
        if mapping.get("quote_unit") == "yield_percent":
            previous_yield = live.get("previous_price")
            if previous_yield is not None:
                item["change_bps"] = round((price - float(previous_yield)) * 100, 2)
            item["quote_unit"] = "percent_per_year"
            item["yield_source"] = f"{provider} {mapping['instrument']}"
        return True
    return False


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
    categories = data.get("categories")
    if not isinstance(categories, dict):
        categories = {}
        data["categories"] = categories

    for assets in categories.values():
        if not isinstance(assets, list):
            continue
        for item in assets:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            if _apply_live_quote(item, symbol, latest_quotes, now, max_age_seconds):
                updated.append(symbol)

    moved_indices = []
    for category_name, assets in list(categories.items()):
        if "ÍNDICES" not in str(category_name).upper() or not isinstance(assets, list):
            continue
        retained = []
        for item in assets:
            symbol = str(item.get("symbol") or "") if isinstance(item, dict) else ""
            if symbol in TOKENIZED_GLOBAL_INDEX_SYMBOLS:
                if not item.get("is_realtime"):
                    candidates = GLOBAL_REALTIME_MAP.get(symbol, ())
                    if candidates:
                        provider, mapping = candidates[0]
                        item["realtime_pending"] = True
                        item["realtime_pending_instrument"] = f"{provider}: {mapping['instrument']}"
                moved_indices.append(item)
            else:
                retained.append(item)
        categories[category_name] = retained
    if moved_indices:
        categories.setdefault("🌍 ÍNDICES TOKENIZADOS", []).extend(moved_indices)

    supplemental_by_category: dict[str, list[dict[str, Any]]] = {}
    for category, name, symbol, lookup_symbol in TOKENIZED_SUPPLEMENTAL_QUOTES:
        display_symbol = symbol.rsplit(":", 1)[-1]
        display_symbol = {
            "BINGX_INDEX_H100": "H100",
            "BINGX_INDEX_KOSPI": "KOSPI",
            "BINGX_INDEX_KOSPI1": "KOSPI 200",
        }.get(display_symbol, display_symbol)
        item = {"name": name, "symbol": symbol, "display_symbol": display_symbol}
        if _apply_live_quote(item, lookup_symbol, latest_quotes, now, max_age_seconds):
            supplemental_by_category.setdefault(category, []).append(item)
            updated.append(symbol)
        else:
            candidates = GLOBAL_REALTIME_MAP.get(lookup_symbol, ())
            if candidates:
                provider, mapping = candidates[0]
                item.update({
                    "price": None,
                    "change": None,
                    "source": "Aguardando WebSocket",
                    "source_symbol": mapping["instrument"],
                    "market_type": mapping["market_type"],
                    "exchange": provider,
                    "realtime_pending": True,
                    "realtime_pending_instrument": f"{provider}: {mapping['instrument']}",
                })
            supplemental_by_category.setdefault(category, []).append(item)
    for category, items in supplemental_by_category.items():
        categories.setdefault(category, []).extend(items)

    unique_updated = sorted(set(updated))
    if not isinstance(data.get("metadata"), dict):
        data["metadata"] = {}
    data["metadata"]["realtime_overlay"] = {
        "source": "Binance/OKX/BingX/Hyperliquid public WebSocket",
        "updated_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "quotes_updated": len(unique_updated),
        "symbols": unique_updated,
        "max_tick_age_seconds": max_age_seconds,
    }
    return data
