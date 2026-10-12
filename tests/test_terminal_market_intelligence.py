from datetime import datetime, timezone

from execution.terminal_market_intelligence import (
    audit_rtd_payload,
    build_terminal_market_brief,
    format_age,
    rtd_number,
    rtd_text,
)


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def test_rtd_bridge_age_uses_sao_paulo_for_naive_bridge_timestamp():
    audit = audit_rtd_payload({"updated_at": "2026-10-12 08:59:50"}, now=NOW)

    assert audit["bridge_age_seconds"] == 10
    assert audit["state"] == "fresh"
    assert audit["market_timestamp"] is None
    assert any("idade de mercado desconhecida" in warning for warning in audit["warnings"])


def test_rtd_excel_error_sentinel_is_rejected_as_quote_and_signal():
    audit = audit_rtd_payload({
        "symbol": "WINZ26",
        "last_price": -2146826246,
        "vwap": 130000,
        "semaforo": {"direcao": "-2146826246"},
    }, now=NOW)

    assert audit["state"] == "invalid"
    assert audit["valid_values"]["last_price"] is None
    assert "last_price" in audit["invalid_fields"]
    assert rtd_number(-2146826246) is None
    assert rtd_text("-2146826246") == "indisponível"


def test_terminal_brief_reports_confirmation_and_rtd_divergence_with_context():
    observed_at = NOW.isoformat()
    markets = {
        "metadata": {"generated_at_utc": observed_at},
        "categories": {
            "fx": [{"symbol": "BRL=X", "change": 0.4, "change_basis": "previous_session_close", "source_timestamp": observed_at, "max_age_seconds": 600}],
            "rates": [
                {"symbol": symbol, "change": 0.3, "source_timestamp": observed_at, "max_age_seconds": 1800}
                for symbol in ("DI1F27", "DI1F29", "DI1F32")
            ],
            "indices": [{"symbol": "^GSPC", "change": 0.6, "source_timestamp": observed_at, "max_age_seconds": 600}],
        },
    }
    di = {"regime": "Curva DI abrindo", "avg_change": 0.3}
    rtd = audit_rtd_payload({"updated_at": "2026-10-12T09:00:00-03:00", "market_timestamp": observed_at, "semaforo": {"direcao": "COMPRA"}}, now=NOW)
    flow = {"records": [{"date": "2026-10-09", "foreigners": -250000}]}

    brief = build_terminal_market_brief(markets, di, rtd, flow, now=NOW)

    assert brief["available"]
    assert any("DI" in line for line in brief["evidence"])
    assert any("RTD comprador diverge" in line for line in brief["divergences"])
    assert any("Fluxo estrangeiro B3" in line for line in brief["evidence"])
    assert any("diferença de janela" in line for line in brief["quality_notes"])
    assert "não é recomendação" in brief["caveat"]


def test_stale_or_unsynchronized_quotes_are_not_used_as_cross_market_confirmation():
    old_timestamp = "2026-10-12T11:00:00+00:00"
    markets = {
        "metadata": {"generated_at_utc": NOW.isoformat()},
        "categories": {
            "fx": [{"symbol": "BRL=X", "change": 0.4, "source_timestamp": old_timestamp, "max_age_seconds": 600}],
            "rates": [
                {"symbol": symbol, "change": 0.3, "source_timestamp": old_timestamp, "max_age_seconds": 1800}
                for symbol in ("DI1F27", "DI1F29", "DI1F32")
            ],
        },
    }

    brief = build_terminal_market_brief(markets, {"regime": "Curva DI abrindo", "avg_change": 0.3}, None, None, now=NOW)

    assert not brief["confirms"]
    assert any("atrasada" in note or "fora da janela" in note for note in brief["quality_notes"])


def test_fresh_quotes_with_more_than_five_minutes_skew_are_not_compared():
    current = NOW.isoformat()
    older_fx = "2026-10-12T11:54:59+00:00"
    markets = {
        "metadata": {"generated_at_utc": current},
        "categories": {
            "fx": [{"symbol": "BRL=X", "change": 0.4, "source_timestamp": older_fx, "max_age_seconds": 600}],
            "rates": [
                {"symbol": symbol, "change": 0.3, "source_timestamp": current, "max_age_seconds": 1800}
                for symbol in ("DI1F27", "DI1F29", "DI1F32")
            ],
        },
    }

    brief = build_terminal_market_brief(markets, {"regime": "Curva DI abrindo", "avg_change": 0.3}, None, None, now=NOW)

    assert not brief["confirms"]
    assert any("alinhados em até 5 minutos" in note for note in brief["quality_notes"])


def test_empty_brief_and_age_format_are_explicit():
    brief = build_terminal_market_brief(None, None, None, None)

    assert not brief["available"]
    assert brief["headline"] == "Aguardando dados para compor a leitura."
    assert format_age(None) == "idade desconhecida"
    assert format_age(3665) == "1h 1min"
