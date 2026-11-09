"""Consolidated public crypto quotes with Binance-first exchange fallbacks."""

from __future__ import annotations

import time
import re
from typing import Any

from execution.crypto_common import request_json, safe_float

ASSETS = [
    "BTC", "ETH", "ZEC", "SOL", "JCT", "XRP", "HYPE", "1000PEPE", "DOGE", "NEAR",
    "BNB", "ON", "AVAX", "ENA", "SUI", "UNI", "WLD", "PUMP", "AIOT", "HOT",
]
COMMODITIES = ["XAU", "XAG", "BZ", "CL", "XPD", "XPT", "COPPER", "NATGAS"]
FX_ASSETS = [
    "AUDJPY", "AUDUSD", "CADCHF", "CADJPY", "CHFJPY", "EURCAD", "EURCHF", "EURGBP", "EURJPY",
    "EURNZD", "EURUSD", "EURSGD", "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD",
    "GBPSGD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCAD", "USDCHF", "USDDKK", "USDJPY", "USDKRW",
    "USDMXN", "USDNOK", "USDPLN", "USDSEK", "USDTHB", "USDTRY", "USDZAR", "USDBRL", "USDSGD",
]
BINGX_FX_INSTRUMENTS = {
    "AUDJPY": "NCFXAUD2JPY-USDT", "AUDUSD": "NCFXAUD2USD-USDT", "CADCHF": "NCFXCAD2CHF-USDT",
    "CADJPY": "NCFXCAD2JPY-USDT", "CHFJPY": "NCFXCHF2JPY-USDT", "EURCAD": "NCFXEUR2CAD-USDT",
    "EURCHF": "NCFXEUR2CHF-USDT", "EURGBP": "NCFXEUR2GBP-USDT", "EURJPY": "NCFXEUR2JPY-USDT",
    "EURNZD": "NCFXEUR2NZD-USDT", "EURUSD": "NCFXEUR2USD-USDT", "EURSGD": "NCFXEURSGD2USD-USDT",
    "GBPAUD": "NCFXGBP2AUD-USDT", "GBPCAD": "NCFXGBP2CAD-USDT", "GBPCHF": "NCFXGBP2CHF-USDT",
    "GBPJPY": "NCFXGBP2JPY-USDT", "GBPNZD": "NCFXGBP2NZD-USDT", "GBPUSD": "NCFXGBP2USD-USDT",
    "GBPSGD": "NCFXGBPSGD2USD-USDT", "NZDCAD": "NCFXNZD2CAD-USDT", "NZDJPY": "NCFXNZD2JPY-USDT",
    "NZDUSD": "NCFXNZD2USD-USDT", "USDCAD": "NCFXUSD2CAD-USDT", "USDCHF": "NCFXUSD2CHF-USDT",
    "USDDKK": "NCFXUSD2DKK-USDT", "USDJPY": "NCFXUSD2JPY-USDT", "USDKRW": "NCFXUSD2KRW-USDT",
    "USDMXN": "NCFXUSD2MXN-USDT", "USDNOK": "NCFXUSD2NOK-USDT", "USDPLN": "NCFXUSD2PLN-USDT",
    "USDSEK": "NCFXUSD2SEK-USDT", "USDTHB": "NCFXUSD2THB-USDT", "USDTRY": "NCFXUSD2TRY-USDT",
    "USDZAR": "NCFXUSD2ZAR-USDT", "USDBRL": "NCFXUSDBRL2USD-USDT", "USDSGD": "NCFXUSDSGD2USD-USDT",
}
SEVEN_MAGNIFICAS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
INDEX_ASSETS = ["SPY", "QQQ", "KORU", "EWY", "TQQQ"]
ASSET_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "ZEC": "Zcash", "SOL": "Solana", "JCT": "JCT",
    "XRP": "XRP", "HYPE": "Hyperliquid", "1000PEPE": "Pepe", "DOGE": "Dogecoin",
    "NEAR": "NEAR Protocol", "BNB": "BNB Chain", "ON": "ON Semiconductor", "AVAX": "Avalanche", "ENA": "Ethena",
    "SUI": "Sui", "UNI": "Uniswap", "WLD": "Worldcoin", "PUMP": "Pump.fun", "AIOT": "AIOT", "HOT": "Holo",
    "XAU": "Ouro", "XAG": "Prata", "BZ": "Brent", "CL": "Petróleo WTI", "XPD": "Paládio",
    "XPT": "Platina", "COPPER": "Cobre", "NATGAS": "Gás Natural",
    "AUDJPY": "Dólar Australiano / Iene", "AUDUSD": "Dólar Australiano / Dólar",
    "CADCHF": "Dólar Canadense / Franco", "CADJPY": "Dólar Canadense / Iene", "CHFJPY": "Franco / Iene",
    "EURCAD": "Euro / Dólar Canadense", "EURCHF": "Euro / Franco", "EURGBP": "Euro / Libra",
    "EURJPY": "Euro / Iene", "EURNZD": "Euro / Dólar Neozelandês", "EURUSD": "Euro / Dólar",
    "EURSGD": "Euro / Dólar de Singapura", "GBPAUD": "Libra / Dólar Australiano",
    "GBPCAD": "Libra / Dólar Canadense", "GBPCHF": "Libra / Franco", "GBPJPY": "Libra / Iene",
    "GBPNZD": "Libra / Dólar Neozelandês", "GBPUSD": "Libra / Dólar", "GBPSGD": "Libra / Dólar de Singapura",
    "NZDCAD": "Dólar Neozelandês / Dólar Canadense", "NZDJPY": "Dólar Neozelandês / Iene",
    "NZDUSD": "Dólar Neozelandês / Dólar", "USDCAD": "Dólar / Dólar Canadense",
    "USDCHF": "Dólar / Franco Suíço", "USDDKK": "Dólar / Coroa Dinamarquesa", "USDJPY": "Dólar / Iene",
    "USDKRW": "Dólar / Won Sul-Coreano", "USDMXN": "Dólar / Peso Mexicano", "USDNOK": "Dólar / Coroa Norueguesa",
    "USDPLN": "Dólar / Zloty", "USDSEK": "Dólar / Coroa Sueca", "USDTHB": "Dólar / Baht",
    "USDTRY": "Dólar / Lira Turca", "USDZAR": "Dólar / Rand", "USDBRL": "Dólar / Real",
    "USDSGD": "Dólar / Dólar de Singapura",
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
    "AUDJPY": "🇦🇺🇯🇵", "AUDUSD": "🇦🇺🇺🇸", "CADCHF": "🇨🇦🇨🇭", "CADJPY": "🇨🇦🇯🇵",
    "CHFJPY": "🇨🇭🇯🇵", "EURCAD": "🇪🇺🇨🇦", "EURCHF": "🇪🇺🇨🇭", "EURGBP": "🇪🇺🇬🇧",
    "EURJPY": "🇪🇺🇯🇵", "EURNZD": "🇪🇺🇳🇿", "EURUSD": "🇪🇺🇺🇸", "EURSGD": "🇪🇺🇸🇬",
    "GBPAUD": "🇬🇧🇦🇺", "GBPCAD": "🇬🇧🇨🇦", "GBPCHF": "🇬🇧🇨🇭", "GBPJPY": "🇬🇧🇯🇵",
    "GBPNZD": "🇬🇧🇳🇿", "GBPUSD": "🇬🇧🇺🇸", "GBPSGD": "🇬🇧🇸🇬", "NZDCAD": "🇳🇿🇨🇦",
    "NZDJPY": "🇳🇿🇯🇵", "NZDUSD": "🇳🇿🇺🇸", "USDCAD": "🇺🇸🇨🇦", "USDCHF": "🇺🇸🇨🇭",
    "USDDKK": "🇺🇸🇩🇰", "USDJPY": "🇺🇸🇯🇵", "USDKRW": "🇺🇸🇰🇷", "USDMXN": "🇺🇸🇲🇽",
    "USDNOK": "🇺🇸🇳🇴", "USDPLN": "🇺🇸🇵🇱", "USDSEK": "🇺🇸🇸🇪", "USDTHB": "🇺🇸🇹🇭",
    "USDTRY": "🇺🇸🇹🇷", "USDZAR": "🇺🇸🇿🇦", "USDSGD": "🇺🇸🇸🇬",
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

