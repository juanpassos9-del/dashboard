"""Consolidated public crypto quotes with Binance-first exchange fallbacks."""

from __future__ import annotations

import time
from typing import Any

from execution.crypto_common import request_json, safe_float

ASSETS = [
    "BTC", "ETH", "ZEC", "SOL", "JCT", "XRP", "HYPE", "1000PEPE", "DOGE", "NEAR",
    "BNB", "ON", "AVAX", "ENA", "SUI", "UNI", "WLD", "PUMP", "AIOT", "HOT",
]
COMMODITIES = ["XAU", "XAG", "BZ", "CL", "XPD", "XPT", "COPPER", "NATGAS"]
FX_ASSETS = ["USDBRL"]
SEVEN_MAGNIFICAS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
INDEX_ASSETS = ["SPY", "QQQ", "KORU", "EWY", "TQQQ"]
ASSET_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "ZEC": "Zcash", "SOL": "Solana", "JCT": "JCT",
    "XRP": "XRP", "HYPE": "Hyperliquid", "1000PEPE": "Pepe", "DOGE": "Dogecoin",
    "NEAR": "NEAR Protocol", "BNB": "BNB Chain", "ON": "ON Semiconductor", "AVAX": "Avalanche", "ENA": "Ethena",
    "SUI": "Sui", "UNI": "Uniswap", "WLD": "Worldcoin", "PUMP": "Pump.fun", "AIOT": "AIOT", "HOT": "Holo",
    "XAU": "Ouro", "XAG": "Prata", "BZ": "Brent", "CL": "Petróleo WTI", "XPD": "Paládio",
    "XPT": "Platina", "COPPER": "Cobre", "NATGAS": "Gás Natural", "USDBRL": "Dólar / Real",
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "KORU": "Coreia do Sul", "EWY": "Coreia do Sul",
    "TQQQ": "Nasdaq 100 3x", "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta", "NVDA": "NVIDIA", "TSLA": "Tesla", "V": "Visa",
    "BE": "Bloom Energy", "BX": "Blackstone", "GS": "Goldman Sachs", "HD": "Home Depot",
    "KO": "Coca-Cola", "MP": "MP Materials", "MU": "Micron", "ZM": "Zoom", "ZS": "Zscaler",
    "ACN": "Accenture", "AMC": "AMC", "AMD": "AMD", "APP": "AppLovin", "ARM": "Arm",
    "SOXL": "Semicondutores 3x", "SNDK": "SanDisk", "SKHYNIX": "SK Hynix", "SOXS": "Semicondutores -3x",
    "SPCX": "SPCX", "SKHY": "SKHY", "SNXX": "SanDisk 2x", "INTC": "Intel", "MSTR": "Strategy",
    "SAMSUNG": "Samsung", "DRAM": "DRAM",
}
ASSET_LOGO_SLUGS = {
    "XAU": "gold", "XAG": "silver", "CL": "crude-oil", "NATGAS": "natural-gas",
    "AAPL": "apple", "MSFT": "microsoft", "GOOGL": "alphabet", "AMZN": "amazon", "META": "meta",
    "NVDA": "nvidia", "TSLA": "tesla", "V": "visa", "BE": "bloom-energy", "BX": "blackstone",
    "GS": "goldman-sachs", "HD": "home-depot", "KO": "coca-cola", "MP": "mp-materials",
    "MU": "micron-technology", "ZM": "zoom-video-communications", "ZS": "zscaler", "ACN": "accenture",
    "AMD": "advanced-micro-devices", "APP": "applovin", "SNDK": "sandisk", "INTC": "intel",
    "AMC": "amctheatres", "ARM": "arm", "SKHYNIX": "skhynix", "MSTR": "strategy",
    "SAMSUNG": "samsung", "SOXL": "direxion", "SOXS": "direxion", "TQQQ": "proshares",
    "SPY": "ssga", "QQQ": "invesco", "KORU": "ishares", "EWY": "ishares",
}
CRYPTO_LOGO_IDS = {
    "BTC": "btc", "ETH": "eth", "ZEC": "zec", "SOL": "sol", "XRP": "xrp", "HYPE": "hype",
    "1000PEPE": "pepe", "DOGE": "doge", "NEAR": "near", "BNB": "bnb", "AVAX": "avax",
    "ENA": "ena", "SUI": "sui", "UNI": "uni", "WLD": "wld", "PUMP": "pump", "HOT": "hot",
}
COMPANY_DOMAINS = {
    "AAPL": "apple.com", "MSFT": "microsoft.com", "GOOGL": "google.com", "AMZN": "amazon.com",
    "META": "meta.com", "NVDA": "nvidia.com", "TSLA": "tesla.com", "V": "visa.com",
    "BE": "bloomenergy.com", "BX": "blackstone.com", "GS": "goldmansachs.com", "HD": "homedepot.com",
    "KO": "coca-cola.com", "MP": "mpmaterials.com", "MU": "micron.com", "ZM": "zoom.us",
    "ZS": "zscaler.com", "ACN": "accenture.com", "AMC": "amctheatres.com", "AMD": "amd.com",
    "APP": "applovin.com", "ARM": "arm.com", "SNDK": "sandisk.com", "SKHYNIX": "skhynix.com",
    "INTC": "intel.com", "MSTR": "strategy.com", "SAMSUNG": "samsung.com",
}
ASSET_FALLBACK_MARKS = {
    "SPY": "🇺🇸", "QQQ": "🇺🇸", "KORU": "🇰🇷", "EWY": "🇰🇷", "TQQQ": "🇺🇸", "USDBRL": "🇧🇷",
    "XPD": "Pd", "XPT": "Pt", "COPPER": "Cu", "BZ": "Br", "XAU": "Au", "XAG": "Ag", "CL": "◉", "NATGAS": "N",
}
SECURITIES = [
    "SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "V", "BE", "BX",
    "GS", "HD", "KO", "MP", "MU", "ZM", "ZS", "ACN", "AMC", "AMD", "APP", "ARM",
    "SOXL", "SNDK", "SKHYNIX", "SOXS", "KORU", "SPCX", "SKHY", "SNXX", "INTC", "MSTR", "TQQQ", "EWY",
    "SAMSUNG", "DRAM",
]
TRADFI_ASSETS = set(COMMODITIES + SECURITIES + FX_ASSETS)
PROVIDERS = ("Binance", "OKX", "BingX")
MAX_QUOTE_AGE_SECONDS = 180


