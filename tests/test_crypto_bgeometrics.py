from execution import crypto_bgeometrics


def test_normalize_daily_metric_parses_bgeometrics_rows():
    rows = crypto_bgeometrics._normalize_daily_metric(
        [
            {"d": "2026-11-10", "unixTs": 1794268800, "balancedPrice": 0},
            {"d": "2026-11-11", "unixTs": 1794355200, "balancedPrice": 29305.42},
            {"d": "invalid", "balancedPrice": 12},
        ],
        "balancedPrice",
    )

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-11"
    assert rows[0]["balancedPrice"] == 29305.42


def test_balanced_price_history_uses_cached_public_series(monkeypatch):
    saved = {}

    class Response:
        text = ""

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return [
                {"d": "2026-11-10", "unixTs": 1794268800, "balancedPrice": 29000},
                {"d": "2026-11-11", "unixTs": 1794355200, "balancedPrice": 29305.42},
            ]

    monkeypatch.setattr(crypto_bgeometrics, "load_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(crypto_bgeometrics, "save_cache", lambda name, payload: saved.update(payload))
    monkeypatch.setattr(crypto_bgeometrics, "mark_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(crypto_bgeometrics.requests, "get", lambda *args, **kwargs: Response())

    payload = crypto_bgeometrics.fetch_bgeometrics_balanced_price_history(days=2)

    assert payload["status"] == "ok"
    assert payload["data"]["latest"]["balancedPrice"] == 29305.42
    assert saved["data"]["points"] == payload["data"]["points"]