BINGX_INDEX_NAMES = {
    "DOWJONES": "Dow Jones", "DXY": "Índice do Dólar", "EWJ": "Ações do Japão",
    "EWY": "Ações da Coreia do Sul", "FLKR": "Ações da Coreia do Sul",
    "H100": "Hang Seng", "KOSPI1": "Kospi 200", "KOSPI": "Kospi",
    "NASDAQ100": "Nasdaq 100", "NIKKEI225": "Nikkei 225",
    "RUSSELL2000": "Russell 2000", "SP500": "S&P 500",
}
BINGX_COMMODITY_NAMES = {
    "NCCO1OILBRENT2USD": ("BRENT", "Petróleo Brent"),
    "NCCO1OILWTI2USD": ("WTI", "Petróleo WTI"),
    "NCCO7241NATGAS2USD": ("NATGAS", "Gás Natural"),
    "NCCO724COPPER2USD": ("COPPER", "Cobre"),
    "NCCOGOLD2USD": ("GOLD", "Ouro"),
    "NCCOHEATINGOIL2USD": ("HEATINGOIL", "Óleo de Aquecimento"),
    "NCCOPALLADIUM2USD": ("PALLADIUM", "Paládio"),
    "NCCOXAG2USD": ("SILVER", "Prata"),
    "NCCOXAGEUR2USD": ("SILVER_EUR", "Prata / Euro"),
    "NCCOXAGJPYUSD": ("SILVER_JPY", "Prata / Iene"),
    "NCCOXAUAUD2USD": ("GOLD_AUD", "Ouro / Dólar Australiano"),
    "NCCOXAUCAD2USD": ("GOLD_CAD", "Ouro / Dólar Canadense"),
    "NCCOXAUCHF2USD": ("GOLD_CHF", "Ouro / Franco Suíço"),
    "NCCOXAUEUR2USD": ("GOLD_EUR", "Ouro / Euro"),
    "NCCOXAUGBP2USD": ("GOLD_GBP", "Ouro / Libra"),
    "NCCOXAUJPY2USD": ("GOLD_JPY", "Ouro / Iene"),
    "NCCOXAUKRW2USD": ("GOLD_KRW", "Ouro / Won Sul-Coreano"),
    "NCCOXAUSGD2USD": ("GOLD_SGD", "Ouro / Dólar de Singapura"),
    "NCCOXAUXAG2USD": ("GOLD_SILVER_RATIO", "Relação Ouro / Prata"),
    "NCCOXAUXPT2USD": ("GOLD_PLATINUM_RATIO", "Relação Ouro / Platina"),
    "NCCOXPT2USD": ("PLATINUM", "Platina"),
    "NCCOXAUZAR2USD": ("GOLD_ZAR", "Ouro / Rand Sul-Africano"),
}


