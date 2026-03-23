"""
Phase 48 governance conflict + pause semantics tests.

Run: python tests/phase48_governance_conflict_pause_test.py
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
    path = base / f"phase48_{uuid.uuid4().hex[:8]}"
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
            "agents": ["coder"],
        }
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("NEXUS.registry.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.governance_layer.PROJECTS", project_map, clear=True))
        stack.enter_context(patch.dict("NEXUS.registry_dashboard.PROJECTS", project_map, clear=True))
        yield


def test_priority_order_resolves_conflict_with_required_schema():
    from NEXUS.meta_engine_governance import resolve_meta_engine_governance

    result = resolve_meta_engine_governance(
        titan_summary={"titan_status": "blocked", "execution_reason": "TITAN blocked."},
        helios_summary={"helios_status": "gated", "execution_gated": True, "improvement_reason": "HELIOS gated."},
        veritas_summary={"veritas_status": "review_required", "truth_reason": "VERITAS contradiction."},
    )
    assert set(result.keys()) == {
        "status",
        "conflict_type",
        "involved_engines",
        "winning_priority",
        "resolution_basis",
        "resolution_state",
        "routing_outcome",
        "reason",
        "governance_trace",
    }
    assert result["status"] == "resolved"
    assert result["winning_priority"] == "VERITAS"
    assert result["resolution_basis"] == "priority_order"
    assert result["resolution_state"] == "escalate"
    assert result["routing_outcome"] == "escalate"


def test_unresolved_conflict_forces_pause():
    from NEXUS.meta_engine_governance import resolve_meta_engine_governance

    result = resolve_meta_engine_governance(
        sentinel_summary={"sentinel_status": "error_fallback", "threat_reason": "SENTINEL unavailable."},
        veritas_summary={"veritas_status": "review_required", "truth_reason": "VERITAS contradiction."},
    )
    assert result["status"] == "unresolved"
    assert result["conflict_type"] == "unsafe_governance_conflict"
    assert result["winning_priority"] == "SENTINEL"
    assert result["resolution_state"] == "pause"
    assert result["routing_outcome"] == "pause"


def test_governance_layer_emits_explicit_escalate_path():
    from NEXUS.governance_layer import evaluate_governance_outcome_safe

    with _local_test_dir() as tmp:
        _write_state(
            tmp,
            {
                "active_project": "phase48proj",
                "last_aegis_decision": {"aegis_decision": "allow", "aegis_reason": "allowed"},
                "guardrail_status": "clear",
                "guardrail_result": {"guardrail_status": "clear", "launch_allowed": True},
                "dispatch_result": {"message": "ok", "execution_status": "simulated_execution"},
            },
        )
        with _patched_projects("phase48proj", tmp):
            with patch(
                "NEXUS.governance_layer._build_meta_engine_conflict",
                return_value={
                    "status": "resolved",
                    "conflict_type": "priority_resolved_governance_conflict",
                    "involved_engines": ["VERITAS", "HELIOS"],
                    "winning_priority": "VERITAS",
                    "resolution_basis": "priority_order",
                    "resolution_state": "escalate",
                    "routing_outcome": "escalate",
                    "reason": "VERITAS contradiction requires escalation.",
                    "governance_trace": {"engine_signals": {}},
                },
            ):
                result = evaluate_governance_outcome_safe(
                    dispatch_status="accepted",
                    runtime_execution_status="simulated_execution",
                    dispatch_result={"execution_status": "simulated_execution"},
                    automation_status="completed",
                    automation_result={},
                    active_project="phase48proj",
                    project_path=str(tmp),
                )
    assert result["resolution_state"] == "escalate"
    assert result["routing_outcome"] == "escalate"
    assert result["workflow_action"] == "manual_review"
    assert result["governance_conflict"]["winning_priority"] == "VERITAS"


def test_governance_layer_emits_explicit_stop_path():
    from NEXUS.governance_layer import evaluate_governance_outcome_safe

    with _local_test_dir() as tmp:
        _write_state(
            tmp,
            {
                "active_project": "phase48proj",
                "last_aegis_decision": {"aegis_decision": "deny", "aegis_reason": "denied"},
                "guardrail_status": "blocked",
                "guardrail_result": {"guardrail_status": "blocked", "launch_allowed": False},
                "dispatch_result": {"message": "blocked", "execution_status": "queued"},
            },
        )
        with _patched_projects("phase48proj", tmp):
            result = evaluate_governance_outcome_safe(
                dispatch_status="accepted",
                runtime_execution_status="simulated_execution",
                dispatch_result={"execution_status": "simulated_execution"},
                automation_status="completed",
                automation_result={},
                active_project="phase48proj",
                project_path=str(tmp),
            )
    assert result["resolution_state"] == "stop"
    assert result["routing_outcome"] == "stop"
    assert result["workflow_action"] == "stop_after_current_stage"
    assert result["governance_status"] == "blocked"


def test_pause_trace_persists_to_package_project_and_dashboard():
    from NEXUS.execution_package_registry import (
        normalize_execution_package,
        read_execution_package,
        record_execution_package_governance_safe,
        read_execution_package_journal_tail,
        write_execution_package_safe,
    )
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    with _local_test_dir() as tmp:
        _write_state(
            tmp,
            {
                "active_project": "phase48proj",
                "governance_status": "review_required",
                "governance_result": {
                    "governance_status": "review_required",
                    "resolution_state": "pause",
                    "routing_outcome": "pause",
                    "conflict_type": "unsafe_governance_conflict",
                    "governance_conflict": {
                        "status": "unresolved",
                        "conflict_type": "unsafe_governance_conflict",
                        "involved_engines": ["SENTINEL", "VERITAS"],
                        "winning_priority": "SENTINEL",
                        "resolution_basis": "highest_priority_signal_not_safe_to_resolve",
                        "resolution_state": "pause",
                        "routing_outcome": "pause",
                        "reason": "pause",
                        "governance_trace": {"engine_signals": {}},
                    },
                },
                "project_lifecycle_status": "paused",
                "project_lifecycle_result": {"lifecycle_status": "paused", "reason": "Governance paused progression."},
            },
        )
        package = normalize_execution_package(
            {
                "project_name": "phase48proj",
                "project_path": str(tmp),
                "runtime_target_id": "windows_review_package",
                "command_request": {"summary": "phase48"},
            }
        )
        write_execution_package_safe(str(tmp), package)
        governance_result = {
            "governance_status": "review_required",
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "governance_conflict": {
                "status": "unresolved",
                "conflict_type": "unsafe_governance_conflict",
                "involved_engines": ["SENTINEL", "VERITAS"],
                "winning_priority": "SENTINEL",
                "resolution_basis": "highest_priority_signal_not_safe_to_resolve",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": "pause",
                "governance_trace": {"engine_signals": {}},
            },
            "governance_trace": {"base_governance": {}, "conflict": {}},
            "conflict_type": "unsafe_governance_conflict",
        }
        record_execution_package_governance_safe(
            project_path=str(tmp),
            package_id=package["package_id"],
            governance_result=governance_result,
        )
        with _patched_projects("phase48proj", tmp):
            dashboard = build_registry_dashboard_summary()
        persisted = read_execution_package(str(tmp), package["package_id"])
        journal_tail = read_execution_package_journal_tail(str(tmp), n=1)
    assert ((persisted.get("metadata") or {}).get("governance_conflict") or {}).get("status") == "unresolved"
    assert journal_tail[-1]["governance_resolution_state"] == "pause"
    assert dashboard["governance_resolution_state_by_project"]["phase48proj"] == "pause"
    assert dashboard["governance_routing_outcome_by_project"]["phase48proj"] == "pause"
    assert dashboard["governance_conflict_status_by_project"]["phase48proj"] == "unresolved"


def test_no_silent_continuation_after_unresolved_conflict():
    from NEXUS.project_lifecycle import evaluate_project_lifecycle_safe
    from NEXUS.project_routing import build_project_routing_decision

    state = {
        "governance_status": "review_required",
        "governance_result": {
            "governance_status": "review_required",
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "reason": "Governance pause required.",
            "workflow_action": "hold",
            "governance_conflict": {
                "status": "unresolved",
                "conflict_type": "unsafe_governance_conflict",
                "involved_engines": ["SENTINEL"],
                "winning_priority": "SENTINEL",
                "resolution_basis": "highest_priority_signal_not_safe_to_resolve",
                "resolution_state": "pause",
                "routing_outcome": "pause",
                "reason": "pause",
                "governance_trace": {},
            },
        },
        "enforcement_status": "hold",
        "task_queue_snapshot": [{"id": "t1", "task": "do thing", "status": "pending"}],
    }
    lifecycle = evaluate_project_lifecycle_safe(
        active_project="phase48proj",
        project_path="C:\\phase48",
        governance_status=state["governance_status"],
        governance_result=state["governance_result"],
        existing_project_state=state,
    )
    routing = build_project_routing_decision(project_key="phase48proj", state=state)
    assert lifecycle["lifecycle_status"] == "paused"
    assert routing["selected_action"] == "pause"
    assert routing["routing_status"] == "paused"


def main():
    tests = [
        test_priority_order_resolves_conflict_with_required_schema,
        test_unresolved_conflict_forces_pause,
        test_governance_layer_emits_explicit_escalate_path,
        test_governance_layer_emits_explicit_stop_path,
        test_pause_trace_persists_to_package_project_and_dashboard,
        test_no_silent_continuation_after_unresolved_conflict,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
