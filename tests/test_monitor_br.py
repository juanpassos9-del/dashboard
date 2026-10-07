from execution.monitor_br import _flow_snapshot, _focus_snapshot, _market_asset, _series_reading


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
    data = {"publish_date": "2026-10-05", "updated_at": "2026-10-05T12:00:00-03:00", "years": {"2026": {"IPCA": {"hoje": 4.2, "4_sem": 4.0}}}}
    result = _focus_snapshot(data)
    assert result["indicators"]["IPCA"] == {"value": 4.2, "delta_4w": 0.2}
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


def test_market_asset_finds_symbol_across_categories():
    data = {"categories": {"indices": [{"symbol": "^BVSP", "price": 130000}]}}
    result = _market_asset(data, ("^BVSP",))
    assert result["symbol"] == "^BVSP"
    assert result["price"] == 130000
    assert result["freshness"] == "sem horário"
