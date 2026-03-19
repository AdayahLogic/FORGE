"""
NEXUS patch proposal summary layer (Phase 23).

Builds patch proposal visibility for dashboard and command surface.
Read-only; no application.
"""

from __future__ import annotations

from typing import Any

from NEXUS.patch_proposal_registry import (
    read_patch_proposal_journal_tail,
    get_proposal_effective_status,
)
from NEXUS.registry import PROJECTS


def build_patch_proposal_summary(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """
    Build patch proposal summary across all projects.
    Uses effective status (resolution overrides base).
    """
    proposed_count = 0
    approval_required_count = 0
    approved_pending_apply_count = 0
    rejected_count = 0
    blocked_count = 0
    applied_count = 0
    by_project: dict[str, dict[str, Any]] = {}
    recent_proposals: list[dict[str, Any]] = []
    by_risk_level: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        tail = read_patch_proposal_journal_tail(project_path=path, n=n_tail)
        for r in tail:
            patch_id = r.get("patch_id")
            effective_status, _ = get_proposal_effective_status(project_path=path, patch_id=patch_id or "")
            r_with_proj = {**r, "_project": proj_key, "effective_status": effective_status}
            recent_proposals.append(r_with_proj)
            status_counts[effective_status] = status_counts.get(effective_status, 0) + 1
            if effective_status == "proposed":
                proposed_count += 1
            elif effective_status == "approval_required":
                approval_required_count += 1
            elif effective_status == "approved_pending_apply":
                approved_pending_apply_count += 1
            elif effective_status == "rejected":
                rejected_count += 1
            elif effective_status == "blocked":
                blocked_count += 1
            elif effective_status == "applied":
                applied_count += 1
            risk = str(r.get("risk_level") or "medium").strip().lower()
            by_risk_level[risk] = by_risk_level.get(risk, 0) + 1
        if tail:
            proj_status_counts: dict[str, int] = {}
            for x in tail:
                es, _ = get_proposal_effective_status(path, x.get("patch_id") or "")
                proj_status_counts[es] = proj_status_counts.get(es, 0) + 1
            pending = proj_status_counts.get("proposed", 0) + proj_status_counts.get("approval_required", 0)
            by_project[proj_key] = {
                "count": len(tail),
                "last_proposal": tail[-1] if tail else None,
                "pending": pending,
                "status_counts": proj_status_counts,
            }

    recent_proposals.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    recent_proposals = recent_proposals[:n_recent]

    pending_count = proposed_count + approval_required_count
    if pending_count > 0:
        patch_status = "pending"
        reason = f"{pending_count} patch proposal(s) pending approval."
    elif approved_pending_apply_count > 0:
        patch_status = "approved_pending_apply"
        reason = f"{approved_pending_apply_count} approved, awaiting apply."
    elif applied_count > 0:
        patch_status = "applied"
        reason = f"{applied_count} patch(es) applied; no pending."
    else:
        patch_status = "clear"
        reason = "No patch proposals."

    return {
        "patch_proposal_status": patch_status,
        "pending_count": pending_count,
        "proposed_count": proposed_count,
        "approval_required_count": approval_required_count,
        "approved_pending_apply_count": approved_pending_apply_count,
        "rejected_count": rejected_count,
        "blocked_count": blocked_count,
        "applied_count": applied_count,
        "approval_blocked_count": approval_required_count,
        "status_counts": status_counts,
        "by_project": by_project,
        "recent_proposals": recent_proposals,
        "by_risk_level": by_risk_level,
        "reason": reason,
    }


def build_patch_proposal_summary_safe(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_patch_proposal_summary(n_recent=n_recent, n_tail=n_tail)
    except Exception:
        return {
            "patch_proposal_status": "error_fallback",
            "pending_count": 0,
            "proposed_count": 0,
            "approval_required_count": 0,
            "approved_pending_apply_count": 0,
            "rejected_count": 0,
            "blocked_count": 0,
            "applied_count": 0,
            "approval_blocked_count": 0,
            "status_counts": {},
            "by_project": {},
            "recent_proposals": [],
            "by_risk_level": {},
            "reason": "Patch proposal summary failed.",
        }
