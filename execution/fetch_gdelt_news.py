"""
fetch_gdelt_news.py - Busca noticias globais via GDELT DOC 2.0 API.

Fonte gratuita, sem chave, usada como segunda camada do feed em tempo real.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import requests

from execution.fetch_financial_juice import normalize_news_translations
from execution.logger_setup import setup_logger

logger = setup_logger("gdelt_news")

CACHE_DIR = ".tmp"
CACHE_FILE = os.path.join(CACHE_DIR, "gdelt_news_cache.json")
API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

QUERY = "fed OR inflation OR treasury OR dollar OR oil OR Nasdaq sourcelang:english"


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
        logger.warning(f"Erro ao salvar cache GDELT: {e}")


def _parse_gdelt_datetime(value):
    if not value:
        return datetime.now(timezone.utc)
    value = str(value)
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _cached_articles(cache, limit):
    cached = [v for k, v in cache.items() if k != "last_network_fetch" and isinstance(v, dict)]
    cached.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return cached[:limit]


def fetch_gdelt_news(limit=30, timespan="3h"):
    """Retorna noticias normalizadas no mesmo contrato do Financial Juice."""
    cache = _load_cache()
    now_ts = datetime.now(timezone.utc).timestamp()
    last_fetch = float(cache.get("last_network_fetch") or 0)
    if now_ts - last_fetch < 180:
        return _cached_articles(cache, limit)

    params = {
        "query": QUERY,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(max(limit, 1), 75),
        "timespan": timespan,
        "sort": "datedesc",
    }

    try:
        response = requests.get(API_URL, params=params, timeout=12)
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles", [])
        cache["last_network_fetch"] = now_ts
    except Exception as e:
        logger.warning(f"Erro ao buscar GDELT: {e}. Usando cache local.")
        cache["last_network_fetch"] = now_ts - 120
        _save_cache(cache)
        return _cached_articles(cache, limit)

    news = []
    for article in articles:
        title = _clean_text(article.get("title"))
        if not title:
            continue

        link = article.get("url", "")
        domain = article.get("domain") or article.get("source") or "GDELT"
        published_dt = _parse_gdelt_datetime(article.get("seendate"))
        summary = _clean_text(article.get("snippet") or title)
        digest = hashlib.md5((link or title).encode("utf-8")).hexdigest()[:12]

        item = {
            "id": f"gdelt_{digest}",
            "title_en": title,
            "title_pt": "",
            "summary": summary,
            "summary_pt": "",
            "source": domain,
            "provider": "GDELT",
            "link": link,
            "published_str": published_dt.strftime("%H:%M"),
            "timestamp": published_dt.timestamp(),
        }
        news.append(item)

    news = normalize_news_translations(news, cache)
    news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    _save_cache(cache)
    return news[:limit]


if __name__ == "__main__":
    for item in fetch_gdelt_news(limit=5):
        print(f"[{item['published_str']}] {item['source']} - {item['title_pt']}")
