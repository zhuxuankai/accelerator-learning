from acc_cockpit.evaluation import quality_gate


def test_quality_gate_passes_thresholds():
    result = quality_gate(
        {"page_hit@3": 0.9, "recall@50": 0.95, "empty_rate": 0.0},
        {"page_hit_at_3": 0.8, "recall_at_50": 0.9, "empty_rate_max": 0.1},
    )
    assert result["status"] == "passed"


def test_quality_gate_reports_each_failure():
    result = quality_gate(
        {"page_hit@3": 0.5, "recall@50": 0.8, "empty_rate": 0.2},
        {"page_hit_at_3": 0.8, "recall_at_50": 0.9, "empty_rate_max": 0.1},
    )
    assert result["status"] == "failed"
    assert len(result["failures"]) == 3
