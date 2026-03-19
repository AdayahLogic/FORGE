"""
Phase 21 HELIX pipeline integration tests.

Run: python tests/phase21_helix_test.py
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


def test_helix_contract_shape():
    """Prove HELIX record has required contract fields."""
    from NEXUS.helix_registry import normalize_helix_record, HELIX_STAGES

    r = normalize_helix_record({
        "helix_id": "abc",
        "pipeline_status": "completed",
        "requires_surgeon": True,
        "approval_blocked": False,
    })
    assert "helix_id" in r
    assert r["pipeline_status"] == "completed"
    assert r["requires_surgeon"] is True
    assert "approval_id_refs" in r
    assert "product_id_refs" in r
    assert "stages" in r
    assert "architect" in r.get("stages", [])


def test_helix_gates_block_on_approval():
    """Prove HELIX pipeline blocks when approval required."""
    from unittest.mock import patch
    from NEXUS.helix_pipeline import run_helix_pipeline
    from NEXUS.registry import PROJECTS

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return

    loaded = {
        "load_error": None,
        "enforcement_result": {"workflow_action": "await_approval", "enforcement_status": "approval_required"},
        "review_queue_entry": {},
        "recovery_result": {},
        "reexecution_result": {},
    }
    with patch("NEXUS.helix_pipeline.load_project_state", return_value=loaded):
        result = run_helix_pipeline(project_path=path, project_name="jarvis", requested_outcome="Test")
    assert result.get("approval_blocked") is True
    assert result.get("pipeline_status") == "blocked"
    assert result.get("stop_reason") == "approval_blocked"


def test_helix_summary_includes_requires_surgeon():
    """Prove HELIX summary includes requires_surgeon."""
    from NEXUS.helix_summary import build_helix_summary_safe, HELIX_SUMMARY_KEYS

    s = build_helix_summary_safe()
    for k in HELIX_SUMMARY_KEYS:
        assert k in s
    assert "requires_surgeon" in s


def test_autonomy_record_has_approval_product_refs():
    """Prove autonomy record has forward-compat approval_id_refs, product_id_refs."""
    from NEXUS.autonomy_registry import normalize_autonomy_record

    r = normalize_autonomy_record({})
    assert "approval_id_refs" in r
    assert "product_id_refs" in r
    assert isinstance(r["approval_id_refs"], list)
    assert isinstance(r["product_id_refs"], list)


def test_product_manifest_has_forward_compat_refs():
    """Prove product manifest has learning_insight_refs, approval_refs, autonomy_refs."""
    from NEXUS.registry import PROJECTS
    from NEXUS.product_builder import build_product_manifest_safe

    path = PROJECTS.get("jarvis", {}).get("path")
    if not path:
        return
    m = build_product_manifest_safe(project_name="jarvis", project_path=path)
    assert "learning_insight_refs" in m
    assert "approval_refs" in m
    assert "autonomy_refs" in m


if __name__ == "__main__":
    ok = 0
    ok += _run("test_helix_contract_shape", test_helix_contract_shape)
    ok += _run("test_helix_gates_block_on_approval", test_helix_gates_block_on_approval)
    ok += _run("test_helix_summary_includes_requires_surgeon", test_helix_summary_includes_requires_surgeon)
    ok += _run("test_autonomy_record_has_approval_product_refs", test_autonomy_record_has_approval_product_refs)
    ok += _run("test_product_manifest_has_forward_compat_refs", test_product_manifest_has_forward_compat_refs)
    print(f"\n{ok}/5 passed")
    sys.exit(0 if ok == 5 else 1)
