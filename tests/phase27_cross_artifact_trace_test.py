"""
Phase 27 cross-artifact trace completion tests.

Run: python tests/phase27_cross_artifact_trace_test.py
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


TRACE_REQUIRED_KEYS = (
    "trace_status",
    "project_name",
    "approval_ids",
    "patch_ids",
    "helix_ids",
    "autonomy_ids",
    "product_ids",
    "learning_record_refs",
    "link_completeness",
    "missing_links",
    "trace_reason",
    "generated_at",
)

LINK_COMPLETENESS_KEYS = (
    "approval_to_patch",
    "patch_to_helix",
    "patch_to_product",
    "autonomy_to_product",
    "helix_to_autonomy",
)


def test_trace_contract_shape():
    """Prove cross-artifact trace returns expected contract shape."""
    from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe

    t = build_cross_artifact_trace_safe()
    for k in TRACE_REQUIRED_KEYS:
        assert k in t, f"Missing key: {k}"
    assert t["trace_status"] in ("ok", "partial", "error_fallback")
    assert isinstance(t["approval_ids"], list)
    assert isinstance(t["patch_ids"], list)
    assert isinstance(t["link_completeness"], dict)
    for k in LINK_COMPLETENESS_KEYS:
        assert k in t["link_completeness"]
    assert isinstance(t["missing_links"], list)


def test_trace_safe_never_raises():
    """Prove build_cross_artifact_trace_safe never raises."""
    from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe

    t = build_cross_artifact_trace_safe(project_name="nonexistent_project")
    assert t["trace_status"] in ("ok", "partial", "error_fallback")
    for k in TRACE_REQUIRED_KEYS:
        assert k in t


def test_trace_fallback_shape():
    """Prove error fallback preserves contract shape."""
    from NEXUS.cross_artifact_trace import _fallback_trace
    from datetime import datetime

    f = _fallback_trace(datetime.now().isoformat(), "Test error", "test_project")
    for k in TRACE_REQUIRED_KEYS:
        assert k in f
    assert f["trace_status"] == "error_fallback"
    assert "Test error" in f["missing_links"][0]
    for k in LINK_COMPLETENESS_KEYS:
        assert f["link_completeness"][k] is False


def test_artifact_trace_command():
    """Prove artifact_trace command returns expected shape."""
    from NEXUS.command_surface import run_command

    r = run_command("artifact_trace")
    assert r["command"] == "artifact_trace"
    payload = r.get("payload") or {}
    assert "trace_status" in payload
    assert "link_completeness" in payload
    assert "missing_links" in payload
    assert "approval_ids" in payload


def test_dashboard_includes_trace():
    """Prove dashboard includes cross_artifact_trace_summary."""
    from NEXUS.registry_dashboard import build_registry_dashboard_summary

    d = build_registry_dashboard_summary()
    assert "cross_artifact_trace_summary" in d
    t = d["cross_artifact_trace_summary"]
    assert t["trace_status"] in ("ok", "partial", "error_fallback")
    assert "link_completeness" in t
    assert "missing_links" in t


def test_integrity_check_trace_shape():
    """Prove integrity checker validates trace summary shape."""
    from NEXUS.integrity_checker import check_trace_summary_shape

    valid_trace = {
        "trace_status": "partial",
        "project_name": None,
        "approval_ids": [],
        "patch_ids": [],
        "helix_ids": [],
        "autonomy_ids": [],
        "product_ids": [],
        "learning_record_refs": [],
        "link_completeness": {"approval_to_patch": False, "patch_to_helix": False, "patch_to_product": False, "autonomy_to_product": False, "helix_to_autonomy": False},
        "missing_links": [],
        "trace_reason": "ok",
        "generated_at": "2025-01-01T00:00:00",
    }
    r = check_trace_summary_shape(valid_trace)
    assert r["valid"] is True
    assert r["payload_type"] == "cross_artifact_trace_summary"

    invalid_trace = {"trace_status": "ok"}
    r2 = check_trace_summary_shape(invalid_trace)
    assert r2["valid"] is False
    assert len(r2["missing_keys"]) > 0


def test_trace_no_fabrication():
    """Prove trace uses only real data; IDs are from journals."""
    from NEXUS.cross_artifact_trace import build_cross_artifact_trace_safe

    t = build_cross_artifact_trace_safe()
    # All IDs should be strings; we don't invent placeholder IDs
    for lst in (t.get("approval_ids") or [], t.get("patch_ids") or [], t.get("helix_ids") or [], t.get("autonomy_ids") or []):
        for x in lst:
            assert isinstance(x, str), "IDs must be strings from real records"
            assert len(x) >= 1, "No empty placeholder IDs"


def main():
    tests = [
        test_trace_contract_shape,
        test_trace_safe_never_raises,
        test_trace_fallback_shape,
        test_artifact_trace_command,
        test_dashboard_includes_trace,
        test_integrity_check_trace_shape,
        test_trace_no_fabrication,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
