from datetime import date, datetime, timedelta, timezone

from execution.renda_fixa_br import build_di_curve_rows, build_fixed_income_intelligence, detect_pu_spikes, historical_delta, latest_rows, parse_tesouro_csv, pu_history_coverage, title_history


CSV = """Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha
Tesouro IPCA+;15/05/2035;08/10/2026;6,50;6,55;1.234,56;1.230,10;1.232,33
Tesouro IPCA+;15/05/2035;09/10/2026;6,60;6,65;1.220,50;1.216,00;1.218,25
Tesouro Selic;01/03/2031;09/10/2026;0,09;0,10;19.991,91;19.972,93;19.972,93
"""


def test_parse_tesouro_daily_csv_and_brazilian_numbers():
    payload = parse_tesouro_csv(CSV)
    assert payload["latest_date"] == "2026-10-09"
    assert payload["rows"][0]["buy_price"] == 1234.56
    assert payload["rows"][0]["buy_rate"] == 6.5
    assert len(latest_rows(payload)) == 2


def test_title_history_filters_by_exact_title_and_maturity():
    payload = parse_tesouro_csv(CSV)
    history = title_history(payload, "Tesouro IPCA+", "2035-05-15")
    assert [row["date"] for row in history] == ["2026-10-08", "2026-10-09"]
    assert len(title_history(payload, "Tesouro Selic", "2035-05-15")) == 0


def test_historical_delta_uses_previous_observation_and_rate_point_change():
    payload = parse_tesouro_csv(CSV)
    history = title_history(payload, "Tesouro IPCA+", "2035-05-15")
    daily, daily_date = historical_delta(history, history[-1], "buy_rate", days=1)
    assert abs(daily - 0.1) < 1e-9
    assert daily_date == "2026-10-08"

    relative, reference_date = historical_delta(history, history[-1], "buy_price", days=1, relative=True)
    assert relative < 0
    assert reference_date == "2026-10-08"


def test_historical_delta_returns_missing_when_reference_is_outside_tolerance():
    payload = parse_tesouro_csv(CSV)
    history = title_history(payload, "Tesouro IPCA+", "2035-05-15")
    change, reference_date = historical_delta(history, history[-1], "buy_rate", days=365, tolerance_days=20)
    assert change is None
    assert reference_date is None


def test_di_curve_sorts_active_contracts_and_drops_expired_or_invalid_quotes():
    contracts = [
        {"symbol": "DI1F28", "rate": 12.7, "maturity": "01/01/2028", "last_trade": "08/10/2026 10:00"},
        {"symbol": "DI1X26", "rate": 13.1, "maturity": "01/11/2026", "last_trade": "08/10/2026 10:00"},
        {"symbol": "DI1V26", "rate": 13.2, "maturity": "01/10/2026", "last_trade": "08/10/2026 10:00"},
        {"symbol": "SPX", "rate": 5000, "maturity": "01/01/2028"},
        {"symbol": "DI1G27", "rate": None, "maturity": "01/02/2027"},
    ]
    curve = build_di_curve_rows(contracts, as_of=date(2026, 10, 12))
    assert [item["symbol"] for item in curve] == ["DI1X26", "DI1F28"]
    assert curve[0]["label"] == "nov/26"


def test_di_curve_uses_timestamp_maturity_when_display_date_is_missing():
    maturity_ts = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())
    curve = build_di_curve_rows([
        {"symbol": "DI1F27", "price": 13.3, "maturity_timestamp": maturity_ts},
    ], as_of=date(2026, 10, 12))
    assert curve[0]["maturity"] == "2027-01-01"


def test_pu_spike_detects_large_move_and_uses_same_bond_baseline():
    rows = []
    price = 100.0
    start = date(2026, 1, 1)
    for index in range(45):
        if index == 44:
            price *= 1.02
        else:
            price *= 1.0005
        rows.append({
            "title": "Tesouro IPCA+",
            "maturity": "2035-05-15",
            "date": (start + timedelta(days=index)).isoformat(),
            "base_price": price,
            "buy_price": price - 0.1,
        })
    payload = {"latest_date": rows[-1]["date"], "rows": rows}

    alerts = detect_pu_spikes(payload)
    daily = next(alert for alert in alerts if alert["horizon_sessions"] == 1)
    assert daily["price_field"] == "base_price"
    assert daily["change_percent"] > daily["threshold_percent"]
    assert daily["current_price"] == rows[-1]["base_price"]


def test_pu_spikes_skip_normal_movement_insufficient_history_and_old_titles():
    rows = []
    start = date(2026, 1, 1)
    price = 100.0
    for index in range(45):
        price *= 1.0005
        rows.append({
            "title": "Tesouro Selic",
            "maturity": "2031-03-01",
            "date": (start + timedelta(days=index)).isoformat(),
            "base_price": price,
        })
    short_history = [dict(row, title="Tesouro Prefixado", maturity="2030-01-01") for row in rows[-10:]]
    old_history = [dict(row, title="Tesouro IPCA+", maturity="2032-05-15") for row in rows[:30]]
    payload = {"latest_date": rows[-1]["date"], "rows": rows + short_history + old_history}
    assert detect_pu_spikes(payload) == []


def test_pu_history_coverage_counts_valid_observations_for_current_securities():
    payload = parse_tesouro_csv(CSV)
    coverage = pu_history_coverage(payload, minimum_observations=2)
    assert coverage == {
        "current_securities": 2,
        "covered_securities": 1,
        "minimum_observations": 2,
    }


def test_pu_history_coverage_does_not_count_missing_or_nonpositive_prices():
    payload = {
        "latest_date": "2026-10-09",
        "rows": [
            {"title": "Tesouro Selic", "maturity": "2031-03-01", "date": "2026-10-08", "base_price": 100},
            {"title": "Tesouro Selic", "maturity": "2031-03-01", "date": "2026-10-09", "base_price": 0},
        ],
    }
    assert pu_history_coverage(payload, minimum_observations=2)["covered_securities"] == 0


def test_fixed_income_intelligence_reads_price_yield_breakeven_and_di_curve():
    dates = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
    rows = []
    for index, day in enumerate(dates):
        rows.extend([
            {"title": "Tesouro Prefixado", "maturity": "2030-01-01", "date": day,
             "buy_rate": 10 - index * 0.1, "base_price": 100 + index * 2},
            {"title": "Tesouro IPCA+", "maturity": "2030-05-15", "date": day,
             "buy_rate": 5 - index * 0.1, "base_price": 100 + index * 2},
        ])
    payload = {"latest_date": dates[-1], "rows": rows}
    contracts = [
        {"symbol": "DI1F27", "rate": 12.0, "maturity": "01/01/2027"},
        {"symbol": "DI1F28", "rate": 13.0, "maturity": "01/01/2028"},
    ]

    result = build_fixed_income_intelligence(payload, contracts, as_of=date(2026, 10, 12))

    assert result["median_pu_change_5d"] > 0
    assert result["median_rate_change_5d"] < 0
    assert "valorização por marcação a mercado" in result["summary"]
    assert abs(result["implied_inflation"] - ((1.095 / 1.045 - 1) * 100)) < 1e-9
    assert result["inflation_pairs"] == 1
    assert result["di_slope"] == 1.0
    assert result["di_curve_read"] == "ascendente"


def test_invalid_csv_fails_instead_of_reporting_empty_success():
    try:
        parse_tesouro_csv("wrong;columns\nvalue;value")
    except ValueError as exc:
        assert "não contém linhas válidas" in str(exc)
    else:
        raise AssertionError("CSV inválido deveria falhar")
