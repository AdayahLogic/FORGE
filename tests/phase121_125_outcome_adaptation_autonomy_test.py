"""
Phase 121-125 outcome tracking + adaptation + autonomy scaling tests.

Run: python tests/phase121_125_outcome_adaptation_autonomy_test.py
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
    path = base / f"phase121_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str) -> None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase121proj",
        "project_path": str(project_path),
        "created_at": "2026-03-26T00:00:00+00:00",
        "package_status": "review_pending",
        "review_status": "pending",
        "requires_human_approval": True,
        "mission_id": f"msn-{package_id}",
        "mission_type": "project_delivery",
        "mission_status": "awaiting_initial_approval",
        "mission_risk_level": "medium",
    }
    assert write_execution_package_safe(str(project_path), payload)


def test_outcome_tracking_persists_and_is_immutable_once_recorded():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_outcome_adaptation_safe,
    )

    with _local_test_dir() as tmp:
        package_id = "pkg-phase121-immutability"
        _write_package(tmp, package_id)
        first = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={
                "expected_outcome": "Close deal and deliver project",
                "expected_revenue": 10000,
                "expected_conversion": 0.6,
                "actual_outcome": "Close deal and deliver project",
                "actual_revenue": 12500,
                "actual_conversion": 0.72,
            },
        )
        assert first["status"] == "ok"
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("outcome_recorded_at")
        assert package.get("outcome_status") in {"success", "partial", "failure"}

        blocked = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={"actual_revenue": 14000},
        )
        assert blocked["status"] == "error"
        assert "immutability" in str(blocked.get("reason") or "").lower()
        package_after = read_execution_package(str(tmp), package_id) or {}
        assert float(package_after.get("actual_revenue") or 0.0) == 12500.0


def test_performance_evaluation_is_deterministic_and_bounded():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_outcome_adaptation_safe,
    )

    with _local_test_dir() as tmp:
        package_id = "pkg-phase121-deterministic"
        _write_package(tmp, package_id)
        updates = {
            "expected_outcome": "Increase conversion",
            "expected_revenue": 5000,
            "expected_conversion": 0.40,
            "actual_outcome": "Increase conversion",
            "actual_revenue": 4500,
            "actual_conversion": 0.35,
        }
        first = record_execution_package_outcome_adaptation_safe(project_path=str(tmp), package_id=package_id, updates=updates)
        second = record_execution_package_outcome_adaptation_safe(project_path=str(tmp), package_id=package_id, updates=updates)
        assert first["status"] == "ok"
        assert second["status"] == "ok"
        package = read_execution_package(str(tmp), package_id) or {}
        score = float(package.get("performance_score") or 0.0)
        assert 0.0 <= score <= 1.0
        assert str(package.get("performance_category") or "") in {"excellent", "good", "average", "poor"}
        assert -1.0 <= float(package.get("outcome_delta_score") or 0.0) <= 1.0


def test_strategy_adaptation_recommends_without_live_override():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_outcome_adaptation_safe,
    )

    with _local_test_dir() as tmp:
        package_id = "pkg-phase121-strategy"
        _write_package(tmp, package_id)
        result = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={
                "expected_outcome": "Improve conversion and revenue",
                "expected_revenue": 15000,
                "expected_conversion": 0.7,
                "actual_outcome": "Outcome missed",
                "actual_revenue": 3000,
                "actual_conversion": 0.1,
                "follow_up_status": "pending",
            },
        )
        assert result["status"] == "ok"
        package = read_execution_package(str(tmp), package_id) or {}
        assert bool(package.get("strategy_adjustment_required")) is True
        assert str(package.get("strategy_adjustment_type") or "") in {"pricing", "messaging", "targeting", "follow_up", "other"}
        assert package.get("strategy_new_recommendation")
        assert 0.0 <= float(package.get("strategy_confidence_update") or 0.0) <= 1.0


def test_autonomy_scaling_respects_boundaries_and_parallel_conflict_detection():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_execution_package_outcome_adaptation_safe,
    )

    with _local_test_dir() as tmp:
        package_id = "pkg-phase121-autonomy"
        _write_package(tmp, package_id)
        blocked = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={
                "expected_outcome": "Internal maintenance",
                "actual_outcome": "Internal maintenance",
                "expected_revenue": 0.0,
                "actual_revenue": 0.0,
                "expected_conversion": 0.0,
                "actual_conversion": 0.0,
                "mission_risk_level": "high",
                "email_direction": "outbound",
                "email_requires_approval": True,
                "metadata": {"safe_pattern_count": 10},
                "autopilot_parallel_capacity": 2,
                "active_missions": [
                    {"mission_id": "m1", "file_targets": ["NEXUS/command_surface.py"]},
                    {"mission_id": "m2", "file_targets": ["NEXUS/command_surface.py"]},
                    {"mission_id": "m3", "file_targets": ["NEXUS/review_queue.py"]},
                ],
            },
        )
        assert blocked["status"] == "ok"
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("auto_approval_allowed") is False
        assert str(package.get("auto_approval_scope") or "") == "manual_review_only"
        assert bool(package.get("mission_conflict_detected")) is True
        assert str(package.get("mission_conflict_resolution_strategy") or "") in {
            "capacity_throttle_and_serialize",
            "serialize_conflicting_file_targets",
        }


def test_read_surfaces_expose_phase121_125_sections_and_queue_summaries():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import record_execution_package_outcome_adaptation_safe

    with _local_test_dir() as tmp:
        package_id = "pkg-phase121-surfaces"
        _write_package(tmp, package_id)
        recorded = record_execution_package_outcome_adaptation_safe(
            project_path=str(tmp),
            package_id=package_id,
            updates={
                "expected_outcome": "Ship internal automation",
                "expected_revenue": 8000,
                "expected_conversion": 0.5,
                "actual_outcome": "Shipped with partial success",
                "actual_revenue": 7000,
                "actual_conversion": 0.45,
                "metadata": {"safe_pattern_count": 4},
                "autopilot_parallel_capacity": 3,
                "active_missions": [{"mission_id": "m1", "file_targets": ["NEXUS/execution_package_registry.py"]}],
            },
        )
        assert recorded["status"] == "ok"

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id=package_id)
        assert details["status"] == "ok"
        sections = details["payload"]["sections"]
        assert "outcome" in sections
        assert "performance" in sections
        assert "strategy_adaptation" in sections
        assert "autonomy" in sections
        assert "mission_parallel_state" in sections

        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        execution_summary = queue["payload"].get("execution_package_queue") or {}
        assert "high_performing_strategies" in execution_summary
        assert "failing_strategies" in execution_summary
        assert "missions_ready_for_auto_approval" in execution_summary
        assert "missions_requiring_review" in execution_summary
        review_summary = queue["payload"].get("review_queue") or {}
        assert "high_risk_adaptation_decisions" in review_summary
        assert "strategy_changes_requiring_approval" in review_summary


def main():
    tests = [
        test_outcome_tracking_persists_and_is_immutable_once_recorded,
        test_performance_evaluation_is_deterministic_and_bounded,
        test_strategy_adaptation_recommends_without_live_override,
        test_autonomy_scaling_respects_boundaries_and_parallel_conflict_detection,
        test_read_surfaces_expose_phase121_125_sections_and_queue_summaries,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
