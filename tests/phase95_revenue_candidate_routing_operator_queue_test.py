"""
Phase 95 revenue candidate routing + operator action queue tests.

Run: python tests/phase95_revenue_candidate_routing_operator_queue_test.py
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
    path = base / f"phase95_{uuid.uuid4().hex[:8]}"
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


def test_normalize_execution_package_adds_operator_action_queue_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase95proj",
            "project_path": "C:/phase95",
            "pipeline_stage": "proposal_pending",
            "execution_score": 0.83,
            "roi_estimate": 0.87,
            "conversion_probability": 0.79,
            "time_sensitivity": 0.72,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
            },
        }
    )
    assert normalized["revenue_candidate_status"] in {"ready", "blocked", "deferred", "review_required"}
    assert isinstance(normalized["revenue_candidate_rank"], int)
    assert "revenue_candidate_reason" in normalized
    assert normalized["operator_action_queue_status"] in {
        "ready_operator_action",
        "blocked_operator_action",
        "deferred_operator_action",
        "review_required_operator_action",
    }
    assert normalized["operator_action_type"] in {
        "review_high_value_lead",
        "approve_proposal_generation",
        "send_human_follow_up",
        "review_blocked_opportunity",
        "request_missing_onboarding_details",
        "escalate_negotiation",
        "defer_low_value_opportunity",
    }
    assert normalized["operator_action_priority"] in {"low", "medium", "high"}


def test_hard_block_never_promoted_into_ready_operator_action():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase95proj",
            "project_path": "C:/phase95",
            "pipeline_stage": "proposal_pending",
            "execution_score": 0.99,
            "roi_estimate": 0.99,
            "conversion_probability": 0.95,
            "time_sensitivity": 0.95,
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert normalized["revenue_activation_status"] == "blocked_for_revenue_action"
    assert normalized["revenue_candidate_status"] == "blocked"
    assert normalized["operator_action_queue_status"] == "blocked_operator_action"
    assert normalized["operator_action_type"] == "review_blocked_opportunity"


def test_command_surface_exposes_operator_action_queue_segments():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-ready",
                "project_name": "phase95proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "execution_score": 0.9,
                "roi_estimate": 0.9,
                "conversion_probability": 0.82,
                "time_sensitivity": 0.78,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-blocked",
                "project_name": "phase95proj",
                "project_path": str(tmp),
                "pipeline_stage": "qualified",
                "execution_score": 0.8,
                "roi_estimate": 0.75,
                "conversion_probability": 0.6,
                "time_sensitivity": 0.6,
                "metadata": {
                    "governance_status": "blocked",
                    "governance_routing_outcome": "stop",
                    "enforcement_status": "blocked",
                },
            },
        )
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-deferred",
                "project_name": "phase95proj",
                "project_path": str(tmp),
                "pipeline_stage": "intake",
                "execution_score": 0.2,
                "roi_estimate": 0.2,
                "conversion_probability": 0.1,
                "time_sensitivity": 0.2,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                },
            },
        )
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-review",
                "project_name": "phase95proj",
                "project_path": str(tmp),
                "pipeline_stage": "qualified",
                "execution_score": 0.5,
                "roi_estimate": 0.55,
                "conversion_probability": 0.45,
                "time_sensitivity": 0.5,
                "metadata": {
                    "governance_status": "review_required",
                    "governance_routing_outcome": "pause",
                    "enforcement_status": "manual_review_required",
                },
            },
        )

        result = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert result["status"] == "ok"
        payload = result["payload"]
        assert "top_operator_actions" in payload
        assert "blocked_operator_actions" in payload
        assert "deferred_operator_actions" in payload
        assert "review_required_operator_actions" in payload
        ready_ids = {str(item.get("package_id") or "") for item in payload["top_operator_actions"]}
        blocked_ids = {str(item.get("package_id") or "") for item in payload["blocked_operator_actions"]}
        deferred_ids = {str(item.get("package_id") or "") for item in payload["deferred_operator_actions"]}
        review_ids = {str(item.get("package_id") or "") for item in payload["review_required_operator_actions"]}
        assert "pkg-ready" in ready_ids
        assert "pkg-blocked" in blocked_ids
        assert "pkg-deferred" in deferred_ids
        assert "pkg-review" in review_ids


def main():
    tests = [
        test_normalize_execution_package_adds_operator_action_queue_fields,
        test_hard_block_never_promoted_into_ready_operator_action,
        test_command_surface_exposes_operator_action_queue_segments,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
