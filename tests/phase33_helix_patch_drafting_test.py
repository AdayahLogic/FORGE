"""
Phase 33 HELIX patch drafting upgrade tests.

Run: python tests/phase33_helix_patch_drafting_test.py
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


def test_surgeon_has_patch_draftability_fields():
    """Prove surgeon repair_metadata includes patch_draftability contract fields."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Reg", "critique_evaluation": {"hidden_failure_points": ["X"], "testing_gaps": ["Y"]}}
    inspector = {"repair_recommended": True, "repair_reason": "Fail", "validation_result": {"regression_reason": "Error in src/foo.py"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert "patch_draftability" in meta
    assert meta.get("patch_draftability") in ("low", "medium", "high")
    assert "draftability_reason" in meta
    assert "draftability_requirements_met" in meta
    assert "draftability_requirements_missing" in meta
    assert "candidate_patch_strategy" in meta
    assert meta.get("candidate_patch_strategy") in ("direct_diff", "guided_patch_followup", "advisory_only")
    assert "candidate_target_files" in meta
    assert "candidate_search_anchors" in meta
    assert "candidate_replacement_intent" in meta
    assert "human_validation_required" in meta


def test_surgeon_high_draftability_when_has_patch():
    """Prove surgeon has patch_draftability=high and direct_diff when builder has patch."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {"patch_request": {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("patch_draftability") == "high"
    assert meta.get("candidate_patch_strategy") == "direct_diff"
    assert "target_file" in (meta.get("draftability_requirements_met") or []) or "search_text" in (meta.get("draftability_requirements_met") or [])


def test_surgeon_medium_draftability_when_followup_candidate():
    """Prove surgeon has patch_draftability=medium and guided_patch_followup when has target + causes."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Regression", "critique_evaluation": {"hidden_failure_points": ["Edge case"], "testing_gaps": ["Unit tests"]}}
    inspector = {"repair_recommended": True, "repair_reason": "Fail", "validation_result": {"regression_reason": "Error in src/bar.py"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert meta.get("patch_draftability") == "medium"
    assert meta.get("candidate_patch_strategy") == "guided_patch_followup"
    assert "src/bar.py" in (meta.get("candidate_target_files") or meta.get("target_files_candidate") or [])


def test_patch_proposal_has_readiness_fields():
    """Prove normalize_patch_proposal includes proposal_readiness, proposal_completeness, requires_followup_before_apply."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "surgeon",
        "status": "proposed",
        "target_files": ["a.py"],
        "change_type": "guided_patch_followup",
        "proposal_readiness": "draft_followup",
        "requires_followup_before_apply": True,
    })
    assert "proposal_readiness" in r
    assert r.get("proposal_readiness") == "draft_followup"
    assert "proposal_completeness" in r
    assert "requires_followup_before_apply" in r
    assert r.get("requires_followup_before_apply") is True
    assert "missing_information_flags" in r
    assert "draft_source" in r


def test_helix_summary_has_draftability_distribution():
    """Prove helix summary repair_artifact_quality includes draftability_distribution."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    rq = s.get("repair_artifact_quality") or {}
    assert "draftability_distribution" in rq
    dist = rq.get("draftability_distribution") or {}
    assert "high" in dist
    assert "medium" in dist
    assert "low" in dist


def test_integrity_draftability_validation():
    """Prove check_repair_metadata_shape validates patch_draftability and candidate_patch_strategy."""
    from NEXUS.helix_stages import run_surgeon_stage
    from NEXUS.integrity_checker import check_repair_metadata_shape

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    result = check_repair_metadata_shape(meta)
    assert result.get("valid") is True


def test_guided_patch_followup_change_type():
    """Prove guided_patch_followup is valid change_type."""
    from NEXUS.patch_proposal_registry import CHANGE_TYPES, normalize_patch_proposal

    assert "guided_patch_followup" in CHANGE_TYPES
    r = normalize_patch_proposal({"source": "surgeon", "change_type": "guided_patch_followup", "target_files": []})
    assert r.get("change_type") == "guided_patch_followup"


def test_draft_followup_proposal_structure():
    """Prove draft-followup proposal has correct structure (no executable patch payload)."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    proposal = {
        "source": "surgeon",
        "status": "proposed",
        "target_files": ["src/foo.py"],
        "change_type": "guided_patch_followup",
        "patch_payload": {
            "draft_followup_artifact": True,
            "candidate_target_files": ["src/foo.py"],
            "candidate_search_anchors": ["Error in foo"],
            "candidate_replacement_intent": "Fix regression",
            "suspected_root_causes": ["Edge case"],
        },
        "proposal_readiness": "draft_followup",
        "requires_followup_before_apply": True,
    }
    r = normalize_patch_proposal(proposal)
    assert r.get("proposal_readiness") == "draft_followup"
    assert r.get("requires_followup_before_apply") is True
    assert r.get("patch_payload", {}).get("draft_followup_artifact") is True
    assert "search_text" not in r.get("patch_payload", {}) or not r.get("patch_payload", {}).get("search_text")


def main():
    tests = [
        test_surgeon_has_patch_draftability_fields,
        test_surgeon_high_draftability_when_has_patch,
        test_surgeon_medium_draftability_when_followup_candidate,
        test_patch_proposal_has_readiness_fields,
        test_helix_summary_has_draftability_distribution,
        test_integrity_draftability_validation,
        test_guided_patch_followup_change_type,
        test_draft_followup_proposal_structure,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
