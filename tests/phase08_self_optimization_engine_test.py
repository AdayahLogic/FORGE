"""
Phase 08 self-optimization engine + strategy evolution + portfolio intelligence tests.

Run: python tests/phase08_self_optimization_engine_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase08_{uuid.uuid4().hex[:8]}"
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


def _observation_fixture() -> dict:
    return {
        "alpha": {
            "project_path": "C:/FORGE/projects/alpha",
            "packages": [
                {
                    "package_id": "a1",
                    "conversion_probability": 0.83,
                    "roi_estimate": 0.78,
                    "time_sensitivity": 0.81,
                    "execution_score": 0.79,
                    "highest_value_next_action_score": 0.84,
                    "linked_conversion_result": "converted",
                    "follow_up_status": "follow_up_not_needed",
                    "action_to_reply_rate": 0.52,
                    "execution_status": "completed",
                    "package_status": "completed",
                },
                {
                    "package_id": "a2",
                    "conversion_probability": 0.71,
                    "roi_estimate": 0.74,
                    "time_sensitivity": 0.69,
                    "execution_score": 0.75,
                    "highest_value_next_action_score": 0.76,
                    "linked_conversion_result": "won",
                    "follow_up_status": "follow_up_due",
                    "action_to_reply_rate": 0.41,
                    "execution_status": "completed",
                    "package_status": "completed",
                },
            ],
            "learning": [
                {"actual_outcome": "success", "tags": ["conversion_ready", "high_value"]},
                {"actual_outcome": "success", "tags": ["conversion_ready"]},
            ],
        },
        "beta": {
            "project_path": "C:/FORGE/projects/beta",
            "packages": [
                {
                    "package_id": "b1",
                    "conversion_probability": 0.22,
                    "roi_estimate": 0.31,
                    "time_sensitivity": 0.9,
                    "execution_score": 0.34,
                    "highest_value_next_action_score": 0.28,
                    "linked_conversion_result": "",
                    "follow_up_status": "follow_up_due",
                    "action_to_reply_rate": 0.1,
                    "execution_status": "failed",
                    "package_status": "pending",
                },
            ],
            "learning": [
                {"actual_outcome": "failed", "tags": ["overdue", "low_conversion"]},
                {"actual_outcome": "warning", "tags": ["follow_up_due"]},
            ],
        },
    }


def test_strategy_performance_analyzer_outputs_expected_metrics():
    from NEXUS.self_optimization_engine import analyze_strategy_performance_safe

    result = analyze_strategy_performance_safe(observations_by_project=_observation_fixture())
    assert result["strategy_performance_status"] == "ok"
    assert float(result["strategy_effectiveness_score"]) > 0.0
    assert result["metrics"]["conversion_rate"] > 0.0
    assert isinstance(result["success_patterns"], list)
    assert isinstance(result["failure_patterns"], list)
    assert result["analysis_window"]["project_count"] == 2


def test_dynamic_weight_adjustment_is_bounded_explainable_and_reversible():
    from NEXUS.self_optimization_engine import adjust_dynamic_weights_safe

    perf = {
        "strategy_effectiveness_score": 42.0,
        "metrics": {
            "conversion_rate": 0.22,
            "follow_up_success_rate": 0.25,
            "execution_reliability": 0.48,
            "mission_completion_rate": 0.4,
            "urgency_signal_average": 0.88,
        },
    }
    adjusted = adjust_dynamic_weights_safe(performance_summary=perf)
    assert adjusted["weight_adjustment_status"] == "ok"
    assert adjusted["bounded"] is True
    assert adjusted["reversible"] is True
    assert adjusted["reversal_target_version"]
    for _, value in adjusted["weights_proposed"].items():
        assert 0.0 <= float(value) <= 1.0
    assert isinstance(adjusted["explainability"], list)


def test_strategy_evolution_detects_underperforming_profile():
    from NEXUS.self_optimization_engine import evolve_strategy_safe

    perf = {
        "strategy_effectiveness_score": 39.0,
        "metrics": {
            "conversion_rate": 0.2,
            "follow_up_success_rate": 0.3,
            "execution_reliability": 0.45,
            "mission_completion_rate": 0.33,
            "urgency_signal_average": 0.86,
        },
    }
    evolution = evolve_strategy_safe(performance_summary=perf)
    assert evolution["strategy_evolution_status"] == "ok"
    assert evolution["evolution_mode"] == "replace_underperforming"
    assert evolution["guardrails"]["bounded"] is True
    assert len(evolution["proposed_changes"]) >= 1


def test_portfolio_intelligence_prioritizes_high_value_projects():
    from NEXUS.self_optimization_engine import build_portfolio_intelligence_safe

    portfolio = build_portfolio_intelligence_safe(observations_by_project=_observation_fixture())
    assert portfolio["portfolio_intelligence_status"] == "ok"
    assert portfolio["priority_project"] in {"alpha", "beta"}
    assert float(portfolio["portfolio_priority_score"]) >= 0.0
    assert isinstance(portfolio["resource_allocation_signals"], list)
    assert len(portfolio["project_performance"]) == 2
    assert portfolio["project_performance"][0]["project_id"] == "alpha"


def test_strategy_versioning_and_feedback_loop_are_stable():
    from NEXUS.self_optimization_engine import (
        get_latest_strategy_weights,
        list_strategy_versions,
        run_self_optimization_feedback_loop_safe,
    )

    with _local_test_dir() as tmp:
        before = get_latest_strategy_weights(strategy_store_dir=str(tmp))
        run1 = run_self_optimization_feedback_loop_safe(
            observations_by_project=_observation_fixture(),
            apply_changes=True,
            strategy_store_dir=str(tmp),
        )
        run2 = run_self_optimization_feedback_loop_safe(
            observations_by_project=_observation_fixture(),
            apply_changes=True,
            strategy_store_dir=str(tmp),
        )
        versions = list_strategy_versions(n=10, strategy_store_dir=str(tmp))
        after = get_latest_strategy_weights(strategy_store_dir=str(tmp))

    assert before["strategy_version_id"] == "strategy-v0-default"
    assert run1["optimization_status"] == "ok"
    assert run2["optimization_status"] == "ok"
    assert versions["strategy_version_count"] >= 2
    assert after["strategy_version_id"] != "strategy-v0-default"
    assert run2["loop"]["apply"]["applied"] is True


def test_command_surface_exposes_phase08_commands():
    from NEXUS.command_surface import SUPPORTED_COMMANDS, run_command

    assert "strategy_performance" in SUPPORTED_COMMANDS
    assert "strategy_evolution" in SUPPORTED_COMMANDS
    assert "strategy_versions" in SUPPORTED_COMMANDS
    assert "optimization_status" in SUPPORTED_COMMANDS
    assert "portfolio_status" in SUPPORTED_COMMANDS

    with patch("NEXUS.command_surface.PROJECTS", {}):
        perf = run_command("strategy_performance")
        evol = run_command("strategy_evolution")
        vers = run_command("strategy_versions", n=5)
        opt = run_command("optimization_status")
        port = run_command("portfolio_status")

    assert perf["status"] == "ok"
    assert evol["status"] == "ok"
    assert vers["status"] == "ok"
    assert opt["status"] == "ok"
    assert port["status"] == "ok"
    assert "portfolio_priority_score" in port["payload"]


def main():
    tests = [
        test_strategy_performance_analyzer_outputs_expected_metrics,
        test_dynamic_weight_adjustment_is_bounded_explainable_and_reversible,
        test_strategy_evolution_detects_underperforming_profile,
        test_portfolio_intelligence_prioritizes_high_value_projects,
        test_strategy_versioning_and_feedback_loop_are_stable,
        test_command_surface_exposes_phase08_commands,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
