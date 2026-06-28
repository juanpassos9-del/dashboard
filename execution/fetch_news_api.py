"""News API fallback feed for macro/market-moving headlines."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


load_dotenv(dotenv_path=".env")

CACHE_DIR = Path(".tmp")
CACHE_FILE = CACHE_DIR / "news_api_cache.json"
BR_TZ = ZoneInfo("America/Sao_Paulo") if ZoneInfo else timezone.utc
NEWS_API_URL = "https://newsapi.org/v2/everything"
DEFAULT_QUERY = (
    '(Fed OR FOMC OR Powell OR CPI OR PCE OR payrolls OR "jobless claims" OR '
    'Treasury OR yields OR dollar OR oil OR crude OR Brent OR WTI OR Iran OR Israel OR '
    'China OR Russia OR "S&P 500" OR Nasdaq OR Bitcoin OR Brazil OR Petrobras OR Vale) '
    'AND (market OR markets OR stocks OR futures OR economy OR economic OR inflation OR oil OR rates OR geopolitical)'
)


def _api_key() -> str:
    try:
        import streamlit as st

        key = st.secrets.get("NEWS_API_KEY", "")
        if key:
            return str(key)
    except Exception:
        pass
    return os.getenv("NEWS_API_KEY", "")


def _read_cache(max_age_seconds: int = 900) -> list[dict[str, Any]]:
    try:
        if not CACHE_FILE.exists():
            return []
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("saved_at", 0)) > max_age_seconds:
            return []
        data = payload.get("items")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_cache(items: list[dict[str, Any]]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps({"saved_at": time.time(), "items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _parse_datetime(raw: str | None) -> tuple[float, str]:
    if not raw:
        return 0.0, ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        ts = dt.timestamp()
        published_br = dt.astimezone(BR_TZ).strftime("%H:%M:%S") if BR_TZ else dt.strftime("%H:%M:%S")
        return ts, published_br
    except Exception:
        return 0.0, ""


def _impact_tags(text: str) -> tuple[list[str], int]:
    lower = text.lower()
    tags: list[str] = []
    score = 0
    rules = [
        (["fed", "fomc", "powell", "rate", "rates", "treasury", "yield"], "Juros", 4),
        (["cpi", "pce", "ppi", "inflation", "payroll", "jobs", "gdp", "pmi", "ism"], "Macro", 4),
        (["oil", "crude", "brent", "wti", "opec"], "Energia", 3),
        (["iran", "israel", "war", "attack", "strike", "russia", "china"], "Geopolitica", 4),
        (["s&p", "nasdaq", "dow", "stocks", "futures"], "Indices", 2),
        (["bitcoin", "crypto", "ethereum"], "Cripto", 2),
        (["brazil", "petrobras", "vale", "real"], "Brasil", 2),
    ]
    for keywords, tag, weight in rules:
        if any(word in lower for word in keywords):
            tags.append(tag)
            score += weight
    if any(word in lower for word in ["breaking", "urgent", "unexpected", "surprise"]):
        score += 3
    return list(dict.fromkeys(tags)), score


def _normalize_article(article: dict[str, Any]) -> dict[str, Any] | None:
    title = str(article.get("title") or "").strip()
    if not title or title == "[Removed]":
        return None
    summary = str(article.get("description") or "").strip()
    url = str(article.get("url") or "").strip()
    ts, published_str = _parse_datetime(article.get("publishedAt"))
    source = article.get("source") if isinstance(article.get("source"), dict) else {}
    source_name = str(source.get("name") or "News API")
    tags, impact_score = _impact_tags(f"{title} {summary} {source_name}")
    item_id = hashlib.sha1((url or title).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return {
        "id": f"newsapi-{item_id}",
        "title": title,
        "title_en": title,
        "title_pt": title,
        "summary": summary,
        "description": summary,
        "source": f"News API / {source_name}",
        "link": url,
        "url": url,
        "timestamp": ts,
        "published_str": published_str,
        "tags": tags,
        "impact_score": impact_score,
        "impact": "ALTO IMPACTO" if impact_score >= 8 else "IMPACTO MEDIO",
    }


def fetch_news_api_news(limit: int = 25, max_age_seconds: int = 900) -> list[dict[str, Any]]:
    cached = _read_cache(max_age_seconds=max_age_seconds)
    if cached:
        return cached[:limit]
    api_key = _api_key()
    if not api_key:
        return []
    params = {
        "q": DEFAULT_QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(max(limit * 2, 20), 50),
        "apiKey": api_key,
    }
    try:
        response = requests.get(NEWS_API_URL, params=params, timeout=15)
        data = response.json()
    except Exception:
        return []
    if data.get("status") != "ok":
        return []
    articles = data.get("articles")
    if not isinstance(articles, list):
        return []
    items = []
    for article in articles:
        item = _normalize_article(article)
        if item and int(item.get("impact_score") or 0) >= 3:
            items.append(item)
    items.sort(key=lambda row: float(row.get("timestamp") or 0), reverse=True)
    _write_cache(items)
    return items[:limit]
