from datetime import datetime, timedelta, timezone

import execution.ai_analyst as analyst


NOW = datetime(2026, 10, 14, 17, 0, tzinfo=timezone.utc)


def _quote(name, change, when=NOW, **extra):
    return {
        "name": name,
        "symbol": name,
        "price": 100.0,
        "change": change,
        "source": "fixture",
        "source_timestamp": when.isoformat(),
        **extra,
    }


def _markets(rows):
    return {"metadata": {"generated_at_utc": NOW.isoformat()}, "categories": {"fixture": rows}}


def test_empty_snapshot_is_insufficient_not_neutral(monkeypatch):
    monkeypatch.setattr(analyst, "analyze_yield_curve_regime", lambda *_args, **_kwargs: {})

    context = analyst.build_macro_regime_context({}, {}, [], now=NOW)
    text = analyst._local_fallback_text(context)

    assert context["regime"] == "Dados insuficientes"
    assert context["score"] == 0
    assert context["data_quality"]["coverage_pct"] == 0
    assert "score n/d" in text
    assert "Sem cotacoes atuais suficientes" in text


def test_group_scoring_avoids_counting_correlated_assets_individually(monkeypatch):
    curve_calls = []

    def fake_curve(data, include_fred=True):
        curve_calls.append(include_fred)
        return {"regime": "Parallel Down", "operational_bias": "Neutro", "macro_reading": "curva em queda"}

    monkeypatch.setattr(analyst, "analyze_yield_curve_regime", fake_curve)
    rows = [
        _quote("S&P 500", 1.0), _quote("Nasdaq", 1.1), _quote("Dow Jones", 0.9),
        _quote("VIX", -5.0), _quote("DXY", -0.5),
        _quote("US 02Y", -0.5), _quote("US 10Y", -0.2), _quote("US 30Y", -0.1),
        _quote("EEM", 0.8), _quote("EWZ", 0.8), _quote("IBOV", 0.7),
        _quote("USDBRL", -0.5), _quote("6L Real CME", 0.5),
        _quote("Bitcoin", 1.0),
    ]

    context = analyst.build_macro_regime_context({}, _markets(rows), [], now=NOW)

    assert context["block_scores"]["equities"]["score"] == 1.0
    assert context["block_scores"]["equities"]["contribution"] == 20.0
    assert curve_calls == [False]
    assert context["data_quality"]["coverage_pct"] == 100
    assert context["confidence"] == "Alta"
    assert context["regime"] == "Risk-on forte"
    assert context["confirmations"]


def test_stale_market_open_quotes_are_excluded(monkeypatch):
    monkeypatch.setattr(analyst, "analyze_yield_curve_regime", lambda *_args, **_kwargs: {})
    stale_time = NOW - timedelta(hours=3)
    context = analyst.build_macro_regime_context(
        {}, _markets([_quote("S&P 500", 1.0, stale_time), _quote("Nasdaq", 1.0, stale_time)]), [], now=NOW
    )

    assert context["regime"] == "Dados insuficientes"
    assert set(context["data_quality"]["stale_assets"]) == {"S&P 500", "Nasdaq"}
    assert context["data_quality"]["fresh_assets"] == 0


def test_last_close_quotes_remain_context_when_market_is_closed(monkeypatch):
    monkeypatch.setattr(analyst, "analyze_yield_curve_regime", lambda *_args, **_kwargs: {})
    saturday = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
    friday_close = datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)
    context = analyst.build_macro_regime_context(
        {}, _markets([_quote("S&P 500", 0.7, friday_close)]), [], now=saturday
    )

    assert context["data_quality"]["last_close_assets"] == 1
    assert "ultimo fechamento" in context["snapshot"][0]


def test_calendar_ignores_old_events_and_keeps_today_surprises():
    calendar = [
        {"date": "2026-10-01", "impact": "HIGH", "event": "Old CPI"},
        {"date": "2026-10-14", "time": "09:00", "currency": "USD", "impact": "HIGH", "event": "CPI", "actual": "3.2%", "forecast": "3.0%", "previous": "2.9%"},
    ]

    events, stale = analyst._calendar_events(calendar, NOW)

    assert not stale
    assert len(events) == 1
    assert "CPI" in events[0] and "atual 3.2%" in events[0]


def test_history_snapshots_are_sampled_and_retained():
    quotes = {"sp500": {"price": 100.0}}
    history = {"samples": []}
    history, added = analyst.append_macro_market_snapshot(history, quotes, NOW)
    assert added and len(history["samples"]) == 1

    unchanged, added = analyst.append_macro_market_snapshot(history, quotes, NOW + timedelta(hours=1))
    assert not added and len(unchanged["samples"]) == 1

    older = NOW - timedelta(days=40)
    seeded = {"samples": [{"timestamp": older.isoformat(), "quotes": quotes}]}
    retained, added = analyst.append_macro_market_snapshot(seeded, {"sp500": {"price": 101.0}}, NOW)
    assert added
    assert len(retained["samples"]) == 1
    assert retained["samples"][0]["quotes"]["sp500"]["price"] == 101.0


