"""
NEXUS approval summary layer (Phase 18).

Builds approval visibility for dashboard and command surface.
Read-only; no approval decisions.
"""

from __future__ import annotations

from typing import Any

from NEXUS.approval_registry import (
    count_pending_approvals,
    get_pending_approvals,
    read_approval_journal_tail,
)
from NEXUS.registry import PROJECTS


def build_approval_summary(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """
    Build approval summary across all projects.

    Returns:
        approval_status: str
        pending_count_total: int
        pending_by_project: dict[str, int]
        recent_approvals: list[dict]
        approval_types: list[str]
        reason: str
    """
    pending_by_project: dict[str, int] = {}
    recent_approvals: list[dict[str, Any]] = []
    approval_types_seen: set[str] = set()

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if path:
            count = count_pending_approvals(project_path=path, n=n_tail)
            pending_by_project[proj_key] = count
            tail = read_approval_journal_tail(project_path=path, n=n_recent)
            for r in tail:
                recent_approvals.append({
                    **r,
                    "_project": proj_key,
                })
                at = r.get("approval_type")
                if at:
                    approval_types_seen.add(str(at))

    pending_count_total = sum(pending_by_project.values())
    recent_approvals.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    recent_approvals = recent_approvals[:n_recent]

    if pending_count_total > 0:
        status = "pending"
        reason = f"{pending_count_total} approval(s) pending across projects."
    else:
        status = "clear"
        reason = "No pending approvals."

    return {
        "approval_status": status,
        "pending_count_total": pending_count_total,
        "pending_by_project": pending_by_project,
        "recent_approvals": recent_approvals,
        "approval_types": sorted(approval_types_seen),
        "reason": reason,
    }


def build_approval_summary_safe(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_approval_summary(n_recent=n_recent, n_tail=n_tail)
    except Exception:
        return {
            "approval_status": "error_fallback",
            "pending_count_total": 0,
            "pending_by_project": {},
            "recent_approvals": [],
            "approval_types": [],
            "reason": "Approval summary evaluation failed.",
        }
