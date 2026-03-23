"""
Phase 41 review-only execution package layer tests.

Run: python tests/phase41_review_package_test.py
"""

from __future__ import annotations

import os
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
    path = base / f"phase41_{uuid.uuid4().hex[:8]}"
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
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _base_dispatch_plan(project_path: str, runtime_target_id: str = "local", *, requires_human_approval: bool = False) -> dict:
    return {
        "dispatch_version": "1.0",
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": True,
        "project": {
            "project_id": "testproj",
            "project_name": "testproj",
            "project_path": project_path,
        },
        "request": {
            "request_id": "",
            "request_type": "user_request",
            "task_type": "coder",
            "summary": "Prepare a narrow reviewed action package.",
            "priority": "normal",
        },
        "routing": {
            "runtime_node": "coder",
            "agent_name": "coder",
            "tool_name": "cursor_agent",
            "selection_status": "selected",
            "selection_reason": "Test dispatch.",
        },
        "execution": {
            "execution_mode": "targeted_runtime",
            "runtime_target_id": runtime_target_id,
            "runtime_target_name": runtime_target_id,
            "requires_human_approval": requires_human_approval,
            "can_execute": True,
        },
        "artifacts": {
            "expected_outputs": ["execution package"],
            "target_files": ["src/module.py"],
            "patch_strategy": "incremental",
        },
        "governance": {
            "policy_checked": True,
            "approval_status": "pending_review" if requires_human_approval else "not_required",
            "risk_level": "low",
        },
        "timestamps": {
            "planned_at": "2026-03-22T00:00:00+00:00",
        },
    }


def test_execution_package_registry_round_trip():
    """Prove execution packages are normalized and persisted append-only."""
    from NEXUS.execution_package_registry import (
        normalize_execution_package,
        write_execution_package_safe,
        read_execution_package,
        read_execution_package_journal_tail,
    )

    with _local_test_dir() as tmp:
        normalized = normalize_execution_package({
            "project_name": "testproj",
            "project_path": str(tmp),
            "runtime_target_id": "local",
            "command_request": {"summary": "hello"},
            "helix_contract_summary": {
                "contract_status": "valid",
                "validation_path": "package_binding_allowed",
                "trace_id": "helix-trace-1",
            },
        })
        assert normalized["package_kind"] == "review_only_execution_envelope"
        assert normalized["sealed"] is True
        written = write_execution_package_safe(str(tmp), normalized)
        assert written is not None
        loaded = read_execution_package(str(tmp), normalized["package_id"])
        assert loaded is not None
        assert loaded["package_id"] == normalized["package_id"]
        assert loaded["helix_contract_summary"]["contract_status"] == "valid"
        tail = read_execution_package_journal_tail(str(tmp), n=5)
        assert len(tail) == 1
        assert tail[0]["package_id"] == normalized["package_id"]
        assert tail[0]["helix_contract_summary"]["trace_id"] == "helix-trace-1"


def test_dispatch_requires_human_approval_creates_review_package():
    """Prove dispatch approval gating now creates a sealed review package."""
    from NEXUS.runtime_dispatcher import dispatch
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        previous_env = os.environ.get("FORGE_ENV")
        try:
            os.environ["FORGE_ENV"] = "local_dev"
            plan = _base_dispatch_plan(str(tmp), "local", requires_human_approval=True)
            result = dispatch(plan)
            assert result["dispatch_status"] == "skipped"
            dr = result["dispatch_result"]
            assert dr["execution_status"] == "queued"
            assert dr["next_action"] == "review_execution_package"
            assert dr.get("approval_required") is True
            package_id = dr.get("execution_package_id")
            assert package_id
            assert Path(str(dr.get("execution_package_path"))).exists()
            persisted = read_execution_package(str(tmp), package_id)
            assert persisted is not None
            assert persisted["sealed"] is True
            assert persisted["requires_human_approval"] is True
            assert persisted["approval_id_refs"]
        finally:
            if previous_env is None:
                os.environ.pop("FORGE_ENV", None)
            else:
                os.environ["FORGE_ENV"] = previous_env


def test_windows_review_package_target_stops_at_package():
    """Prove the dedicated review-only runtime target packages and stops."""
    from NEXUS.runtime_dispatcher import dispatch
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        previous_env = os.environ.get("FORGE_ENV")
        try:
            os.environ["FORGE_ENV"] = "local_dev"
            plan = _base_dispatch_plan(str(tmp), "windows_review_package", requires_human_approval=False)
            result = dispatch(plan)
            assert result["dispatch_status"] == "accepted"
            dr = result["dispatch_result"]
            assert dr["execution_status"] == "queued"
            assert dr["next_action"] == "review_execution_package"
            assert dr.get("package_review_required") is True
            package_id = dr.get("execution_package_id")
            assert package_id
            persisted = read_execution_package(str(tmp), package_id)
            assert persisted is not None
            assert persisted["runtime_target_id"] == "windows_review_package"
            assert persisted["sealed"] is True
            assert persisted["metadata"]["openclaw_active"] is False
            assert persisted["helix_contract_summary"] == {}
        finally:
            if previous_env is None:
                os.environ.pop("FORGE_ENV", None)
            else:
                os.environ["FORGE_ENV"] = previous_env


def test_runtime_target_selector_supports_review_package():
    """Prove runtime selector recognizes the review-only package target."""
    from NEXUS.runtime_target_selector import select_runtime_target

    decision = select_runtime_target(task_type="review_package")
    assert decision["selected_target"] == "windows_review_package"
    assert decision["review_required"] is True


def test_automation_and_governance_recognize_review_package():
    """Prove downstream layers treat package state as human-review only."""
    from NEXUS.automation_layer import evaluate_automation_outcome_safe
    from NEXUS.governance_layer import evaluate_governance_outcome_safe

    dispatch_result = {
        "execution_status": "queued",
        "execution_package_id": "pkg123",
        "package_review_required": True,
        "approval_required": True,
    }
    automation = evaluate_automation_outcome_safe(
        dispatch_status="skipped",
        runtime_execution_status="queued",
        dispatch_result=dispatch_result,
        dispatch_plan_summary={"dispatch_planning_status": "planned"},
    )
    assert automation["recommended_action"] == "review_execution_package"
    governance = evaluate_governance_outcome_safe(
        dispatch_status="skipped",
        runtime_execution_status="queued",
        dispatch_result=dispatch_result,
        automation_status=automation["automation_status"],
        automation_result=automation,
    )
    assert governance["governance_status"] == "review_required"
    assert "review_package" in governance["policy_tags"]


def main():
    tests = [
        test_execution_package_registry_round_trip,
        test_dispatch_requires_human_approval_creates_review_package,
        test_windows_review_package_target_stops_at_package,
        test_runtime_target_selector_supports_review_package,
        test_automation_and_governance_recognize_review_package,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
