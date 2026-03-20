"""
NEXUS release readiness layer (Phase 26).

Unified operator release posture. Read-only; consumes existing summaries.
No deployment; no execution. Conservative rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

RELEASE_READINESS_STATUSES = ("ready", "blocked", "review_required", "error_fallback")


def build_release_readiness(
    *,
    project_name: str | None = None,
    dashboard_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build unified release readiness summary.
    Consumes existing summaries; does not duplicate logic.
    Conservative: prefer blocked/review_required over ready.
    """
    now = datetime.now().isoformat()
    critical_blockers: list[str] = []
    review_items: list[str] = []
    trace_links_present: dict[str, bool] = {
        "approval_linked": False,
        "patch_linked": False,
        "autonomy_linked": False,
        "product_linked": False,
        "helix_linked": False,
    }

    if dashboard_summary is None:
        try:
            from NEXUS.registry_dashboard import build_registry_dashboard_summary
            dashboard_summary = build_registry_dashboard_summary()
        except Exception:
            return _fallback_readiness(now, "Dashboard unavailable.", project_name)

    if not isinstance(dashboard_summary, dict):
        return _fallback_readiness(now, "Invalid dashboard.", project_name)

    product = dashboard_summary.get("product_summary") or {}
    approval = dashboard_summary.get("approval_summary") or {}
    patch = dashboard_summary.get("patch_proposal_summary") or {}
    exec_env = dashboard_summary.get("execution_environment_summary") or {}
    autonomy = dashboard_summary.get("autonomy_summary") or {}
    helix = dashboard_summary.get("helix_summary") or {}

    product_status = str(product.get("product_status") or "unknown").strip().lower()
    approval_status = str(approval.get("approval_status") or "unknown").strip().lower()
    patch_status = str(patch.get("patch_proposal_status") or "unknown").strip().lower()
    exec_status = str(exec_env.get("execution_environment_status") or "unknown").strip().lower()
    autonomy_posture = str((autonomy.get("autonomy_posture") or "").strip().lower())
    helix_posture = str((helix.get("helix_posture") or "").strip().lower())

    # Trace linkage visibility (do not invent links)
    if product.get("approval_linkage_present"):
        trace_links_present["approval_linked"] = True
    if (
        product.get("learning_linkage_present")
        or product.get("autonomy_linkage_present")
        or product.get("approval_linkage_present")
        or product.get("patch_linkage_present")
        or product.get("helix_linkage_present")
    ):
        trace_links_present["product_linked"] = True
    if patch.get("approved_pending_apply_count", 0) > 0 or patch.get("pending_count", 0) > 0:
        trace_links_present["patch_linked"] = True
    if helix.get("autonomy_linkage_presence", 0) > 0:
        trace_links_present["helix_linked"] = True
        trace_links_present["autonomy_linked"] = True

    # BLOCKED rules (conservative)
    if product_status == "restricted":
        critical_blockers.append("Product restricted; safety issues present.")
    if approval_status == "pending" and (approval.get("pending_count_total") or 0) > 0:
        critical_blockers.append(f"{approval.get('pending_count_total')} approval(s) pending.")
    if patch_status == "pending" and (patch.get("pending_count") or 0) > 0:
        critical_blockers.append(f"{patch.get('pending_count')} patch proposal(s) pending approval.")
    if (patch.get("approved_pending_apply_stale_count") or 0) > 0:
        critical_blockers.append("Stale approvals blocking patch apply; re-approval required.")
    if exec_status == "error_fallback":
        critical_blockers.append("Execution environment unavailable or error.")
    if autonomy_posture == "approval_blocked":
        critical_blockers.append("Autonomy blocked by approval gate.")
    if helix_posture == "approval_blocked":
        critical_blockers.append("HELIX blocked by approval gate.")
    if helix_posture == "safety_blocked":
        critical_blockers.append("HELIX blocked by safety gate.")

    # Integrity check
    try:
        from NEXUS.integrity_checker import run_integrity_check_safe
        integrity = run_integrity_check_safe()
        if not integrity.get("all_valid", True):
            critical_blockers.append("Integrity checks failed; contracts inconsistent.")
    except Exception:
        critical_blockers.append("Integrity check unavailable.")

    # REVIEW_REQUIRED rules (no blockers, but items need attention)
    if (patch.get("proposed_count") or 0) > 0 and not critical_blockers:
        review_items.append(f"{patch.get('proposed_count')} patch proposal(s) proposed but not resolved.")
    if (patch.get("approved_pending_apply_count") or 0) > 0 and not critical_blockers:
        review_items.append(f"{patch.get('approved_pending_apply_count')} patch(es) approved, awaiting apply.")
    if (approval.get("stale_count") or 0) > 0 and not critical_blockers:
        review_items.append(f"{approval.get('stale_count')} stale approval(s); may need re-approval.")
    if product_status == "draft" and not critical_blockers:
        review_items.append("Product in draft; review before release.")
    if not any(trace_links_present.values()) and not critical_blockers:
        review_items.append("No trace linkage present; consider linking artifacts.")

    # Determine final status
    if critical_blockers:
        status = "blocked"
        reason = "; ".join(critical_blockers[:3])
        ready_for_operator_release = False
    elif review_items:
        status = "review_required"
        reason = "; ".join(review_items[:3])
        ready_for_operator_release = False
    else:
        status = "ready"
        reason = "No blockers; no review items. Operator may proceed with release decisions."
        ready_for_operator_release = True

    return {
        "release_readiness_status": status,
        "project_name": project_name,
        "product_status": product_status,
        "approval_status": approval_status,
        "execution_environment_status": exec_status,
        "patch_status": patch_status,
        "autonomy_status": autonomy_posture,
        "helix_status": helix_posture,
        "critical_blockers": critical_blockers,
        "review_items": review_items,
        "readiness_reason": reason,
        "ready_for_operator_release": ready_for_operator_release,
        "trace_links_present": trace_links_present,
        "generated_at": now,
    }


def build_release_readiness_safe(
    *,
    project_name: str | None = None,
    dashboard_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_release_readiness(project_name=project_name, dashboard_summary=dashboard_summary)
    except Exception as e:
        return _fallback_readiness(
            datetime.now().isoformat(),
            f"Release readiness failed: {e}",
            project_name,
        )


def _fallback_readiness(generated_at: str, reason: str, project_name: str | None) -> dict[str, Any]:
    """Error fallback shape; preserves contract."""
    return {
        "release_readiness_status": "error_fallback",
        "project_name": project_name,
        "product_status": "unknown",
        "approval_status": "unknown",
        "execution_environment_status": "unknown",
        "patch_status": "unknown",
        "autonomy_status": "unknown",
        "helix_status": "unknown",
        "critical_blockers": [reason],
        "review_items": [],
        "readiness_reason": reason,
        "ready_for_operator_release": False,
        "trace_links_present": {
            "approval_linked": False,
            "patch_linked": False,
            "autonomy_linked": False,
            "product_linked": False,
            "helix_linked": False,
        },
        "generated_at": generated_at,
    }


def build_operator_release_summary(
    *,
    project_name: str | None = None,
) -> dict[str, Any]:
    """
    Alias for release readiness with operator-focused naming.
    Same contract; clearer for operator workflows.
    """
    r = build_release_readiness_safe(project_name=project_name)
    r["operator_summary"] = (
        f"Status: {r.get('release_readiness_status')}. "
        f"Blockers: {len(r.get('critical_blockers', []))}. "
        f"Review items: {len(r.get('review_items', []))}."
    )
    return r
