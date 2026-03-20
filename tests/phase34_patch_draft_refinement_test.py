"""
Phase 34 governed patch draft refinement tests.

Run: python tests/phase34_patch_draft_refinement_test.py
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


def test_refine_patch_draft_module():
    """Prove refine_patch_draft produces refinement artifact."""
    from NEXUS.helix_patch_refinement import refine_patch_draft

    meta = {"candidate_target_files": ["a.py"], "candidate_replacement_intent": "Fix", "suspected_root_causes": ["X"], "patch_draftability": "medium"}
    r = refine_patch_draft(None, meta, False)
    assert "refinement_status" in r
    assert r.get("refinement_status") in ("not_refinable", "partially_refined", "draft_ready")
    assert "refinement_reason" in r
    assert "refinement_inputs_present" in r
    assert "refinement_inputs_missing" in r
    assert "draft_candidate_quality" in r
    assert "candidate_change_scope" in r
    assert "candidate_validation_steps" in r
    assert "candidate_followup_actions" in r
    assert "requires_human_reconstruction" in r


def test_refine_patch_draft_draft_ready_when_has_patch():
    """Prove refinement_status=draft_ready when has full patch."""
    from NEXUS.helix_patch_refinement import refine_patch_draft

    builder = {"implementation_plan": {"patch_request": {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}}}
    meta = {"candidate_target_files": ["a.py"], "patch_draftability": "high"}
    r = refine_patch_draft(builder, meta, True)
    assert r.get("refinement_status") == "draft_ready"
    assert r.get("draft_candidate_quality") == "high"
    assert r.get("requires_human_reconstruction") is False


def test_refine_patch_draft_partially_refined():
    """Prove refinement_status=partially_refined when medium draftability with target+causes."""
    from NEXUS.helix_patch_refinement import refine_patch_draft

    meta = {"candidate_target_files": ["src/foo.py"], "candidate_replacement_intent": "Fix regression", "suspected_root_causes": ["Edge case"], "patch_draftability": "medium"}
    r = refine_patch_draft(None, meta, False)
    assert r.get("refinement_status") == "partially_refined"
    assert r.get("draft_candidate_quality") == "medium"
    assert r.get("requires_human_reconstruction") is True
    assert "candidate_followup_actions" in r
    assert len(r.get("candidate_followup_actions") or []) > 0


def test_surgeon_has_refinement_fields():
    """Prove surgeon repair_metadata includes Phase 34 refinement fields."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Reg", "critique_evaluation": {"hidden_failure_points": ["X"], "testing_gaps": ["Y"]}}
    inspector = {"repair_recommended": True, "repair_reason": "Fail", "validation_result": {"regression_reason": "Error in src/bar.py"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert "refinement_status" in meta
    assert meta.get("refinement_status") in ("not_refinable", "partially_refined", "draft_ready")
    assert "refinement_reason" in meta
    assert "draft_candidate_quality" in meta
    assert "candidate_change_scope" in meta
    assert "candidate_validation_steps" in meta
    assert "candidate_followup_actions" in meta
    assert "requires_human_reconstruction" in meta


def test_helix_summary_has_refinement_distribution():
    """Prove helix summary repair_artifact_quality includes refinement_distribution."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    rq = s.get("repair_artifact_quality") or {}
    assert "refinement_distribution" in rq
    dist = rq.get("refinement_distribution") or {}
    assert "draft_ready" in dist
    assert "partially_refined" in dist
    assert "not_refinable" in dist


def test_patch_proposal_has_refinement_fields():
    """Prove normalize_patch_proposal includes refinement_status, draft_candidate_quality."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "surgeon",
        "change_type": "guided_patch_followup",
        "patch_payload": {"refinement_status": "partially_refined", "draft_candidate_quality": "medium", "requires_human_reconstruction": True},
    })
    assert "refinement_status" in r
    assert r.get("refinement_status") == "partially_refined"
    assert "draft_candidate_quality" in r
    assert "candidate_change_scope" in r
    assert "requires_human_reconstruction" in r


def test_integrity_refinement_validation():
    """Prove check_repair_metadata_shape validates refinement_status."""
    from NEXUS.helix_stages import run_surgeon_stage
    from NEXUS.integrity_checker import check_repair_metadata_shape

    critic = {"repair_recommended": True, "repair_reason": "x", "critique_evaluation": {}}
    inspector = {"repair_recommended": True, "repair_reason": "x", "validation_result": {}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    result = check_repair_metadata_shape(meta)
    assert result.get("valid") is True


def main():
    tests = [
        test_refine_patch_draft_module,
        test_refine_patch_draft_draft_ready_when_has_patch,
        test_refine_patch_draft_partially_refined,
        test_surgeon_has_refinement_fields,
        test_helix_summary_has_refinement_distribution,
        test_patch_proposal_has_refinement_fields,
        test_integrity_refinement_validation,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
