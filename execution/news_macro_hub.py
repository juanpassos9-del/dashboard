"""Macro news hub for Market Report.

Collects public/open headlines from priority market sources, normalizes them,
and classifies impact, macro theme, affected assets and risk bias.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import requests

from execution.fetch_gdelt_news import _parse_gdelt_datetime

BR_TZ = ZoneInfo("America/Sao_Paulo")
CACHE_DIR = ".tmp"
CACHE_FILE = os.path.join(CACHE_DIR, "news_macro_hub.json")
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

RSS_SOURCES = {
    "Bloomberg": ("nivel_1", "https://feeds.bloomberg.com/markets/news.rss"),
    "CNBC": ("nivel_1", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    "Federal Reserve": ("nivel_1", "https://www.federalreserve.gov/feeds/press_all.xml"),
    "ECB": ("nivel_1", "https://www.ecb.europa.eu/rss/press.html"),
    "Banco Central do Brasil": ("nivel_1", "https://www.bcb.gov.br/rss/bcbnoticias.xml"),
    "U.S. Treasury": ("nivel_1", "https://home.treasury.gov/news/press-releases/rss"),
    "IMF": ("nivel_1", "https://www.imf.org/en/News/rss"),
    "World Bank": ("nivel_1", "https://www.worldbank.org/en/news/all?format=rss"),
    "Investing": ("nivel_2", "https://www.investing.com/rss/news_25.rss"),
    "CME Group": ("nivel_2", "https://www.cmegroup.com/rss/press-releases.xml"),
    "Nasdaq": ("nivel_2", "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),
    "CoinDesk": ("nivel_2", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
}

GDELT_QUERIES = {
    "Reuters": (
        "nivel_1",
        'domainis:reuters.com (markets OR stocks OR Fed OR inflation OR Treasury OR dollar OR oil OR China OR Brazil)',
    ),
    "Financial Times": (
        "nivel_1",
        'domainis:ft.com (markets OR central banks OR inflation OR bonds OR commodities OR Brazil OR China)',
    ),
    "Wall Street Journal": (
        "nivel_1",
        'domainis:wsj.com (markets OR economy OR Fed OR inflation OR bonds OR oil OR China)',
    ),
    "Trading Economics": (
        "nivel_2",
        'domainis:tradingeconomics.com (calendar OR inflation OR interest rate OR GDP OR PMI OR unemployment)',
    ),
    "B3": (
        "nivel_2",
        'domainis:b3.com.br (mercado OR bolsa OR juros OR futuro OR derivativos OR investidores)',
    ),
    "NYSE": (
        "nivel_2",
        'domainis:nyse.com (markets OR listing OR trading OR volatility)',
    ),
    "The Block": (
        "nivel_2",
        'domainis:theblock.co (bitcoin OR ethereum OR crypto OR ETF OR stablecoin)',
    ),
}

THEME_RULES = [
    ("Fed/Juros EUA", ["fed", "fomc", "powell", "treasury", "yield", "rate cut", "rate hike", "bostic", "waller"]),
    ("Inflação", ["inflation", "cpi", "ppi", "pce", "prices", "breakeven", "inflação", "ipca"]),
    ("Atividade", ["payroll", "jobs", "unemployment", "pmi", "ism", "gdp", "retail sales", "industrial production"]),
    ("Petróleo/Energia", ["oil", "crude", "brent", "wti", "opec", "gas", "refinery", "energia", "petróleo"]),
    ("China", ["china", "pboc", "yuan", "property", "exports", "imports", "beijing"]),
    ("Brasil", ["brazil", "brasil", "bcb", "copom", "selic", "fiscal", "ibovespa", "petrobras", "vale"]),
    ("Geopolítica", ["war", "sanction", "tariff", "iran", "israel", "russia", "ukraine", "taiwan", "geopolitical"]),
    ("Cripto", ["bitcoin", "ethereum", "crypto", "stablecoin", "etf", "solana"]),
    ("Crédito", ["credit", "high yield", "investment grade", "default", "cds", "spread"]),
]

ASSET_RULES = [
    ("US10Y/US30Y", ["fed", "treasury", "yield", "rate", "inflation", "cpi", "pce", "bond"]),
    ("DXY", ["dollar", "fed", "yield", "euro", "yen", "yuan", "fx"]),
    ("S&P/Nasdaq", ["stocks", "wall street", "nasdaq", "s&p", "risk", "earnings", "tech"]),
    ("Petróleo", ["oil", "crude", "brent", "wti", "opec", "iran", "refinery"]),
    ("Ouro", ["gold", "safe haven", "real yield", "war", "geopolitical"]),
    ("Ibov/USDBRL", ["brazil", "brasil", "bcb", "copom", "selic", "fiscal", "petrobras", "vale"]),
    ("Cripto", ["bitcoin", "ethereum", "crypto", "stablecoin", "solana"]),
]

HIGH_IMPACT_TERMS = [
    "fed", "fomc", "powell", "inflation", "cpi", "pce", "payroll", "treasury", "yield",
    "rate cut", "rate hike", "oil", "opec", "war", "sanction", "tariff", "china",
    "brazil", "bcb", "copom", "selic", "fiscal", "bitcoin", "etf",
]

NOISE_TERMS = [
    "sports", "celebrity", "movie", "music", "crime", "viral", "entertainment",
    "football", "soccer", "tennis", "wedding",
]


def _clean_text(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _load_cache() -> dict[str, Any]:
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(payload: dict[str, Any]) -> None:
    try:
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _make_id(source: str, title: str, link: str = "") -> str:
    digest = hashlib.md5(f"{source}|{title}|{link}".encode("utf-8")).hexdigest()[:14]
    return f"macrohub_{digest}"


def _parse_rss_datetime(entry) -> datetime:
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _source_weight(level: str) -> int:
    return {"nivel_1": 20, "nivel_2": 12, "nivel_3": 7}.get(level, 5)


def _classify(item: dict[str, Any]) -> dict[str, Any] | None:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if any(term in text for term in NOISE_TERMS):
        return None

    themes = [name for name, terms in THEME_RULES if any(term in text for term in terms)]
    assets = [name for name, terms in ASSET_RULES if any(term in text for term in terms)]
    keyword_score = sum(4 for term in HIGH_IMPACT_TERMS if term in text)
    recency_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - float(item.get("timestamp", 0))) / 3600)
    recency_score = max(0, 12 - recency_hours * 1.5)
    score = _source_weight(str(item.get("level", ""))) + keyword_score + recency_score + len(themes) * 2 + len(assets) * 2
    impact = "ALTO" if score >= 38 else ("MEDIO" if score >= 25 else "BAIXO")

    risk_off_terms = ["war", "sanction", "tariff", "inflation", "rate hike", "yield rise", "oil jumps", "default"]
    risk_on_terms = ["rate cut", "stimulus", "cooling inflation", "soft landing", "ceasefire", "growth rebounds"]
    if any(term in text for term in risk_off_terms):
        bias = "Risk-off"
    elif any(term in text for term in risk_on_terms):
        bias = "Risk-on"
    else:
        bias = "Neutro"

    return {
        **item,
        "impact": impact,
        "score": round(score, 1),
        "themes": themes[:3] or ["Macro"],
        "assets": assets[:4] or ["Mercado Global"],
        "bias": bias,
    }


def _fetch_rss(limit_per_source: int = 8) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTSMacroHub/1.0)"}
    rows: list[dict[str, Any]] = []
    for source, (level, url) in RSS_SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=8)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception:
            continue
        for entry in feed.entries[:limit_per_source]:
            title = _clean_text(entry.get("title", ""))
            if not title:
                continue
            link = entry.get("link", "")
            dt = _parse_rss_datetime(entry)
            rows.append({
                "id": _make_id(source, title, link),
                "source": source,
                "level": level,
                "provider": "RSS",
                "title": title,
                "summary": _clean_text(entry.get("summary", entry.get("description", title)))[:260],
                "link": link,
                "timestamp": dt.timestamp(),
                "published_str": dt.astimezone(BR_TZ).strftime("%d/%m %H:%M"),
            })
    return rows


def _fetch_gdelt(limit_per_source: int = 6, timespan: str = "12h") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, (level, query) in GDELT_QUERIES.items():
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(max(limit_per_source, 1), 20),
            "timespan": timespan,
            "sort": "datedesc",
        }
        try:
            response = requests.get(GDELT_API_URL, params=params, timeout=10)
            response.raise_for_status()
            articles = response.json().get("articles", [])
        except Exception:
            continue
        for article in articles:
            title = _clean_text(article.get("title"))
            if not title:
                continue
            link = article.get("url", "")
            dt = _parse_gdelt_datetime(article.get("seendate"))
            rows.append({
                "id": _make_id(source, title, link),
                "source": source,
                "level": level,
                "provider": "GDELT",
                "title": title,
                "summary": _clean_text(article.get("snippet") or title)[:260],
                "link": link,
                "timestamp": dt.timestamp(),
                "published_str": dt.astimezone(BR_TZ).strftime("%d/%m %H:%M"),
            })
    return rows


def build_macro_news_hub(limit: int = 24, max_age_hours: int = 24, force: bool = False) -> dict[str, Any]:
    cache = _load_cache()
    now_ts = time.time()
    if not force and cache.get("items") and now_ts - float(cache.get("updated_ts", 0)) < 900:
        return cache

    rows = _fetch_rss()
    rows.extend(_fetch_gdelt())
    cutoff = now_ts - max_age_hours * 3600
    seen = set()
    classified = []
    for row in rows:
        title_key = _clean_text(row.get("title", "")).lower()[:90]
        if not title_key or title_key in seen or float(row.get("timestamp", 0)) < cutoff:
            continue
        seen.add(title_key)
        item = _classify(row)
        if item:
            classified.append(item)

    classified.sort(key=lambda item: (item.get("impact") == "ALTO", item.get("score", 0), item.get("timestamp", 0)), reverse=True)
    if not classified and cache.get("items"):
        cache["stale"] = True
        return cache

    payload = {
        "updated_at": datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "updated_ts": now_ts,
        "stale": False,
        "items": classified[:limit],
        "sources": sorted({item["source"] for item in classified}),
        "counts": {
            "alto": sum(1 for item in classified if item.get("impact") == "ALTO"),
            "medio": sum(1 for item in classified if item.get("impact") == "MEDIO"),
            "baixo": sum(1 for item in classified if item.get("impact") == "BAIXO"),
        },
    }
    _save_cache(payload)
    return payload


if __name__ == "__main__":
    hub = build_macro_news_hub(force=True)
    for item in hub.get("items", [])[:10]:
        print(f"[{item['impact']}] {item['source']} {item['published_str']} - {item['title']}")
