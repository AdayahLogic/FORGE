"""
Phase 43 execution package decision layer tests.

Run: python tests/phase43_execution_package_decision_layer_test.py
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
    path = base / f"phase43_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str, *, sealed: bool = True) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase43proj",
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
        "execution_summary": {"review_only": True, "can_execute": False},
        "command_request": {"summary": "Inspect package contents.", "task_type": "coder"},
        "candidate_paths": ["src/module.py"],
        "expected_outputs": ["execution package"],
        "review_checklist": ["Confirm package remains sealed."],
        "rollback_notes": ["Discard if incorrect."],
        "runtime_artifacts": [],
        "metadata": {"openclaw_active": False},
    }
    return write_execution_package_safe(str(project_path), package)


def test_decision_defaults_present():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package({"package_id": "pkg-default"})
    assert normalized["decision_status"] == "pending"
    assert normalized["decision_timestamp"] == ""
    assert normalized["decision_actor"] == ""
    assert normalized["decision_notes"] == ""
    assert normalized["decision_id"] == ""


def test_approve_decision_persists_and_is_immutable():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-approve")
        result = run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-approve",
            decision_status="approved",
            decision_actor="operator_a",
            decision_notes="Scope looks correct.",
        )
        assert result["status"] == "ok"
        decision = result["payload"]["decision"]
        assert decision["decision_status"] == "approved"
        assert decision["decision_timestamp"].endswith("Z")
        assert decision["decision_actor"] == "operator_a"
        assert decision["decision_notes"] == "Scope looks correct."
        assert decision["decision_id"]
        persisted = read_execution_package(str(tmp), "pkg-approve")
        assert persisted is not None
        assert persisted["decision_status"] == "approved"
        assert persisted["sealed"] is True
        assert persisted["metadata"]["openclaw_active"] is False
        retry = run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-approve",
            decision_status="rejected",
            decision_actor="operator_b",
        )
        assert retry["status"] == "error"
        assert retry["payload"]["reason"] == "Execution package decision is immutable once set."


def test_reject_decision_and_status_command():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-reject")
        result = run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-reject",
            decision_status="rejected",
            decision_actor="operator_b",
            decision_notes="Out of scope.",
        )
        assert result["status"] == "ok"
        status_result = run_command(
            "execution_package_decision_status",
            project_path=str(tmp),
            execution_package_id="pkg-reject",
        )
        assert status_result["status"] == "ok"
        decision = status_result["payload"]["decision"]
        assert decision["decision_status"] == "rejected"
        assert decision["decision_actor"] == "operator_b"
        assert decision["decision_notes"] == "Out of scope."


def test_invalid_and_unsealed_decisions_rejected():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-open", sealed=False)
        invalid = run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-open",
            decision_status="maybe",
            decision_actor="operator_c",
        )
        assert invalid["status"] == "error"
        assert invalid["payload"]["reason"] == "decision_status must be approved or rejected."
        unsealed = run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-open",
            decision_status="approved",
            decision_actor="operator_c",
        )
        assert unsealed["status"] == "error"
        assert unsealed["payload"]["reason"] == "Only sealed execution packages may be decided."


def test_details_and_dashboard_include_decision_summary_only():
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard")
        run_command(
            "execution_package_decide",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
            decision_status="approved",
            decision_actor="operator_d",
            decision_notes="Approved for later manual handling.",
        )
        details = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-dashboard",
        )
        assert details["status"] == "ok"
        sections = details["payload"]["sections"]
        assert "decision" in sections
        assert sections["decision"]["decision_status"] == "approved"
        project_key = f"phase43_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            decision_summary = summary.get("execution_package_decision_summary") or {}
            assert decision_summary.get("approved_count_total", 0) >= 1
            assert decision_summary.get("decision_counts_by_project", {}).get(project_key, {}).get("approved") == 1
            assert decision_summary.get("latest_decision_status_by_project", {}).get(project_key) == "approved"
            review_rows = (summary.get("execution_package_review_summary") or {}).get("packages_by_project", {}).get(project_key) or []
            assert review_rows
            assert "command_request" not in review_rows[0]
            assert "metadata" not in review_rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_decision_defaults_present,
        test_approve_decision_persists_and_is_immutable,
        test_reject_decision_and_status_command,
        test_invalid_and_unsealed_decisions_rejected,
        test_details_and_dashboard_include_decision_summary_only,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
