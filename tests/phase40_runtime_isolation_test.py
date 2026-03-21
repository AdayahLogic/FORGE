"""
Phase 40 runtime isolation and sandbox hardening tests.

Run: python tests/phase40_runtime_isolation_test.py
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


ISOLATION_POSTURE_KEYS = (
    "isolation_posture",
    "file_scope_status",
    "network_scope_status",
    "secret_scope_status",
    "connector_scope_status",
    "mutation_scope_status",
    "rollback_posture",
    "isolation_reason",
    "runtime_restrictions",
    "allowed_execution_domains",
    "blocked_execution_domains",
    "destructive_risk_posture",
    "generated_at",
)


def test_runtime_isolation_contract_shape():
    """Prove runtime isolation posture returns expected contract shape."""
    from NEXUS.runtime_isolation import build_runtime_isolation_posture_safe

    p = build_runtime_isolation_posture_safe()
    for k in ISOLATION_POSTURE_KEYS:
        assert k in p, f"Missing key: {k}"
    assert p["isolation_posture"] in ("weak", "bounded", "restricted", "isolated_planned", "error_fallback")
    assert isinstance(p["runtime_restrictions"], list)
    assert isinstance(p["allowed_execution_domains"], list)
    assert isinstance(p["blocked_execution_domains"], list)


def test_runtime_isolation_honest_weak_or_bounded():
    """Prove current active envs yield weak or bounded (no fake isolated)."""
    from NEXUS.runtime_isolation import build_runtime_isolation_posture_safe

    p = build_runtime_isolation_posture_safe(
        execution_environment_summary={"active_environments": ["local_current", "local_bounded"]}
    )
    assert p["isolation_posture"] in ("weak", "bounded")
    assert p["isolation_posture"] != "isolated_planned"


def test_runtime_isolation_fallback_shape():
    """Prove error fallback preserves contract shape."""
    from NEXUS.runtime_isolation import build_runtime_isolation_posture_safe, _fallback_isolation_posture
    from datetime import datetime

    f = _fallback_isolation_posture("Test error", datetime.now().isoformat())
    for k in ISOLATION_POSTURE_KEYS:
        assert k in f, f"Missing key in fallback: {k}"
    assert f["isolation_posture"] == "error_fallback"
    assert "Test error" in (f["isolation_reason"] or "")


def test_runtime_isolation_safe_never_raises():
    """Prove build_runtime_isolation_posture_safe never raises."""
    from NEXUS.runtime_isolation import build_runtime_isolation_posture_safe

    p = build_runtime_isolation_posture_safe(execution_environment_summary={"invalid": "data"})
    assert p["isolation_posture"] in ("weak", "bounded", "error_fallback")
    for k in ISOLATION_POSTURE_KEYS:
        assert k in p


def test_execution_environment_includes_isolation():
    """Prove execution environment summary includes runtime_isolation_posture."""
    from NEXUS.execution_environment_summary import build_execution_environment_summary_safe

    s = build_execution_environment_summary_safe()
    assert "runtime_isolation_posture" in s
    iso = s["runtime_isolation_posture"]
    assert isinstance(iso, dict)
    assert "isolation_posture" in iso


def test_release_readiness_includes_isolation_review():
    """Prove release readiness considers isolation posture."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"product_status": "ok"},
        "approval_summary": {"approval_status": "ok", "pending_count_total": 0},
        "patch_proposal_summary": {"patch_proposal_status": "ok", "pending_count": 0, "proposed_count": 0, "approved_pending_apply_count": 0, "approved_pending_apply_stale_count": 0},
        "execution_environment_summary": {
            "execution_environment_status": "available",
            "runtime_isolation_posture": {"isolation_posture": "weak"},
        },
        "autonomy_summary": {"autonomy_posture": "ok"},
        "helix_summary": {"helix_posture": "ok"},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert "runtime_isolation_posture" in r
    assert r["runtime_isolation_posture"]["isolation_posture"] == "weak"
    assert any("isolation" in (x or "").lower() or "weak" in (x or "").lower() for x in r.get("review_items", []))


def test_runtime_isolation_status_command():
    """Prove runtime_isolation_status command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("runtime_isolation_status")
    assert r["command"] == "runtime_isolation_status"
    payload = r.get("payload") or {}
    assert "isolation_posture" in payload
    assert "runtime_restrictions" in payload
    assert "file_scope_status" in payload


def test_sandbox_posture_command():
    """Prove sandbox_posture command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("sandbox_posture")
    assert r["command"] == "sandbox_posture"
    payload = r.get("payload") or {}
    assert "isolation_posture" in payload
    assert "isolation_reason" in payload


def test_integrity_check_runtime_isolation():
    """Prove integrity checker validates runtime isolation shape."""
    from NEXUS.integrity_checker import check_runtime_isolation_shape

    valid = {
        "isolation_posture": "bounded",
        "file_scope_status": "policy_bounded",
        "network_scope_status": "unrestricted",
        "secret_scope_status": "unknown",
        "connector_scope_status": "unknown",
        "mutation_scope_status": "policy_bounded",
        "rollback_posture": "none",
        "isolation_reason": "test",
        "runtime_restrictions": [],
        "allowed_execution_domains": [],
        "blocked_execution_domains": [],
        "destructive_risk_posture": "elevated",
        "generated_at": "2025-01-01T00:00:00",
    }
    r = check_runtime_isolation_shape(valid)
    assert r["valid"] is True
    r2 = check_runtime_isolation_shape({"isolation_posture": "invalid_value"})
    assert r2["valid"] is False


def test_operator_summary_includes_isolation():
    """Prove operator_release_summary includes isolation in operator_summary."""
    from NEXUS.release_readiness import build_operator_release_summary

    r = build_operator_release_summary()
    assert "operator_summary" in r
    assert "Isolation:" in r["operator_summary"] or "isolation" in r["operator_summary"].lower()


def main():
    tests = [
        test_runtime_isolation_contract_shape,
        test_runtime_isolation_honest_weak_or_bounded,
        test_runtime_isolation_fallback_shape,
        test_runtime_isolation_safe_never_raises,
        test_execution_environment_includes_isolation,
        test_release_readiness_includes_isolation_review,
        test_runtime_isolation_status_command,
        test_sandbox_posture_command,
        test_integrity_check_runtime_isolation,
        test_operator_summary_includes_isolation,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