def _bingx_tradfi_identity(instrument: str) -> dict[str, str] | None:
    """Turn BingX's opaque synthetic contract IDs into stable internal assets."""
    symbol = str(instrument).split("-", 1)[0].upper()
    if symbol.startswith("NCSK"):
        ticker = re.sub(r"(?:2(?:USD|JPY|KRW)|USDT)$", "", symbol[4:])
        if not ticker:
            return None
        label = ASSET_NAMES.get(ticker, ticker)
        category = "7 Magníficas" if ticker in SEVEN_MAGNIFICAS else "Ações/ETFs"
        return {
            "asset": f"BINGX_STOCK_{ticker}",
            "display_name": f"{label} · BingX perpétuo",
            "asset_class": category,
            "underlying": ticker,
            "mark": ticker[:2],
        }
    if symbol.startswith("NCSI"):
        code = re.sub(r"2(?:USD|JPY|KRW)$", "", symbol[4:])
        if not code:
            return None
        return {
            "asset": f"BINGX_INDEX_{code}",
            "display_name": f"{BINGX_INDEX_NAMES.get(code, code)} · BingX perpétuo",
            "asset_class": "Índices",
            "underlying": code,
            "mark": "IDX",
        }
    if symbol.startswith("NCCO"):
        identity = BINGX_COMMODITY_NAMES.get(symbol)
        if identity:
            code, label = identity
        else:
            code = re.sub(r"2(?:USD|JPY|KRW)$", "", symbol[4:])
            label = code.replace("_", " ").title()
        if not code:
            return None
        return {
            "asset": f"BINGX_COMMODITY_{code}",
            "display_name": f"{label} · BingX perpétuo",
            "asset_class": "Commodities",
            "underlying": code,
            "mark": "CMD",
        }
    return None


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


