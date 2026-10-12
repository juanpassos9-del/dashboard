from execution.top_movers import choose_top_movers_payload


def _payload(source, count):
    return {"source": source, "rows_count": count, "gainers": [{"ticker": "AAA"}], "losers": []}


def test_sufficient_primary_coverage_wins_over_fallback():
    yahoo = _payload("Yahoo Finance", 12)
    brapi = _payload("Brapi", 20)

    assert choose_top_movers_payload(yahoo, brapi, minimum_rows=10) is yahoo


def test_fallback_wins_when_primary_coverage_is_incomplete():
    yahoo = _payload("Yahoo Finance", 4)
    brapi = _payload("Brapi", 8)

    assert choose_top_movers_payload(yahoo, brapi, minimum_rows=10) is brapi


def test_primary_partial_data_is_kept_if_fallback_is_not_better():
    yahoo = _payload("Yahoo Finance", 5)
    brapi = _payload("Brapi", 3)

    assert choose_top_movers_payload(yahoo, brapi, minimum_rows=10) is yahoo


def test_no_sources_returns_empty_payload():
    assert choose_top_movers_payload(None, None, minimum_rows=10) == {
        "gainers": [], "losers": [], "updated_at": "", "source": "Yahoo Finance/Brapi"
    }
