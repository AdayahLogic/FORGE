"""
Phase 102 outcome-aware strategy evaluation and safe promotion tests.

Run: python tests/phase102_outcome_aware_strategy_evaluation_policy_promotion_test.py
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
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase102_{uuid.uuid4().hex[:8]}"
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


def _won() -> dict:
    return {"status": "closed_won", "reason": "positive conversion"}


def _lost() -> dict:
    return {"status": "closed_lost", "reason": "negative conversion"}


def test_strategy_stays_experimental_with_low_data():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase102proj",
            "project_path": "C:/phase102",
            "metadata": {
                "revenue_recent_outcomes": [_won(), _lost(), _won()],
            },
        }
    )
    assert package["strategy_outcome_count"] == 3
    assert package["strategy_state"] == "experimental"
    assert package["strategy_promotion_candidate"] is False
    assert package["strategy_demotion_candidate"] is False


def test_strategy_becomes_recommended_and_promotion_candidate_with_consistent_success():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase102proj",
            "project_path": "C:/phase102",
            "pipeline_stage": "qualified",
            "conversion_probability": 0.83,
            "roi_estimate": 0.81,
            "time_sensitivity": 0.69,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
                "revenue_recent_outcomes": [_won(), _won(), _won(), _won(), _won(), _won(), _won(), _won()],
            },
        }
    )
    assert package["strategy_outcome_count"] >= 8
    assert package["strategy_success_count"] >= 8
    assert package["strategy_state"] == "recommended"
    assert package["strategy_promotion_candidate"] is True
    assert package["strategy_policy_recommendation"] == "promote_to_recommended_policy"
    assert package["strategy_execution_policy_status"] in {"allowed", "allowed_with_review"}


def test_strategy_demotion_restricts_policy_without_overriding_governance_blocks():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase102proj",
            "project_path": "C:/phase102",
            "pipeline_stage": "qualified",
            "conversion_probability": 0.21,
            "roi_estimate": 0.24,
            "time_sensitivity": 0.48,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
                "revenue_recent_outcomes": [_lost(), _lost(), _lost(), _lost(), _lost(), _lost(), _lost()],
            },
        }
    )
    assert package["strategy_state"] == "deprecated"
    assert package["strategy_demotion_candidate"] is True
    assert package["strategy_policy_recommendation"] == "restrict_to_conservative_policy"
    assert package["strategy_execution_policy_status"] == "deferred"
    assert package["strategy_execution_allowed"] is False
    assert package["strategy_experimentation_enabled"] is False


def test_command_surface_exposes_state_and_promotion_demotion_signals():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase102",
                "project_name": "phase102proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "conversion_probability": 0.78,
                "roi_estimate": 0.75,
                "time_sensitivity": 0.71,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "approval_required",
                    "revenue_recent_outcomes": [_won(), _won(), _won(), _won(), _won(), _won(), _won(), _won()],
                },
            },
        )
        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        row = queue["payload"]["packages"][0]
        assert "strategy_state" in row
        assert "strategy_policy_recommendation" in row
        assert "strategy_promotion_candidate" in row
        assert "strategy_demotion_candidate" in row

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-phase102")
        assert details["status"] == "ok"
        review_header = details["payload"]["review_header"]
        assert "strategy_outcome_count" in review_header
        assert "strategy_state" in review_header
        assert "strategy_promotion_candidate" in review_header
        assert "strategy_demotion_candidate" in review_header
        scope = (details["payload"]["sections"] or {}).get("scope") or {}
        assert "strategy_outcomes" in scope
        assert "strategy_state" in scope


def main():
    tests = [
        test_strategy_stays_experimental_with_low_data,
        test_strategy_becomes_recommended_and_promotion_candidate_with_consistent_success,
        test_strategy_demotion_restricts_policy_without_overriding_governance_blocks,
        test_command_surface_exposes_state_and_promotion_demotion_signals,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
