from datetime import datetime
from zoneinfo import ZoneInfo

import execution.market_report as market_report


def test_market_report_uses_local_fallback_when_ai_fails(monkeypatch, tmp_path):
    now = datetime(2026, 10, 14, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    date_str = now.strftime("%Y-%m-%d")
    monkeypatch.setenv("GOOGLE_API_KEY", "configured")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(market_report, "_now_local", lambda: now)
    monkeypatch.setattr(market_report, "get_report_slot", lambda *_args, **_kwargs: "tarde")
    monkeypatch.setattr(market_report, "load_daily_reports", lambda _date: {"date": date_str, "reports": []})
    monkeypatch.setattr(market_report, "_load_json_file", lambda *_args: {})
    monkeypatch.setattr(market_report, "fetch_all_news", lambda **_kwargs: [])
    monkeypatch.setattr(market_report, "_load_calendar_events_for_report", lambda *_args: ([], "fixture"))
    monkeypatch.setattr(market_report, "_asset_snapshot", lambda _data: {})
    monkeypatch.setattr(market_report, "_market_regime", lambda _snapshot: {})
    monkeypatch.setattr(market_report, "_market_context_lines", lambda *_args: [])
    monkeypatch.setattr(market_report, "_market_implications", lambda *_args: [])
    monkeypatch.setattr(market_report, "_generate_ai_report_text", lambda _prompt: (_ for _ in ()).throw(RuntimeError("Gemini 503")))
    monkeypatch.setattr(market_report, "_generate_local_report_text", lambda *_args: "Relatorio local de teste")
    monkeypatch.setattr(market_report, "DAILY_REPORT_FILE", str(tmp_path / "daily.json"))
    monkeypatch.setattr(market_report, "LATEST_REPORT_FILE", str(tmp_path / "latest.json"))

    import execution.yield_curve_regime as yield_curve_regime

    monkeypatch.setattr(yield_curve_regime, "analyze_yield_curve_regime", lambda _data: {})
    report = market_report.generate_market_report(force=True)

    assert report["report"] == "Relatorio local de teste"
    assert report["provider"] == "Local/fallback (IA indisponivel)"
    assert "Gemini 503" in report["fallback_errors"][0]
