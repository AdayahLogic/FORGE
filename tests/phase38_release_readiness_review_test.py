"""
Phase 38 release readiness review integration tests.

Run: python tests/phase38_release_readiness_review_test.py
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


def test_release_readiness_has_review_fields():
    """Prove release readiness includes Phase 38 review fields."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"product_status": "draft"},
        "approval_summary": {"approval_status": "clear", "pending_count_total": 0},
        "patch_proposal_summary": {"recent_proposals": [], "pending_count": 0},
        "execution_environment_summary": {"execution_environment_status": "ok"},
        "autonomy_summary": {"autonomy_posture": "idle"},
        "helix_summary": {"helix_posture": "idle"},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert "review_status_summary" in r
    assert "review_blocker_count" in r
    assert "review_required_count" in r
    assert "changes_requested_count" in r
    assert "approved_for_approval_count" in r
    assert "candidates_pending_review" in r
    assert "candidates_not_ready_for_review" in r
    assert "review_linkage_present" in r
    assert "review_reasoning" in r
    assert "trace_links_present" in r
    assert "review_linked" in r.get("trace_links_present", {})


def test_review_awareness_summary_helper():
    """Prove _build_review_awareness_summary returns expected shape."""
    from NEXUS.release_readiness import _build_review_awareness_summary

    r = _build_review_awareness_summary({"recent_proposals": []})
    assert "review_blocker_count" in r
    assert "review_required_count" in r
    assert "changes_requested_count" in r
    assert "approved_for_approval_count" in r
    assert "candidates_pending_review" in r
    assert "review_status_summary" in r
    assert "review_linkage_present" in r


def test_operator_release_summary_has_review():
    """Prove operator_release_summary includes operator_review_summary."""
    from NEXUS.release_readiness import build_operator_release_summary

    minimal = {
        "product_summary": {"product_status": "draft"},
        "approval_summary": {"approval_status": "clear", "pending_count_total": 0},
        "patch_proposal_summary": {"recent_proposals": [], "pending_count": 0},
        "execution_environment_summary": {"execution_environment_status": "ok"},
        "autonomy_summary": {"autonomy_posture": "idle"},
        "helix_summary": {"helix_posture": "idle"},
    }
    r = build_operator_release_summary(dashboard_summary=minimal)
    assert "operator_summary" in r
    assert "operator_review_summary" in r
    assert "Review" in r.get("operator_summary", "")
    assert "approval" in r.get("operator_review_summary", "").lower()


def test_fallback_has_review_fields():
    """Prove fallback readiness includes Phase 38 fields."""
    from NEXUS.release_readiness import _fallback_readiness

    r = _fallback_readiness("2025-01-01", "test", None)
    assert "review_status_summary" in r
    assert r.get("review_blocker_count") == 0
    assert "review_linked" in r.get("trace_links_present", {})


def test_integrity_release_readiness_check():
    """Prove check_release_readiness_shape validates release readiness."""
    from NEXUS.integrity_checker import check_release_readiness_shape

    r = check_release_readiness_shape({
        "release_readiness_status": "ready",
        "critical_blockers": [],
        "review_items": [],
        "trace_links_present": {},
        "review_status_summary": "",
        "review_blocker_count": 0,
        "review_required_count": 0,
        "review_linkage_present": False,
    })
    assert r.get("valid") is True


def test_review_and_approval_distinct():
    """Prove operator_review_summary states review != approval."""
    from NEXUS.release_readiness import build_operator_release_summary

    minimal = {
        "product_summary": {"product_status": "draft"},
        "approval_summary": {"approval_status": "clear"},
        "patch_proposal_summary": {"recent_proposals": []},
        "execution_environment_summary": {"execution_environment_status": "ok"},
        "autonomy_summary": {"autonomy_posture": "idle"},
        "helix_summary": {"helix_posture": "idle"},
    }
    r = build_operator_release_summary(dashboard_summary=minimal)
    summary = r.get("operator_review_summary", "")
    assert "approval" in summary.lower()
    assert "Review" in summary or "review" in summary


def main():
    tests = [
        test_release_readiness_has_review_fields,
        test_review_awareness_summary_helper,
        test_operator_release_summary_has_review,
        test_fallback_has_review_fields,
        test_integrity_release_readiness_check,
        test_review_and_approval_distinct,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
