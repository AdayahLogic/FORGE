"""
Phase 85 budget caps + kill switch tests.

Run: python tests/phase85_budget_caps_kill_switch_test.py
"""

from __future__ import annotations

import json
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
    path = base / f"phase85_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, *, run_id: str = "run-phase85"):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase85proj",
        notes="",
        architect_plan=None,
        task_queue=[],
        coder_output_path=None,
        implementation_file_path=None,
        test_report_path=None,
        docs_output_path=None,
        execution_report_path=None,
        workspace_report_path=None,
        operator_log_path=None,
        supervisor_report_path=None,
        supervisor_decision=None,
        autonomous_cycle_report_path=None,
        autonomous_cycle_summary=None,
        computer_use_report_path=None,
        computer_use_summary=None,
        tool_execution_report_path=None,
        tool_execution_summary=None,
        file_modification_report_path=None,
        file_modification_summary=None,
        diff_patch_report_path=None,
        diff_patch_summary=None,
        agent_routing_report_path=None,
        agent_routing_summary=None,
        execution_bridge_report_path=None,
        execution_bridge_summary=None,
        engine_registry_report_path=None,
        engine_registry_summary=None,
        capability_registry_report_path=None,
        capability_registry_summary=None,
        terminal_report_path=None,
        terminal_summary=None,
        browser_research_report_path=None,
        browser_research_summary=None,
        full_automation_report_path=None,
        full_automation_summary=None,
        dispatch_status="queued",
        governance_status="ok",
        enforcement_status="approval_required",
        project_lifecycle_status="active",
        autonomy_mode="supervised_build",
        allowed_actions=["prepare_package", "recommend_next_step"],
        blocked_actions=["unbounded_loop"],
        run_id=run_id,
    )


def _set_budget_caps(project_path: Path, caps: dict[str, object]):
    state_path = project_path / "state" / "project_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["budget_caps"] = caps
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_package(project_path: Path, project_key: str, *, run_id: str, budget_caps: dict[str, object] | None = None) -> str:
    from NEXUS.execution_package_registry import write_execution_package

    package_id = f"pkg-{uuid.uuid4().hex[:10]}"
    package = {
        "package_id": package_id,
        "project_name": project_key,
        "project_path": str(project_path),
        "run_id": run_id,
        "package_status": "review_pending",
        "review_status": "pending",
        "execution_status": "pending",
        "expected_outputs": ["implementation_plan", "summary_report"],
        "execution_receipt": {
            "result_status": "",
            "exit_code": None,
            "log_ref": "",
            "files_touched_count": 1,
            "artifacts_written_count": 1,
            "failure_class": "",
        },
    }
    if isinstance(budget_caps, dict):
        package["budget_caps"] = budget_caps
    out = write_execution_package(str(project_path), package)
    assert out
    return package_id


def test_within_budget_state():
    from NEXUS.budget_controls import evaluate_budget_controls

    control = evaluate_budget_controls(
        budget_caps={"operation_budget_cap": 1.0, "kill_switch_enabled": True},
        current_operation_cost=0.2,
        current_project_cost=0.2,
        current_session_cost=0.2,
    )
    assert control["budget_status"] == "within_budget"
    assert control["kill_switch_active"] is False


def test_approaching_cap_state():
    from NEXUS.budget_controls import evaluate_budget_controls

    control = evaluate_budget_controls(
        budget_caps={"operation_budget_cap": 1.0, "kill_switch_enabled": True},
        current_operation_cost=0.8,
        current_project_cost=0.8,
        current_session_cost=0.8,
    )
    assert control["budget_status"] == "approaching_cap"
    assert control["budget_scope"] == "operation"


def test_cap_exceeded_state_without_kill_switch():
    from NEXUS.budget_controls import evaluate_budget_controls

    control = evaluate_budget_controls(
        budget_caps={"operation_budget_cap": 1.0, "kill_switch_enabled": False},
        current_operation_cost=1.2,
        current_project_cost=1.2,
        current_session_cost=1.2,
    )
    assert control["budget_status"] == "cap_exceeded"
    assert control["kill_switch_active"] is False