def asset_class(asset: str) -> str:
    if asset in ASSETS:
        return "Cripto"
    if asset in SEVEN_MAGNIFICAS:
        return "7 Magníficas"
    if asset in INDEX_ASSETS:
        return "Índices"
    if asset in COMMODITIES:
        return "Commodities"
    if asset in FX_ASSETS:
        return "FX"
    return "Ações/ETFs"


def asset_display_name(asset: str) -> str:
    return ASSET_NAMES.get(asset, asset)


def asset_logo_url(asset: str) -> str:
    if asset in ASSETS:
        logo_id = CRYPTO_LOGO_IDS.get(asset)
        return f"https://assets.coincap.io/assets/icons/{logo_id}@2x.png" if logo_id else ""
    domain = COMPANY_DOMAINS.get(asset)
    if domain:
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    slug = ASSET_LOGO_SLUGS.get(asset)
    return f"https://www.google.com/s2/favicons?domain={slug}.com&sz=64" if slug else ""


def asset_fallback_mark(asset: str) -> str:
    return ASSET_FALLBACK_MARKS.get(asset, "ETF" if asset in SECURITIES or asset in INDEX_ASSETS else "◆")


def _binance_tickers() -> dict[str, dict[str, Any]]:
    result = {}
    warnings = []

    spot_urls = (
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api-gcp.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr",
    )
    spot_rows = None
    spot_errors = []
    for url in spot_urls:
        try:
            spot_rows, _ = request_json(url, timeout=8)
            if isinstance(spot_rows, list):
                break
            spot_errors.append(f"{url}: resposta inesperada")
            spot_rows = None
        except Exception as exc:
            spot_errors.append(f"{url}: {str(exc)[:120]}")
    if spot_rows is None:
        warnings.append("Spot Binance indisponível; " + " | ".join(spot_errors[-2:]))
    else:
        if spot_errors:
            warnings.append("Host primário de Spot falhou; conexão feita por host alternativo.")
        for row in spot_rows:
            symbol = str(row.get("symbol") or "")
            if symbol.endswith("USDT"):
                base = symbol[:-4]
                result[base] = {
                    "price": safe_float(row.get("lastPrice")),
                    "change_pct_24h": safe_float(row.get("priceChangePercent")),
                    "quote_volume_24h": safe_float(row.get("quoteVolume")),
                    "high_24h": safe_float(row.get("highPrice")),
                    "low_24h": safe_float(row.get("lowPrice")),
                    "timestamp_ms": int(safe_float(row.get("closeTime"))),
                    "instrument": symbol,
                    "market_type": "Spot",
                }

    try:
        futures_rows, _ = request_json("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10)
        if not isinstance(futures_rows, list):
            raise ValueError("resposta inesperada do endpoint USDⓈ-M")
    except Exception as exc:
        futures_rows = None
        warnings.append(f"Futuros USDⓈ-M Binance indisponível: {str(exc)[:180]}")

    for row in futures_rows or []:
        symbol = str(row.get("symbol") or "")
        if not symbol.endswith("USDT"):
            continue
        base = symbol[:-4]
        if base not in TRADFI_ASSETS and base in result:
            continue
        result[base] = {
            "price": safe_float(row.get("lastPrice")),
            "change_pct_24h": safe_float(row.get("priceChangePercent")),
            "quote_volume_24h": safe_float(row.get("quoteVolume")),
            "high_24h": safe_float(row.get("highPrice")),
            "low_24h": safe_float(row.get("lowPrice")),
            "timestamp_ms": int(safe_float(row.get("closeTime"))),
            "instrument": symbol,
            "market_type": "Perpétuo USDⓈ-M",
        }
    if not result:
        raise RuntimeError("Binance Spot e USDⓈ-M sem dados. " + " | ".join(warnings))
    if warnings:
        result["_warnings"] = warnings
    return result


def _bingx_tickers() -> dict[str, dict[str, Any]]:
    result = {}
    endpoints = (
        ("https://open-api.bingx.com/openApi/spot/v1/ticker/24hr", "Spot"),
        ("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", "Perpétuo"),
    )
    for url, market_type in endpoints:
        data, _ = request_json(url, timeout=10)
        rows = data.get("data", []) if isinstance(data, dict) else []
        for row in rows if isinstance(rows, list) else []:
            symbol = str(row.get("symbol") or "")
            if not symbol.endswith("-USDT"):
                continue
            base = symbol[:-5]
            if market_type == "Perpétuo" and base in result:
                continue
            result[base] = {
                "price": safe_float(row.get("lastPrice")),
                "change_pct_24h": safe_float(row.get("priceChangePercent")),
                "quote_volume_24h": safe_float(row.get("quoteVolume")),
                "high_24h": safe_float(row.get("highPrice")),
                "low_24h": safe_float(row.get("lowPrice")),
                "timestamp_ms": int(safe_float(row.get("closeTime") or row.get("time"))),
                "instrument": symbol,
                "market_type": market_type,
            }
    return result


def _okx_tickers() -> dict[str, dict[str, Any]]:
    result = {}
    for inst_type in ("SPOT", "SWAP"):
        data, _ = request_json(
            "https://www.okx.com/api/v5/market/tickers",
            params={"instType": inst_type},
            timeout=10,
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        for row in rows if isinstance(rows, list) else []:
            symbol = str(row.get("instId") or "")
            suffix = "-USDT-SWAP" if inst_type == "SWAP" else "-USDT"
            if not symbol.endswith(suffix):
                continue
            base = symbol[:-len(suffix)]
            if inst_type == "SWAP" and base in result:
                continue
            last = safe_float(row.get("last"))
            open_24h = safe_float(row.get("open24h"))
            result[base] = {
                "price": last,
                "change_pct_24h": ((last / open_24h) - 1) * 100 if open_24h else 0.0,
                "quote_volume_24h": safe_float(row.get("volCcy24h")),
                "high_24h": safe_float(row.get("high24h")),
                "low_24h": safe_float(row.get("low24h")),
                "timestamp_ms": int(safe_float(row.get("ts"))),
                "instrument": symbol,
                "market_type": "Spot" if inst_type == "SPOT" else "Perpétuo",
            }
    return result


def fetch_cryptodash_quotes(assets: list[str] | None = None) -> dict[str, Any]:
    """Fetch each exchange in priority order and fill missing/stale quotes."""
    assets = [str(asset).upper() for asset in (assets or ASSETS + COMMODITIES + SECURITIES + FX_ASSETS)]
    loaders = (("Binance", _binance_tickers), ("OKX", _okx_tickers), ("BingX", _bingx_tickers))
    provider_data: dict[str, dict[str, dict[str, Any]]] = {}
    provider_errors: dict[str, str] = {}
    for provider, loader in loaders:
        try:
            loaded = loader()
            warnings = loaded.pop("_warnings", [])
            provider_data[provider] = loaded
            if warnings:
                provider_errors[provider] = " | ".join(str(warning) for warning in warnings)
        except Exception as exc:
            provider_errors[provider] = str(exc)[:240]
            provider_data[provider] = {}

    now_ms = int(time.time() * 1000)
    quotes = []
    unsupported = []
    for asset in assets:
        selected = None
        last_known = None
        for provider in PROVIDERS:
            item = provider_data[provider].get(asset)
            if not item or item.get("price", 0) <= 0:
                continue
            stamp = int(item.get("timestamp_ms") or 0)
            age = max(0, (now_ms - stamp) / 1000) if stamp else 0
            if stamp and age > MAX_QUOTE_AGE_SECONDS:
                if last_known is None or age < last_known["age_seconds"]:
                    last_known = {
                        "asset": asset,
                        **item,
                        "exchange": provider,
                        "age_seconds": round(age),
                        "stale": True,
                    }
                continue
            selected = {
                "asset": asset,
                **item,
                "exchange": provider,
                "age_seconds": round(age) if stamp else None,
                "stale": False,
            }
            break
        if selected is None:
            selected = last_known
        if selected:
            quotes.append(selected)
        else:
            unsupported.append(asset)

    return {
        "quotes": quotes,
        "unsupported": unsupported,
        "provider_errors": provider_errors,
        "updated_at": time.time(),
        "providers": list(PROVIDERS),
    }
