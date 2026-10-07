from execution.monitor_br import _focus_snapshot, _market_asset, _series_reading


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
    data = {"publish_date": "2026-10-05", "years": {"2026": {"IPCA": {"hoje": 4.2, "4_sem": 4.0}}}}
    result = _focus_snapshot(data)
    assert result["indicators"]["IPCA"] == {"value": 4.2, "delta_4w": 0.2}
    assert result["indicators"]["Selic"]["value"] is None


def test_market_asset_finds_symbol_across_categories():
    data = {"categories": {"indices": [{"symbol": "^BVSP", "price": 130000}]}}
    result = _market_asset(data, ("^BVSP",))
    assert result["symbol"] == "^BVSP"
    assert result["price"] == 130000
    assert result["freshness"] == "sem horário"
