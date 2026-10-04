from datetime import datetime, timezone

from execution.news_macro_hub import _classify, _google_news_source, generate_daily_macro_briefing


def test_google_news_source_reads_structured_publisher():
    assert _google_news_source({"source": {"title": "Agência Brasil"}}) == "Agência Brasil"


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
