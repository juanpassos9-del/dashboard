from execution.monitor_br_vintages import latest_monitor_br_revisions, merge_monitor_br_vintages


def test_vintages_deduplicate_identical_values_and_keep_changed_value_as_revision():
    history = {"series": [{
        "key": "ipca", "name": "IPCA", "topic": "Inflação", "unit": "% m/m", "source": "IBGE",
        "observations": [{"period": "202608", "date": "2026-08", "value": 0.4}],
    }]}
    first = merge_monitor_br_vintages({}, history, collected_at="2026-10-01T09:00:00-03:00")
    repeated = merge_monitor_br_vintages(first, history, collected_at="2026-10-02T09:00:00-03:00")

    assert repeated["observation_count"] == 1
    assert repeated["added_observations"] == 0

    revised_history = {"series": [{**history["series"][0], "observations": [{"period": "202608", "date": "2026-08", "value": 0.5}]}]}
    revised = merge_monitor_br_vintages(repeated, revised_history, collected_at="2026-10-03T09:00:00-03:00")
    revisions = latest_monitor_br_revisions(revised)

    assert revised["observation_count"] == 2
    assert revised["revision_count"] == 1
    assert revisions[0]["Valor anterior"] == 0.4
    assert revisions[0]["Valor atual"] == 0.5


def test_vintages_limits_archive_and_skips_missing_values():
    history = {"series": [{"key": "s", "observations": [
        {"period": "1", "value": 1}, {"period": "2", "value": None},
        {"period": "3", "value": 3},
    ]}]}
    archive = merge_monitor_br_vintages({}, history, collected_at="2026-10-01T09:00:00-03:00", max_rows=1)

    assert archive["observation_count"] == 1
    assert archive["observations"][0]["reference_period"] == "3"
