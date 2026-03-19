"""
Phase 20 bounded autonomy layer tests.

Run: python tests/phase20_autonomy_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure FORGE root is on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def test_stop_on_approval_required():
    """Prove _check_pre_step_gates stops when approval_required."""
    from NEXUS.bounded_autonomy_runner import _check_pre_step_gates, STOP_APPROVAL_REQUIRED

    # Gate order: recovery -> enforcement (approval) -> ... ; approval is checked before guardrails
    loaded = {
        "recovery_result": {"recovery_status": "retry_ready"},
        "enforcement_result": {"workflow_action": "await_approval", "enforcement_status": "approval_required"},
        "review_queue_entry": {},
    }
    proceed, stop_reason, approval_blocked, safety_blocked = _check_pre_step_gates(loaded, "jarvis")
    assert not proceed
    assert stop_reason == STOP_APPROVAL_REQUIRED
    assert approval_blocked is True
    assert safety_blocked is False


def test_stop_on_max_steps():
    """Prove run_bounded_autonomy stops at max_steps when gates pass."""
    from unittest.mock import patch
    from NEXUS.bounded_autonomy_runner import run_bounded_autonomy, STOP_MAX_STEPS_REACHED

    from NEXUS.registry import PROJECTS
    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return  # skip if no jarvis

    mock_result = {
        "autonomy_status": "ran",
        "autonomous_run_started": True,
        "autonomy_reason": "mocked",
    }
    permissive_state = {
        "load_error": None,
        "run_id": "test",
        "recovery_result": {"recovery_status": "retry_ready", "retry_permitted": True},
        "reexecution_result": {"run_permitted": True},
        "guardrail_result": {"launch_allowed": True},
        "enforcement_result": {"workflow_action": "continue", "enforcement_status": "passed"},
        "review_queue_entry": {"queue_status": "cleared"},
        "scheduler_result": {"next_cycle_permitted": True},
        "heartbeat_result": {"next_cycle_allowed": True},
        "resume_result": {"resume_status": "resumable"},
        "heartbeat_status": "continue_cycle",
        "project_lifecycle_status": "active",
        "project_lifecycle_result": {},
        "governance_status": "passed",
        "governance_result": {},
        "resume_status": "resumable",
        "autonomous_cycle_summary": {},
    }
    with patch("NEXUS.bounded_autonomy_runner.run_project_autonomy", return_value=mock_result):
        with patch("NEXUS.bounded_autonomy_runner.load_project_state", return_value=permissive_state):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                result = run_bounded_autonomy(project_path=path, project_name="jarvis", max_steps=1)
    assert result.get("stop_reason") == STOP_MAX_STEPS_REACHED, f"got stop_reason={result.get('stop_reason')}"
    assert result.get("reached_limit") is True
    assert result.get("steps_attempted") >= 1
    assert result.get("max_steps") == 1


def test_autonomy_summary_includes_execution_environment_posture():
    """Prove autonomy summary includes execution_environment_posture."""
    from NEXUS.autonomy_summary import build_autonomy_summary_safe, AUTONOMY_SUMMARY_KEYS

    exec_env = {
        "execution_environment_status": "available",
        "active_environments": ["local"],
        "planned_environments": [],
        "reason": "Test.",
    }
    summary = build_autonomy_summary_safe(execution_environment_summary=exec_env)
    assert "execution_environment_posture" in summary
    posture = summary["execution_environment_posture"]
    assert isinstance(posture, dict)
    assert posture.get("execution_environment_status") == "available"
    assert posture.get("active_environments") == ["local"]
    assert "reason" in posture
    for k in AUTONOMY_SUMMARY_KEYS:
        assert k in summary


def test_autonomy_summary_fallback_has_execution_environment_posture():
    """Prove error fallback has execution_environment_posture."""
    from NEXUS.autonomy_summary import build_autonomy_summary_safe

    # Force exception by passing invalid type
    summary = build_autonomy_summary_safe(n_recent=-999)
    # Actually -1 might not raise. Let's just verify the safe wrapper returns the fallback shape
    # by calling with exec_env that would make it succeed - we already tested that.
    # Test the fallback by provoking an error. We could pass a non-dict.
    try:
        build_autonomy_summary_safe(execution_environment_summary="not_a_dict")  # type: ignore
    except Exception:
        pass
    # The safe wrapper catches and returns fallback. So we need to trigger the except.
    # Simplest: mock build_autonomy_summary to raise
    from unittest.mock import patch
    with patch("NEXUS.autonomy_summary.build_autonomy_summary", side_effect=RuntimeError("test")):
        summary = build_autonomy_summary_safe()
    assert summary["autonomy_posture"] == "error_fallback"
    assert "execution_environment_posture" in summary
    assert summary["execution_environment_posture"]["execution_environment_status"] == "error_fallback"


if __name__ == "__main__":
    ok = 0
    ok += _run("test_stop_on_approval_required", test_stop_on_approval_required)
    ok += _run("test_stop_on_max_steps", test_stop_on_max_steps)
    ok += _run("test_autonomy_summary_includes_execution_environment_posture", test_autonomy_summary_includes_execution_environment_posture)
    ok += _run("test_autonomy_summary_fallback_has_execution_environment_posture", test_autonomy_summary_fallback_has_execution_environment_posture)
    print(f"\n{ok}/4 passed")
    sys.exit(0 if ok == 4 else 1)
