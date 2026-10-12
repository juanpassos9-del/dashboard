from datetime import date, datetime, timezone

from execution.renda_fixa_br import build_di_curve_rows, historical_delta, latest_rows, parse_tesouro_csv, title_history


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


def test_invalid_csv_fails_instead_of_reporting_empty_success():
    try:
        parse_tesouro_csv("wrong;columns\nvalue;value")
    except ValueError as exc:
        assert "não contém linhas válidas" in str(exc)
    else:
        raise AssertionError("CSV inválido deveria falhar")
