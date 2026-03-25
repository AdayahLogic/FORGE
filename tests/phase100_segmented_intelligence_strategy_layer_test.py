"""
Phase 100 segmented intelligence + strategy layer tests.

Run: python tests/phase100_segmented_intelligence_strategy_layer_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase100_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def test_normalize_execution_package_adds_phase100_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase100proj",
            "project_path": "C:/phase100",
            "business_function": "sales",
        }
    )
    assert package["segment_id"].startswith("seg-")
    assert package["segment_type"] in {"industry", "business_function", "opportunity", "value_tier", "pipeline_group"}
    assert package["segment_key"]
    assert 0.0 <= float(package["segment_confidence"]) <= 1.0
    assert package["segment_reason"]
    assert package["recommended_strategy_type"] in {
        "aggressive_follow_up",
        "soft_nurture_sequence",
        "high_touch_manual",
        "fast_conversion_push",
    }
    assert package["strategy_confidence_level"] in {"low", "medium", "high"}
    assert package["data_maturity_level"] in {"low", "medium", "high"}
    assert package["detected_pattern_type"] in {
        "repeated_drop_off",
        "high_performing_sequence",
        "ineffective_follow_up",
        "timing_sensitivity",
        "insufficient_pattern_evidence",
    }
    assert package["strategy_recommendation_only"] is True
    assert package["strategy_governance_guard"] == "recommendation_only_no_auto_execution"


def test_low_data_defaults_to_exploration_mode():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase100proj",
            "project_path": "C:/phase100",
            "pipeline_stage": "intake",
            "metadata": {"revenue_recent_outcomes": []},
        }
    )
    assert package["data_maturity_level"] == "low"
    assert package["exploration_mode"] is True
    assert package["recommended_strategy_type"] in {"soft_nurture_sequence", "high_touch_manual"}


def test_governance_block_forces_manual_strategy():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase100proj",
            "project_path": "C:/phase100",
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert package["recommended_strategy_type"] == "high_touch_manual"
    assert package["recommended_follow_up_pattern"] == "operator_gated_checkpoints"
    assert package["strategy_recommendation_only"] is True


def test_high_data_can_raise_maturity_and_confidence():
    from NEXUS.execution_package_registry import normalize_execution_package

    outcomes = [
        {"status": "closed_won", "channel": "email", "stage": "proposal_pending", "at": f"2026-03-{i:02d}T00:00:00Z"}
        for i in range(1, 10)
    ]
    package = normalize_execution_package(
        {
            "project_name": "phase100proj",
            "project_path": "C:/phase100",
            "industry": "Healthcare",
            "pipeline_stage": "proposal_pending",
            "roi_estimate": 0.88,
            "conversion_probability": 0.8,
            "time_sensitivity": 0.77,
            "metadata": {
                "revenue_recent_outcomes": outcomes,
                "action_tracking_summary": {"total_actions": 10},
                "follow_up_intelligence": {
                    "observed_sequences": 8,
                    "response_rate": 0.7,
                    "conversion_rate": 0.66,
                    "follow_up_success_rate": 0.69,
                    "sequence_completion_rate": 0.72,
                },
            },
        }
    )
    assert package["data_maturity_level"] in {"medium", "high"}
    assert package["strategy_confidence_level"] in {"medium", "high"}
    assert package["data_point_count"] >= 15


def test_command_surface_queue_and_details_expose_phase100_fields():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase100",
                "project_name": "phase100proj",
                "project_path": str(tmp),
                "industry": "technology",
                "pipeline_stage": "qualified",
                "metadata": {
                    "revenue_recent_outcomes": [
                        {"status": "closed_won", "channel": "email", "stage": "proposal_pending", "at": "2026-03-01T00:00:00Z"}
                    ]
                },
            },
        )
        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        row = queue["payload"]["packages"][0]
        assert "segment_key" in row
        assert "recommended_strategy_type" in row
        assert "strategy_confidence_level" in row
        assert row.get("strategy_recommendation_only") is True

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-phase100")
        assert details["status"] == "ok"
        review_header = details["payload"]["review_header"]
        assert "segment_key" in review_header
        assert "recommended_strategy_type" in review_header
        assert "strategy_confidence_level" in review_header
        assert review_header.get("strategy_recommendation_only") is True
        scope = (details["payload"]["sections"] or {}).get("scope") or {}
        assert "segment_classification" in scope
        assert "strategy_recommendation" in scope


def main():
    tests = [
        test_normalize_execution_package_adds_phase100_fields,
        test_low_data_defaults_to_exploration_mode,
        test_governance_block_forces_manual_strategy,
        test_high_data_can_raise_maturity_and_confidence,
        test_command_surface_queue_and_details_expose_phase100_fields,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
