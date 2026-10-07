from execution.monitor_br_briefing import build_monitor_br_briefing


def test_briefing_translates_current_indicators_into_plain_language():
    payload = {
        "official": {"selic": {"value": 15.0, "date": "07/10/2026"}},
        "official_history": {"series": [
            {"key": "ipca", "observations": [
                {"period": "202607", "date": "2026-07", "value": 0.2},
                {"period": "202608", "date": "2026-08", "value": 0.5},
            ]},
            {"key": "ipca_group_1", "name": "Alimentação", "observations": [
                {"period": "202608", "contribution_pp_approx": 0.2},
            ]},
            {"key": "ipca_group_2", "name": "Habitação", "observations": [
                {"period": "202608", "contribution_pp_approx": -0.1},
            ]},
            {"key": "ibc_br", "name": "IBC-Br", "unit": "índice", "observations": [
                {"period": "202607", "date": "2026-07", "value": 110},
                {"period": "202608", "date": "2026-08", "value": 111},
            ]},
            {"key": "retail", "name": "Varejo", "unit": "% m/m", "observations": [
                {"period": "202607", "date": "2026-07", "value": 0.4},
                {"period": "202608", "date": "2026-08", "value": -0.2},
            ]},
            {"key": "unemployment", "observations": [
                {"period": "2026-07", "date": "2026-07", "value": 5.2},
                {"period": "2026-08", "date": "2026-08", "value": 5.4},
            ]},
            {"key": "credit_interest", "name": "Juros", "observations": [
                {"period": "2026-07", "date": "2026-07", "value": 32.0},
                {"period": "2026-08", "date": "2026-08", "value": 32.2},
            ]},
            {"key": "credit_delinquency", "name": "Inadimplência", "observations": [
                {"period": "2026-07", "date": "2026-07", "value": 5.0},
                {"period": "2026-08", "date": "2026-08", "value": 5.1},
            ]},
            {"key": "credit_balance", "name": "Saldo", "observations": [
                {"period": "2026-07", "date": "2026-07", "value": 7_300_000},
                {"period": "2026-08", "date": "2026-08", "value": 7_400_000},
            ]},
            {"key": "credit_concessions", "name": "Concessões", "observations": [
                {"period": "2026-07", "date": "2026-07", "value": 700_000},
                {"period": "2026-08", "date": "2026-08", "value": 710_000},
            ]},
        ]},
        "focus": {"year": "2026", "publish_date": "2026-10-05", "indicators": {"IPCA": {"value": 4.3, "delta_4w": 0.1}}},
        "derived": {"selic_di_spread_pp": 0.5},
        "monetary_policy": {"next_meeting": {"decision_date": "2026-11-04"}},
    }

    briefing = build_monitor_br_briefing(payload)
    rendered_text = " ".join(point["text"] for point in briefing["points"])

    assert [point["title"] for point in briefing["points"]] == [
        "Preços", "Atividade e consumo", "Trabalho", "Crédito", "Juros e expectativas",
    ]
    assert "subiu de 0,20% para 0,50%" in rendered_text
    assert "Alimentação" in rendered_text and "Habitação" in rendered_text
    assert "taxa trimestral móvel" in rendered_text
    assert "sem descontar a inflação" in rendered_text
    assert "R$ 7.400,0 bilhões" in rendered_text
    assert "não uma promessa" in rendered_text
    assert "DI curto" in rendered_text and "2026-11-04" in rendered_text


def test_briefing_does_not_infer_from_missing_data():
    briefing = build_monitor_br_briefing({"official_history": {"series": []}})

    assert briefing["points"] == []
    assert "séries suficientes" in briefing["empty_message"]


def test_briefing_falls_back_to_current_ipca_when_history_is_unavailable():
    briefing = build_monitor_br_briefing({
        "official": {"ipca": {"value": 0.4, "previous": 0.2, "date": "08/2026"}},
        "official_history": {"series": []},
    })

    assert briefing["points"][0]["title"] == "Preços"
    assert "0,40%" in briefing["points"][0]["text"]
    assert briefing["points"][0]["reference"].startswith("BCB SGS 433")
