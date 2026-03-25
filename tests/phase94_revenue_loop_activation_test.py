"""
Phase 94 revenue loop activation tests.

Run: python tests/phase94_revenue_loop_activation_test.py
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
    path = base / f"phase94_{uuid.uuid4().hex[:8]}"
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


def test_normalize_execution_package_adds_revenue_fields_backward_compatible():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase94proj",
            "project_path": "C:/phase94",
            "command_request": {"summary": "phase94 default package"},
        }
    )
    assert "lead_id" in normalized
    assert "pipeline_stage" in normalized
    assert "highest_value_next_action" in normalized
    assert "revenue_activation_status" in normalized
    assert "opportunity_classification" in normalized
    assert normalized["pipeline_stage"] == "intake"
    assert normalized["lead_id"] == ""
    assert normalized["highest_value_next_action"] in {
        "send follow-up",
        "escalate human review",
        "delay low-value opportunity",
        "prioritize high-value opportunity",
        "generate offer",
        "request onboarding info",
    }


def test_revenue_activation_respects_governance_hard_block():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase94proj",
            "project_path": "C:/phase94",
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert normalized["revenue_activation_status"] == "blocked_for_revenue_action"
    assert normalized["revenue_workflow_ready"] is False
    assert normalized["operator_revenue_review_required"] is True
    assert normalized["highest_value_next_action"] == "escalate human review"


def test_command_surface_exposes_top_and_blocked_revenue_candidates():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-ready",
                "project_name": "phase94proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "execution_score": 0.88,
                "roi_estimate": 0.86,
                "conversion_probability": 0.8,
                "time_sensitivity": 0.75,
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
                "project_name": "phase94proj",
                "project_path": str(tmp),
                "pipeline_stage": "qualified",
                "execution_score": 0.7,
                "roi_estimate": 0.6,
                "conversion_probability": 0.5,
                "time_sensitivity": 0.5,
                "metadata": {
                    "governance_status": "blocked",
                    "governance_routing_outcome": "stop",
                    "enforcement_status": "blocked",
                },
            },
        )

        result = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert result["status"] == "ok"
        payload = result["payload"]
        assert "top_revenue_candidates" in payload
        assert "blocked_revenue_candidates" in payload
        top_ids = {str(item.get("package_id") or "") for item in payload["top_revenue_candidates"]}
        blocked_ids = {str(item.get("package_id") or "") for item in payload["blocked_revenue_candidates"]}
        assert "pkg-ready" in top_ids
        assert "pkg-blocked" in blocked_ids


def test_revenue_activation_persistence_updates_package_metadata_and_fields():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_revenue_activation_safe,
        write_execution_package_safe,
    )

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-activation",
                "project_name": "phase94proj",
                "project_path": str(tmp),
                "pipeline_stage": "qualified",
            },
        )
        persisted = record_execution_package_revenue_activation_safe(
            project_path=str(tmp),
            package_id="pkg-activation",
            governance_result={"governance_status": "blocked", "routing_outcome": "stop"},
            enforcement_result={"enforcement_status": "blocked"},
            project_state={
                "revenue_recent_outcomes": [
                    {"status": "closed_won", "at": "2026-03-01T00:00:00+00:00", "reason": "reference"},
                ]
            },
        )
        assert persisted["status"] == "ok"
        package = read_execution_package(str(tmp), "pkg-activation") or {}
        metadata = package.get("metadata") or {}
        assert metadata.get("enforcement_status") == "blocked"
        assert package.get("revenue_activation_status") == "blocked_for_revenue_action"
        assert package.get("operator_revenue_review_required") is True


def main():
    tests = [
        test_normalize_execution_package_adds_revenue_fields_backward_compatible,
        test_revenue_activation_respects_governance_hard_block,
        test_command_surface_exposes_top_and_blocked_revenue_candidates,
        test_revenue_activation_persistence_updates_package_metadata_and_fields,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