def test_historical_horizons_require_adequate_independent_coverage():
    old = NOW - timedelta(days=7)
    history = {
        "samples": [{
            "timestamp": old.isoformat(),
            "quotes": {
                "sp500": {"price": 100}, "nasdaq": {"price": 100},
                "vix": {"price": 100}, "dxy": {"price": 100},
            },
        }]
    }
    current = {
        "sp500": {"price": 110}, "nasdaq": {"price": 110},
        "vix": {"price": 90}, "dxy": {"price": 95},
    }

    scores = analyst._historical_horizon_scores(history, current, NOW)

    assert scores["5 pregoes"]["score"] is not None
    assert scores["5 pregoes"]["coverage_pct"] == 50
    assert scores["20 pregoes"]["score"] is None


def test_dashboard_inputs_override_persisted_market_snapshot(monkeypatch):
    import execution.app_state_sync as app_state_sync

    class Query:
        def select(self, *_args):
            return self

        def in_(self, *_args):
            return self

        def execute(self):
            return type("Response", (), {"data": [
                {"key": analyst.FALLBACK_HISTORY_KEY, "value": {"samples": [{"timestamp": NOW.isoformat(), "quotes": {}}]}},
                {"key": "mercados_globais", "value": {"persisted": True}},
            ]})()

    class Client:
        def table(self, *_args):
            return Query()

    client = Client()
    monkeypatch.setattr(app_state_sync, "get_service_client", lambda: client)
    dashboard_snapshot = {"dashboard": "same in-memory snapshot"}

    inputs, loaded_client = analyst._load_macro_inputs({"mercados_globais": dashboard_snapshot})

    assert loaded_client is client
    assert inputs["mercados_globais"] is dashboard_snapshot
    assert len(inputs[analyst.FALLBACK_HISTORY_KEY]["samples"]) == 1


def test_dashboard_rtd_is_contextual_and_requires_recent_market_tick():
    fresh_rtd = [{
        "symbol": "WINF27",
        "updated_at": NOW.isoformat(),
        "market_timestamp": NOW.isoformat(),
        "last_price": 130000,
        "change_percent": 0.45,
        "saldo_agressao": 2500,
        "semaforo": {"direcao": "COMPRA"},
    }]
    stale_rtd = [{**fresh_rtd[0], "market_timestamp": (NOW - timedelta(seconds=40)).isoformat()}]

    fresh = analyst._dashboard_rtd_context(fresh_rtd, NOW)
    stale = analyst._dashboard_rtd_context(stale_rtd, NOW)

    assert fresh["usable_for_confirmation"]
    assert any("saldo de agressao" in line for line in fresh["evidence"])
    assert not stale["usable_for_confirmation"]
    assert "atrasado" in stale["evidence"][0]


def test_manual_analysis_refreshes_old_or_low_coverage_snapshots():
    assert analyst._macro_snapshot_needs_refresh({
        "data_quality": {"coverage_pct": 20}, "market_snapshot_age_seconds": 30,
    })
    assert analyst._macro_snapshot_needs_refresh({
        "data_quality": {"coverage_pct": 80}, "market_snapshot_age_seconds": 601,
    })
    assert analyst._macro_snapshot_needs_refresh({
        "data_quality": {"coverage_pct": 80}, "market_snapshot_age_seconds": None,
    })
    assert not analyst._macro_snapshot_needs_refresh({
        "data_quality": {"coverage_pct": 80}, "market_snapshot_age_seconds": 500,
    })


def test_on_demand_refresh_replaces_stale_snapshot_with_dashboard_collector(monkeypatch):
    import execution.market_data_engine as market_data_engine

    client = object()
    old_snapshot = {"metadata": {"generated_at_utc": "old"}}
    updated_snapshot = {"metadata": {"generated_at_utc": NOW.isoformat()}}
    inputs = {"mercados_globais": old_snapshot}
    calls = []

    def collect(passed_client):
        calls.append(passed_client)
        return updated_snapshot

    monkeypatch.setattr(market_data_engine, "collect_and_publish_market_snapshot", collect)
    snapshot, status = analyst._refresh_macro_dashboard_snapshot(
        inputs, client, {"data_quality": {"coverage_pct": 20}, "market_snapshot_age_seconds": 30}
    )

    assert snapshot is updated_snapshot
    assert inputs["mercados_globais"] is updated_snapshot
    assert calls == [client]
    assert status == {"attempted": True, "succeeded": True, "error": None}
