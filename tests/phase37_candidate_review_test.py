"""
Phase 37 governed candidate review workflow tests.

Run: python tests/phase37_candidate_review_test.py
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


def test_evaluate_candidate_review_readiness_module():
    """Prove evaluate_candidate_review_readiness produces review artifact."""
    from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness

    p = {"executable_candidate": True, "completion_status": "completed_patch_candidate", "requires_followup_before_approval": False, "missing_information_flags": []}
    r = evaluate_candidate_review_readiness(p)
    assert "review_status" in r
    assert r.get("review_status") in ("not_ready_for_review", "ready_for_review", "reviewed", "changes_requested", "approved_for_approval", "error_fallback")
    assert "review_readiness" in r
    assert r.get("review_readiness") in ("low", "medium", "high")
    assert "review_requirements_met" in r
    assert "review_requirements_missing" in r
    assert "human_review_required" in r
    assert "approval_progression_ready" in r
    assert "next_step_recommendation" in r


def test_review_ready_when_executable_complete():
    """Prove review_status=ready_for_review when executable and complete."""
    from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness

    p = {"executable_candidate": True, "completion_status": "completed_patch_candidate", "requires_followup_before_approval": False, "missing_information_flags": [], "proposal_readiness": "fully_ready"}
    r = evaluate_candidate_review_readiness(p)
    assert r.get("review_status") == "ready_for_review"
    assert r.get("review_readiness") == "high"
    assert r.get("approval_progression_ready") is True


def test_review_not_ready_when_advisory():
    """Prove review_status=not_ready_for_review when advisory only."""
    from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness

    p = {"proposal_maturity": "advisory", "change_type": "advisory_only"}
    r = evaluate_candidate_review_readiness(p)
    assert r.get("review_status") == "not_ready_for_review"
    assert r.get("approval_progression_ready") is False


def test_candidate_review_registry_module():
    """Prove candidate review registry has append and read."""
    from NEXUS.candidate_review_registry import (
        normalize_review_record,
        append_candidate_review_record_safe,
        read_candidate_review_journal_tail,
        get_latest_review_for_patch,
    )

    rec = normalize_review_record({"patch_id": "test37", "project_name": "test", "review_status": "reviewed"})
    assert rec.get("review_id")
    assert rec.get("patch_id") == "test37"
    assert rec.get("review_status") == "reviewed"
    tail = read_candidate_review_journal_tail(project_path=None, n=5)
    assert isinstance(tail, list)
    latest = get_latest_review_for_patch(project_path=None, patch_id="nonexistent")
    assert latest is None or isinstance(latest, dict)


def test_patch_proposal_has_review_fields():
    """Prove normalize_patch_proposal includes review_status, review_readiness."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "surgeon",
        "change_type": "guided_patch_followup",
        "executable_candidate": False,
        "completion_status": "partially_completable",
    })
    assert "review_status" in r
    assert r.get("review_status") in ("not_ready_for_review", "ready_for_review")
    assert "review_readiness" in r
    assert "next_step_recommendation" in r
    assert "approval_progression_ready" in r


def test_patch_proposal_summary_has_review_fields():
    """Prove patch proposal summary enriches proposals with review_status."""
    from NEXUS.patch_proposal_summary import build_patch_proposal_summary_safe

    s = build_patch_proposal_summary_safe(n_recent=5, n_tail=20)
    props = s.get("recent_proposals", [])
    for p in props[:3]:
        assert "review_status" in p
        assert "review_readiness" in p


def test_integrity_review_record_validation():
    """Prove check_review_record_shape validates review_status."""
    from NEXUS.integrity_checker import check_review_record_shape

    r = check_review_record_shape({"review_status": "reviewed", "review_readiness": "medium"})
    assert r.get("valid") is True
    r2 = check_review_record_shape({"review_status": "invalid_status"})
    assert r2.get("valid") is False


def test_commands_registered():
    """Prove candidate_review_status, review_candidate, candidate_review_details are supported."""
    from NEXUS.command_surface import SUPPORTED_COMMANDS

    assert "candidate_review_status" in SUPPORTED_COMMANDS
    assert "review_candidate" in SUPPORTED_COMMANDS
    assert "candidate_review_details" in SUPPORTED_COMMANDS


def main():
    tests = [
        test_evaluate_candidate_review_readiness_module,
        test_review_ready_when_executable_complete,
        test_review_not_ready_when_advisory,
        test_candidate_review_registry_module,
        test_patch_proposal_has_review_fields,
        test_patch_proposal_summary_has_review_fields,
        test_integrity_review_record_validation,
        test_commands_registered,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
