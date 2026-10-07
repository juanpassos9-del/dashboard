from datetime import datetime
from zoneinfo import ZoneInfo

from execution.economic_calendar_history import merge_calendar_history


def test_archive_is_brazil_only_and_preserves_released_values():
    now = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
    old = {
        "events": [{
            "date": "2026-10-07", "time": "09:00", "currency": "BRL", "event": "IPCA mensal",
            "actual": "0,4%", "forecast": "0,3%", "first_seen_at": "first",
        }]
    }
    fresh = [
        {"date": "2026-10-07", "time": "09:00", "currency": "BRL", "event": "IPCA mensal", "actual": "---", "forecast": "0,35%"},
        {"date": "2026-10-07", "time": "09:00", "currency": "USD", "event": "CPI", "actual": "3%"},
    ]
    result = merge_calendar_history(old, [fresh], now=now)
    assert result["event_count"] == 1
    event = result["events"][0]
    assert event["actual"] == "0,4%"
    assert event["forecast"] == "0,35%"
    assert event["first_seen_at"] == "first"


def test_archive_discards_events_outside_retention():
    now = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
    result = merge_calendar_history(None, [[
        {"date": "2020-01-01", "currency": "BRL", "event": "IPCA"},
        {"date": "2026-10-06", "currency": "BRL", "event": "IPCA"},
    ]], now=now)
    assert [event["date"] for event in result["events"]] == ["2026-10-06"]
