"""
Phase 80 revenue lead qualification preview tests.

Run: python tests/phase80_revenue_lead_qualification_test.py
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
    path = base / f"phase80_{uuid.uuid4().hex[:8]}"
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


def _write_state(project_path: Path):
    from NEXUS.project_state import save_project_state

    save_project_state(
        project_path=str(project_path),
        active_project="phase80proj",
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
        run_id="run-phase80",
    )


def _preview_for(project_key: str, qualification: dict[str, str]):
    from ops.forge_console_bridge import build_intake_preview

    return build_intake_preview(
        request_kind="lead_intake",
        project_key=project_key,
        objective="Qualify this inbound lead before pursuing a formal offer.",
        project_context="Revenue intake preview for a custom build engagement.",
        constraints_json=json.dumps(
            {
                "scope_boundaries": ["Do not generate offers in this phase."],
                "risk_notes": ["Keep qualification preview-only and auditable."],
                "runtime_preferences": ["No frontend routing authority."],
                "output_expectations": ["Return explicit qualification summary fields."],
                "review_expectations": ["Qualification reasoning must be human-readable."],
            }
        ),
        requested_artifacts_json=json.dumps(
            {
                "selected": ["implementation_plan"],
                "custom": [],
            }
        ),
        linked_attachment_ids_json=json.dumps([]),
        autonomy_mode="supervised_build",
        qualification_json=json.dumps(qualification),
    )


def test_qualified_lead_preview():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase80_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 80 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "medium",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "Strong domain alignment.",
                },
            )
            assert preview["status"] == "ok"
            payload = preview["payload"]
            summary = payload["qualification_summary"]
            assert summary["qualification_status"] == "qualified"
            assert summary["missing_qualification_fields"] == []
            assert payload["package_preview"]["package_creation_allowed"] is False
        finally:
            PROJECTS.pop(project_key, None)


def test_underqualified_lead_preview():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase80_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 80 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "none",
                    "urgency": "low",
                    "problem_clarity": "unclear",
                    "decision_readiness": "exploring",
                    "fit_notes": "",
                },
            )
            payload = preview["payload"]
            summary = payload["qualification_summary"]
            assert summary["qualification_status"] == "underqualified"
            assert summary["lead_readiness_level"] == "low"
        finally:
            PROJECTS.pop(project_key, None)


def test_needs_more_info_when_qualification_incomplete():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase80_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 80 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "",
                    "problem_clarity": "partial",
                    "decision_readiness": "",
                    "fit_notes": "",
                },
            )
            payload = preview["payload"]
            summary = payload["qualification_summary"]
            assert summary["qualification_status"] == "needs_more_info"
            assert "urgency" in summary["missing_qualification_fields"]
            assert "decision_readiness" in summary["missing_qualification_fields"]
        finally:
            PROJECTS.pop(project_key, None)


def test_high_priority_when_urgency_and_readiness_strong():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        project_key = f"phase80_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 80 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "high",
                    "urgency": "critical",
                    "problem_clarity": "very_clear",
                    "decision_readiness": "committed",
                    "fit_notes": "Executive sponsor already identified.",
                },
            )
            payload = preview["payload"]
            summary = payload["qualification_summary"]
            assert summary["qualification_status"] == "high_priority"
            assert summary["lead_readiness_level"] == "expedite"
        finally:
            PROJECTS.pop(project_key, None)


def test_preview_only_no_package_or_execution_side_effects():
    from NEXUS.registry import PROJECTS

    with _local_test_dir() as tmp:
        _write_state(tmp)
        state_path = tmp / "state" / "project_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        project_key = f"phase80_{uuid.uuid4().hex[:8]}"
        PROJECTS[project_key] = {"name": project_key, "path": str(tmp), "description": "Phase 80 temp project"}
        try:
            preview = _preview_for(
                project_key,
                {
                    "budget_band": "medium",
                    "urgency": "high",
                    "problem_clarity": "clear",
                    "decision_readiness": "ready",
                    "fit_notes": "",
                },
            )
            payload = preview["payload"]
            after = json.loads(state_path.read_text(encoding="utf-8"))
            assert payload["package_preview"]["creation_mode"] in {"preview_only", "lead_preview_only"}
            assert payload["package_preview"]["package_creation_allowed"] is False
            assert payload["package_preview"]["routing_authority"] == "NEXUS"
            assert payload["package_preview"]["execution_authority"] == "package_governance_only"
            assert (after.get("execution_package_id") or "") == (before.get("execution_package_id") or "")
            assert (after.get("execution_package_path") or "") == (before.get("execution_package_path") or "")
            assert (after.get("runtime_execution_status") or "") == (before.get("runtime_execution_status") or "")
        finally:
            PROJECTS.pop(project_key, None)


def main():
    tests = [
        test_qualified_lead_preview,
        test_underqualified_lead_preview,
        test_needs_more_info_when_qualification_incomplete,
        test_high_priority_when_urgency_and_readiness_strong,
        test_preview_only_no_package_or_execution_side_effects,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
