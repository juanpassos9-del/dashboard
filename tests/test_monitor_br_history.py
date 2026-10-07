from execution import monitor_br_history as history


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_sidra_series_parses_values_and_discards_missing_periods(monkeypatch):
    payload = [{"resultados": [{"series": [{"serie": {"202601": "0.4", "202602": ".."}}]}]}]
    monkeypatch.setattr(history.requests, "get", lambda *args, **kwargs: FakeResponse(payload))

    rows = history._fetch_sidra_series(history.SIDRA_SERIES[0], 24, 10)

    assert rows == [{"period": "202601", "date": "2026-01", "value": 0.4}]


def test_bcb_ibc_uses_date_range_not_limited_ultimos_endpoint(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse([{"data": "01/01/2026", "valor": "110.2"}])

    monkeypatch.setattr(history.requests, "get", fake_get)
    rows = history._fetch_bcb_ibc_br(36, 10)

    assert seen["url"].endswith("/dados")
    assert seen["params"]["dataInicial"]
    assert rows[0]["value"] == 110.2


def test_history_keeps_available_official_sources_when_one_fails(monkeypatch):
    def fake_sidra(spec, periods, timeout):
        return [{"period": "202601", "date": "2026-01", "value": 0.5}]

    def fail_bcb(periods, timeout):
        raise RuntimeError("temporariamente indisponível")

    monkeypatch.setattr(history, "_fetch_sidra_series", fake_sidra)
    monkeypatch.setattr(history, "_fetch_bcb_ibc_br", fail_bcb)

    result = history.fetch_monitor_br_history(periods=36)

    assert [item["key"] for item in result["series"]] == ["ipca", "retail", "unemployment"]
    assert len(result["errors"]) == 1
    assert "IBC-Br" in result["errors"][0]
