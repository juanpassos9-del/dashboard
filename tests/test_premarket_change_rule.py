from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from execution.fetch_global_markets import (
    PREMARKET_CHANGE_TICKERS,
    _extended_hours_snapshot,
    _uses_premarket_change,
)


BR_TZ = ZoneInfo("America/Sao_Paulo")
NY_TZ = ZoneInfo("America/New_York")


def test_only_eight_requested_symbols_use_premarket_change():
    assert PREMARKET_CHANGE_TICKERS == {"BBD", "BDORY", "ITUB", "VALE", "PBR", "EWZ", "EWZS", "EEM"}
    assert _uses_premarket_change("EWZ", datetime(2026, 10, 5, 10, 29, tzinfo=BR_TZ))
    assert not _uses_premarket_change("SPY", datetime(2026, 10, 5, 10, 0, tzinfo=BR_TZ))


def test_premarket_change_uses_previous_regular_close_until_brazil_cutoff():
    session_date = datetime(2026, 10, 5).date()
    index = pd.DatetimeIndex([
        datetime(2026, 10, 2, 15, 59, tzinfo=NY_TZ),
        datetime(2026, 10, 5, 4, 0, tzinfo=NY_TZ),
        datetime(2026, 10, 5, 9, 25, tzinfo=NY_TZ),
    ])
    frame = pd.DataFrame(
        {"Close": [100.0, 101.0, 105.0], "High": [100.0, 101.0, 105.0], "Low": [100.0, 101.0, 101.0]},
        index=index,
    )

    snapshot = _extended_hours_snapshot("EWZ", frame, now_br=datetime(2026, 10, 5, 10, 29, tzinfo=BR_TZ))

    assert snapshot["market_state"] == "PRE"
    assert snapshot["price"] == 105.0
    assert snapshot["change"] == 5.0
    assert snapshot["change_basis"] == "previous_close_including_premarket"
    assert snapshot["regular_prev_close"] == 100.0
    assert snapshot["high"] == 105.0


def test_premarket_special_variation_ends_at_1030_brazil():
    assert _uses_premarket_change("EEM", datetime(2026, 10, 5, 10, 29, 59, tzinfo=BR_TZ))
    assert not _uses_premarket_change("EEM", datetime(2026, 10, 5, 10, 30, tzinfo=BR_TZ))
    assert not _uses_premarket_change("EEM", datetime(2026, 10, 5, 11, 0, tzinfo=BR_TZ))
