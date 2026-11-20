from datetime import datetime, timezone
from types import SimpleNamespace

from PIL import Image
from io import BytesIO

from execution.macro_news_art import generate_macro_news_art
from execution.news_macro_hub import RSS_SOURCES, _classify, _fetch_rss, _google_news_source, _parallel_collect, generate_daily_macro_briefing


def test_google_news_source_reads_structured_publisher():
    assert _google_news_source({"source": {"title": "Agência Brasil"}}) == "Agência Brasil"


def test_economist_rss_is_collected_as_credited_headline(monkeypatch):
    feed_url = "https://www.economist.com/finance-and-economics/rss.xml"
    rss = b"""<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'><channel><item>
      <title>Bond yields are rising everywhere except China</title>
      <description>The central bank changed its policy rate.</description>
      <link>https://www.economist.com/finance-and-economics/example</link>
      <pubDate>Thu, 19 Nov 2026 10:04:37 +0000</pubDate>
    </item></channel></rss>"""

    def fake_get(url, **_kwargs):
        if url != feed_url:
            raise RuntimeError("not mocked")
        return SimpleNamespace(
            content=rss,
            headers={"content-type": "text/xml"},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("execution.news_macro_hub.requests.get", fake_get)
    rows = _fetch_rss(limit_per_source=1)

    economist_rows = [row for row in rows if row["source"] == "The Economist"]
    assert RSS_SOURCES["The Economist"][1] == feed_url
    assert len(economist_rows) == 1
    assert economist_rows[0]["title"] == "Bond yields are rising everywhere except China"
    assert economist_rows[0]["link"].startswith("https://www.economist.com/")
    assert economist_rows[0]["provider"] == "RSS"


def test_macro_news_art_is_a_deterministic_theme_based_png():
    first = generate_macro_news_art("Juros & Fed", "story-1")
    same = generate_macro_news_art("Juros & Fed", "story-1")
    other_theme = generate_macro_news_art("Brasil", "story-1")

    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert first == same
    assert first != other_theme
    with Image.open(BytesIO(first)) as image:
        assert image.size == (640, 280)


def test_parallel_collection_preserves_task_order():
    def slow_first():
        import time
        time.sleep(0.03)
        return [{"title": "first"}]

    def fast_second():
        return [{"title": "second"}]

    rows = _parallel_collect([slow_first, fast_second], max_workers=2)

    assert [row["title"] for row in rows] == ["first", "second"]


def test_classification_marks_brazil_politics_and_recent_breaking_news():
    item = _classify({
        "id": "news-breaking",
        "title": "Última hora: Congresso aprova medida fiscal no Brasil",
        "summary": "",
        "source": "Agência Brasil",
        "level": "nivel_2",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    })

    assert item["breaking"] is True
    assert "Política" in item["themes"]
    assert "Brasil" in item["themes"]
    assert {"Brasil", "Política", "Breaking news"}.issubset(item["sections"])


def test_daily_briefing_runs_locally_without_api_and_uses_feed_evidence():
    items = [{
        "id": "news-1",
        "title": "Fed mantém juros",
        "summary": "O Federal Reserve manteve a taxa de juros nesta reunião. O comunicado afirmou que novas decisões dependerão dos dados de inflação e emprego.",
        "source": "Federal Reserve",
        "link": "https://example.com/news-1",
        "themes": ["Fed/Juros EUA"],
        "assets": ["US10Y/US30Y"],
        "sections": ["Macro global"],
    }]
    result = generate_daily_macro_briefing(items)

    assert len(result["stories"]) == 1
    assert result["stories"][0]["source_ids"] == ["news-1"]
    assert result["stories"][0]["primary_confirmation"] is True
    assert result["stories"][0]["confidence"] == "Alta"
    assert result["stories"][0]["summary"].startswith("O Federal Reserve manteve")
    assert "trajetoria de juros" in result["stories"][0]["interpretation"]
    assert result["model"] == "Local deterministico"
