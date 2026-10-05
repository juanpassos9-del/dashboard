from datetime import datetime
from zoneinfo import ZoneInfo

from execution.market_clock import select_upcoming_calendar_events


def test_selects_only_future_market_events_in_time_order():
    now = datetime(2026, 10, 5, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    calendar = [
        {"date": "2026-10-05", "time": "10:00", "currency": "USD", "event": "CPI", "impact": "HIGH"},
        {"date": "2026-10-05", "time": "08:00", "currency": "BRL", "event": "Past event", "impact": "HIGH"},
        {"date": "2026-10-05", "time": "09:00", "currency": "XYZ", "event": "Other market", "impact": "HIGH"},
        {"date": "2026-10-05", "time": "09:30", "currency": "BRL", "event": "IPCA", "impact": "MEDIUM"},
    ]

    events = select_upcoming_calendar_events(calendar, now=now)

    assert [event["event"] for event in events] == ["IPCA", "CPI"]
    assert events[0]["time"] == "09:30"
    assert events[0]["timestamp"] < events[1]["timestamp"]


def test_accepts_wrapped_calendar_and_skips_invalid_records():
    now = datetime(2026, 10, 5, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    events = select_upcoming_calendar_events({"events": [
        {"date": "bad-date", "time": "09:00", "currency": "USD", "event": "Bad", "impact": "HIGH"},
        {"date": "2026-10-05", "time": "09:00", "currency": "USD", "event": "Valid", "impact": "HIGH"},
    ]}, now=now)

    assert len(events) == 1
    assert events[0]["event"] == "Valid"
