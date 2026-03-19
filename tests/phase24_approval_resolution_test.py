"""
Phase 24 approval resolution and controlled apply tests.

Run: python tests/phase24_approval_resolution_test.py
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


def test_resolution_contract():
    """Prove resolution appends and effective status overrides base."""
    from NEXUS.patch_proposal_registry import (
        append_patch_proposal_safe,
        append_patch_proposal_resolution,
        get_proposal_effective_status,
        PATCH_STATUSES,
    )
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    pid = "test_res_" + __import__("uuid").uuid4().hex[:8]
    append_patch_proposal_safe(path, {
        "patch_id": pid,
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    es, res = get_proposal_effective_status(path, pid)
    assert es == "proposed"
    assert res is None
    append_patch_proposal_resolution(path, pid, "approve", "approved_pending_apply", "aid1", project_name="jarvis")
    es2, res2 = get_proposal_effective_status(path, pid)
    assert es2 == "approved_pending_apply"
    assert res2 is not None
    assert res2.get("decision") == "approve"


def test_resolve_patch_proposal():
    """Prove resolve_patch_proposal approves/rejects and creates approval record."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_safe, resolve_patch_proposal, get_proposal_effective_status
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    pid = "test_resolve_" + __import__("uuid").uuid4().hex[:8]
    append_patch_proposal_safe(path, {
        "patch_id": pid,
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    result = resolve_patch_proposal(path, pid, "reject", project_name="jarvis", reason="Test reject")
    assert result.get("resolved") is True
    assert result.get("effective_status") == "rejected"
    assert result.get("approval_id")
    es, _ = get_proposal_effective_status(path, pid)
    assert es == "rejected"


def test_approve_command():
    """Prove approve_patch_proposal command works."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_safe, find_proposal_and_project
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    pid = "test_approve_" + __import__("uuid").uuid4().hex[:8]
    append_patch_proposal_safe(path, {
        "patch_id": pid,
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    r = run_command("approve_patch_proposal", patch_id=pid)
    assert r["command"] == "approve_patch_proposal"
    payload = r.get("payload") or {}
    assert payload.get("resolved") is True
    assert payload.get("effective_status") == "approved_pending_apply"


def test_reject_command():
    """Prove reject_patch_proposal command works."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_safe
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    pid = "test_reject_" + __import__("uuid").uuid4().hex[:8]
    append_patch_proposal_safe(path, {
        "patch_id": pid,
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    r = run_command("reject_patch_proposal", patch_id=pid)
    assert r["command"] == "reject_patch_proposal"
    payload = r.get("payload") or {}
    assert payload.get("resolved") is True
    assert payload.get("effective_status") == "rejected"


def test_apply_requires_approved():
    """Prove apply_patch_proposal fails when not approved_pending_apply."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_safe
    from NEXUS.command_surface import run_command
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    pid = "test_apply_rej_" + __import__("uuid").uuid4().hex[:8]
    append_patch_proposal_safe(path, {
        "patch_id": pid,
        "project_name": "jarvis",
        "source": "manual",
        "status": "proposed",
        "summary": "Test",
        "target_files": [],
        "change_type": "advisory_only",
    })
    r = run_command("apply_patch_proposal", patch_id=pid)
    payload = r.get("payload") or {}
    assert payload.get("applied") is False
    assert payload.get("patch_applied") is False
    assert payload.get("effective_status") == "proposed"


def test_summary_effective_status():
    """Prove patch proposal summary uses effective status."""
    from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe

    s = build_patch_proposal_summary_safe()
    assert "proposed_count" in s
    assert "approved_pending_apply_count" in s
    assert "rejected_count" in s
    assert "applied_count" in s
    assert "status_counts" in s


def test_surgeon_repair_patch_proposal():
    """Prove Surgeon includes repair_patch_proposal when builder has patch_request."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Regression failed"}
    inspector = {}
    builder = {
        "implementation_plan": {
            "patch_request": {
                "target_relative_path": "src/foo.py",
                "search_text": "old",
                "replacement_text": "new",
                "replace_all": False,
            },
        },
    }
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    assert r.get("repair_recommended") is True
    assert r.get("repair_patch_proposal") is not None
    assert r["repair_patch_proposal"].get("target_relative_path") == "src/foo.py"


def main():
    tests = [
        test_resolution_contract,
        test_resolve_patch_proposal,
        test_approve_command,
        test_reject_command,
        test_apply_requires_approved,
        test_summary_effective_status,
        test_surgeon_repair_patch_proposal,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
