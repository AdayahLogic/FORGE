"""
Phase 35 governed draft-to-patch conversion tests.

Run: python tests/phase35_draft_conversion_test.py
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


def test_evaluate_draft_conversion_module():
    """Prove evaluate_draft_conversion produces conversion artifact."""
    from NEXUS.helix_draft_conversion import evaluate_draft_conversion

    meta = {"candidate_target_files": ["a.py"], "refinement_status": "partially_refined", "draft_candidate_quality": "medium"}
    r = evaluate_draft_conversion(meta, False, {})
    assert "conversion_status" in r
    assert r.get("conversion_status") in ("not_convertible", "conditionally_convertible", "converted_to_patch_candidate")
    assert "executable_candidate" in r
    assert "proposal_maturity" in r
    assert "conversion_confidence" in r
    assert "ready_for_human_patch_review" in r


def test_conversion_converted_when_has_patch():
    """Prove conversion_status=converted_to_patch_candidate when full patch payload exists."""
    from NEXUS.helix_draft_conversion import evaluate_draft_conversion

    meta = {"candidate_target_files": ["a.py"]}
    payload = {"search_text": "x", "replacement_text": "y", "target_relative_path": "a.py"}
    r = evaluate_draft_conversion(meta, True, payload)
    assert r.get("conversion_status") == "converted_to_patch_candidate"
    assert r.get("executable_candidate") is True
    assert r.get("proposal_maturity") == "executable"
    assert r.get("ready_for_governed_patch_validation") is True


def test_conversion_conditionally_convertible():
    """Prove conversion_status=conditionally_convertible for strong draft."""
    from NEXUS.helix_draft_conversion import evaluate_draft_conversion

    meta = {
        "candidate_target_files": ["src/foo.py"],
        "candidate_search_anchors": ["Error in foo"],
        "candidate_replacement_intent": "Fix regression",
        "refinement_status": "partially_refined",
        "draft_candidate_quality": "medium",
        "candidate_change_scope": "single_file",
    }
    r = evaluate_draft_conversion(meta, False, {})
    assert r.get("conversion_status") == "conditionally_convertible"
    assert r.get("executable_candidate") is False
    assert r.get("proposal_maturity") in ("strong_candidate", "guided_followup")
    assert r.get("ready_for_human_patch_review") is True


def test_surgeon_has_conversion_fields():
    """Prove surgeon repair_metadata includes Phase 35 conversion fields."""
    from NEXUS.helix_stages import run_surgeon_stage

    critic = {"repair_recommended": True, "repair_reason": "Reg", "critique_evaluation": {"hidden_failure_points": ["X"], "testing_gaps": ["Y"]}}
    inspector = {"repair_recommended": True, "repair_reason": "Fail", "validation_result": {"regression_reason": "Error in src/bar.py"}}
    builder = {"implementation_plan": {}}
    r = run_surgeon_stage(critic, inspector, "test", builder_result=builder)
    meta = r.get("repair_metadata") or {}
    assert "conversion_status" in meta
    assert meta.get("conversion_status") in ("not_convertible", "conditionally_convertible", "converted_to_patch_candidate")
    assert "executable_candidate" in meta
    assert "proposal_maturity" in meta


def test_patch_proposal_has_conversion_fields():
    """Prove normalize_patch_proposal includes conversion_status, executable_candidate, proposal_maturity."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "surgeon",
        "change_type": "guided_patch_followup",
        "conversion_status": "conditionally_convertible",
        "executable_candidate": False,
        "proposal_maturity": "strong_candidate",
    })
    assert "conversion_status" in r
    assert r.get("conversion_status") == "conditionally_convertible"
    assert "executable_candidate" in r
    assert r.get("executable_candidate") is False
    assert "proposal_maturity" in r
    assert "conversion_confidence" in r
    assert "ready_for_human_patch_review" in r


def test_helix_summary_has_conversion_distribution():
    """Prove helix summary repair_artifact_quality includes conversion_distribution."""
    from NEXUS.helix_summary import build_helix_summary_safe

    s = build_helix_summary_safe(n_recent=5)
    rq = s.get("repair_artifact_quality") or {}
    assert "conversion_distribution" in rq
    dist = rq.get("conversion_distribution") or {}
    assert "converted_to_patch_candidate" in dist
    assert "conditionally_convertible" in dist
    assert "not_convertible" in dist


def test_integrity_conversion_validation():
    """Prove check_repair_metadata_shape validates conversion_status."""
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
        test_evaluate_draft_conversion_module,
        test_conversion_converted_when_has_patch,
        test_conversion_conditionally_convertible,
        test_surgeon_has_conversion_fields,
        test_patch_proposal_has_conversion_fields,
        test_helix_summary_has_conversion_distribution,
        test_integrity_conversion_validation,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
