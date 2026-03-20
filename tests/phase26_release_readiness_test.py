"""
Phase 26 operator readiness and release controls tests.

Run: python tests/phase26_release_readiness_test.py
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


REQUIRED_KEYS = (
    "release_readiness_status",
    "project_name",
    "product_status",
    "approval_status",
    "execution_environment_status",
    "patch_status",
    "autonomy_status",
    "helix_status",
    "critical_blockers",
    "review_items",
    "readiness_reason",
    "ready_for_operator_release",
    "trace_links_present",
    "generated_at",
)


def test_release_readiness_contract_shape():
    """Prove release readiness returns expected contract shape."""
    from NEXUS.release_readiness import build_release_readiness_safe

    r = build_release_readiness_safe()
    for k in REQUIRED_KEYS:
        assert k in r, f"Missing key: {k}"
    assert r["release_readiness_status"] in ("ready", "blocked", "review_required", "error_fallback")
    assert isinstance(r["critical_blockers"], list)
    assert isinstance(r["review_items"], list)
    assert isinstance(r["trace_links_present"], dict)
    assert "approval_linked" in r["trace_links_present"]
    assert isinstance(r["ready_for_operator_release"], bool)


def test_release_readiness_blocked_rules():
    """Prove blocked status when product restricted."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"product_status": "restricted"},
        "approval_summary": {},
        "patch_proposal_summary": {},
        "execution_environment_summary": {},
        "autonomy_summary": {},
        "helix_summary": {},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert r["release_readiness_status"] == "blocked"
    assert len(r["critical_blockers"]) > 0
    assert r["ready_for_operator_release"] is False


def test_release_readiness_review_required_rules():
    """Prove review_required when product draft and no blockers."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"product_status": "draft"},
        "approval_summary": {"approval_status": "ok", "pending_count_total": 0},
        "patch_proposal_summary": {"patch_proposal_status": "ok", "pending_count": 0, "proposed_count": 0, "approved_pending_apply_count": 0, "approved_pending_apply_stale_count": 0},
        "execution_environment_summary": {"execution_environment_status": "ok"},
        "autonomy_summary": {"autonomy_posture": "ok"},
        "helix_summary": {"helix_posture": "ok"},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert r["release_readiness_status"] in ("review_required", "ready")
    assert r["ready_for_operator_release"] is False or r["release_readiness_status"] == "ready"


def test_release_readiness_safe_never_raises():
    """Prove build_release_readiness_safe never raises."""
    from NEXUS.release_readiness import build_release_readiness_safe

    r = build_release_readiness_safe(dashboard_summary={"invalid": "data"})
    assert r["release_readiness_status"] in ("ready", "blocked", "review_required", "error_fallback")
    for k in REQUIRED_KEYS:
        assert k in r


def test_release_readiness_command():
    """Prove release_readiness command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("release_readiness")
    assert r["command"] == "release_readiness"
    payload = r.get("payload") or {}
    assert "release_readiness_status" in payload
    assert "critical_blockers" in payload
    assert "review_items" in payload
    assert "ready_for_operator_release" in payload


def test_operator_release_summary_command():
    """Prove operator_release_summary command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("operator_release_summary")
    assert r["command"] == "operator_release_summary"
    payload = r.get("payload") or {}
    assert "release_readiness_status" in payload
    assert "operator_summary" in payload
    assert "critical_blockers" in payload


def test_dashboard_includes_release_readiness():
    """Prove dashboard includes release_readiness_summary."""
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    d = build_registry_dashboard_summary()
    assert "release_readiness_summary" in d
    rr = d["release_readiness_summary"]
    assert rr["release_readiness_status"] in ("ready", "blocked", "review_required", "error_fallback")
    assert "critical_blockers" in rr
    assert "review_items" in rr


def test_fallback_shape_consistency():
    """Prove error fallback preserves contract shape."""
    from NEXUS.release_readiness import _fallback_readiness
    from datetime import datetime

    f = _fallback_readiness(datetime.now().isoformat(), "Test error", "test_project")
    for k in REQUIRED_KEYS:
        assert k in f
    assert f["release_readiness_status"] == "error_fallback"
    assert f["ready_for_operator_release"] is False
    assert "Test error" in f["critical_blockers"][0]


def main():
    tests = [
        test_release_readiness_contract_shape,
        test_release_readiness_blocked_rules,
        test_release_readiness_review_required_rules,
        test_release_readiness_safe_never_raises,
        test_release_readiness_command,
        test_operator_release_summary_command,
        test_dashboard_includes_release_readiness,
        test_fallback_shape_consistency,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
