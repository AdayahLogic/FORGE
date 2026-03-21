"""
Phase 39 approval lifecycle deepening tests.

Run: python tests/phase39_approval_lifecycle_test.py
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


def test_get_staleness_hours():
    """Prove get_staleness_hours returns type-specific or default."""
    from NEXUS.approval_staleness import get_staleness_hours, APPROVAL_STALENESS_HOURS

    assert get_staleness_hours("patch_proposal_resolution") == 24.0
    assert get_staleness_hours("unknown") == APPROVAL_STALENESS_HOURS
    assert get_staleness_hours(None) == APPROVAL_STALENESS_HOURS


def test_compute_expiry_metadata():
    """Prove compute_expiry_metadata returns expiry fields."""
    from NEXUS.approval_staleness import compute_expiry_metadata

    r = {"timestamp": "2020-01-01T00:00:00", "new_status": "approved_pending_apply"}
    m = compute_expiry_metadata(r, record_type="resolution")
    assert "expiry_timestamp" in m
    assert "expiry_status" in m
    assert m.get("expiry_status") in ("active", "stale", "unknown")
    assert "stale_after_hours" in m
    assert "requires_reapproval" in m


def test_evaluate_resolution_lifecycle():
    """Prove evaluate_resolution_lifecycle returns lifecycle artifact."""
    from NEXUS.approval_lifecycle import evaluate_resolution_lifecycle

    r = {"new_status": "approved_pending_apply", "timestamp": "2020-01-01T00:00:00"}
    lc = evaluate_resolution_lifecycle(r)
    assert "approval_lifecycle_status" in lc
    assert lc.get("approval_lifecycle_status") in ("active", "stale", "unknown")
    assert "reapproval_required" in lc
    assert "retry_after_expiry_ready" in lc
    assert "lifecycle_reason" in lc
    assert "lifecycle_next_step" in lc


def test_approval_summary_has_reapproval_count():
    """Prove approval summary includes reapproval_required_count."""
    from NEXUS.approval_summary import build_approval_summary_safe

    s = build_approval_summary_safe(n_recent=5, n_tail=20)
    assert "reapproval_required_count" in s
    assert isinstance(s.get("reapproval_required_count"), (int, float))


def test_normalize_approval_record_has_expiry():
    """Prove normalize_approval_record adds expiry fields when approved."""
    from NEXUS.approval_registry import normalize_approval_record
    from datetime import datetime

    r = {
        "status": "approved",
        "decision_timestamp": datetime.now().isoformat(),
        "approval_type": "patch_proposal_resolution",
    }
    n = normalize_approval_record(r)
    assert "expiry_timestamp" in n
    assert "expiry_status" in n
    assert "stale_after_hours" in n
    assert "requires_reapproval" in n


def test_commands_registered():
    """Prove Phase 39 commands are supported."""
    from NEXUS.command_surface import SUPPORTED_COMMANDS

    assert "approval_lifecycle_status" in SUPPORTED_COMMANDS
    assert "reapproval_status" in SUPPORTED_COMMANDS
    assert "retry_after_expiry_status" in SUPPORTED_COMMANDS


def test_release_readiness_reapproval_blocker():
    """Prove release readiness considers reapproval_required_count."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"product_status": "draft"},
        "approval_summary": {"reapproval_required_count": 2, "pending_count_total": 0},
        "patch_proposal_summary": {"recent_proposals": [], "pending_count": 0, "approved_pending_apply_stale_count": 0},
        "execution_environment_summary": {"execution_environment_status": "ok"},
        "autonomy_summary": {"autonomy_posture": "idle"},
        "helix_summary": {"helix_posture": "idle"},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert "blocked" in r.get("release_readiness_status", "") or "reapproval" in str(r.get("critical_blockers", [])).lower()


def main():
    tests = [
        test_get_staleness_hours,
        test_compute_expiry_metadata,
        test_evaluate_resolution_lifecycle,
        test_approval_summary_has_reapproval_count,
        test_normalize_approval_record_has_expiry,
        test_commands_registered,
        test_release_readiness_reapproval_blocker,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
