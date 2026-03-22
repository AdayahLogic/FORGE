"""
Phase 44 execution package eligibility gate tests.

Run: python tests/phase44_execution_package_eligibility_gate_test.py
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
    path = base / f"phase44_{uuid.uuid4().hex[:8]}"
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


def _write_package(
    project_path: Path,
    package_id: str,
    *,
    decision_status: str = "approved",
    approval_refs: list[str] | None = None,
    runtime_target_id: str = "windows_review_package",
    sealed: bool = True,
    execution_summary: dict | None = None,
    runtime_artifacts: list | None = None,
) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase44proj",
        "project_path": str(project_path),
        "created_at": "2026-03-22T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": sealed,
        "seal_reason": "Review-only package.",
        "runtime_target_id": runtime_target_id,
        "runtime_target_name": runtime_target_id,
        "execution_mode": "manual_only",
        "requested_action": "adapter_dispatch_call",
        "requested_by": "workflow",
        "requires_human_approval": True,
        "approval_id_refs": approval_refs if approval_refs is not None else ["appr-1"],
        "aegis_decision": "approval_required",
        "aegis_scope": "runtime_dispatch_only",
        "reason": "Human review required before any activation.",
        "dispatch_plan_summary": {"ready_for_dispatch": True},
        "routing_summary": {"runtime_node": "coder", "tool_name": "cursor_agent"},
        "execution_summary": execution_summary if execution_summary is not None else {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Inspect package contents.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Discard if incorrect."],
        "runtime_artifacts": runtime_artifacts if runtime_artifacts is not None else [],
        "metadata": {"openclaw_active": False},
        "decision_status": decision_status,
        "decision_timestamp": "2026-03-22T00:01:00Z" if decision_status != "pending" else "",
        "decision_actor": "operator_a" if decision_status != "pending" else "",
        "decision_notes": "Decision made." if decision_status != "pending" else "",
        "decision_id": str(uuid.uuid4()) if decision_status != "pending" else "",
    }
    return write_execution_package_safe(str(project_path), package)


def test_eligibility_defaults_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package({"package_id": "pkg-default"})
    assert normalized["eligibility_status"] == "pending"
    assert normalized["eligibility_timestamp"] == ""
    assert normalized["eligibility_reason"] == {"code": "", "message": ""}
    assert normalized["eligibility_checked_by"] == ""
    assert normalized["eligibility_check_id"] == ""


def test_pending_decision_blocks_eligibility_check():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-pending", decision_status="pending")
        result = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-pending",
            eligibility_checked_by="operator_e",
        )
        assert result["status"] == "error"
        assert result["payload"]["reason"] == "Eligibility check requires a non-pending decision."


def test_eligibility_check_marks_eligible_and_persists():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-eligible")
        result = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-eligible",
            eligibility_checked_by="operator_e",
        )
        assert result["status"] == "ok"
        eligibility = result["payload"]["eligibility"]
        assert eligibility["eligibility_status"] == "eligible"
        assert eligibility["eligibility_timestamp"].endswith("Z")
        assert eligibility["eligibility_checked_by"] == "operator_e"
        assert eligibility["eligibility_reason"]["code"] == "eligible"
        assert eligibility["eligibility_check_id"]
        persisted = read_execution_package(str(tmp), "pkg-eligible")
        assert persisted is not None
        assert persisted["eligibility_status"] == "eligible"


def test_eligibility_check_marks_ineligible_for_invalid_conditions():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-rejected", decision_status="rejected")
        rejected = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-rejected",
            eligibility_checked_by="operator_e",
        )
        assert rejected["status"] == "ok"
        assert rejected["payload"]["eligibility"]["eligibility_status"] == "ineligible"
        assert rejected["payload"]["eligibility"]["eligibility_reason"]["code"] == "decision_not_approved"

        _write_package(tmp, "pkg-no-refs", approval_refs=[])
        no_refs = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-no-refs",
            eligibility_checked_by="operator_e",
        )
        assert no_refs["payload"]["eligibility"]["eligibility_reason"]["code"] == "approval_refs_missing"

        _write_package(tmp, "pkg-bad-runtime", runtime_target_id="remote_worker")
        bad_runtime = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-bad-runtime",
            eligibility_checked_by="operator_e",
        )
        assert bad_runtime["payload"]["eligibility"]["eligibility_reason"]["code"] == "runtime_target_invalid"

        _write_package(tmp, "pkg-executed", execution_summary={"can_execute": True}, runtime_artifacts=[{"artifact": "ran"}])
        executed = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-executed",
            eligibility_checked_by="operator_e",
        )
        assert executed["payload"]["eligibility"]["eligibility_reason"]["code"] == "execution_detected"


def test_safe_defaults_and_recompute_behavior():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package, write_execution_package_safe

    with _local_test_dir() as tmp:
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-safe-defaults",
                "project_name": "phase44proj",
                "project_path": str(tmp),
                "sealed": True,
                "runtime_target_id": "windows_review_package",
                "approval_id_refs": ["appr-1"],
                "decision_status": "approved",
                "decision_timestamp": "2026-03-22T00:01:00Z",
                "decision_actor": "operator_a",
                "decision_id": str(uuid.uuid4()),
            },
        )
        first = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-safe-defaults",
            eligibility_checked_by="operator_e",
        )
        second = run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-safe-defaults",
            eligibility_checked_by="operator_f",
        )
        assert first["status"] == "ok"
        assert second["status"] == "ok"
        assert first["payload"]["eligibility"]["eligibility_status"] == "eligible"
        assert second["payload"]["eligibility"]["eligibility_status"] == "eligible"
        assert first["payload"]["eligibility"]["eligibility_check_id"] != second["payload"]["eligibility"]["eligibility_check_id"]
        persisted = read_execution_package(str(tmp), "pkg-safe-defaults")
        assert persisted is not None
        assert persisted["eligibility_checked_by"] == "operator_f"


def test_status_details_and_dashboard_include_eligibility():
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard")
        run_command(
            "execution_package_eligibility_check",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
            eligibility_checked_by="operator_e",
        )
        status_result = run_command(
            "execution_package_eligibility_status",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert status_result["status"] == "ok"
        assert status_result["payload"]["eligibility"]["eligibility_status"] == "eligible"
        details = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert details["status"] == "ok"
        assert details["payload"]["review_header"]["eligibility_status"] == "eligible"
        assert details["payload"]["sections"]["eligibility"]["eligibility_status"] == "eligible"
        project_key = f"phase44_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            eligibility_summary = summary.get("execution_package_eligibility_summary") or {}
            assert eligibility_summary.get("eligible_count_total", 0) >= 1
            assert eligibility_summary.get("eligibility_counts_by_project", {}).get(project_key, {}).get("eligible") == 1
            assert eligibility_summary.get("latest_eligibility_status_by_project", {}).get(project_key) == "eligible"
            review_rows = (summary.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert review_rows
            assert "command_request" not in review_rows[0]
            assert "metadata" not in review_rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_eligibility_defaults_present,
        test_pending_decision_blocks_eligibility_check,
        test_eligibility_check_marks_eligible_and_persists,
        test_eligibility_check_marks_ineligible_for_invalid_conditions,
        test_safe_defaults_and_recompute_behavior,
        test_status_details_and_dashboard_include_eligibility,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
