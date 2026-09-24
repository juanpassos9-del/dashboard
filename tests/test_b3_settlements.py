import io
import zipfile
from datetime import date

import pytest

from execution.fetch_b3_settlements import (
    SettlementNotFoundError,
    _with_changes,
    _win_expiry,
    build_settlement_levels,
    parse_bvbg187,
    select_front_contract,
)


def _nested_report_zip() -> bytes:
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <Document xmlns="urn:bvmf.052.01.xsd"><PricRpt xmlns="urn:bvmf.217.01.xsd">
      <TradDt><Dt>2026-09-23</Dt></TradDt><SctyId><TckrSymb>WINV26</TckrSymb></SctyId>
      <FinInstrmAttrbts><OpnIntrst>100</OpnIntrst><RglrTxsQty>900</RglrTxsQty>
      <AdjstdQt>187044</AdjstdQt><PrvsAdjstdQt>188810</PrvsAdjstdQt><AdjstdQtStin>F</AdjstdQtStin></FinInstrmAttrbts>
    </PricRpt><PricRpt xmlns="urn:bvmf.217.01.xsd">
      <TradDt><Dt>2026-09-23</Dt></TradDt><SctyId><TckrSymb>WDOV26</TckrSymb></SctyId>
      <FinInstrmAttrbts><OpnIntrst>200</OpnIntrst><RglrTxsQty>800</RglrTxsQty>
      <AdjstdQt>5175.139</AdjstdQt><PrvsAdjstdQt>5114.328</PrvsAdjstdQt><AdjstdQtStin>F</AdjstdQtStin></FinInstrmAttrbts>
    </PricRpt></Document>"""
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w") as inner:
        inner.writestr("BVBG.187.01.xml", xml)
    outer_buffer = io.BytesIO()
    with zipfile.ZipFile(outer_buffer, "w") as outer:
        outer.writestr("SPRD260923.zip", inner_buffer.getvalue())
    return outer_buffer.getvalue()


def test_parse_and_select_front_contracts():
    records = parse_bvbg187(_nested_report_zip())
    trade_date = date(2026, 9, 23)
    assert select_front_contract(records, "WIN", trade_date)["ticker"] == "WINV26"
    assert select_front_contract(records, "WDO", trade_date)["ticker"] == "WDOV26"


def test_win_expiry_is_nearest_wednesday_to_day_15():
    assert _win_expiry(2026, 10) == date(2026, 10, 14)


def test_change_calculation():
    result = _with_changes({"settlement": 187044.0, "previous_settlement": 188810.0})
    assert result["change_points"] == -1766.0
    assert result["change_percent"] == pytest.approx(-0.935331815)


def test_win_levels_use_half_percent_and_five_point_tick():
    levels = build_settlement_levels(187044, 0.5, tick_size=5)
    assert [item["percent"] for item in levels["up"]] == [0.5, 1.0, 1.5, 2.0, 2.5]
    assert levels["up"][0]["price"] == 187980
    assert levels["down"][0]["price"] == 186110
    assert all(item["price"] % 5 == 0 for item in levels["up"] + levels["down"])


def test_wdo_levels_use_quarter_percent_and_half_point_tick():
    levels = build_settlement_levels(5175.139, 0.25, tick_size=0.5)
    assert [item["percent"] for item in levels["up"]] == [0.25, 0.5, 0.75, 1.0, 1.25]
    assert levels["up"][0]["price"] == 5188.0
    assert levels["down"][0]["price"] == 5162.0
    assert all((item["price"] * 2).is_integer() for item in levels["up"] + levels["down"])


def test_expired_win_is_rejected():
    records = parse_bvbg187(_nested_report_zip())
    with pytest.raises(SettlementNotFoundError):
        select_front_contract(records, "WIN", date(2026, 10, 15))
