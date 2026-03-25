"""
Phase 89 live operation visibility tests.

Run: python tests/phase89_live_operation_visibility_test.py
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
    path = base / f"phase89_{uuid.uuid4().hex[:8]}"
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
        active_project="phase89proj",
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
        allowed_actions=["prepare_package", "recommend_next_step"],
        blocked_actions=["unbounded_loop"],
        run_id="run-phase89",
    )


def _write_package(project_path: Path, package: dict) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package_id = str(package.get("package_id") or f"pkg-{uuid.uuid4().hex[:10]}")
    payload = {
        "package_id": package_id,
        "project_name": "phase89proj",
        "project_path": str(project_path),
        "run_id": "run-phase89",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "pending",
        "release_status": "pending",
        "execution_status": "pending",
        **package,
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_idle_state_has_clear_reason():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="",
        project_name="",
        project_state={},
        package={},
        cost_summary={},
        delivery_summary={},
    )
    assert status["operation_status"] == "idle"
    assert "active project" in status["idle_reason"].lower()


def test_running_state_exposes_phase_and_step():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="phase89_running",
        project_name="phase89_running",
        project_state={"project_lifecycle_status": "active", "execution_package_id": "pkg-run"},
        package={"package_id": "pkg-run", "execution_status": "running"},
        cost_summary={"budget_status": "within_budget"},
        delivery_summary={},
    )
    assert status["operation_status"] == "running"
    assert status["current_phase"] == "execution"
    assert status["current_step"]


def test_awaiting_review_state_has_review_activity():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="phase89_review",
        project_name="phase89_review",
        project_state={"execution_package_id": "pkg-review"},
        package={"package_id": "pkg-review", "review_status": "review_pending"},
        cost_summary={"budget_status": "within_budget"},
        delivery_summary={},
    )
    assert status["operation_status"] == "awaiting_review"
    activity_types = [entry["activity_type"] for entry in status["recent_activity"]]
    assert "review_awaited" in activity_types


def test_blocked_state_has_blocker_reason():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="phase89_blocked",
        project_name="phase89_blocked",
        project_state={"execution_package_id": "pkg-blocked"},
        package={"package_id": "pkg-blocked"},
        cost_summary={
            "budget_status": "cap_exceeded",
            "kill_switch_active": False,
        },
        delivery_summary={},
    )
    assert status["operation_status"] == "blocked"
    assert "budget" in status["idle_reason"].lower()


def test_completed_state_has_recent_activity():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="phase89_complete",
        project_name="phase89_complete",
        project_state={"execution_package_id": "pkg-complete"},
        package={
            "package_id": "pkg-complete",
            "execution_status": "succeeded",
            "release_status": "released",
            "created_at": "2026-03-25T00:00:00",
        },
        cost_summary={"budget_status": "within_budget"},
        delivery_summary={"delivery_progress_state": "client_safe_packaging_ready"},
    )
    assert status["operation_status"] == "completed"
    assert len(status["recent_activity"]) >= 1


def test_recent_activity_entries_are_concise_and_safe():
    from NEXUS.live_operation_status import build_live_operation_status

    status = build_live_operation_status(
        project_key="phase89_safe",
        project_name="phase89_safe",
        project_state={"execution_package_id": "pkg-safe"},
        package={
            "package_id": "pkg-safe",
            "review_status": "review_pending",
            "local_analysis_summary": {"suggested_next_action": "operator_review"},
            "created_at": "2026-03-25T00:00:00",
        },
        cost_summary={"budget_status": "within_budget"},
        delivery_summary={},
    )
    assert status["recent_activity"]
    for entry in status["recent_activity"]:
        summary = str(entry.get("activity_summary") or "")
        assert summary
        assert len(summary) <= 140
        lowered = summary.lower()
        assert "authority_trace" not in lowered
        assert "governance_trace" not in lowered
        assert "raw" not in lowered


def test_snapshot_build_has_no_execution_side_effects():
    from NEXUS.registry import PROJECTS
    from NEXUS.project_state import get_project_state_file
    from NEXUS.execution_package_registry import get_execution_package_file_path
    from ops.forge_console_bridge import build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "review_pending",
                "execution_status": "pending",
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase89_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 89 side-effect check"}
        try:
            state_file = get_project_state_file(str(tmp))
            package_file = Path(get_execution_package_file_path(str(tmp), package_id))
            state_before = state_file.read_text(encoding="utf-8")
            package_before = package_file.read_text(encoding="utf-8")
            snapshot = build_project_snapshot(project_key)
            assert snapshot["status"] == "ok"
            assert snapshot["payload"]["live_operation_status"]["operation_status"] in {
                "idle",
                "running",
                "awaiting_review",
                "blocked",
                "completed",
            }
            state_after = state_file.read_text(encoding="utf-8")
            package_after = package_file.read_text(encoding="utf-8")
            assert state_before == state_after
            assert package_before == package_after
        finally:
            PROJECTS.pop(project_key, None)


def test_phase79_to_88_regression_contracts_remain_compatible():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview, build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "review_pending",
                "execution_status": "pending",
                "local_analysis_summary": {"suggested_next_action": "request_human_review"},
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase89_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 89 regression"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Regression check for phases 79-88.",
                project_context="Ensure prior visibility and revenue previews remain stable.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["Visibility-only"],
                        "risk_notes": ["No hidden execution"],
                        "runtime_preferences": ["Governed flow only"],
                        "output_expectations": ["Keep previous summaries available"],
                        "review_expectations": ["Human review preserved"],
                    }
                ),
                requested_artifacts_json=json.dumps({"selected": ["implementation_summary"], "custom": []}),
                linked_attachment_ids_json=json.dumps([]),
                autonomy_mode="supervised_build",
                lead_intake_json=json.dumps(
                    {
                        "contact_name": "Casey",
                        "contact_email": "casey@example.com",
                        "company_name": "Forge Revenue",
                        "problem_summary": "Need visibility-first governed delivery.",
                    }
                ),
                qualification_json=json.dumps(
                    {
                        "budget_band": "medium",
                        "urgency": "medium",
                        "problem_clarity": "clear",
                        "decision_readiness": "ready",
                        "fit_notes": "",
                    }
                ),
            )
            assert preview["status"] == "ok"
            payload = preview["payload"]
            assert payload["qualification_summary"] is not None
            assert payload["offer_summary"] is not None
            assert payload["response_summary"] is not None
            assert payload["conversion_summary"] is not None

            project_snapshot = build_project_snapshot(project_key)
            assert project_snapshot["status"] == "ok"
            assert "workflow_activity" in project_snapshot["payload"]
            assert "delivery_summary" in project_snapshot["payload"]
            assert "live_operation_status" in project_snapshot["payload"]
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_idle_state_has_clear_reason,
        test_running_state_exposes_phase_and_step,
        test_awaiting_review_state_has_review_activity,
        test_blocked_state_has_blocker_reason,
        test_completed_state_has_recent_activity,
        test_recent_activity_entries_are_concise_and_safe,
        test_snapshot_build_has_no_execution_side_effects,
        test_phase79_to_88_regression_contracts_remain_compatible,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
