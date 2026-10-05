from datetime import datetime
from zoneinfo import ZoneInfo

from execution.market_clock import active_market_sessions, select_upcoming_calendar_events


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


def test_reports_overlapping_new_york_europe_and_brazil_sessions():
    now = datetime(2026, 10, 5, 11, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    sessions = active_market_sessions(now)

    assert [session["region"] for session in sessions] == ["EUROPA", "NOVA YORK", "BRASIL"]


def test_reports_asia_when_hong_kong_and_tokyo_are_open_and_ignores_weekend():
    asia_morning = datetime(2026, 10, 5, 22, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    saturday = datetime(2026, 10, 10, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    assert [session["region"] for session in active_market_sessions(asia_morning)] == ["ÁSIA"]
    assert active_market_sessions(saturday) == []
