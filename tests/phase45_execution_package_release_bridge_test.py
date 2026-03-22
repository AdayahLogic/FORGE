"""
Phase 45 execution package release bridge tests.

Run: python tests/phase45_execution_package_release_bridge_test.py
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
    path = base / f"phase45_{uuid.uuid4().hex[:8]}"
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
    eligibility_status: str = "eligible",
    sealed: bool = True,
    execution_summary: dict | None = None,
    runtime_artifacts: list | None = None,
) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase45proj",
        "project_path": str(project_path),
        "created_at": "2026-03-22T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": sealed,
        "seal_reason": "Review-only package.",
        "runtime_target_id": "windows_review_package",
        "runtime_target_name": "windows_review_package",
        "execution_mode": "manual_only",
        "requested_action": "adapter_dispatch_call",
        "requested_by": "workflow",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-1"],
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
        "eligibility_status": eligibility_status,
        "eligibility_timestamp": "2026-03-22T00:02:00Z" if eligibility_status != "pending" else "",
        "eligibility_reason": {"code": eligibility_status, "message": f"Eligibility {eligibility_status}."} if eligibility_status != "pending" else {"code": "", "message": ""},
        "eligibility_checked_by": "operator_b" if eligibility_status != "pending" else "",
        "eligibility_check_id": str(uuid.uuid4()) if eligibility_status != "pending" else "",
    }
    return write_execution_package_safe(str(project_path), package)


def test_release_defaults_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package({"package_id": "pkg-default"})
    assert normalized["release_status"] == "pending"
    assert normalized["release_timestamp"] == ""
    assert normalized["release_actor"] == ""
    assert normalized["release_notes"] == ""
    assert normalized["release_id"] == ""
    assert normalized["release_reason"] == {"code": "", "message": ""}
    assert normalized["release_version"] == "v1"


def test_release_request_marks_released_and_persists():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-released")
        result = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-released",
            release_actor="operator_r",
            release_notes="Released for future manual execution handling.",
        )
        assert result["status"] == "ok"
        release = result["payload"]["release"]
        assert release["release_status"] == "released"
        assert release["release_timestamp"].endswith("Z")
        assert release["release_actor"] == "operator_r"
        assert release["release_notes"] == "Released for future manual execution handling."
        assert release["release_id"]
        assert release["release_reason"]["code"] == "released"
        assert release["release_version"] == "v1"
        persisted = read_execution_package(str(tmp), "pkg-released")
        assert persisted is not None
        assert persisted["release_status"] == "released"


def test_release_request_marks_blocked_for_invalid_conditions():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-no-approval", decision_status="rejected", eligibility_status="eligible")
        no_approval = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-no-approval",
            release_actor="operator_r",
        )
        assert no_approval["status"] == "ok"
        assert no_approval["payload"]["release"]["release_status"] == "blocked"
        assert no_approval["payload"]["release"]["release_reason"]["code"] == "decision_not_approved"

        _write_package(tmp, "pkg-not-eligible", decision_status="approved", eligibility_status="ineligible")
        not_eligible = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-not-eligible",
            release_actor="operator_r",
        )
        assert not_eligible["payload"]["release"]["release_reason"]["code"] == "eligibility_not_eligible"

        _write_package(tmp, "pkg-sealed-false", sealed=False)
        not_sealed = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-sealed-false",
            release_actor="operator_r",
        )
        assert not_sealed["payload"]["release"]["release_reason"]["code"] == "not_sealed"

        _write_package(tmp, "pkg-executed", execution_summary={"can_execute": True}, runtime_artifacts=[{"artifact": "ran"}])
        executed = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-executed",
            release_actor="operator_r",
        )
        assert executed["payload"]["release"]["release_reason"]["code"] == "execution_detected"

        _write_package(tmp, "pkg-eligibility-pending", eligibility_status="pending")
        pending_eligibility = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-eligibility-pending",
            release_actor="operator_r",
        )
        assert pending_eligibility["payload"]["release"]["release_reason"]["code"] == "eligibility_not_eligible"


def test_release_actor_required_and_recompute_behavior():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-recompute")
        missing_actor = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-recompute",
        )
        assert missing_actor["status"] == "error"
        assert missing_actor["payload"]["reason"] == "release_actor required."
        first = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-recompute",
            release_actor="operator_r1",
        )
        second = run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-recompute",
            release_actor="operator_r2",
        )
        assert first["status"] == "ok"
        assert second["status"] == "ok"
        assert first["payload"]["release"]["release_id"] != second["payload"]["release"]["release_id"]
        persisted = read_execution_package(str(tmp), "pkg-recompute")
        assert persisted is not None
        assert persisted["release_actor"] == "operator_r2"


def test_release_status_details_and_dashboard_include_release():
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard")
        run_command(
            "execution_package_release_request",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
            release_actor="operator_r",
            release_notes="Released for later use.",
        )
        status_result = run_command(
            "execution_package_release_status",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert status_result["status"] == "ok"
        assert status_result["payload"]["release"]["release_status"] == "released"
        details = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert details["status"] == "ok"
        assert details["payload"]["review_header"]["release_status"] == "released"
        assert details["payload"]["sections"]["release"]["release_status"] == "released"
        project_key = f"phase45_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            release_summary = summary.get("execution_package_release_summary") or {}
            assert release_summary.get("released_count_total", 0) >= 1
            assert release_summary.get("release_counts_by_project", {}).get(project_key, {}).get("released") == 1
            assert release_summary.get("latest_release_status_by_project", {}).get(project_key) == "released"
            review_rows = (summary.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert review_rows
            assert "command_request" not in review_rows[0]
            assert "metadata" not in review_rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_release_defaults_present,
        test_release_request_marks_released_and_persists,
        test_release_request_marks_blocked_for_invalid_conditions,
        test_release_actor_required_and_recompute_behavior,
        test_release_status_details_and_dashboard_include_release,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
