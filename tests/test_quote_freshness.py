from datetime import datetime, timedelta, timezone

from execution.quote_freshness import quote_freshness_label


def test_quote_freshness_uses_provider_timestamp():
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    label, state = quote_freshness_label(
        {
            "source": "Yahoo Finance",
            "source_timestamp": (now - timedelta(seconds=45)).isoformat(),
        },
        now=now,
    )

    assert label == "Yahoo Finance · 45s atrás"
    assert state == "fresh"


def test_quote_freshness_marks_old_quote_as_stale():
    label, state = quote_freshness_label(
        {"source": "Brapi", "age_seconds": 16 * 60, "max_age_seconds": 15 * 60}
    )

    assert label == "Brapi · ATRASADA · 16min"
    assert state == "stale"


def test_timestamp_takes_precedence_over_collector_age():
    now = datetime(2026, 10, 5, 12, 20, tzinfo=timezone.utc)
    label, state = quote_freshness_label(
        {
            "source": "Yahoo Finance",
            "source_timestamp": (now - timedelta(minutes=20)).isoformat(),
            "age_seconds": 1,
            "max_age_seconds": 15 * 60,
        },
        now=now,
    )

    assert label == "Yahoo Finance · ATRASADA · 20min"
    assert state == "stale"


def test_quote_freshness_does_not_assume_missing_timestamp_is_current():
    label, state = quote_freshness_label({"source": "InfoMoney DI"})

    assert label == "InfoMoney DI · HORÁRIO INDISPONÍVEL"
    assert state == "unknown"
