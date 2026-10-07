from execution import monitor_br_history as history


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

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
    monkeypatch.setattr(history, "_fetch_ipca_group", lambda *args: {"key": "ipca_group_test", "name": "Grupo", "observations": [{"period": "202601", "date": "2026-01", "value": 0.1}]})
    monkeypatch.setattr(history, "_fetch_bcb_credit_series", lambda spec, *args: {"key": spec["key"], "name": spec["name"], "observations": [{"period": "2026-01-01", "date": "2026-01-01", "value": 1.0}]})

    result = history.fetch_monitor_br_history(periods=36)

    keys = [item["key"] for item in result["series"]]
    assert keys[:3] == ["ipca", "retail", "unemployment"]
    assert "ipca_group_test" in keys
    assert "credit_balance" in keys
    assert len(result["errors"]) == 1
    assert "IBC-Br" in result["errors"][0]


def test_ipca_group_parser_includes_monthly_weight_and_approx_contribution(monkeypatch):
    payload = [
        {"id": "63", "resultados": [{"series": [{"serie": {"202608": "0.5"}}]}]},
        {"id": "66", "resultados": [{"series": [{"serie": {"202608": "20.0"}}]}]},
    ]
    monkeypatch.setattr(history.requests, "get", lambda *args, **kwargs: FakeResponse(payload))

    result = history._fetch_ipca_group("7170", "Alimentação e bebidas", 120, 10)

    assert result["observations"] == [{
        "period": "202608", "date": "2026-08", "value": 0.5,
        "weight": 20.0, "contribution_pp_approx": 0.1,
    }]


def test_bcb_credit_uses_range_sgs_endpoint(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        return FakeResponse([{"data": "01/09/2026", "valor": "5.04"}])

    monkeypatch.setattr(history.requests, "get", fake_get)
    result = history._fetch_bcb_credit_series(history.BCB_CREDIT_SERIES[-1], 24, 10)

    assert ".21082/" in seen["url"]
    assert result["observations"][0]["value"] == 5.04


def test_bcb_sgs_retries_transient_server_error(monkeypatch):
    attempts = []

    def fake_get(url, **kwargs):
        attempts.append(url)
        response = FakeResponse([{"data": "01/01/2026", "valor": "100"}])
        response.status_code = 502 if len(attempts) == 1 else 200
        return response

    monkeypatch.setattr(history.requests, "get", fake_get)
    monkeypatch.setattr(history.time, "sleep", lambda _: None)

    rows = history._fetch_bcb_sgs_range(20539, 12, 10)

    assert len(attempts) == 2
    assert rows[0]["value"] == 100
