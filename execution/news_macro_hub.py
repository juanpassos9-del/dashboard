"""Macro news hub for Market Report.

Collects public/open headlines from priority market sources, normalizes them,
and classifies impact, macro theme, affected assets and risk bias.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from urllib.parse import urlencode
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
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"

# Keep queries focused to avoid turning the macro hub into a general news feed.
GOOGLE_NEWS_QUERIES = {
    "Brasil Macro": ("nivel_2", '(Brasil OR Brazil) (BCB OR Copom OR Selic OR fiscal OR Ibovespa OR PIB OR inflação)'),
    "Política": ("nivel_2", '(política OR governo OR Congresso OR eleição OR Lula OR Câmara OR Senado OR STF) Brasil'),
    "Macro Global": ("nivel_2", '(Fed OR FOMC OR inflation OR Treasury OR yields OR ECB OR central bank OR GDP) economy markets'),
    "Breaking News": ("nivel_2", '("breaking news" OR "ultima hora" OR urgente OR "developing story") (markets OR economy OR Brazil OR Fed OR oil OR war)'),
}
PRIMARY_SOURCE_NAMES = {
    "federal reserve",
    "ecb",
    "banco central do brasil",
    "bcb",
    "u.s. treasury",
    "imf",
    "world bank",
}

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
    ("Política", ["politics", "political", "politica", "política", "government", "governo", "congress", "congresso", "election", "eleição", "senado", "câmara", "stf", "parliament", "president", "presidente", "trump", "lula"]),
    ("Breaking News", ["breaking", "ultima hora", "última hora", "urgent", "urgente", "just in", "developing story", "live updates"]),
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

BREAKING_TERMS = ["breaking", "ultima hora", "última hora", "urgent", "urgente", "just in", "developing story", "live updates"]

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


def _google_news_source(entry) -> str:
    source_data = entry.get("source", "")
    source = _clean_text(source_data.get("title", "") if hasattr(source_data, "get") else source_data)
    if source:
        return html.unescape(source)
    title = _clean_text(entry.get("title", ""))
    # Google News commonly appends the publisher after the headline separator.
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Veiculo nao identificado"


def _source_weight(level: str) -> int:
    return {"nivel_1": 20, "nivel_2": 12, "nivel_3": 7}.get(level, 5)


def _classify(item: dict[str, Any]) -> dict[str, Any] | None:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if any(term in text for term in NOISE_TERMS):
        return None

    themes = [name for name, terms in THEME_RULES if any(term in text for term in terms)]
    assets = [name for name, terms in ASSET_RULES if any(term in text for term in terms)]
    recency_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - float(item.get("timestamp", 0))) / 3600)
    is_breaking = recency_hours <= 6 and any(term in text for term in BREAKING_TERMS)
    keyword_score = sum(4 for term in HIGH_IMPACT_TERMS if term in text)
    recency_score = max(0, 12 - recency_hours * 1.5)
    score = _source_weight(str(item.get("level", ""))) + keyword_score + recency_score + len(themes) * 2 + len(assets) * 2 + (8 if is_breaking else 0)
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
        "breaking": is_breaking,
        "sections": [
            section for section, matched in (
                ("Brasil", "Brasil" in themes),
                ("Política", "Política" in themes),
                ("Macro global", any(theme in themes for theme in ("Fed/Juros EUA", "Inflação", "Atividade", "Petróleo/Energia", "China", "Crédito"))),
                ("Breaking news", is_breaking),
            ) if matched
        ] or ["Mercados"],
    }


def _fetch_rss(limit_per_source: int = 8) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTSMacroHub/1.0)"}
    rows: list[dict[str, Any]] = []
    for source, (level, url) in RSS_SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=8)
            response.raise_for_status()
            feed = feedparser.parse(response.content, response_headers=response.headers)
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


def _fetch_google_news(limit_per_query: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTSMacroHub/1.0)"}
    for topic, (level, query) in GOOGLE_NEWS_QUERIES.items():
        params = {
            "q": query,
            "hl": "pt-BR",
            "gl": "BR",
            "ceid": "BR:pt-419",
        }
        try:
            response = requests.get(
                f"{GOOGLE_NEWS_RSS_URL}?{urlencode(params)}",
                headers=headers,
                timeout=8,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content, response_headers=response.headers)
        except Exception:
            continue
        for entry in feed.entries[:limit_per_query]:
            raw_title = _clean_text(entry.get("title", ""))
            if not raw_title:
                continue
            publisher = _google_news_source(entry)
            # RSS titles often contain "headline - publisher"; keep the publisher
            # as a separate field so it can be shown without duplicating the title.
            title = raw_title
            suffix = f" - {publisher}"
            if publisher != "Veiculo nao identificado" and title.endswith(suffix):
                title = title[: -len(suffix)].strip()
            dt = _parse_rss_datetime(entry)
            link = entry.get("link", "")
            rows.append({
                "id": _make_id(f"Google News:{publisher}", title, link),
                "source": publisher,
                "provider": "Google News RSS",
                "collection_topic": topic,
                "level": level,
                "title": title,
                "summary": _clean_text(entry.get("summary", entry.get("description", title)))[:260],
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
    rows.extend(_fetch_google_news())
    rows.extend(_fetch_gdelt())
    cutoff = now_ts - max_age_hours * 3600
    seen = set()
    classified = []
    for row in rows:
        title_key = re.sub(r"\W+", " ", _clean_text(row.get("title", "")).lower()).strip()[:120]
        if not title_key or title_key in seen or float(row.get("timestamp", 0)) < cutoff:
            continue
        seen.add(title_key)
        item = _classify(row)
        if item:
            classified.append(item)

    classified.sort(key=lambda item: (item.get("breaking", False), item.get("impact") == "ALTO", item.get("score", 0), item.get("timestamp", 0)), reverse=True)
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


def _local_news_summary(item: dict[str, Any]) -> str:
    title = html.unescape(_clean_text(str(item.get("title", ""))))
    snippet = html.unescape(_clean_text(str(item.get("summary", ""))))
    if not snippet or snippet.casefold() == title.casefold() or len(snippet) < 45:
        return "A fonte nao forneceu contexto suficiente no trecho do feed; consulte a materia original."
    sentences = re.split(r"(?<=[.!?])\s+", snippet)
    summary = " ".join(sentence for sentence in sentences[:2] if sentence)
    return summary[:650].rstrip()


def _local_market_interpretation(item: dict[str, Any]) -> tuple[str, list[str]]:
    themes = set(item.get("themes") or [])
    assets = item.get("assets") or []
    if "Política" in themes:
        interpretation = "O desdobramento pode alterar expectativas fiscais, regulatórias ou comerciais. O efeito depende do conteúdo e da implementação; a manchete, por si só, não define direção."
        channels = ["Ibov/USDBRL: possível repricing de risco local, condicionado aos detalhes"]
    elif "Brasil" in themes:
        interpretation = "A notícia pode influenciar expectativas sobre atividade, inflação, política monetária ou risco fiscal brasileiro. A direcao depende dos dados e da resposta dos ativos."
        channels = ["DI/real/IBOV: acompanhar a transmissao para juros, cambio e acoes"]
    elif "Fed/Juros EUA" in themes or "Inflação" in themes:
        interpretation = "O tema pode alterar expectativas para a trajetoria de juros e rendimentos nos EUA. A leitura depende da surpresa frente ao esperado e da comunicacao oficial."
        channels = ["Treasuries/DXY: sensiveis a expectativas de juros", "S&P/Nasdaq: sensiveis a juros de desconto"]
    elif "Atividade" in themes:
        interpretation = "Indicadores de atividade podem mudar a leitura de crescimento e a expectativa de juros. Sem comparacao com consenso e revisoes, nao e possivel inferir surpresa ou direcao."
        channels = ["Treasuries/bolsas: reacao depende da surpresa e do regime macro"]
    elif "Petróleo/Energia" in themes or "Geopolítica" in themes:
        interpretation = "O evento pode afetar premio de risco, oferta de energia ou demanda por protecao. A magnitude depende da duracao e da confirmacao por dados de mercado."
        channels = ["Petroleo/ouro: possivel sensibilidade a oferta e risco", "Inflacao/juros: eventual transmissao depende da persistencia"]
    elif "China" in themes:
        interpretation = "Noticias sobre a China podem alterar expectativas de demanda por commodities e crescimento global. A direcao depende das medidas efetivas e dos dados subsequentes."
        channels = ["Commodities/BRL: possivel canal via demanda e comercio"]
    elif "Crédito" in themes:
        interpretation = "Mudancas nas condicoes de credito podem afetar custo de financiamento e apetite a risco. E necessario acompanhar spreads e precos para confirmar a transmissao."
        channels = ["Spreads/bolsas: possivel canal via condicoes financeiras"]
    elif "Cripto" in themes:
        interpretation = "O tema pode afetar ativos digitais diretamente; a transmissao para outros mercados depende de liquidez, regulacao e apetite a risco."
        channels = ["Cripto: efeito direto depende dos detalhes do evento"]
    else:
        interpretation = "O trecho disponivel nao permite estabelecer um canal macro especifico. Trate a relacao com os mercados como inconclusiva ate consultar a materia original."
        channels = []

    relevant_assets = [asset for asset in assets if asset not in {"Mercado Global", "Cripto"}]
    if relevant_assets and channels:
        channels[-1] += f"; ativos monitorados no feed: {', '.join(relevant_assets[:3])}"
    return interpretation, channels[:3]


def generate_daily_macro_briefing(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a deterministic, source-linked daily briefing without an AI API."""
    stories = []
    for item in items[:12]:
        item_id = str(item.get("id", ""))
        if not item_id:
            continue
        source = str(item.get("source", "")).strip().lower()
        summary = _local_news_summary(item)
        interpretation, channels = _local_market_interpretation(item)
        has_context = not summary.startswith("A fonte nao forneceu")
        primary_confirmation = source in PRIMARY_SOURCE_NAMES
        confidence = "Alta" if has_context and primary_confirmation else ("Media" if has_context else "Baixa")
        stories.append({
            "headline": str(item.get("title", ""))[:240],
            "summary": summary,
            "interpretation": interpretation,
            "market_channels": channels,
            "confidence": confidence,
            "sections": [str(value)[:40] for value in item.get("sections", [])[:4]],
            "source_ids": [item_id],
            "primary_confirmation": primary_confirmation,
            "limitation": "Resumo local baseado somente no trecho do feed; a materia completa nao foi analisada.",
        })
    if not stories:
        raise ValueError("Nao ha noticias validas para montar o briefing.")
    stories.sort(key=lambda story: (story["confidence"] == "Alta", story["confidence"] == "Media"), reverse=True)
    return {
        "generated_at": datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "model": "Local deterministico",
        "stories": stories[:5],
    }


if __name__ == "__main__":
    hub = build_macro_news_hub(force=True)
    for item in hub.get("items", [])[:10]:
        print(f"[{item['impact']}] {item['source']} {item['published_str']} - {item['title']}")
