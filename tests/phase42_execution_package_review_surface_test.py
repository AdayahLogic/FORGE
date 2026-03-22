"""
Phase 42 read-only execution package review surface tests.

Run: python tests/phase42_execution_package_review_surface_test.py
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
    path = base / f"phase42_{uuid.uuid4().hex[:8]}"
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


def _write_package(project_path: Path, package_id: str, created_at: str, *, review_status: str = "pending") -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase42proj",
        "project_path": str(project_path),
        "created_at": created_at,
        "package_status": "review_pending",
        "review_status": review_status,
        "sealed": True,
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


def test_execution_package_queue_sorted_and_limited():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        for i in range(55):
            _write_package(
                tmp,
                f"pkg{i:02d}",
                f"2026-03-22T{(i // 60):02d}:{(i % 60):02d}:00+00:00",
            )
        result = run_command("execution_package_queue", project_path=str(tmp), n=100)
        assert result["status"] == "ok"
        payload = result["payload"]
        assert payload["status"] == "ok"
        assert payload["count"] == 50
        assert payload["pending_count"] == 50
        assert payload["packages"][0]["package_id"] == "pkg54"
        assert payload["packages"][-1]["package_id"] == "pkg05"


def test_execution_package_details_has_stable_sections():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-details", "2026-03-22T00:00:00+00:00")
        result = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="pkg-details",
        )
        assert result["status"] == "ok"
        payload = result["payload"]
        assert payload["status"] == "ok"
        assert payload["package_id"] == "pkg-details"
        assert "review_header" in payload
        assert "package" in payload
        sections = payload.get("sections") or {}
        assert sorted(sections.keys()) == ["approval", "command_request", "decision", "eligibility", "metadata", "rollback", "safety", "scope"]
        assert sections["command_request"]["summary"] == "Inspect package contents."
        assert sections["scope"]["candidate_paths"] == ["src/module.py"]
        assert sections["approval"]["approval_id_refs"] == ["appr-1"]
        assert sections["decision"]["decision_status"] == "pending"
        assert sections["eligibility"]["eligibility_status"] == "pending"
        assert sections["safety"]["sealed"] is True
        assert sections["rollback"]["rollback_notes"] == ["Discard if incorrect."]
        assert sections["metadata"]["openclaw_active"] is False


def test_execution_package_details_not_found_error_shape():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        result = run_command(
            "execution_package_details",
            project_path=str(tmp),
            execution_package_id="missing-package",
        )
        assert result["status"] == "error"
        payload = result["payload"]
        assert payload["status"] == "error"
        assert payload["project_path"] == str(tmp)
        assert payload["package_id"] == "missing-package"
        assert payload["reason"] == "Execution package not found."


def test_dashboard_summary_is_summary_only():
    from NEXUS.registry import PROJECTS
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-dashboard", "2026-03-22T00:00:00+00:00")
        project_key = f"phase42_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp)}
        try:
            summary = build_registry_dashboard_summary()
            review_summary = summary.get("execution_package_review_summary") or {}
            assert review_summary.get("review_surface_status") == "ok"
            assert review_summary.get("pending_by_project", {}).get(project_key) == 1
            assert review_summary.get("latest_package_id_by_project", {}).get(project_key) == "pkg-dashboard"
            rows = review_summary.get("packages_by_project", {}).get(project_key) or []
            assert len(rows) == 1
            assert rows[0]["package_id"] == "pkg-dashboard"
            assert "command_request" not in rows[0]
            assert "candidate_paths" not in rows[0]
            assert "metadata" not in rows[0]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_execution_package_queue_sorted_and_limited,
        test_execution_package_details_has_stable_sections,
        test_execution_package_details_not_found_error_shape,
        test_dashboard_summary_is_summary_only,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
