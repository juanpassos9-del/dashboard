"""
fetch_news.py — Busca notícias financeiras via RSS feeds gratuitos.
Parte da Camada 3 (Execução) do sistema.
"""

import feedparser
from datetime import datetime, timedelta
import re
import warnings

warnings.filterwarnings("ignore")

RSS_FEEDS = {
    "Reuters Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "Investing.com": "https://www.investing.com/rss/news_25.rss",
    "Bloomberg Markets": "https://www.bloomberg.com/feeds/bview/register", # Often requires specific tokens, using a proxy or fallback
    "Valor Economico": "https://valor.globo.com/rss/valor/",
    "CNN Business": "http://rss.cnn.com/rss/money_topstories.rss",
    "CNBC Markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
}

KEYWORDS = [
    "oil", "crude", "gold", "vix", "volatility", "dollar", "dxy", "euro", "yen",
    "forex", "real", "brl", "s&p 500", "wall street", "nasdaq", "russell",
    "brazil", "brasil", "petrobras", "vale", "itau", "bradesco", "ewz",
    "emerging market", "treasury", "yield", "bond", "fed", "fomc",
    "interest rate", "rate cut", "rate hike", "inflation", "cpi", "payroll",
    "gdp", "recession", "tariff", "china", "geopolitical",
    "petróleo", "ouro", "dólar", "juros", "selic", "copom",
]


def is_relevant(title, summary=""):
    text = (title + " " + summary).lower()
    return any(kw in text for kw in KEYWORDS)


def parse_date(entry):
    for field in ["published_parsed", "updated_parsed"]:
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                pass
    return datetime.now()


def fetch_all_news(max_results=15, max_age_hours=24):
    all_news = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    for feed_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                pub_date = parse_date(entry)

                if pub_date >= cutoff and is_relevant(title, summary):
                    clean_summary = re.sub(r"<[^>]+>", "", summary)
                    clean_summary = clean_summary[:200] + "..." if len(clean_summary) > 200 else clean_summary
                    all_news.append({
                        "title": title.strip(),
                        "summary": clean_summary.strip(),
                        "source": feed_name,
                        "link": link,
                        "published": pub_date,
                        "published_str": pub_date.strftime("%H:%M"),
                    })
        except Exception as e:
            print(f"[WARN] Falha no feed {feed_name}: {e}")

    # Remove duplicatas
    seen = set()
    unique = []
    for item in all_news:
        key = item["title"].lower().strip()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: x["published"], reverse=True)
    return unique[:max_results]


def categorize_news(news_list):
    categories = {
        "📊 Inflação": ["inflation", "cpi", "pce", "ppi", "inflação", "preços ao consumidor"],
        "🏦 Juros / Treasuries": ["fed", "fomc", "rate", "treasury", "yield", "juros", "selic", "copom", "bond"],
        "🛢️ Petróleo": ["oil", "crude", "brent", "wti", "petróleo", "opep", "opec"],
        "🏗️ Minério de Ferro": ["iron ore", "minério de ferro", "vale", "fortescue", "rio tinto"],
        "✨ Ouro / Prata": ["gold", "silver", "ouro", "prata", "XAU", "XAG"],
        "₿ Bitcoin / Ethereum": ["bitcoin", "ethereum", "btc", "eth", "crypto", "cripto"],
        "🌍 Emergentes": ["emerging market", "brazil", "brasil", "china", "mexico", "ewz", "eem"],
    }

    categorized = {}
    for item in news_list:
        text = (item["title"] + " " + item["summary"]).lower()
        for cat_name, kws in categories.items():
            if any(kw in text for kw in kws):
                categorized.setdefault(cat_name, []).append(item)
    return categorized


if __name__ == "__main__":
    print("Buscando notícias financeiras...")
    news = fetch_all_news(max_results=10)
    if news:
        for i, item in enumerate(news, 1):
            print(f"{i}. [{item['source']}] {item['published_str']} - {item['title']}")
    else:
        print("Nenhuma notícia relevante encontrada.")
