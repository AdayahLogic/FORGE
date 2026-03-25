"""
Phase 90 operator quick actions tests.

Run: python tests/phase90_operator_quick_actions_test.py
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
    path = base / f"phase90_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, package_id: str = ""):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase90proj",
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
        execution_package_id=package_id,
        execution_package_path=str(project_path / "state" / "execution_packages" / f"{package_id}.json") if package_id else "",
        dispatch_status="queued",
        governance_status="ok",
        enforcement_status="approval_required",
        project_lifecycle_status="active",
        autonomy_mode="supervised_build",
        run_id="run-phase90",
    )


def _write_package(project_path: Path, package: dict) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package_id = str(package.get("package_id") or f"pkg-{uuid.uuid4().hex[:10]}")
    payload = {
        "package_id": package_id,
        "project_name": "phase90proj",
        "project_path": str(project_path),
        "run_id": "run-phase90",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "pending",
        "release_status": "pending",
        "execution_status": "pending",
        **package,
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_quick_actions_none_when_no_relevant_state():
    from NEXUS.operator_quick_actions import (
        build_intake_preview_quick_actions,
        build_overview_quick_actions,
    )

    intake = build_intake_preview_quick_actions({})
    overview = build_overview_quick_actions([])
    assert intake["quick_actions_status"] == "none"
    assert intake["available_actions"] == []
    assert overview["quick_actions_status"] == "none"
    assert overview["available_actions"] == []


def test_quick_actions_available_for_review_input_and_package_contexts():
    from NEXUS.operator_quick_actions import (
        build_intake_preview_quick_actions,
        build_project_quick_actions,
        build_review_center_quick_actions,
    )

    intake = build_intake_preview_quick_actions(
        {
            "request_kind": "lead_intake",
            "composition_status": {"missing_fields": ["lead_contact_name", "lead_problem_summary"]},
            "warnings": ["Attachment cannot inform request preview."],
            "response_summary": {"response_status": "response_ready"},
            "conversion_summary": {"conversion_status": "conversion_needs_review"},
            "budget_status": "within_budget",
        }
    )
    assert intake["quick_actions_status"] == "available"
    labels = {item["action_label"] for item in intake["available_actions"]}
    kinds = {item["action_kind"] for item in intake["available_actions"]}
    assert "Provide missing qualification fields" in labels
    assert "Review generated response" in labels
    assert "inspect" in kinds
    assert "input_request" in kinds

    project = build_project_quick_actions(
        project_state={"execution_package_id": "pkg-1"},
        workflow_activity={"active_package_id": "pkg-1"},
        intake_preview={"composition_status": {"missing_fields": []}, "request_kind": "update_request"},
        delivery_summary={"delivered_artifact_count": 1},
        cost_summary={"budget_status": "within_budget"},
    )
    assert project["quick_actions_status"] == "available"
    assert any(item["action_id"] == "inspect_current_package" for item in project["available_actions"])

    review = build_review_center_quick_actions(
        review_center={
            "approval_ready_context": {"review_status": "pending", "requires_human_approval": True},
            "related_attachments": [{"attachment_id": "att-1"}],
            "delivery_summary": {"delivery_progress_state": "delivery_summary_ready"},
        },
        package_json={"budget_status": "within_budget"},
        cost_summary={"budget_status": "within_budget"},
    )
    assert review["quick_actions_status"] == "available"
    assert any(item["action_label"] == "Open delivery summary" for item in review["available_actions"])
    assert any(item["action_kind"] == "review" for item in review["available_actions"])


def test_quick_actions_blocked_when_budget_or_governance_blocked():
    from NEXUS.operator_quick_actions import (
        build_project_quick_actions,
        build_review_center_quick_actions,
    )

    project = build_project_quick_actions(
        project_state={},
        workflow_activity={},
        intake_preview={"composition_status": {"missing_fields": []}},
        delivery_summary={},
        cost_summary={"budget_status": "cap_exceeded"},
    )
    blocked = [item for item in project["available_actions"] if item["action_id"] == "inspect_budget_blockers"]
    assert blocked
    assert blocked[0]["action_enabled"] is False
    assert blocked[0]["blocked_reason"]

    review = build_review_center_quick_actions(
        review_center={"approval_ready_context": {}, "related_attachments": []},
        package_json={},
        cost_summary={"budget_status": "kill_switch_active"},
    )
    blocked2 = [item for item in review["available_actions"] if item["action_id"] == "inspect_budget_blockers"]
    assert blocked2
    assert blocked2[0]["action_enabled"] is False
    assert blocked2[0]["blocked_reason"]


def test_bridge_snapshot_quick_actions_are_read_only_and_present():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import (
        build_package_snapshot,
        build_project_snapshot,
        build_studio_snapshot,
    )

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "review_pending",
                "requires_human_approval": True,
                "expected_outputs": ["approved_summary"],
                "runtime_artifacts": [{"artifact_type": "test_report"}],
                "cost_tracking": {
                    "cost_estimate": 0.04,
                    "cost_unit": "usd_estimated",
                    "cost_source": "model_execution",
                    "cost_breakdown": {"model": "forge_router", "estimated_tokens": 10000, "estimated_cost": 0.04},
                },
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase90_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 90 temp project"}
        try:
            state_path = tmp / "state" / "project_state.json"
            package_journal = tmp / "state" / "execution_packages" / "execution_package_journal.jsonl"
            before_state = state_path.read_text(encoding="utf-8")
            before_journal = package_journal.read_text(encoding="utf-8") if package_journal.exists() else ""

            studio = build_studio_snapshot()
            project = build_project_snapshot(project_key)
            package = build_package_snapshot(package_id, project_key=project_key)

            assert studio["overview"]["quick_actions"]["quick_actions_status"] in {"none", "available", "blocked"}
            assert project["payload"]["quick_actions"]["quick_actions_status"] in {"none", "available", "blocked"}
            assert package["payload"]["review_center"]["quick_actions"]["quick_actions_status"] in {
                "none",
                "available",
                "blocked",
            }
            assert package["payload"]["quick_actions"] == package["payload"]["review_center"]["quick_actions"]

            after_state = state_path.read_text(encoding="utf-8")
            after_journal = package_journal.read_text(encoding="utf-8") if package_journal.exists() else ""
            assert before_state == after_state
            assert before_journal == after_journal
        finally:
            PROJECTS.pop(project_key, None)


def test_regression_phase79_to_phase89_surfaces_remain_visible():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview, build_package_snapshot, build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "reviewed",
                "decision_status": "approved",
                "release_status": "released",
                "execution_status": "succeeded",
                "expected_outputs": ["implementation_summary"],
                "runtime_artifacts": [{"artifact_type": "test_report"}],
                "routing_summary": {"model_lane": "balanced", "routing_policy_version": "phase86"},
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase90_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 90 regression"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Regression check.",
                project_context="Ensure phases 79-89 contracts remain visible.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["No side effects."],
                        "risk_notes": ["No auto execution."],
                        "runtime_preferences": ["Governed only."],
                        "output_expectations": ["Keep revenue and review outputs visible."],
                        "review_expectations": ["Operator-auditable output."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_summary"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Alex",
                        "contact_email": "alex@example.com",
                        "company_name": "Forge Revenue",
                        "problem_summary": "Need governed delivery support.",
                    }
                ),
                qualification_json=json.dumps(
                    {
                        "budget_band": "medium",
                        "urgency": "medium",
                        "problem_clarity": "clear",
                        "decision_readiness": "ready",
                    }
                ),
            )
            project = build_project_snapshot(project_key)
            package = build_package_snapshot(package_id, project_key=project_key)

            payload = preview["payload"]
            assert payload["qualification_summary"] is not None
            assert payload["offer_summary"] is not None
            assert payload["response_summary"] is not None
            assert payload["conversion_summary"] is not None
            assert payload["model_routing_policy"]["selected_model_lane"] is not None
            assert payload["quick_actions"]["quick_actions_status"] in {"none", "available", "blocked"}

            assert project["payload"]["workflow_activity"]["current_phase"] in {"planning", "routing", "execution", "review"}
            assert project["payload"]["cost_summary"]["budget_status"] in {
                "within_budget",
                "approaching_cap",
                "cap_exceeded",
                "kill_switch_triggered",
            }
            assert package["payload"]["delivery_summary"]["delivered_artifact_count"] >= 0
            assert package["payload"]["review_center"]["quick_actions"]["quick_actions_status"] in {
                "none",
                "available",
                "blocked",
            }
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_quick_actions_none_when_no_relevant_state,
        test_quick_actions_available_for_review_input_and_package_contexts,
        test_quick_actions_blocked_when_budget_or_governance_blocked,
        test_bridge_snapshot_quick_actions_are_read_only_and_present,
        test_regression_phase79_to_phase89_surfaces_remain_visible,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

