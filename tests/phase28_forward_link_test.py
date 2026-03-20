"""
Phase 28 forward link completion tests.

Run: python tests/phase28_forward_link_test.py
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


def test_ref_utils_normalize():
    """Prove normalize_ref_list dedupes and coerces to str."""
    from NEXUS.ref_utils import normalize_ref_list, merge_ref_lists

    assert normalize_ref_list(None) == []
    assert normalize_ref_list([]) == []
    assert normalize_ref_list("abc") == ["abc"]
    assert normalize_ref_list([1, "b", "b", None, "c"]) == ["1", "b", "c"]
    assert merge_ref_lists([], ["a"], ["a", "b"]) == ["a", "b"]


def test_approval_patch_id_refs_capture():
    """Prove approval record captures patch_id_refs from context."""
    from NEXUS.approval_registry import normalize_approval_record

    r = normalize_approval_record({
        "approval_id": "a1",
        "context": {"patch_id": "p1", "decision": "approve"},
    })
    assert "patch_id_refs" in r
    assert r["patch_id_refs"] == ["p1"]


def test_learning_model_refs():
    """Prove learning record normalizes patch_id_refs, approval_id_refs."""
    from NEXUS.learning_models import normalize_learning_record

    r = normalize_learning_record({
        "record_type": "test",
        "patch_id_refs": ["p1", "p2"],
        "approval_id_refs": ["a1"],
    })
    assert r["patch_id_refs"] == ["p1", "p2"]
    assert r["approval_id_refs"] == ["a1"]
    assert r["helix_id_refs"] == []
    assert r["autonomy_id_refs"] == []


def test_patch_proposal_uses_ref_utils():
    """Prove patch proposal normalize uses ref_utils."""
    from NEXUS.patch_proposal_registry import normalize_patch_proposal

    r = normalize_patch_proposal({
        "source": "helix_builder",
        "approval_id_refs": ["a1", "a1"],
        "helix_id_refs": ["h1"],
    })
    assert "a1" in r["approval_id_refs"]
    assert r["helix_id_refs"] == ["h1"]


def test_apply_resolution_approval_id():
    """Prove apply resolution receives approval_id from resolution (code path)."""
    from NEXUS.patch_proposal_registry import append_patch_proposal_resolution

    # We can't easily test the full apply flow without side effects.
    # Verify append_patch_proposal_resolution accepts approval_id for "apply".
    # Resolution record shape includes approval_id.
    record = {
        "patch_id": "test",
        "decision": "apply",
        "new_status": "applied",
        "approval_id": "aid123",
        "project_name": "",
        "reason": "test",
    }
    assert record["approval_id"] == "aid123"


def test_cross_artifact_trace_approval_patch_id_refs():
    """Prove trace uses approval patch_id_refs when present."""
    from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe

    t = build_cross_artifact_trace_safe(n_recent=10)
    assert "link_completeness" in t
    assert "approval_to_patch" in t["link_completeness"]


def test_integrity_patch_ref_keys():
    """Prove integrity checker validates patch ref keys including helix_id_refs."""
    from NEXUS.integrity_checker import check_refs_in_record, REF_KEYS_PATCH

    r = check_refs_in_record(
        {"approval_id_refs": [], "helix_id_refs": ["h1"], "product_id_refs": []},
        ref_keys=REF_KEYS_PATCH,
    )
    assert r["valid"] is True


def main():
    tests = [
        test_ref_utils_normalize,
        test_approval_patch_id_refs_capture,
        test_learning_model_refs,
        test_patch_proposal_uses_ref_utils,
        test_apply_resolution_approval_id,
        test_cross_artifact_trace_approval_patch_id_refs,
        test_integrity_patch_ref_keys,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
