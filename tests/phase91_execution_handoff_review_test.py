"""
Phase 91 execution handoff review tests.

Run: python tests/phase91_execution_handoff_review_test.py
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
    path = base / f"phase91_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path, package_id: str = "", *, hold: bool = False):
    from NEXUS.project_state import save_project_state
    from NEXUS.project_state import get_project_state_file

    save_project_state(
        project_path=str(project_path),
        active_project="phase91proj",
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
        run_id="run-phase91",
    )
    if hold:
        state_file = Path(get_project_state_file(str(project_path)))
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["manual_hold_active"] = True
        state_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_package(project_path: Path, package: dict) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package_id = str(package.get("package_id") or f"pkg-{uuid.uuid4().hex[:10]}")
    payload = {
        "package_id": package_id,
        "project_name": "phase91proj",
        "project_path": str(project_path),
        "run_id": "run-phase91",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "pending",
        "release_status": "pending",
        "execution_status": "pending",
        **package,
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_not_ready_when_prerequisites_absent():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="project",
        project_state={},
        has_active_package=False,
    )
    assert review["handoff_status"] == "not_ready"
    assert any("execution package" in item.lower() for item in review["handoff_requirements"])


def test_needs_review_when_review_still_required():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="package",
        project_state={"execution_package_id": "pkg-1"},
        package={
            "package_id": "pkg-1",
            "review_status": "review_pending",
            "decision_status": "approved",
            "release_status": "released",
            "requires_human_approval": False,
        },
        has_active_package=True,
    )
    assert review["handoff_status"] == "needs_review"
    assert any("review" in item.lower() for item in review["handoff_requirements"])


def test_awaiting_approval_when_approval_or_checkpoint_pending():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="package",
        project_state={"execution_package_id": "pkg-2"},
        package={
            "package_id": "pkg-2",
            "review_status": "reviewed",
            "decision_status": "pending",
            "release_status": "pending",
            "requires_human_approval": True,
        },
        has_active_package=True,
    )
    assert review["handoff_status"] == "awaiting_approval"
    assert review["approval_posture"] in {"approval_required", "checkpoint_pending"}


def test_ready_for_handoff_when_all_conditions_met():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="package",
        project_state={"execution_package_id": "pkg-3"},
        package={
            "package_id": "pkg-3",
            "review_status": "reviewed",
            "decision_status": "approved",
            "release_status": "released",
            "requires_human_approval": False,
        },
        model_routing_policy={"routing_status": "routed"},
        budget_status="within_budget",
        has_active_package=True,
    )
    assert review["handoff_status"] == "ready_for_handoff"
    assert review["handoff_readiness"] == "high"


def test_handoff_blocked_when_budget_or_governance_blocks_progression():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="package",
        project_state={"execution_package_id": "pkg-4", "manual_hold_active": True},
        package={"package_id": "pkg-4"},
        budget_status="cap_exceeded",
        budget_reason="Project budget cap exceeded.",
        has_active_package=True,
    )
    assert review["handoff_status"] == "handoff_blocked"
    assert review["handoff_blockers"]
    assert any("budget" in item.lower() or "hold" in item.lower() for item in review["handoff_blockers"])


def test_blockers_requirements_and_next_action_are_explicit():
    from NEXUS.execution_handoff_review import build_execution_handoff_review_safe

    review = build_execution_handoff_review_safe(
        scope="package",
        project_state={"execution_package_id": "pkg-5"},
        package={
            "package_id": "pkg-5",
            "review_status": "review_pending",
            "decision_status": "approved",
            "release_status": "released",
        },
        review_center_context={
            "approval_ready_context": {
                "review_checklist": ["validate_artifacts", "confirm_governance_notes"],
            }
        },
        has_active_package=True,
    )
    assert review["handoff_status"] == "needs_review"
    assert len(review["handoff_requirements"]) >= 1
    assert review["next_handoff_action"]


def test_no_execution_side_effects_from_handoff_review_surfaces():
    from NEXUS.registry import PROJECTS
    from NEXUS.project_state import get_project_state_file
    from NEXUS.execution_package_registry import get_execution_package_file_path
    from ops.forge_console_bridge import build_package_snapshot, build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "review_pending",
                "decision_status": "pending",
                "release_status": "pending",
                "requires_human_approval": True,
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase91_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 91 side-effect check"}
        try:
            state_file = get_project_state_file(str(tmp))
            package_file = Path(get_execution_package_file_path(str(tmp), package_id))
            before_state = state_file.read_text(encoding="utf-8")
            before_package = package_file.read_text(encoding="utf-8")
            project = build_project_snapshot(project_key)
            package = build_package_snapshot(package_id, project_key=project_key)
            assert project["status"] == "ok"
            assert package["status"] == "ok"
            assert project["payload"]["execution_handoff_review"]["handoff_status"] in {
                "not_ready",
                "needs_review",
                "awaiting_approval",
                "ready_for_handoff",
                "handoff_blocked",
            }
            assert package["payload"]["review_center"]["execution_handoff_review"]["handoff_status"] in {
                "not_ready",
                "needs_review",
                "awaiting_approval",
                "ready_for_handoff",
                "handoff_blocked",
            }
            after_state = state_file.read_text(encoding="utf-8")
            after_package = package_file.read_text(encoding="utf-8")
            assert before_state == after_state
            assert before_package == after_package
        finally:
            PROJECTS.pop(project_key, None)


def test_regression_phase79_to_phase90_contracts_remain_visible():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview, build_package_snapshot, build_project_snapshot, build_studio_snapshot

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
        project_key = f"phase91_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 91 regression"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Regression check for phases 79-90.",
                project_context="Ensure prior surfaces remain visible with phase 91 handoff review.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["Visibility-only."],
                        "risk_notes": ["No hidden execution."],
                        "runtime_preferences": ["Governed flow only."],
                        "output_expectations": ["Preserve existing summaries."],
                        "review_expectations": ["Human review preserved."],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_summary"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Jordan",
                        "contact_email": "jordan@example.com",
                        "company_name": "Forge Revenue",
                        "problem_summary": "Need governed execution clarity.",
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
            overview = build_studio_snapshot()
            assert preview["status"] == "ok"
            assert project["status"] == "ok"
            assert package["status"] == "ok"
            assert preview["payload"]["qualification_summary"] is not None
            assert project["payload"]["operator_guidance"]["guidance_scope"] == "project"
            assert package["payload"]["review_center"]["quick_actions"]["quick_actions_status"] in {
                "none",
                "available",
                "blocked",
            }
            assert overview["overview"]["execution_handoff_review"]["handoff_status"] in {
                "not_ready",
                "needs_review",
                "awaiting_approval",
                "ready_for_handoff",
                "handoff_blocked",
            }
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_not_ready_when_prerequisites_absent,
        test_needs_review_when_review_still_required,
        test_awaiting_approval_when_approval_or_checkpoint_pending,
        test_ready_for_handoff_when_all_conditions_met,
        test_handoff_blocked_when_budget_or_governance_blocks_progression,
        test_blockers_requirements_and_next_action_are_explicit,
        test_no_execution_side_effects_from_handoff_review_surfaces,
        test_regression_phase79_to_phase90_contracts_remain_visible,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
