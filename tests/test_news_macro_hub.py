import json
from unittest.mock import patch

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


def test_daily_briefing_keeps_only_known_source_references():
    items = [{
        "id": "news-1",
        "title": "Fed mantém juros",
        "summary": "Comunicado oficial do banco central.",
        "source": "Federal Reserve",
        "link": "https://example.com/news-1",
        "themes": ["Fed/Juros EUA"],
        "assets": ["US10Y/US30Y"],
    }]
    generated = {
        "stories": [{
            "headline": "Fed mantém juros",
            "summary": "O comunicado confirma a manutenção das taxas.",
            "interpretation": "A decisão pode afetar a curva americana.",
            "market_channels": ["Treasuries: possível ajuste da curva"],
            "confidence": "Alta",
            "source_ids": ["news-1", "invented-id"],
            "limitation": "Sem dados de preço para confirmar a reação.",
        }]
    }

    class FakeModel:
        def generate_content(self, *_args, **_kwargs):
            return type("Response", (), {"text": json.dumps(generated)})()

    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel", return_value=FakeModel()
    ):
        result = generate_daily_macro_briefing(items, "test-key")

    assert len(result["stories"]) == 1
    assert result["stories"][0]["source_ids"] == ["news-1"]
    assert result["stories"][0]["primary_confirmation"] is True
    assert result["stories"][0]["market_channels"] == ["Treasuries: possível ajuste da curva"]
