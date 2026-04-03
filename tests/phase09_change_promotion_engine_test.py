"""
Phase 09 change promotion engine + experimental rollout + comparative validation tests.

Run: python tests/phase09_change_promotion_engine_test.py
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
    path = base / f"phase09_{uuid.uuid4().hex[:8]}"
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


def _summary(
    *,
    effectiveness: float,
    conversion: float,
    revenue: float,
    execution_reliability: float,
    follow_up: float,
    actions: int = 40,
) -> dict:
    return {
        "strategy_performance_status": "ok",
        "strategy_effectiveness_score": effectiveness,
        "analysis_window": {"total_actions": actions, "project_count": 2},
        "metrics": {
            "conversion_rate": conversion,
            "revenue_outcome_score": revenue,
            "execution_reliability": execution_reliability,
            "follow_up_success_rate": follow_up,
        },
    }


def test_promotion_decision_logic_is_governed_and_confident():
    from NEXUS.strategy_promotion_engine import evaluate_change_promotion_decision

    baseline = _summary(effectiveness=58.0, conversion=0.41, revenue=0.43, execution_reliability=0.82, follow_up=0.44)
    candidate = _summary(effectiveness=79.0, conversion=0.67, revenue=0.71, execution_reliability=0.9, follow_up=0.66)
    result = evaluate_change_promotion_decision(
        baseline_summary=baseline,
        candidate_summary=candidate,
        baseline_version_id="strategy-v-baseline",
        candidate_version_id="strategy-v-candidate",
        risk_level="medium",
        approval_status="approved",
    )

    assert result["promotion_status"] == "ok"
    assert result["promotion_decision"] in {"promote_partial", "promote_full"}
    assert result["promotion_confidence"] >= 0.45
    assert result["governance"]["requires_approval"] is True


def test_experiment_setup_supports_shadow_and_controlled_rollout():
    from NEXUS.strategy_promotion_engine import start_strategy_experiment

    with _local_test_dir() as tmp:
        shadow = start_strategy_experiment(
            candidate_version_id="strategy-v-candidate",
            baseline_version_id="strategy-v-baseline",
            mode="shadow",
            strategy_store_dir=str(tmp),
        )
        controlled = start_strategy_experiment(
            candidate_version_id="strategy-v-candidate",
            baseline_version_id="strategy-v-baseline",
            mode="controlled_rollout",
            rollout_percentage=25,
            rollout_scope="per_action_type",
            strategy_store_dir=str(tmp),
        )

    assert shadow["mode"] == "shadow"
    assert shadow["decision_effective"] is False
    assert controlled["mode"] == "controlled_rollout"
    assert controlled["rollout_percentage"] == 25
    assert controlled["decision_effective"] is True


def test_comparative_validation_picks_winner_and_delta():
    from NEXUS.strategy_promotion_engine import run_comparative_validation

    baseline = _summary(effectiveness=60.0, conversion=0.44, revenue=0.45, execution_reliability=0.84, follow_up=0.48)
    candidate = _summary(effectiveness=74.0, conversion=0.6, revenue=0.65, execution_reliability=0.9, follow_up=0.59)
    with _local_test_dir() as tmp:
        result = run_comparative_validation(
            baseline_summary=baseline,
            candidate_summary=candidate,
            baseline_version_id="strategy-v-baseline",
            candidate_version_id="strategy-v-candidate",
            strategy_store_dir=str(tmp),
        )

    assert result["comparison_status"] == "ok"
    assert result["winner_strategy"] == "strategy-v-candidate"
    assert result["performance_delta"]["weighted_index_delta"] > 0
    assert result["statistical_confidence"] > 0
    assert result["validation_status"] == "candidate_wins"


def test_rollout_controller_follows_ramp_progression():
    from NEXUS.strategy_promotion_engine import update_rollout_controller

    with _local_test_dir() as tmp:
        first = update_rollout_controller(
            candidate_version_id="strategy-v-candidate",
            baseline_version_id="strategy-v-baseline",
            rollout_percentage=0,
            rollout_scope="per_project",
            validation_status="candidate_wins",
            strategy_store_dir=str(tmp),
        )
        second = update_rollout_controller(
            candidate_version_id="strategy-v-candidate",
            baseline_version_id="strategy-v-baseline",
            rollout_percentage=first["rollout_percentage"],
            rollout_scope="per_project",
            validation_status="candidate_wins",
            strategy_store_dir=str(tmp),
        )

    assert first["rollout_percentage"] == 10
    assert second["rollout_percentage"] == 25
    assert first["controller_status"] == "advancing"


def test_rollback_trigger_is_deterministic_and_marks_lifecycle():
    from NEXUS.strategy_promotion_engine import trigger_rollback
    from NEXUS.self_optimization_engine import read_strategy_lifecycle_registry_safe, update_strategy_lifecycle_safe

    with _local_test_dir() as tmp:
        update_strategy_lifecycle_safe(
            strategy_version_id="strategy-v-candidate",
            lifecycle_status="testing",
            reason="pre-rollback test setup",
            strategy_store_dir=str(tmp),
        )
        update_strategy_lifecycle_safe(
            strategy_version_id="strategy-v-baseline",
            lifecycle_status="active",
            reason="pre-rollback baseline setup",
            strategy_store_dir=str(tmp),
        )
        rollback = trigger_rollback(
            candidate_version_id="strategy-v-candidate",
            fallback_version_id="strategy-v-baseline",
            reason="Regression detected in controlled rollout.",
            degradation_detected=True,
            strategy_store_dir=str(tmp),
        )
        lifecycle = read_strategy_lifecycle_registry_safe(strategy_store_dir=str(tmp))
        versions = lifecycle.get("versions") or {}

    assert rollback["rollback_triggered"] is True
    assert rollback["deterministic"] is True
    assert versions["strategy-v-candidate"]["lifecycle_status"] == "failed"
    assert versions["strategy-v-baseline"]["lifecycle_status"] == "active"


def test_lifecycle_transitions_through_candidate_testing_active():
    from NEXUS.strategy_promotion_engine import run_strategy_promotion_cycle, set_active_strategy
    from NEXUS.self_optimization_engine import read_strategy_lifecycle_registry_safe

    baseline = _summary(effectiveness=58.0, conversion=0.4, revenue=0.41, execution_reliability=0.82, follow_up=0.45)
    candidate = _summary(effectiveness=77.0, conversion=0.66, revenue=0.69, execution_reliability=0.91, follow_up=0.67)
    with _local_test_dir() as tmp:
        cycle = run_strategy_promotion_cycle(
            candidate_version_id="strategy-v-candidate",
            baseline_version_id="strategy-v-baseline",
            candidate_summary=candidate,
            baseline_summary=baseline,
            risk_level="low",
            approval_status="approved",
            rollout_percentage=50,
            strategy_store_dir=str(tmp),
        )
        set_active_strategy(
            strategy_version_id="strategy-v-candidate",
            previous_strategy_version_id="strategy-v-baseline",
            activation_reason="Phase 09 lifecycle transition check.",
            strategy_store_dir=str(tmp),
        )
        lifecycle = read_strategy_lifecycle_registry_safe(strategy_store_dir=str(tmp))
        versions = lifecycle.get("versions") or {}

    assert cycle["strategy_promotion_status"] == "ok"
    assert versions["strategy-v-candidate"]["lifecycle_status"] == "active"
    assert versions["strategy-v-baseline"]["lifecycle_status"] in {"deprecated", "active"}


def test_command_surface_visibility_includes_phase09_commands():
    from NEXUS.command_surface import SUPPORTED_COMMANDS, run_command

    assert "strategy_promotion_status" in SUPPORTED_COMMANDS
    assert "strategy_experiments" in SUPPORTED_COMMANDS
    assert "strategy_comparison" in SUPPORTED_COMMANDS
    assert "rollout_status" in SUPPORTED_COMMANDS
    assert "rollback_history" in SUPPORTED_COMMANDS
    assert "active_strategy" in SUPPORTED_COMMANDS

    with patch("NEXUS.command_surface.PROJECTS", {}):
        promotion = run_command("strategy_promotion_status")
        experiments = run_command("strategy_experiments", n=5)
        comparisons = run_command("strategy_comparison", n=5)
        rollout = run_command("rollout_status")
        rollback = run_command("rollback_history", n=5)
        active = run_command("active_strategy")

    assert promotion["status"] == "ok"
    assert experiments["status"] == "ok"
    assert comparisons["status"] == "ok"
    assert rollout["status"] == "ok"
    assert rollback["status"] == "ok"
    assert active["status"] == "ok"


def main():
    tests = [
        test_promotion_decision_logic_is_governed_and_confident,
        test_experiment_setup_supports_shadow_and_controlled_rollout,
        test_comparative_validation_picks_winner_and_delta,
        test_rollout_controller_follows_ramp_progression,
        test_rollback_trigger_is_deterministic_and_marks_lifecycle,
        test_lifecycle_transitions_through_candidate_testing_active,
        test_command_surface_visibility_includes_phase09_commands,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
