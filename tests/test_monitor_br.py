from execution import monitor_br
from execution.monitor_br import _br_calendar_snapshot, _calendar_event_reading, _flow_snapshot, _focus_snapshot, _market_asset, _series_reading


def test_series_reading_reports_latest_and_change():
    result = _series_reading(
        [{"date": "01/01/2026", "value": 10.0}, {"date": "01/02/2026", "value": 10.5}],
        "selic",
    )
    assert result["value"] == 10.5
    assert result["previous"] == 10.0
    assert result["delta"] == 0.5
    assert result["source"] == "BCB SGS 432"


def test_focus_snapshot_uses_four_week_reference():
    data = {"publish_date": "2026-10-05", "updated_at": "2026-10-05T12:00:00-03:00", "years": {"2026": {"IPCA": {"hoje": 4.2, "4_sem": 4.0}}, "2027": {"IPCA": {"hoje": 3.8, "4_sem": 3.9}}}}
    result = _focus_snapshot(data)
    assert result["indicators"]["IPCA"] == {"value": 4.2, "delta_4w": 0.2}
    assert result["horizons"]["2027"]["IPCA"] == {"value": 3.8, "delta_4w": -0.1}
    assert result["indicators"]["Selic"]["value"] is None
    assert result["updated_at"] == data["updated_at"]


def test_flow_snapshot_summarizes_recent_trading_days():
    result = _flow_snapshot({"source": "Dados de Mercado", "records": [
        {"date": "2026-10-02", "foreigners": 1500},
        {"date": "2026-10-01", "foreigners": -500},
        {"date": "2026-09-30", "foreigners": 2000},
    ]})
    assert result["latest"] == {"date": "2026-10-02", "foreigners_thousands": 1500.0}
    assert result["sum_5d_thousands"] == 3000.0
    assert result["sum_20d_thousands"] == 3000.0


def test_calendar_groups_brazilian_events_and_interprets_inflation_surprise():
    result = _br_calendar_snapshot([
        {"date": "2026-10-01", "currency": "BRL", "event": "IPCA (Mensal)", "actual": "0,50%", "forecast": "0,40%", "previous": "0,30%"},
        {"date": "2026-10-01", "currency": "BRL", "event": "IPCA (Mensal)", "actual": "---", "forecast": "---", "previous": "---"},
        {"date": "2026-10-01", "currency": "USD", "event": "CPI", "actual": "2%", "forecast": "2%"},
    ])
    event = result["groups"]["inflation"][0]
    assert result["total_events"] == 1
    assert event["comparison"] == "Surpresa inflacionária"
    assert event["status"] == "divulgado"
    assert event["movement_vs_previous"] == "Inflação acelerou vs. anterior"


def test_calendar_inverts_unemployment_surprise_and_includes_fiscal_topic():
    result = _br_calendar_snapshot([
        {"date": "2026-10-02", "currency": "BRL", "event": "Taxa de desemprego", "actual": "6,0%", "forecast": "6,2%"},
        {"date": "2026-10-03", "currency": "BRL", "event": "Resultado Primário", "actual": "-10B", "forecast": "-12B"},
    ])
    assert result["groups"]["labor"][0]["comparison"] == "Trabalho mais forte que o consenso"
    assert result["groups"]["labor"][0]["movement_vs_previous"] == "Sem comparação com o anterior"
    assert result["groups"]["fiscal"][0]["comparison"] == "Acima do consenso"


def test_calendar_accepts_brazil_country_name_from_fallback_source():
    result = _br_calendar_snapshot([
        {"date": "2026-10-01", "currency": "Brazil", "event": "Vendas no Varejo", "actual": "1,2%", "forecast": "0,5%", "previous": "0,8%"},
    ])
    assert result["groups"]["consumption_activity"][0]["movement_vs_previous"] == "Atividade avançou vs. anterior"
    assert result["latest_released_date"] == "2026-10-01"


def test_official_ibge_release_is_not_mislabeled_as_an_actual_value():
    event = _calendar_event_reading({
        "date": "2026-10-01", "time": "09:00", "currency": "BRL", "event": "Índice Nacional de Preços ao Consumidor Amplo",
        "actual": "---", "forecast": "---", "previous": "---", "official_release": True,
        "source": "IBGE · API oficial", "reference_period": "2026-08",
    }, "inflation")
    assert event["status"] == "data divulgada"
    assert event["actual"] == "---"
    assert "indisponível nesta fonte" in event["comparison"]
    assert event["reference_period"] == "2026-08"


def test_market_asset_finds_symbol_across_categories():
    data = {"categories": {"indices": [{"symbol": "^BVSP", "price": 130000}]}}
    result = _market_asset(data, ("^BVSP",))
    assert result["symbol"] == "^BVSP"
    assert result["price"] == 130000
    assert result["freshness"] == "sem horário"


def test_monitor_payload_builds_calendar_before_history_metadata(monkeypatch):
    monkeypatch.setattr(monitor_br, "_fetch_bcb_series", lambda series_id, count: [])
    monkeypatch.setattr(monitor_br, "_fetch_ibge_ipca", lambda: None)
    monkeypatch.setattr(
        "execution.monitor_br_history.fetch_monitor_br_history",
        lambda: {"series": [], "errors": []},
    )

    payload = monitor_br.build_monitor_br_payload(
        calendar_events=[{"date": "2026-10-01", "currency": "BRL", "event": "IPCA mensal", "actual": "0,4%"}],
        calendar_history={"event_count": 1, "ibge_calendar_status": "ok:1"},
    )

    assert payload["calendar_br"]["total_events"] == 1
    assert payload["calendar_history"]["official_release_count"] == payload["calendar_br"]["official_release_count"]


def test_monitor_payload_includes_monetary_policy_documents_and_horizon(monkeypatch):
    monkeypatch.setattr(monitor_br, "_fetch_bcb_series", lambda series_id, count: [{"date": "01/10/2026", "value": 15.0}] if series_id == 432 else [])
    monkeypatch.setattr(monitor_br, "_fetch_ibge_ipca", lambda: None)
    monkeypatch.setattr("execution.monitor_br_history.fetch_monitor_br_history", lambda: {"series": [], "errors": []})
    monkeypatch.setattr("execution.monetary_policy.fetch_copom_documents", lambda: [{"title": "Ata recente", "document_url": "https://www.bcb.gov.br/ata"}])

    payload = monitor_br.build_monitor_br_payload(focus={
        "publish_date": "2026-10-05",
        "years": {"2026": {"IPCA": {"hoje": 4.3, "4_sem": 4.2}}},
    })

    assert payload["monetary_policy"]["selic"]["value"] == 15.0
    assert payload["monetary_policy"]["focus_horizons"]["2026"]["IPCA"]["value"] == 4.3
    assert payload["monetary_policy"]["documents"][0]["title"] == "Ata recente"
