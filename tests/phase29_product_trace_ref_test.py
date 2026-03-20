"""
Phase 29 product / trace ref alignment tests.

Run: python tests/phase29_product_trace_ref_test.py
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


def test_product_manifest_has_ref_fields():
    """Prove product manifest includes normalized ref fields."""
    from NEXUS.product_builder import build_product_manifest_safe
    from NEXUS.registry import PROJECTS

    key = next(iter(PROJECTS.keys()), None)
    if not key:
        return
    proj = PROJECTS[key]
    path = proj.get("path")
    m = build_product_manifest_safe(project_name=key, project_path=path, project_key=key)
    for k in ("approval_id_refs", "patch_id_refs", "helix_id_refs", "autonomy_id_refs", "learning_insight_refs"):
        assert k in m, f"Missing {k}"
        assert isinstance(m[k], list)


def test_get_product_refs():
    """Prove get_product_refs returns normalized ref dict."""
    from NEXUS.product_builder import get_product_refs

    r = get_product_refs({"approval_refs": ["a1"], "patch_id_refs": ["p1"]})
    assert r["approval_id_refs"] == ["a1"]
    assert r["patch_id_refs"] == ["p1"]
    assert r["helix_id_refs"] == []
    r2 = get_product_refs(None)
    assert r2["approval_id_refs"] == []


def test_product_summary_linkage_fields():
    """Prove product summary includes patch_linkage_present, helix_linkage_present."""
    from NEXUS.product_summary import build_product_summary_safe

    s = build_product_summary_safe()
    assert "patch_linkage_present" in s
    assert "helix_linkage_present" in s
    assert isinstance(s["patch_linkage_present"], bool)
    assert isinstance(s["helix_linkage_present"], bool)


def test_product_registry_normalize_refs():
    """Prove normalize_product_manifest includes ref fields."""
    from NEXUS.product_registry import normalize_product_manifest

    m = normalize_product_manifest({"product_id": "p1", "approval_refs": ["a1"], "patch_id_refs": ["p1"]})
    assert "approval_id_refs" in m
    assert "patch_id_refs" in m
    assert m["approval_id_refs"] == ["a1"]
    assert m["patch_id_refs"] == ["p1"]


def test_release_readiness_product_linked():
    """Prove release readiness uses product linkage for trace."""
    from NEXUS.release_readiness import build_release_readiness

    minimal = {
        "product_summary": {"patch_linkage_present": True, "approval_linkage_present": False, "learning_linkage_present": False, "autonomy_linkage_present": False, "helix_linkage_present": False},
        "approval_summary": {},
        "patch_proposal_summary": {},
        "execution_environment_summary": {},
        "autonomy_summary": {},
        "helix_summary": {},
    }
    r = build_release_readiness(dashboard_summary=minimal)
    assert r["trace_links_present"]["product_linked"] is True


def test_integrity_product_summary_keys():
    """Prove integrity checker expects patch_linkage_present, helix_linkage_present."""
    from NEXUS.integrity_checker import check_product_summary_shape, PRODUCT_SUMMARY_KEYS

    assert "patch_linkage_present" in PRODUCT_SUMMARY_KEYS
    assert "helix_linkage_present" in PRODUCT_SUMMARY_KEYS
    valid = {"product_status": "draft", "draft_count": 1, "ready_count": 0, "restricted_count": 0, "total_count": 1, "products_by_project": {}, "safety_indicators": {}, "learning_linkage_present": False, "approval_linkage_present": False, "autonomy_linkage_present": False, "patch_linkage_present": False, "helix_linkage_present": False, "reason": "ok"}
    r = check_product_summary_shape(valid)
    assert r["valid"] is True


def main():
    tests = [
        test_product_manifest_has_ref_fields,
        test_get_product_refs,
        test_product_summary_linkage_fields,
        test_product_registry_normalize_refs,
        test_release_readiness_product_linked,
        test_integrity_product_summary_keys,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
