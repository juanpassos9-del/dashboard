"""
fetch_source_news.py - Fontes editoriais para o feed do Terminal Bloomberg.

Fontes:
- Bloomberg Markets RSS
- CNBC Markets RSS
- SCMP Business RSS
- Reuters via GDELT domain filter, pois o RSS publico do reuters.com costuma bloquear.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import feedparser
import requests

from execution.fetch_financial_juice import normalize_news_translations
from execution.fetch_gdelt_news import _parse_gdelt_datetime
from execution.logger_setup import setup_logger

logger = setup_logger("source_news")
BR_TZ = ZoneInfo("America/Sao_Paulo")

CACHE_DIR = ".tmp"
CACHE_FILE = os.path.join(CACHE_DIR, "source_news_cache.json")
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

RSS_SOURCES = {
    "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "SCMP": "https://www.scmp.com/rss/91/feed",
}

REUTERS_QUERY = (
    'domainis:reuters.com '
    '(markets OR stocks OR fed OR inflation OR treasury OR dollar OR oil OR China OR Brazil)'
)


def _load_cache():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data):
    try:
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Erro ao salvar cache source_news: {e}")


def _cached_items(cache, limit):
    items = [v for k, v in cache.items() if k != "last_network_fetch" and isinstance(v, dict)]
    items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return items[:limit]


def _clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss_datetime(entry):
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _make_id(prefix, link, title):
    digest = hashlib.md5((link or title).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _fetch_rss_sources(limit_per_source=10):
    items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for source, url in RSS_SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as e:
            logger.warning(f"Erro RSS {source}: {e}")
            continue

        for entry in feed.entries[:limit_per_source]:
            title = _clean_text(entry.get("title", ""))
            if not title:
                continue
            link = entry.get("link", "")
            published_dt = _parse_rss_datetime(entry)
            summary = _clean_text(entry.get("summary", entry.get("description", title)))
            items.append({
                "id": _make_id(source.lower(), link, title),
                "title_en": title,
                "title_pt": "",
                "summary": summary or title,
                "summary_pt": "",
                "source": source,
                "provider": "RSS",
                "link": link,
                "published_str": published_dt.astimezone(BR_TZ).strftime("%H:%M"),
                "timestamp": published_dt.timestamp(),
            })
    return items


def _fetch_reuters_gdelt(limit=10, timespan="6h"):
    params = {
        "query": REUTERS_QUERY,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(max(limit, 1), 50),
        "timespan": timespan,
        "sort": "datedesc",
    }
    try:
        response = requests.get(GDELT_API_URL, params=params, timeout=12)
        response.raise_for_status()
        articles = response.json().get("articles", [])
    except Exception as e:
        logger.warning(f"Erro Reuters/GDELT: {e}")
        return []

    items = []
    for article in articles:
        title = _clean_text(article.get("title"))
        if not title:
            continue
        link = article.get("url", "")
        published_dt = _parse_gdelt_datetime(article.get("seendate"))
        items.append({
            "id": _make_id("reuters", link, title),
            "title_en": title,
            "title_pt": "",
            "summary": _clean_text(article.get("snippet") or title),
            "summary_pt": "",
            "source": "Reuters",
            "provider": "GDELT",
            "link": link,
            "published_str": published_dt.astimezone(BR_TZ).strftime("%H:%M"),
            "timestamp": published_dt.timestamp(),
        })
    return items


def fetch_source_news(limit=40, timespan="6h"):
    cache = _load_cache()
    now_ts = datetime.now(timezone.utc).timestamp()
    last_fetch = float(cache.get("last_network_fetch") or 0)
    if now_ts - last_fetch < 180:
        return _cached_items(cache, limit)

    news = []
    news.extend(_fetch_rss_sources(limit_per_source=12))
    news.extend(_fetch_reuters_gdelt(limit=12, timespan=timespan))

    if not news:
        cache["last_network_fetch"] = now_ts - 120
        _save_cache(cache)
        return _cached_items(cache, limit)

    news = normalize_news_translations(news, cache)
    cache["last_network_fetch"] = now_ts
    _save_cache(cache)
    news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return news[:limit]


if __name__ == "__main__":
    for item in fetch_source_news(limit=8):
        print(f"[{item['published_str']}] {item['source']} - {item['title_pt']}")
