"""
Phase 36 governed builder assist for patch completion tests.

Run: python tests/phase36_patch_completion_test.py
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


def test_evaluate_patch_completion_module():
    """Prove evaluate_patch_completion produces completion artifact."""
    from NEXUS.helix_patch_completion import evaluate_patch_completion

    meta = {"candidate_target_files": ["a.py"], "refinement_status": "partially_refined", "conversion_status": "conditionally_convertible"}
    r = evaluate_patch_completion(None, meta, {})
    assert "completion_status" in r
    assert r.get("completion_status") in ("not_completable", "partially_completable", "completed_patch_candidate")
    assert "completion_reason" in r
    assert "completion_requirements_met" in r
    assert "completion_requirements_missing" in r
    assert "completed_target_file" in r
    assert "completed_search_text" in r
    assert "completed_replacement_text" in r
    assert "human_review_required" in r
    assert "requires_followup_before_approval" in r


def test_completion_completed_when_has_patch():
    """Prove completion_status=completed_patch_candidate when full patch from Builder."""
    from NEXUS.helix_patch_completion import evaluate_patch_completion

    builder = {"implementation_plan": {"patch_request": {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}}}
    meta = {"candidate_target_files": ["a.py"]}
    payload = {"target_relative_path": "a.py", "search_text": "x", "replacement_text": "y"}
    r = evaluate_patch_completion(builder, meta, payload)
    assert r.get("completion_status") == "completed_patch_candidate"
    assert r.get("completed_target_file") == "a.py"
    assert r.get("completed_search_text") == "x"
    assert r.get("completed_replacement_text") == "y"
    assert r.get("human_review_required") is False
    assert r.get("requires_followup_before_approval") is False


def test_completion_no_fabrication():
    """Prove completed_search_text and completed_replacement_text are empty when not from Builder."""
    from NEXUS.helix_patch_completion import evaluate_patch_completion

    meta = {"candidate_target_files": ["src/foo.py"], "candidate_replacement_intent": "Fix", "refinement_status": "partially_refined", "conversion_status": "conditionally_convertible"}
    r = evaluate_patch_completion(None, meta, {})
    assert r.get("completion_status") in ("partially_completable", "not_completable")
    assert r.get("completed_search_text") == ""
    assert r.get("completed_replacement_text") == ""
    assert "search_text" in (r.get("completion_requirements_missing") or [])


def test_surgeon_has_completion_fields():
    """Prove surgeon repair_metadata includes Phase 36 completion fields."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Reg", "critique_evaluation": {"hidden_failure_points": ["X"], "testing_gaps": ["Y"]}}
    inspector = {"repair_recommended": True, "repair_reason": "Fail", "validation_result": {"regression_reason": "Error in src/bar.py"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert "completion_status" in meta
    assert meta.get("completion_status") in ("not_completable", "partially_completable", "completed_patch_candidate")
    assert "completion_reason" in meta
    assert "completion_confidence" in meta
    assert "completed_candidate_type" in meta
    assert "requires_followup_before_approval" in meta


def test_patch_proposal_has_completion_fields():
    """Prove normalize_patch_proposal includes completion_status, completed_candidate_type."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "surgeon",
        "change_type": "guided_patch_followup",
        "completion_status": "partially_completable",
        "completed_candidate_type": "guided_followup_only",
    })
    assert "completion_status" in r
    assert r.get("completion_status") == "partially_completable"
    assert "completed_candidate_type" in r
    assert "completion_requirements_missing" in r
    assert "requires_followup_before_approval" in r


def test_helix_summary_has_completion_distribution():
    """Prove helix summary repair_artifact_quality includes completion_distribution."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    rq = s.get("repair_artifact_quality") or {}
    assert "completion_distribution" in rq
    dist = rq.get("completion_distribution") or {}
    assert "completed_patch_candidate" in dist
    assert "partially_completable" in dist
    assert "not_completable" in dist


def test_integrity_completion_validation():
    """Prove check_repair_metadata_shape validates completion_status."""
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
        test_evaluate_patch_completion_module,
        test_completion_completed_when_has_patch,
        test_completion_no_fabrication,
        test_surgeon_has_completion_fields,
        test_patch_proposal_has_completion_fields,
        test_helix_summary_has_completion_distribution,
        test_integrity_completion_validation,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
