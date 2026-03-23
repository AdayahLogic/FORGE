"""
Phase 58 Cursor bridge hardening tests.

Run: python tests/phase58_cursor_bridge_hardening_test.py
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase58_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, payload: dict) -> None:
    state_dir = project_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "project_state.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


@contextmanager
def _patched_projects(project_name: str, project_path: Path):
    project_map = {
        project_name: {
            "name": project_name,
            "path": str(project_path),
            "agents": ["cursor"],
        }
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("NEXUS.registry.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.registry_dashboard.PROJECTS", project_map, clear=True))
        yield


def _cursor_dispatch_plan(project_path: str) -> dict:
    return {
        "dispatch_version": "1.0",
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": True,
        "project": {
            "project_id": "phase58proj",
            "project_name": "phase58proj",
            "project_path": project_path,
        },
        "request": {
            "request_type": "user_request",
            "task_type": "implementation",
            "summary": "Ship governed Cursor bridge changes.",
            "priority": "normal",
        },
        "routing": {
            "runtime_node": "nexus",
            "agent_name": "nexus",
            "tool_name": "runtime_dispatcher",
            "selection_status": "selected",
            "selection_reason": "Cursor bridge hardening test.",
        },
        "execution": {
            "execution_mode": "manual_only",
            "runtime_target_id": "cursor",
            "runtime_target_name": "cursor",
            "requires_human_approval": False,
            "can_execute": False,
        },
        "artifacts": {
            "expected_outputs": ["patch_summary", "changed_files"],
            "target_files": ["NEXUS/runtimes/cursor_runtime.py"],
        },
        "timestamps": {"planned_at": "2026-03-23T12:00:00+00:00"},
    }


def _create_cursor_linked_package(project_path: str):
    from NEXUS.execution_package_builder import build_execution_package_safe
    from NEXUS.execution_package_registry import write_execution_package_safe
    from NEXUS.runtimes.cursor_runtime import normalize_cursor_bridge_handoff

    plan = _cursor_dispatch_plan(project_path)
    handoff = normalize_cursor_bridge_handoff(
        plan,
        authority_trace={
            "component_name": "cursor_bridge",
            "component_role": "generation_bridge_only",
            "authority_status": "authorized",
        },
        governance_trace={"origin": "phase58_test", "review_only": True},
        status="prepared",
    )
    package = build_execution_package_safe(
        dispatch_plan=plan,
        package_reason="Phase 58 governed Cursor bridge package.",
        cursor_bridge_summary=handoff,
    )
    metadata = dict(package.get("metadata") or {})
    metadata["cursor_bridge_summary"] = handoff
    package["metadata"] = metadata
    package["cursor_bridge_summary"] = handoff
    package_path = write_execution_package_safe(project_path, package)
    assert package_path
    return plan, handoff, package, package_path


def test_valid_governed_task_handoff():
    from NEXUS.runtimes.cursor_runtime import dispatch

    result = dispatch(_cursor_dispatch_plan("C:\\phase58"))
    summary = result["cursor_bridge_summary"]
    assert result["status"] == "accepted"
    assert result["execution_mode"] == "manual_only"
    assert summary["bridge_phase"] == "phase_5_hardened"
    assert summary["bridge_task_id"]
    assert summary["task_type"] == "implementation"
    assert summary["requested_artifacts"] == ["patch_summary", "changed_files"]
    assert summary["execution_enabled"] is False


def test_valid_governed_artifact_return():
    from NEXUS.execution_package_registry import read_execution_package, record_cursor_bridge_artifact_return_safe

    with _local_test_dir() as tmp:
        _, handoff, package, _ = _create_cursor_linked_package(str(tmp))
        result = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": handoff["bridge_task_id"],
                "package_id": package["package_id"],
                "artifact_type": "patch",
                "artifact_summary": "Prepared governed patch output.",
                "changed_files": ["NEXUS/runtimes/cursor_runtime.py"],
                "patch_summary": {"files_changed": 1, "notes": "bridge hardening"},
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
                "authority_trace": {"component_name": "cursor_bridge"},
                "governance_trace": {"origin": "phase58_test", "review_only": True},
            },
        )
        persisted = read_execution_package(str(tmp), package["package_id"])
    assert result["status"] == "ok"
    assert result["validation_status"] == "validated"
    assert result["artifact_record"]["package_id"] == package["package_id"]
    assert persisted is not None
    assert persisted["cursor_bridge_summary"]["bridge_status"] == "artifact_recorded"
    assert persisted["cursor_bridge_summary"]["latest_validation_status"] == "validated"
    assert persisted["cursor_bridge_artifacts"][-1]["artifact_type"] == "patch"
    assert persisted["runtime_artifacts"][-1]["artifact_type"] == "cursor_bridge_artifact_return"


def test_malformed_artifact_return_denied():
    from NEXUS.execution_package_registry import record_cursor_bridge_artifact_return_safe

    with _local_test_dir() as tmp:
        _, handoff, package, _ = _create_cursor_linked_package(str(tmp))
        result = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": handoff["bridge_task_id"],
                "package_id": package["package_id"],
                "artifact_type": "patch",
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
            },
        )
    assert result["status"] == "denied"
    assert result["validation_status"] == "rejected_malformed"


def test_unlinked_artifact_return_denied():
    from NEXUS.execution_package_builder import build_execution_package_safe
    from NEXUS.execution_package_registry import record_cursor_bridge_artifact_return_safe, write_execution_package_safe

    with _local_test_dir() as tmp:
        package = build_execution_package_safe(
            dispatch_plan=_cursor_dispatch_plan(str(tmp)),
            package_reason="Package without Cursor bridge linkage.",
        )
        assert write_execution_package_safe(str(tmp), package)
        result = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": "bridge-unlinked",
                "package_id": package["package_id"],
                "artifact_type": "patch",
                "artifact_summary": "Should be denied.",
                "changed_files": ["NEXUS/command_surface.py"],
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
            },
        )
    assert result["status"] == "denied"
    assert result["validation_status"] == "rejected_package_linkage"


def test_cursor_execution_authority_attempt_denied():
    from NEXUS.execution_package_registry import record_cursor_bridge_artifact_return_safe

    with _local_test_dir() as tmp:
        _, handoff, package, _ = _create_cursor_linked_package(str(tmp))
        result = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": handoff["bridge_task_id"],
                "package_id": package["package_id"],
                "artifact_type": "patch",
                "artifact_summary": "Unsafe authority attempt.",
                "changed_files": ["NEXUS/runtime_execution.py"],
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
                "can_execute": True,
                "execution_mode": "external_runtime",
            },
        )
    assert result["status"] == "denied"
    assert result["validation_status"] == "rejected_authority_boundary"


def test_trace_persistence_and_package_linkage_verification():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        read_execution_package_journal_tail,
        record_cursor_bridge_artifact_return_safe,
    )
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_state(
            tmp,
            {
                "active_project": "phase58proj",
                "execution_package_id": "",
                "execution_package_path": "",
                "governance_status": "review_required",
                "governance_result": {
                    "governance_status": "review_required",
                    "resolution_state": "pause",
                    "routing_outcome": "pause",
                },
            },
        )
        _, handoff, package, package_path = _create_cursor_linked_package(str(tmp))
        _write_state(
            tmp,
            {
                "active_project": "phase58proj",
                "execution_package_id": package["package_id"],
                "execution_package_path": package_path,
                "governance_status": "review_required",
                "governance_result": {
                    "governance_status": "review_required",
                    "resolution_state": "pause",
                    "routing_outcome": "pause",
                },
            },
        )
        result = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": handoff["bridge_task_id"],
                "package_id": package["package_id"],
                "artifact_type": "diff",
                "artifact_summary": "Recorded diff for review package.",
                "changed_files": ["NEXUS/execution_package_registry.py"],
                "patch_summary": {"files_changed": 1},
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
                "authority_trace": {"component_name": "cursor_bridge", "authority_status": "authorized"},
                "governance_trace": {"origin": "phase58_test", "review_only": True},
            },
        )
        persisted = read_execution_package(str(tmp), package["package_id"])
        journal_tail = read_execution_package_journal_tail(str(tmp), n=1)
        with _patched_projects("phase58proj", tmp):
            dashboard = build_registry_dashboard_summary()
    assert result["status"] == "ok"
    assert persisted["cursor_bridge_summary"]["bridge_task_id"] == handoff["bridge_task_id"]
    assert persisted["cursor_bridge_artifacts"][-1]["governance_trace"]["origin"] == "phase58_test"
    assert journal_tail[-1]["cursor_bridge_status"] == "artifact_recorded"
    assert dashboard["execution_package_cursor_bridge_summary"]["latest_bridge_status_by_project"]["phase58proj"] == "artifact_recorded"
    assert dashboard["execution_package_cursor_bridge_summary"]["latest_bridge_task_id_by_project"]["phase58proj"] == handoff["bridge_task_id"]


def test_governance_and_package_flows_remain_intact():
    from NEXUS.execution_package_registry import (
        read_execution_package,
        record_cursor_bridge_artifact_return_safe,
        record_execution_package_governance_safe,
    )

    with _local_test_dir() as tmp:
        _, handoff, package, _ = _create_cursor_linked_package(str(tmp))
        governance_result = {
            "governance_status": "review_required",
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "governance_conflict": {
                "status": "unresolved",
                "conflict_type": "unsafe_governance_conflict",
            },
            "governance_trace": {"origin": "phase58_governance"},
        }
        gov = record_execution_package_governance_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            governance_result=governance_result,
        )
        art = record_cursor_bridge_artifact_return_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            artifact_payload={
                "bridge_task_id": handoff["bridge_task_id"],
                "package_id": package["package_id"],
                "artifact_type": "patch",
                "artifact_summary": "Patch remains review-linked under governance pause.",
                "changed_files": ["NEXUS/registry_dashboard.py"],
                "source_runtime": "cursor",
                "actor": "cursor_bridge",
            },
        )
        persisted = read_execution_package(str(tmp), package["package_id"])
    assert gov["status"] == "ok"
    assert art["status"] == "ok"
    assert ((persisted.get("metadata") or {}).get("governance_conflict") or {}).get("status") == "unresolved"
    assert persisted["cursor_bridge_summary"]["bridge_status"] == "artifact_recorded"


def main():
    tests = [
        test_valid_governed_task_handoff,
        test_valid_governed_artifact_return,
        test_malformed_artifact_return_denied,
        test_unlinked_artifact_return_denied,
        test_cursor_execution_authority_attempt_denied,
        test_trace_persistence_and_package_linkage_verification,
        test_governance_and_package_flows_remain_intact,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
