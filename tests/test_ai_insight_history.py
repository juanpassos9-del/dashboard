from datetime import datetime

from execution.ai_insight_history import append_direction_history, freshness_minutes


def _insight(**updates):
    value = {
        "sentiment": "COMPRA",
        "macro_regime": "Risk-on forte",
        "confidence": "Alta",
        "macro_score": 19,
        "curve_regime": "Bull Flattening",
        "curve_bias": "Risk-on forte",
        "drivers": ["S&P 500 favorável"],
        "provider": "Local",
    }
    return {**value, **updates}


def test_identical_readings_inside_thirty_minutes_are_not_repeated():
    now = datetime.fromisoformat("2026-10-12T10:00:00-03:00")
    history, added = append_direction_history([], _insight(), now)
    repeated, added_again = append_direction_history(history, _insight(), now.replace(minute=5))

    assert added is True
    assert added_again is False
    assert len(repeated) == 1
    assert repeated[0]["updated_at"] == "2026-10-12T10:00:00-03:00"
    assert repeated[0]["provider"] == "Local"


def test_direction_change_is_recorded_immediately():
    now = datetime.fromisoformat("2026-10-12T10:00:00-03:00")
    history, _ = append_direction_history([], _insight(), now)
    changed, added = append_direction_history(
        history,
        _insight(sentiment="VENDA", macro_regime="Risk-off forte", macro_score=-7),
        now.replace(minute=2),
    )

    assert added is True
    assert [item["sentiment"] for item in changed] == ["COMPRA", "VENDA"]


def test_legacy_duplicate_entries_are_compacted_using_epoch_ids():
    history = [
        {"sentiment": "COMPRA", "macro_regime": "Risk-on forte", "confidence": "Alta", "curve_regime": "Bull", "curve_bias": "Risk-on", "macro_score": 19, "id": 1791286125},
        {"sentiment": "COMPRA", "macro_regime": "Risk-on forte", "confidence": "Alta", "curve_regime": "Bull", "curve_bias": "Risk-on", "macro_score": 19, "id": 1791286128},
        {"sentiment": "COMPRA", "macro_regime": "Risk-on forte", "confidence": "Alta", "curve_regime": "Bull", "curve_bias": "Risk-on", "macro_score": 19, "id": 1791286131},
    ]
    compacted, added = append_direction_history(
        history,
        _insight(),
        datetime.fromisoformat("2026-10-12T10:00:00-03:00"),
    )

    assert added is True
    assert len(compacted) == 2
    assert compacted[0]["id"] == 1791286125


def test_freshness_uses_aware_timestamps():
    now = datetime.fromisoformat("2026-10-12T10:20:00-03:00")
    assert freshness_minutes("2026-10-12T10:00:00-03:00", now) == 20
