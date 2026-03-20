"""
Phase 25 approval maturity and trace completion tests.

Run: python tests/phase25_approval_maturity_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def test_staleness_evaluation():
    """Prove staleness is derived from timestamp."""
    from datetime import datetime, timezone, timedelta
    from NEXUS.approval_staleness import evaluate_approval_staleness, evaluate_proposal_approval_staleness

    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=30)
    recent = now - timedelta(hours=1)
    approval_old = {"status": "approved", "decision_timestamp": old.isoformat()}
    approval_recent = {"status": "approved", "decision_timestamp": recent.isoformat()}
    is_stale_old, _ = evaluate_approval_staleness(approval_old, now=now, staleness_hours=24.0)
    is_stale_recent, _ = evaluate_approval_staleness(approval_recent, now=now, staleness_hours=24.0)
    assert is_stale_old is True
    assert is_stale_recent is False


def test_approval_summary_stale_count():
    """Prove approval summary includes stale_count."""
    from NEXUS.approval_summary import build_approval_summary_safe

    s = build_approval_summary_safe()
    assert "stale_count" in s
    assert "approved_pending_apply_count" in s


def test_patch_summary_stale_count():
    """Prove patch proposal summary includes approved_pending_apply_stale_count."""
    from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe

    s = build_patch_proposal_summary_safe()
    assert "approved_pending_apply_stale_count" in s


def test_retry_command():
    """Prove retry_patch_proposal returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("retry_patch_proposal", patch_id="nonexistent")
    assert r["command"] == "retry_patch_proposal"
    payload = r.get("payload") or {}
    assert "ready_for_apply" in payload
    assert "error" in payload or "patch_id" in payload


def test_approval_trace_command():
    """Prove approval_trace returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("approval_trace")
    assert r["command"] == "approval_trace"
    payload = r.get("payload") or {}
    assert "error" in payload or ("approval" in payload and "patch_proposal" in payload)


def test_surgeon_repair_metadata():
    """Prove Surgeon includes repair_metadata when repair recommended."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Regression failed"}
    inspector = {"validation_result": {"regression_reason": "test failure"}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result={})
    assert r.get("repair_recommended") is True
    assert r.get("repair_metadata") is not None
    assert r["repair_metadata"].get("has_patch_payload") is False
    assert r["repair_metadata"].get("repair_reason")


def test_is_proposal_approval_stale():
    """Prove is_proposal_approval_stale returns correct shape for approved_pending_apply."""
    from datetime import datetime, timezone, timedelta
    from NEXUS.approval_staleness import evaluate_proposal_approval_staleness

    old_res = {"new_status": "approved_pending_apply", "timestamp": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()}
    is_stale, hours = evaluate_proposal_approval_staleness(old_res, staleness_hours=24.0)
    assert is_stale is True
    assert hours > 24


def main():
    tests = [
        test_staleness_evaluation,
        test_approval_summary_stale_count,
        test_patch_summary_stale_count,
        test_retry_command,
        test_approval_trace_command,
        test_surgeon_repair_metadata,
        test_is_proposal_approval_stale,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
