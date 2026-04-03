"""
Phase 11 production convergence integration tests.

Run: python tests/phase11_production_convergence_integration_test.py
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
def _local_test_dir(prefix: str):
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _registered_project(project_key: str, project_path: Path):
    from NEXUS.registry import PROJECTS

    key = str(project_key).strip().lower()
    PROJECTS[key] = {
        "name": key,
        "path": str(project_path),
        "description": "Phase 11 convergence integration fixture",
        "workspace_type": "internal",
        "agents": ["coder", "tester", "operator"],
    }
    try:
        yield key
    finally:
        PROJECTS.pop(key, None)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _seed_project_state(project_path: Path, project_name: str):
    from NEXUS.project_state import save_project_state

    queue = [
        {
            "id": "task-1",
            "type": "implementation_step",
            "payload": {"description": "Execute bounded mission and verify outcome."},
            "priority": 0,
            "status": "pending",
            "task": "Execute bounded mission and verify outcome.",
        }
    ]

    save_project_state(
        project_path=str(project_path),
        active_project=project_name,
        notes="phase11 convergence fixture",
        architect_plan={
            "objective": "Converge mission, execution truth, revenue follow-up, and strategic promotion loops.",
            "next_agent": "coder",
            "implementation_steps": [queue[0]["task"]],
        },
        task_queue=queue,
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
        agent_routing_summary={"runtime_node": "coder", "agent_name": "coder", "tool_name": "cursor_agent"},
        execution_bridge_report_path=None,
        execution_bridge_summary={
            "runtime_node": "coder",
            "selected_runtime_target": "local",
            "fallback_runtime_target": "local",
            "runtime_selection_status": "selected",
        },
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
        task_queue_snapshot=queue,
        run_id=f"run-{project_name}",
        dispatch_status="accepted",
        dispatch_result={
            "status": "accepted",
            "execution_status": "succeeded",
            "runtime": "local",
            "message": "Bounded execution accepted.",
        },
        execution_package_id="pkg-phase11",
        execution_package_path=str(project_path / "state" / "execution_packages" / "pkg-phase11.json"),
    )


def test_command_surface_completeness_phase11():
    from NEXUS.command_surface import SUPPORTED_COMMANDS

    expected = {
        "mission_packet",
        "execution_truth",
        "execution_verification",
        "revenue_follow_up",
        "outcome_verification",
        "strategy_performance",
        "strategy_evolution",
        "strategy_versions",
        "optimization_status",
        "self_optimization_cycle",
        "strategy_promotion_cycle",
        "strategy_promotion_status",
        "strategy_experiments",
        "strategy_comparison",
        "rollout_status",
        "rollback_history",
        "active_strategy",
        "autonomous_portfolio_tick",
        "autonomous_portfolio_loop",
        "portfolio_autonomy_kill_switch",
        "portfolio_status",
        "dashboard_summary",
    }
    missing = sorted(expected.difference(SUPPORTED_COMMANDS))
    assert not missing, f"Missing converged commands: {missing}"


def test_end_to_end_mission_execution_truth_verification():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir("phase11_a") as project_dir, _registered_project("phase11a", project_dir) as project_key:
        _seed_project_state(project_dir, project_key)
        assert write_execution_package_safe(
            str(project_dir),
            {
                "package_id": "pkg-phase11",
                "project_name": project_key,
                "project_path": str(project_dir),
                "execution_status": "succeeded",
                "package_status": "completed",
                "execution_receipt": {"artifacts_written_count": 1},
            },
        )

        mission = run_command("mission_packet", project_name=project_key)
        truth = run_command("execution_truth", project_name=project_key)
        verify = run_command("execution_verification", project_name=project_key, n=20)

        assert mission["status"] == "ok"
        assert truth["status"] == "ok"
        assert verify["status"] == "ok"
        assert truth["payload"]["execution_truth_status"] in {
            "simulated",
            "prepared",
            "queued_for_review",
            "approved_not_executed",
            "handed_off",
            "executed_unverified",
            "executed_verified",
            "failed",
            "blocked",
            "rolled_back",
        }
        assert int(verify["payload"]["verification_count"]) >= 1


def test_end_to_end_revenue_follow_up_outcome_flow():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir("phase11_b") as project_dir, _registered_project("phase11b", project_dir) as project_key:
        _seed_project_state(project_dir, project_key)
        assert write_execution_package_safe(
            str(project_dir),
            {
                "package_id": "pkg-revenue-1",
                "project_name": project_key,
                "project_path": str(project_dir),
                "lead_id": "lead-1",
                "deal_status": "open",
                "pipeline_stage": "proposal_pending",
                "follow_up_status": "pending",
                "conversation_last_updated_at": "2026-03-01T00:00:00+00:00",
            },
        )

        follow = run_command("revenue_follow_up", project_name=project_key, n=50)
        outcome = run_command("outcome_verification", project_name=project_key, n=50)

        assert follow["status"] == "ok"
        assert outcome["status"] == "ok"
        assert "follow_up" in follow["payload"]
        assert int(outcome["payload"]["outcome_count"]) >= 1


def test_end_to_end_strategy_promotion_autonomous_visibility():
    from NEXUS.command_surface import run_command

    perf = run_command("strategy_performance")
    evol = run_command("strategy_evolution")
    promotion = run_command(
        "strategy_promotion_cycle",
        candidate_version_id="strategy-v-candidate-phase11",
        baseline_version_id="strategy-v-baseline-phase11",
        approval_status="approved",
        rollout_percentage=25,
    )
    tick = run_command("autonomous_portfolio_tick", execute_actions=False, parallel_capacity=2)
    portfolio = run_command("portfolio_status")

    assert perf["status"] == "ok"
    assert evol["status"] == "ok"
    assert promotion["status"] == "ok"
    assert tick["status"] == "ok"
    assert portfolio["status"] == "ok"
    assert "portfolio_status" in portfolio["payload"]


def test_state_contract_dashboard_runtime_consistency():
    from NEXUS.command_surface import run_command
    from NEXUS.project_state import load_project_state

    with _local_test_dir("phase11_c") as project_dir, _registered_project("phase11c", project_dir) as project_key:
        _seed_project_state(project_dir, project_key)
        run_command("mission_packet", project_name=project_key)
        run_command("execution_truth", project_name=project_key)
        run_command("execution_verification", project_name=project_key)
        run_command("revenue_follow_up", project_name=project_key)
        run_command("outcome_verification", project_name=project_key)
        run_command("self_optimization_cycle", project_name=project_key, apply_changes=False)
        run_command(
            "strategy_promotion_cycle",
            project_name=project_key,
            candidate_version_id="strategy-v-candidate-phase11c",
            baseline_version_id="strategy-v-baseline-phase11c",
            approval_status="approved",
        )
        run_command("autonomous_portfolio_tick", project_name=project_key, execute_actions=False)

        state = load_project_state(str(project_dir))
        required_keys = [
            "mission_status",
            "mission_packet",
            "execution_truth_status",
            "execution_truth_snapshot",
            "execution_verification_summary",
            "revenue_follow_up_status",
            "revenue_follow_up_summary",
            "outcome_verification_status",
            "outcome_verification_summary",
            "self_optimization_status",
            "self_optimization_result",
            "strategy_promotion_status",
            "strategy_promotion_result",
            "autonomous_portfolio_status",
            "autonomous_portfolio_result",
        ]
        missing = [key for key in required_keys if key not in state]
        assert not missing, f"State contract drift: missing keys {missing}"

        dashboard = run_command("dashboard_summary")
        assert dashboard["status"] == "ok"
        phase_summary = dashboard["payload"].get("phase_convergence_summary") or {}
        assert "self_optimization_status_count" in phase_summary
        assert "strategy_promotion_status_count" in phase_summary
        assert "autonomous_portfolio_status_count" in phase_summary


def test_no_stale_unreachable_advanced_systems():
    from NEXUS.command_surface import run_command

    checks = [
        run_command("strategy_versions", n=5),
        run_command("strategy_promotion_status"),
        run_command("strategy_experiments", n=5),
        run_command("strategy_comparison", n=5),
        run_command("rollout_status"),
        run_command("rollback_history", n=5),
        run_command("active_strategy"),
        run_command("portfolio_autonomy_kill_switch"),
    ]
    for result in checks:
        assert result["status"] == "ok", result
        assert "Unknown command" not in str(result.get("summary") or "")


def main():
    tests = [
        test_command_surface_completeness_phase11,
        test_end_to_end_mission_execution_truth_verification,
        test_end_to_end_revenue_follow_up_outcome_flow,
        test_end_to_end_strategy_promotion_autonomous_visibility,
        test_state_contract_dashboard_runtime_consistency,
        test_no_stale_unreachable_advanced_systems,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

