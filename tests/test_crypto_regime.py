from execution.crypto_regime import calculate_crypto_regime


def _inputs(onchain):
    return (
        {"data": {"assets": [
            {"symbol": "BTCUSDT", "price": 100, "change_pct_24h": 0, "trend_80h_pct": 0, "funding_rate": 0},
            {"symbol": "ETHUSDT", "price": 50, "change_pct_24h": 0, "trend_80h_pct": 0, "funding_rate": 0},
        ]}},
        {"data": {"btc_dominance": 50, "eth_dominance": 15, "total_market_cap_usd": 1000}},
        {"data": {"current": {"value": 50}}},
        {"data": {"stablecoin_market_cap_usd": 50, "total_tvl_usd": 100}},
        {"data": onchain},
    )


def _calculate(onchain):
    return calculate_crypto_regime(*_inputs(onchain), save_file=False)


def test_balanced_price_contributes_moderately_and_is_exposed_in_regime():
    base = _calculate({"mvrv": 1.5, "mvrv_z_score": 3, "mayer_multiple": 1.2, "puell_multiple": 1, "aviv": 1})
    discounted = _calculate({
        "mvrv": 1.5, "mvrv_z_score": 3, "mayer_multiple": 1.2, "puell_multiple": 1, "aviv": 1,
        "balanced_price": 110, "balanced_price_date": "2026-11-11",
    })

    assert discounted["score"] == base["score"] + 4
    assert discounted["onchain"]["balanced_gap_pct"] == -9.09
    assert discounted["onchain"]["balanced_price_date"] == "2026-11-11"
    assert any("Balanced Price" in item for item in discounted["drivers_positive"])


def test_realized_price_is_used_if_mvrv_is_missing():
    result = _calculate({
        "mvrv_z_score": 3, "mayer_multiple": 1.2, "puell_multiple": 1, "aviv": 1,
        "realized_price": 110,
    })

    assert result["onchain"]["realized_gap_pct"] == -9.09
    assert any("abaixo do Realized Price" in item for item in result["drivers_positive"])


def test_realized_price_does_not_double_count_when_mvrv_is_present():
    base = _calculate({"mvrv": 1.5, "mvrv_z_score": 3, "mayer_multiple": 1.2, "puell_multiple": 1, "aviv": 1})
    with_realized = _calculate({
        "mvrv": 1.5, "mvrv_z_score": 3, "mayer_multiple": 1.2, "puell_multiple": 1, "aviv": 1,
        "realized_price": 110,
    })

    assert with_realized["score"] == base["score"]
    assert any("confirmacao do MVRV" in item for item in with_realized["drivers_positive"])
