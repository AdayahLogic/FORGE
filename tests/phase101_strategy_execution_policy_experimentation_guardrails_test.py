"""
Phase 101 strategy execution policies + experimentation guardrails tests.

Run: python tests/phase101_strategy_execution_policy_experimentation_guardrails_test.py
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
    path = base / f"phase101_{uuid.uuid4().hex[:8]}"
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


def test_strategy_execution_policy_blocks_hard_governance_states():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase101proj",
            "project_path": "C:/phase101",
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert package["strategy_execution_policy_status"] == "blocked"
    assert package["strategy_execution_allowed"] is False
    assert package["strategy_experimentation_enabled"] is False
    assert package["strategy_experimentation_status"] == "disabled_policy_block"
    assert package["strategy_variant_guardrail_status"] == "hard_block"


def test_low_signal_policy_defers_and_keeps_conservative_guardrails():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase101proj",
            "project_path": "C:/phase101",
            "pipeline_stage": "intake",
            "conversion_probability": 0.2,
            "roi_estimate": 0.2,
            "metadata": {"revenue_recent_outcomes": []},
        }
    )
    assert package["strategy_execution_policy_status"] == "deferred"
    assert package["strategy_execution_allowed"] is False
    assert package["strategy_experimentation_enabled"] is False
    assert package["strategy_experimentation_status"] in {
        "disabled_low_maturity",
        "disabled_conservative_mode",
    }
    assert package["strategy_variant_type"] == "conservative_follow_up_variant"


def test_operator_gated_policy_enables_review_required_experimentation():
    from NEXUS.execution_package_registry import normalize_execution_package

    package = normalize_execution_package(
        {
            "project_name": "phase101proj",
            "project_path": "C:/phase101",
            "pipeline_stage": "qualified",
            "conversion_probability": 0.74,
            "roi_estimate": 0.8,
            "time_sensitivity": 0.75,
            "metadata": {
                "enforcement_status": "approval_required",
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "revenue_recent_outcomes": [
                    {"status": "closed_won"},
                    {"status": "closed_won"},
                    {"status": "closed_won"},
                    {"status": "closed_won"},
                    {"status": "closed_won"},
                    {"status": "closed_won"},
                ],
            },
        }
    )
    assert package["strategy_execution_policy_status"] == "allowed_with_review"
    assert package["strategy_execution_allowed"] is True
    assert package["strategy_execution_requires_operator_review"] is True
    assert package["strategy_experimentation_enabled"] is True
    assert package["strategy_experimentation_status"] == "enabled_review_required"
    assert package["strategy_variant_guardrail_status"] == "operator_review_required"
    assert package["strategy_variant_id"].startswith("var-")


def test_command_surface_exposes_policy_experimentation_and_comparison_fields():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase101",
                "project_name": "phase101proj",
                "project_path": str(tmp),
                "pipeline_stage": "proposal_pending",
                "conversion_probability": 0.76,
                "roi_estimate": 0.79,
                "time_sensitivity": 0.72,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "approval_required",
                    "revenue_recent_outcomes": [
                        {"status": "closed_won"},
                        {"status": "closed_won"},
                        {"status": "closed_won"},
                        {"status": "closed_won"},
                        {"status": "closed_won"},
                    ],
                },
            },
        )
        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        row = queue["payload"]["packages"][0]
        assert "strategy_execution_policy_status" in row
        assert "strategy_experimentation_status" in row
        assert "strategy_variant_type" in row
        assert "strategy_comparison_status" in row

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-phase101")
        assert details["status"] == "ok"
        review_header = details["payload"]["review_header"]
        assert "strategy_execution_policy_status" in review_header
        assert "strategy_experimentation_status" in review_header
        assert "strategy_variant_guardrail_status" in review_header
        assert "strategy_comparison_status" in review_header
        scope = (details["payload"]["sections"] or {}).get("scope") or {}
        assert "strategy_execution_policy" in scope
        assert "strategy_experimentation" in scope
        assert "strategy_comparison" in scope


def main():
    tests = [
        test_strategy_execution_policy_blocks_hard_governance_states,
        test_low_signal_policy_defers_and_keeps_conservative_guardrails,
        test_operator_gated_policy_enables_review_required_experimentation,
        test_command_surface_exposes_policy_experimentation_and_comparison_fields,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