def quote_change_direction(previous: float | None, current: float) -> str:
    if previous is None or current == previous:
        return ""
    return "up" if current > previous else "down"


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
            fx_asset = next((asset for asset, instrument in BINGX_FX_INSTRUMENTS.items() if instrument == symbol), None)
            if fx_asset:
                result[fx_asset] = {
                    "price": safe_float(row.get("lastPrice")),
                    "change_pct_24h": safe_float(row.get("priceChangePercent")),
                    "quote_volume_24h": safe_float(row.get("quoteVolume")),
                    "high_24h": safe_float(row.get("highPrice")),
                    "low_24h": safe_float(row.get("lowPrice")),
                    "timestamp_ms": int(safe_float(row.get("closeTime") or row.get("time"))),
                    "instrument": symbol,
                    "market_type": "Índice Forex perpétuo",
                }
                continue
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
    requested_assets = [str(asset).upper() for asset in assets] if assets is not None else None
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

    asset_catalog: dict[str, dict[str, Any]] = {}
    dynamic_crypto_assets: set[str] = set()
    core_assets = list(dict.fromkeys(ASSETS + COMMODITIES + SECURITIES + FX_ASSETS))
    for raw_asset, item in list(provider_data.get("BingX", {}).items()):
        identity = _bingx_tradfi_identity(str(item.get("instrument") or raw_asset))
        if not identity:
            continue
        alias = identity["asset"]
        provider_data["BingX"][alias] = item
        asset_catalog[alias] = {**identity, "dynamic": True, "exchange": "BingX"}

    if requested_assets is None:
        known_tradfi = set(core_assets)
        non_crypto_prefixes = ("NCSK", "NCSI", "NCCO", "NCFX", "BINGX_")
        crypto_assets = set()
        for rows in provider_data.values():
            for asset, item in rows.items():
                if asset.startswith("_") or asset in known_tradfi or asset.startswith(non_crypto_prefixes):
                    continue
                if item.get("price", 0) > 0:
                    crypto_assets.add(asset)
        dynamic_crypto = sorted(
            crypto_assets,
            key=lambda asset: max(
                (safe_float(rows.get(asset, {}).get("quote_volume_24h")) for rows in provider_data.values()),
                default=0,
            ),
            reverse=True,
        )
        dynamic_crypto_assets = set(dynamic_crypto) - set(core_assets)
        assets = list(dict.fromkeys(core_assets + dynamic_crypto + list(asset_catalog)))
    else:
        assets = requested_assets

    for asset in assets:
        if asset not in asset_catalog:
            category = "Cripto" if asset in dynamic_crypto_assets else asset_class(asset)
            asset_catalog[asset] = {
                "display_name": asset_display_name(asset),
                "asset_class": category,
                "dynamic": asset not in core_assets,
                "logo_url": asset_logo_url(asset),
                "mark": asset_fallback_mark(asset),
            }
        else:
            underlying = asset_catalog[asset].get("underlying")
            asset_catalog[asset]["logo_url"] = asset_logo_url(underlying) if underlying else ""

    now_ms = int(time.time() * 1000)
    quotes = []
    unsupported = []
    for asset in assets:
        selected = None
        last_known = None
        provider_order = ("BingX", "Binance", "OKX") if asset in FX_ASSETS else PROVIDERS
        for provider in provider_order:
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
            selected.update({
                "display_name": asset_catalog.get(asset, {}).get("display_name", asset_display_name(asset)),
                "asset_class": asset_catalog.get(asset, {}).get("asset_class", asset_class(asset)),
                "logo_url": asset_catalog.get(asset, {}).get("logo_url", asset_logo_url(asset)),
                "fallback_mark": asset_catalog.get(asset, {}).get("mark", asset_fallback_mark(asset)),
                "dynamic": asset_catalog.get(asset, {}).get("dynamic", False),
            })
            quotes.append(selected)
        else:
            unsupported.append(asset)

    return {
        "quotes": quotes,
        "unsupported": unsupported,
        "provider_errors": provider_errors,
        "asset_catalog": asset_catalog,
        "universe_counts": {
            category: sum(info.get("asset_class") == category for info in asset_catalog.values())
            for category in ("Cripto", "7 Magníficas", "Índices", "Ações/ETFs", "Commodities", "FX")
        },
        "realtime_subscriptions": {
            provider: [
                {
                    "asset": quote.get("asset"),
                    "instrument": str(quote.get("instrument") or ""),
                    "market_type": str(quote.get("market_type") or ""),
                }
                for quote in quotes
                if quote.get("exchange") == provider and quote.get("instrument") and quote.get("price", 0) > 0
            ]
            for provider in PROVIDERS
        },
        "updated_at": time.time(),
        "providers": list(PROVIDERS),
    }
