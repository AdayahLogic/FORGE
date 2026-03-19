"""
NEXUS patch proposal summary layer (Phase 23).

Builds patch proposal visibility for dashboard and command surface.
Read-only; no application.
"""

from __future__ import annotations

from typing import Any

from NEXUS.patch_proposal_registry import read_patch_proposal_journal_tail
from NEXUS.registry import PROJECTS


def build_patch_proposal_summary(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """
    Build patch proposal summary across all projects.

    Returns:
        patch_proposal_status: str
        pending_count: int
        approval_blocked_count: int
        applied_count: int
        by_project: dict[str, dict]
        recent_proposals: list[dict]
        by_risk_level: dict[str, int]
        reason: str
    """
    pending_count = 0
    approval_blocked_count = 0
    applied_count = 0
    by_project: dict[str, dict[str, Any]] = {}
    recent_proposals: list[dict[str, Any]] = []
    by_risk_level: dict[str, int] = {}

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        tail = read_patch_proposal_journal_tail(project_path=path, n=n_tail)
        for r in tail:
            r_with_proj = {**r, "_project": proj_key}
            recent_proposals.append(r_with_proj)
            status = str(r.get("status") or "proposed").strip().lower()
            if status == "proposed" or status == "approval_required":
                pending_count += 1
            elif status == "approval_required":
                approval_blocked_count += 1
            elif status == "applied":
                applied_count += 1
            risk = str(r.get("risk_level") or "medium").strip().lower()
            by_risk_level[risk] = by_risk_level.get(risk, 0) + 1
        if tail:
            by_project[proj_key] = {
                "count": len(tail),
                "last_proposal": tail[-1] if tail else None,
                "pending": sum(1 for x in tail if str(x.get("status") or "").strip().lower() in ("proposed", "approval_required")),
            }

    recent_proposals.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    recent_proposals = recent_proposals[:n_recent]

    if pending_count > 0:
        patch_status = "pending"
        reason = f"{pending_count} patch proposal(s) pending approval."
    elif applied_count > 0:
        patch_status = "applied"
        reason = f"{applied_count} patch(es) applied; no pending."
    else:
        patch_status = "clear"
        reason = "No patch proposals."

    return {
        "patch_proposal_status": patch_status,
        "pending_count": pending_count,
        "approval_blocked_count": approval_blocked_count,
        "applied_count": applied_count,
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
            "approval_blocked_count": 0,
            "applied_count": 0,
            "by_project": {},
            "recent_proposals": [],
            "by_risk_level": {},
            "reason": "Patch proposal summary failed.",
        }