def test_kill_switch_triggered_state():
    from NEXUS.budget_controls import evaluate_budget_controls

    control = evaluate_budget_controls(
        budget_caps={"operation_budget_cap": 1.0, "kill_switch_enabled": True},
        current_operation_cost=1.2,
        current_project_cost=1.2,
        current_session_cost=1.2,
    )
    assert control["budget_status"] == "kill_switch_triggered"
    assert control["kill_switch_active"] is True


def test_scope_selection_prefers_governing_scope():
    from NEXUS.budget_controls import evaluate_budget_controls

    control = evaluate_budget_controls(
        budget_caps={
            "operation_budget_cap": 10.0,
            "project_budget_cap": 1.0,
            "session_budget_cap": 20.0,
            "kill_switch_enabled": False,
        },
        current_operation_cost=0.2,
        current_project_cost=1.5,
        current_session_cost=0.4,
    )
    assert control["budget_scope"] == "project"
    assert control["budget_status"] == "cap_exceeded"


def test_kill_switch_blocks_execution_explicitly_without_governance_bypass():
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_execution
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        run_id = "run-phase85-kill-switch"
        _write_state(tmp, run_id=run_id)
        _set_budget_caps(
            tmp,
            {
                "operation_budget_cap": 0.0001,
                "project_budget_cap": 1.0,
                "session_budget_cap": 1.0,
                "kill_switch_enabled": True,
            },
        )
        project_key = f"phase85_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 85 temp project"}
        try:
            package_id = _create_package(
                tmp,
                project_key,
                run_id=run_id,
                budget_caps={
                    "operation_budget_cap": 0.0001,
                    "project_budget_cap": 1.0,
                    "session_budget_cap": 1.0,
                    "kill_switch_enabled": True,
                },
            )
            result = record_execution_package_execution(
                project_path=str(tmp),
                package_id=package_id,
                execution_actor="openclaw",
            )
            assert result["status"] == "denied"
            package = read_execution_package(str(tmp), package_id) or {}
            assert package.get("execution_status") == "blocked"
            assert package.get("budget_status") == "kill_switch_triggered"
            assert package.get("kill_switch_active") is True
            assert "budget" in str((package.get("execution_reason") or {}).get("message") or "").lower()
            assert package.get("execution_receipt", {}).get("result_status") == "blocked"
            assert package.get("execution_receipt", {}).get("failure_class") == "preflight_block"
        finally:
            PROJECTS.pop(project_key, None)


def test_budget_fields_attach_to_preview_outputs():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp, run_id="run-phase85-preview")
        _set_budget_caps(
            tmp,
            {
                "operation_budget_cap": 0.5,
                "project_budget_cap": 2.0,
                "session_budget_cap": 1.5,
                "kill_switch_enabled": True,
            },
        )
        project_key = f"phase85_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 85 temp project"}
        try:
            preview = build_intake_preview(
                request_kind="update_request",
                project_key=project_key,
                objective="Budget control preview visibility",
                project_context="Phase 85 budget preview test",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["No authority bypass."],
                        "risk_notes": ["Budget signal only."],
                        "runtime_preferences": ["Explicit governance trace."],
                        "output_expectations": ["Budget state is visible."],
                        "review_expectations": ["Keep additive behavior."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_plan"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
            )
            payload = preview["payload"]
            assert preview["status"] == "ok"
            assert payload["budget_status"] in {
                "within_budget",
                "approaching_cap",
                "cap_exceeded",
                "kill_switch_triggered",
            }
            assert payload["budget_scope"] in {"operation", "project", "session"}
            assert isinstance(payload["remaining_estimated_budget"], float)
            assert isinstance(payload["kill_switch_active"], bool)
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_within_budget_state,
        test_approaching_cap_state,
        test_cap_exceeded_state_without_kill_switch,
        test_kill_switch_triggered_state,
        test_scope_selection_prefers_governing_scope,
        test_kill_switch_blocks_execution_explicitly_without_governance_bypass,
        test_budget_fields_attach_to_preview_outputs,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
