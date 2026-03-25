"""
Phase 87 delivery summary packaging tests.

Run: python tests/phase87_delivery_summary_packaging_test.py
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
    path = base / f"phase87_{uuid.uuid4().hex[:8]}"
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
        active_project="phase87proj",
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
        run_id="run-phase87",
    )


def _write_package(project_path: Path, package: dict) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package_id = str(package.get("package_id") or f"pkg-{uuid.uuid4().hex[:10]}")
    payload = {
        "package_id": package_id,
        "project_name": "phase87proj",
        "project_path": str(project_path),
        "run_id": "run-phase87",
        "package_status": "review_pending",
        "review_status": "pending",
        "decision_status": "pending",
        "release_status": "pending",
        "execution_status": "pending",
        **package,
    }
    assert write_execution_package_safe(str(project_path), payload)
    return package_id


def test_delivery_summary_ready_when_suitable_output_exists():
    from NEXUS.execution_package_registry import build_delivery_summary_contract

    summary = build_delivery_summary_contract(
        {
            "review_status": "reviewed",
            "decision_status": "pending",
            "execution_status": "succeeded",
            "expected_outputs": ["implementation_summary"],
            "runtime_artifacts": [{"artifact_type": "test_report"}],
        }
    )
    assert summary["delivery_progress_state"] in {"delivery_summary_ready", "client_safe_packaging_ready"}
    assert summary["delivered_artifact_count"] == 2
    assert set(summary["delivered_artifact_types"]) == {"implementation_summary", "test_report"}


def test_no_delivery_summary_when_no_suitable_output_exists():
    from NEXUS.execution_package_registry import build_delivery_summary_contract

    summary = build_delivery_summary_contract(
        {
            "review_status": "pending",
            "decision_status": "pending",
            "execution_status": "pending",
            "expected_outputs": [],
            "runtime_artifacts": [],
        }
    )
    assert summary["delivery_progress_state"] in {"no_delivery_summary", "delivery_in_progress"}
    assert summary["delivered_artifact_count"] == 0


def test_client_safe_packaging_ready_when_safe_for_surface():
    from NEXUS.execution_package_registry import build_delivery_summary_contract

    summary = build_delivery_summary_contract(
        {
            "review_status": "reviewed",
            "decision_status": "approved",
            "release_status": "released",
            "execution_status": "succeeded",
            "expected_outputs": ["approved_summary", "test_report"],
            "runtime_artifacts": [{"artifact_type": "diff_review"}],
        }
    )
    assert summary["delivery_progress_state"] == "client_safe_packaging_ready"
    assert summary["delivery_status"] == "client_safe_ready"
    assert summary["internal_details_redacted"] is True


def test_internal_review_required_when_output_not_yet_client_ready():
    from NEXUS.execution_package_registry import build_delivery_summary_contract

    summary = build_delivery_summary_contract(
        {
            "review_status": "pending",
            "decision_status": "pending",
            "execution_status": "succeeded",
            "expected_outputs": ["implementation_summary"],
            "runtime_artifacts": [{"artifact_type": "code_artifacts"}],
        }
    )
    assert summary["delivery_progress_state"] == "internal_review_required"
    assert summary["delivery_status"] == "internal_review_required"


def test_artifact_count_and_labels_are_normalized():
    from NEXUS.execution_package_registry import build_delivery_summary_contract

    summary = build_delivery_summary_contract(
        {
            "decision_status": "approved",
            "expected_outputs": ["implementation_summary", "implementation_summary"],
            "runtime_artifacts": [
                {"artifact_type": "test_report"},
                {"artifact_type": "test_report"},
                {"artifact_type": "approved_summary"},
            ],
        }
    )
    assert summary["delivered_artifact_count"] == 3
    assert "Implementation Summary" in summary["delivered_artifact_labels"]
    assert "Test Report" in summary["delivered_artifact_labels"]


def test_client_safe_summary_has_no_governance_or_authority_leakage():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_client_view_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "reviewed",
                "decision_status": "approved",
                "release_status": "released",
                "execution_status": "succeeded",
                "expected_outputs": ["approved_summary"],
                "runtime_artifacts": [{"artifact_type": "test_report"}],
                "metadata": {
                    "authority_traces": {"delivery": {"actor": "nexus"}},
                    "governance_trace": {"origin": "phase87_test"},
                },
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase87_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 87 temp project"}
        try:
            result = build_client_view_snapshot(project_key)
            assert result["status"] == "ok"
            project = result["payload"]["project"]
            summary = project["delivery_summary"]
            assert summary["delivery_progress_state"] == "client_safe_packaging_ready"
            serialized = json.dumps(summary)
            assert "authority_trace" not in serialized
            assert "governance_trace" not in serialized
        finally:
            PROJECTS.pop(project_key, None)


def test_revenue_phase_79_to_83_flow_still_visible_in_preview():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_intake_preview

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase87_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 87 revenue regression"}
        try:
            preview = build_intake_preview(
                request_kind="lead_intake",
                project_key=project_key,
                objective="Revenue flow regression check.",
                project_context="Phase 87 must not break phases 79-83.",
                constraints_json=json.dumps(
                    {
                        "scope_boundaries": ["No side effects."],
                        "risk_notes": ["No execution triggers."],
                        "runtime_preferences": ["Governed only."],
                        "output_expectations": ["Keep intake and conversion previews working."],
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
                        "fit_notes": "",
                    }
                ),
            )
            payload = preview["payload"]
            assert payload["request_kind"] == "lead_intake"
            assert payload["qualification_summary"] is not None
            assert payload["offer_summary"] is not None
            assert payload["response_summary"] is not None
            assert payload["conversion_summary"] is not None
        finally:
            PROJECTS.pop(project_key, None)


def test_finance_and_routing_visibility_remain_in_operator_surfaces():
    from NEXUS.registry import PROJECTS
    from ops.forge_console_bridge import build_package_snapshot, build_project_snapshot

    with _local_test_dir() as tmp:
        package_id = _write_package(
            tmp,
            {
                "review_status": "reviewed",
                "decision_status": "approved",
                "release_status": "released",
                "execution_status": "succeeded",
                "expected_outputs": ["implementation_summary"],
                "routing_summary": {"model_lane": "balanced", "routing_policy_version": "phase86"},
                "cost_tracking": {
                    "cost_estimate": 0.125,
                    "cost_unit": "usd_estimated",
                    "cost_source": "model_execution",
                    "cost_breakdown": {"model": "forge_router", "estimated_tokens": 31000, "estimated_cost": 0.125},
                },
            },
        )
        _write_state(tmp, package_id)
        project_key = f"phase87_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 87 finance/routing regression"}
        try:
            project_snapshot = build_project_snapshot(project_key)
            package_snapshot = build_package_snapshot(package_id, project_key=project_key)
            assert project_snapshot["status"] == "ok"
            assert package_snapshot["status"] == "ok"
            assert project_snapshot["payload"]["cost_summary"]["cost_per_project"]["estimated_cost_total"] >= 0
            assert package_snapshot["payload"]["package_json"]["routing_summary"]["model_lane"] == "balanced"
            assert package_snapshot["payload"]["delivery_summary"]["delivered_artifact_count"] >= 1
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_delivery_summary_ready_when_suitable_output_exists,
        test_no_delivery_summary_when_no_suitable_output_exists,
        test_client_safe_packaging_ready_when_safe_for_surface,
        test_internal_review_required_when_output_not_yet_client_ready,
        test_artifact_count_and_labels_are_normalized,
        test_client_safe_summary_has_no_governance_or_authority_leakage,
        test_revenue_phase_79_to_83_flow_still_visible_in_preview,
        test_finance_and_routing_visibility_remain_in_operator_surfaces,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
