"""
NEXUS integrity checker (hardening phase).

Read-only, deterministic checks for contract consistency, fallback shapes,
and cross-phase refs. No execution; no side effects.
"""

from __future__ import annotations

from typing import Any

# Canonical keys for recent-phase payloads (success and fallback must include these)
APPROVAL_SUMMARY_KEYS = (
    "approval_status",
    "pending_count_total",
    "pending_by_project",
    "recent_approvals",
    "approval_types",
    "reason",
)
PRODUCT_SUMMARY_KEYS = (
    "product_status",
    "draft_count",
    "ready_count",
    "restricted_count",
    "total_count",
    "products_by_project",
    "safety_indicators",
    "learning_linkage_present",
    "approval_linkage_present",
    "autonomy_linkage_present",
    "reason",
)
AUTONOMY_SUMMARY_KEYS = (
    "autonomy_posture",
    "last_autonomy_run",
    "last_stop_reason",
    "autonomy_capable",
    "approval_blocked",
    "recent_runs",
    "per_project",
    "execution_environment_posture",
    "reason",
)
HELIX_SUMMARY_KEYS = (
    "helix_posture",
    "last_helix_run",
    "last_stop_reason",
    "approval_blocked",
    "safety_blocked",
    "requires_surgeon",
    "stage_distribution",
    "surgeon_invocation_frequency",
    "approval_blocked_frequency",
    "autonomy_linkage_presence",
    "recent_runs",
    "per_project",
    "reason",
)
REF_KEYS = ("approval_id_refs", "autonomy_id_refs", "product_id_refs")
PATCH_PROPOSAL_SUMMARY_KEYS = (
    "patch_proposal_status",
    "pending_count",
    "approval_blocked_count",
    "applied_count",
    "by_project",
    "recent_proposals",
    "by_risk_level",
    "reason",
)


def _check_keys(payload: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    """Return list of missing keys."""
    if not isinstance(payload, dict):
        return list(required)
    return [k for k in required if k not in payload]


def _check_refs_shape(refs: Any) -> tuple[bool, str]:
    """Return (valid, message). Refs must be list of strings or empty list."""
    if refs is None:
        return True, "refs absent (defaults to [])"
    if not isinstance(refs, list):
        return False, f"refs must be list, got {type(refs).__name__}"
    for i, x in enumerate(refs):
        if not isinstance(x, str):
            return False, f"refs[{i}] must be str, got {type(x).__name__}"
    return True, "ok"


def check_approval_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check approval summary has required keys. Read-only."""
    missing = _check_keys(payload, APPROVAL_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "approval_summary",
    }


def check_product_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check product summary has required keys. Read-only."""
    missing = _check_keys(payload, PRODUCT_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "product_summary",
    }


def check_autonomy_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check autonomy summary has required keys. Read-only."""
    missing = _check_keys(payload, AUTONOMY_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "autonomy_summary",
    }


def check_helix_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check helix summary has required keys. Read-only."""
    missing = _check_keys(payload, HELIX_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "helix_summary",
    }


def check_patch_proposal_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check patch proposal summary has required keys. Read-only."""
    missing = _check_keys(payload, PATCH_PROPOSAL_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "patch_proposal_summary",
    }


def check_refs_in_record(record: dict[str, Any]) -> dict[str, Any]:
    """Check approval_id_refs, autonomy_id_refs, product_id_refs are list of str. Read-only."""
    issues: list[str] = []
    for key in REF_KEYS:
        val = record.get(key)
        if val is None:
            continue
        ok, msg = _check_refs_shape(val)
        if not ok:
            issues.append(f"{key}: {msg}")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "payload_type": "refs",
    }


def check_product_manifest_sections(manifest: dict[str, Any]) -> dict[str, Any]:
    """Check product manifest has required sections. Read-only."""
    required = (
        "product_id",
        "project_name",
        "status",
        "approval_requirements",
        "safety_summary",
        "risk_profile",
    )
    missing = _check_keys(manifest, required)
    refs_ok = check_refs_in_record(manifest)
    return {
        "valid": len(missing) == 0 and refs_ok.get("valid", True),
        "missing_keys": missing,
        "ref_issues": refs_ok.get("issues", []),
        "payload_type": "product_manifest",
    }


def run_integrity_check(
    *,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Run deterministic integrity checks on recent-phase artifacts.
    Read-only; no side effects.
    """
    results: list[dict[str, Any]] = []
    all_valid = True

    try:
        from NEXUS.registry_dashboard import build_registry_dashboard_summary
        dash = build_registry_dashboard_summary()
    except Exception as e:
        return {
            "integrity_status": "error",
            "reason": str(e),
            "checks": [],
            "all_valid": False,
        }

    # Approval summary
    approval = dash.get("approval_summary") or {}
    r = check_approval_summary_shape(approval)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Product summary
    product = dash.get("product_summary") or {}
    r = check_product_summary_shape(product)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Autonomy summary
    autonomy = dash.get("autonomy_summary") or {}
    r = check_autonomy_summary_shape(autonomy)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # HELIX summary
    helix = dash.get("helix_summary") or {}
    r = check_helix_summary_shape(helix)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Patch proposal summary (Phase 23)
    patch_proposal = dash.get("patch_proposal_summary") or {}
    r = check_patch_proposal_summary_shape(patch_proposal)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Ref shape in a sample record (if available)
    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.autonomy_registry import read_autonomy_journal_tail
        for proj_key in list(PROJECTS.keys())[:1]:
            path = PROJECTS.get(proj_key, {}).get("path")
            if path:
                tail = read_autonomy_journal_tail(project_path=path, n=1)
                if tail:
                    r = check_refs_in_record(tail[-1])
                    r["source"] = "autonomy_journal"
                    results.append(r)
                    if not r["valid"]:
                        all_valid = False
            break
    except Exception:
        pass

    return {
        "integrity_status": "ok" if all_valid else "issues_detected",
        "reason": "All checks passed." if all_valid else "Some checks failed.",
        "checks": results,
        "all_valid": all_valid,
    }


def run_integrity_check_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return run_integrity_check(**kwargs)
    except Exception as e:
        return {
            "integrity_status": "error",
            "reason": str(e),
            "checks": [],
            "all_valid": False,
        }
