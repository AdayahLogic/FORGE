"""
Phase 93 adaptive execution + feedback loop tests.

Run: python tests/phase93_adaptive_execution_feedback_loop_test.py
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
    path = base / f"phase93_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str, **overrides) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "project_name": "phase93proj",
        "project_path": str(project_path),
        "created_at": "2026-03-25T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": True,
        "runtime_target_id": "windows_review_package",
        "runtime_target_name": "windows_review_package",
        "execution_mode": "manual_only",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-1"],
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "execution_status": "pending",
        "command_request": {"priority": "normal", "summary": "Phase 93 queue check"},
        "metadata": {},
        **overrides,
    }
    written = write_execution_package_safe(str(project_path), package)
    assert written
    return package_id


def test_normalization_includes_adaptive_and_feedback_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    pkg = normalize_execution_package({"package_id": "pkg-default"})
    assert "dynamic_execution_priority" in pkg
    assert "last_score_update_timestamp" in pkg
    assert "priority_decay_factor" in pkg
    assert "execution_result" in pkg
    assert "conversion_result" in pkg
    assert "revenue_realized" in pkg
    assert "expected_vs_actual_delta" in pkg
    assert "performance_accuracy_score" in pkg
    assert isinstance(pkg["dynamic_execution_priority"], float)
    assert pkg["conversion_result"] == "pending"


def test_queue_intelligence_ranks_candidates_and_hard_blocks():
    from NEXUS.execution_package_registry import build_execution_queue_intelligence_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-strong",
            execution_score=92,
            roi_estimate=88,
            execution_probability=0.9,
            time_sensitivity=0.9,
            execution_priority=90,
            priority_decay_factor=0.01,
        )
        _write_package(
            tmp,
            "pkg-stale-low",
            execution_score=40,
            roi_estimate=25,
            execution_probability=0.2,
            time_sensitivity=0.2,
            execution_priority=20,
            last_score_update_timestamp="2025-01-01T00:00:00Z",
            priority_decay_factor=0.2,
        )
        _write_package(
            tmp,
            "pkg-hard-block",
            execution_score=99,
            roi_estimate=99,
            execution_probability=0.99,
            time_sensitivity=0.99,
            metadata={"governance_status": "blocked", "governance_routing_outcome": "stop"},
        )

        intelligence = build_execution_queue_intelligence_safe(project_path=str(tmp), n=10)
        assert intelligence["queue_intelligence_status"] == "ok"
        top = intelligence["top_execution_candidates"]
        assert top
        assert top[0]["package_id"] == "pkg-strong"
        blocked = [x for x in intelligence["ranked_packages"] if x["package_id"] == "pkg-hard-block"][0]
        assert blocked["queue_eligible"] is False
        assert blocked["hard_block"] is True


def test_business_outcome_recording_is_immutable_and_auditable():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_business_outcome_safe,
    )

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-outcome",
            expected_roi=70,
            expected_conversion=0.8,
            execution_status="succeeded",
            execution_result="succeeded",
        )
        first = record_execution_package_business_outcome_safe(
            project_path=str(tmp),
            package_id="pkg-outcome",
            conversion_result="converted",
            revenue_realized=76,
            actual_conversion=1.0,
            outcome_actor="abacus_operator",
        )
        assert first["status"] == "ok"
        pkg = read_execution_package(str(tmp), "pkg-outcome")
        assert pkg
        assert pkg["conversion_result"] == "converted"
        assert float(pkg["revenue_realized"]) == 76.0
        assert pkg["performance_accuracy_score"] >= 0
        audit = ((pkg.get("metadata") or {}).get("adaptive_priority_audit") or [])
        assert audit
        assert any(str(item.get("event_type") or "") == "business_outcome_recorded" for item in audit)

        second = record_execution_package_business_outcome_safe(
            project_path=str(tmp),
            package_id="pkg-outcome",
            conversion_result="not_converted",
            revenue_realized=12,
            outcome_actor="abacus_operator",
        )
        assert second["status"] == "error"
        assert "immutable" in str(second["reason"]).lower()


def test_command_surface_queue_exposes_top_candidates_without_execution():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-cmd-1",
            execution_priority=85,
            execution_score=90,
            roi_estimate=85,
            execution_probability=0.85,
            time_sensitivity=0.7,
            execution_status="pending",
        )
        _write_package(
            tmp,
            "pkg-cmd-2",
            execution_priority=40,
            execution_score=45,
            roi_estimate=30,
            execution_probability=0.3,
            time_sensitivity=0.2,
            execution_status="pending",
        )
        result = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert result["status"] == "ok"
        payload = result["payload"]
        assert payload["queue_intelligence_status"] == "ok"
        assert isinstance(payload["top_execution_candidates"], list)
        assert payload["top_execution_candidates"]
        pkg = read_execution_package(str(tmp), "pkg-cmd-1")
        assert pkg
        assert pkg["execution_status"] == "pending"


def test_pending_rows_do_not_mutate_adaptive_profile_weights():
    from NEXUS.execution_package_registry import build_execution_queue_intelligence_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-pending-high-roi",
            expected_roi=95,
            roi_estimate=95,
            conversion_result="pending",
            actual_conversion="",
            execution_status="pending",
            execution_result="pending",
        )
        intelligence = build_execution_queue_intelligence_safe(project_path=str(tmp), n=10)
        profile = intelligence.get("adaptive_profile") or {}
        weights = dict(profile.get("weights") or {})
        assert weights == {
            "execution_score_weight": 0.35,
            "roi_weight": 0.3,
            "probability_weight": 0.2,
            "time_sensitivity_weight": 0.15,
        }
        assert list(profile.get("adaptation_history") or []) == []


def test_adaptive_profile_does_not_drift_on_repeated_queue_reads():
    from NEXUS.execution_package_registry import build_execution_queue_intelligence_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-outcome-not-converted",
            expected_roi=90,
            roi_estimate=90,
            conversion_result="not_converted",
            actual_conversion=0.0,
            execution_status="succeeded",
            execution_result="succeeded",
        )
        first = build_execution_queue_intelligence_safe(project_path=str(tmp), n=10)
        second = build_execution_queue_intelligence_safe(project_path=str(tmp), n=10)
        first_history = list((first.get("adaptive_profile") or {}).get("adaptation_history") or [])
        second_history = list((second.get("adaptive_profile") or {}).get("adaptation_history") or [])
        assert len(first_history) == 1
        assert len(second_history) == 1
        assert dict((first.get("adaptive_profile") or {}).get("weights") or {}) == dict(
            (second.get("adaptive_profile") or {}).get("weights") or {}
        )


def test_persisted_dynamic_priority_matches_computed_audit_value():
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_business_outcome_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-priority-consistency",
            expected_roi=70,
            expected_conversion=0.8,
            execution_status="succeeded",
            execution_result="succeeded",
        )
        result = record_execution_package_business_outcome_safe(
            project_path=str(tmp),
            package_id="pkg-priority-consistency",
            conversion_result="converted",
            revenue_realized=75,
            actual_conversion=1.0,
            outcome_actor="abacus_operator",
        )
        assert result["status"] == "ok"
        pkg = read_execution_package(str(tmp), "pkg-priority-consistency")
        assert pkg
        audit = list(((pkg.get("metadata") or {}).get("adaptive_priority_audit") or []))
        priority_events = [item for item in audit if str(item.get("event_type") or "") == "priority_update"]
        assert priority_events
        persisted_priority = float(pkg.get("dynamic_execution_priority") or 0.0)
        audited_priority = float(priority_events[-1].get("dynamic_execution_priority") or 0.0)
        assert persisted_priority == audited_priority


def main():
    tests = [
        test_normalization_includes_adaptive_and_feedback_fields,
        test_queue_intelligence_ranks_candidates_and_hard_blocks,
        test_business_outcome_recording_is_immutable_and_auditable,
        test_command_surface_queue_exposes_top_candidates_without_execution,
        test_pending_rows_do_not_mutate_adaptive_profile_weights,
        test_adaptive_profile_does_not_drift_on_repeated_queue_reads,
        test_persisted_dynamic_priority_matches_computed_audit_value,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
