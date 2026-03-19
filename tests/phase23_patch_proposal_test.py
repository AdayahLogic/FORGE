"""
Phase 23 patch proposal pathway tests.

Run: python tests/phase23_patch_proposal_test.py
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


def test_patch_proposal_contract():
    """Prove patch proposal has required contract fields."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "project_name": "jarvis",
        "source": "helix_builder",
        "status": "proposed",
        "summary": "Test patch",
        "target_files": ["src/foo.py"],
        "change_type": "diff_patch",
        "patch_payload": {"target_relative_path": "src/foo.py", "search_text": "x", "replacement_text": "y"},
    })
    assert "patch_id" in r
    assert r["source"] == "helix_builder"
    assert r["status"] == "proposed"
    assert r["change_type"] == "diff_patch"
    assert "approval_id_refs" in r
    assert "helix_id_refs" in r
    assert r["approval_id_refs"] == []
    assert r["requires_approval"] is True


def test_patch_proposal_refs_default():
    """Prove refs default to empty lists."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({})
    assert r["approval_id_refs"] == []
    assert r["product_id_refs"] == []
    assert r["autonomy_id_refs"] == []
    assert r["helix_id_refs"] == []


def test_patch_proposal_append_safe():
    """Prove append never raises."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_safe
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    result = append_patch_proposal_safe(project_path=path, record={
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    assert result is None or isinstance(result, str)


def test_patch_proposal_summary_shape():
    """Prove patch proposal summary has required keys."""
    from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe

    s = build_patch_proposal_summary_safe()
    for k in ("patch_proposal_status", "pending_count", "applied_count", "by_project", "recent_proposals", "reason"):
        assert k in s


def test_patch_proposals_command():
    """Prove patch_proposals command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("patch_proposals")
    assert r["command"] == "patch_proposals"
    payload = r.get("payload") or {}
    assert "patch_proposal_status" in payload
    assert "pending_count" in payload
    assert "recent_proposals" in payload


def test_patch_proposal_details_command():
    """Prove patch_proposal_details command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("patch_proposal_details")
    assert r["command"] == "patch_proposal_details"
    payload = r.get("payload") or {}
    assert "recent_proposals" in payload or "patch_proposal" in payload or "patch_proposal_summary" in payload


def test_integrity_checker_patch_proposal():
    """Prove integrity checker includes patch proposal summary."""
    from NEXUS.integrity_checker import run_integrity_check_safe, check_patch_proposal_summary_shape

    r = run_integrity_check_safe()
    checks = r.get("checks") or []
    types = [c.get("payload_type") for c in checks]
    assert "patch_proposal_summary" in types

    valid = {
        "patch_proposal_status": "clear",
        "pending_count": 0,
        "proposed_count": 0,
        "approval_required_count": 0,
        "approved_pending_apply_count": 0,
        "rejected_count": 0,
        "blocked_count": 0,
        "applied_count": 0,
        "approval_blocked_count": 0,
        "status_counts": {},
        "by_project": {},
        "recent_proposals": [],
        "by_risk_level": {},
        "reason": "ok",
    }
    cr = check_patch_proposal_summary_shape(valid)
    assert cr["valid"] is True


def main():
    tests = [
        test_patch_proposal_contract,
        test_patch_proposal_refs_default,
        test_patch_proposal_append_safe,
        test_patch_proposal_summary_shape,
        test_patch_proposals_command,
        test_patch_proposal_details_command,
        test_integrity_checker_patch_proposal,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
