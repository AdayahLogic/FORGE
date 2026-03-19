"""
NEXUS HELIX summary layer (Phase 21).

Builds HELIX pipeline visibility for dashboard and command surface.
Read-only; no execution capability.
"""

from __future__ import annotations

from typing import Any

from NEXUS.helix_registry import read_helix_journal_tail
from NEXUS.registry import PROJECTS


HELIX_SUMMARY_KEYS = (
    "helix_posture",
    "last_helix_run",
    "last_stop_reason",
    "approval_blocked",
    "safety_blocked",
    "requires_surgeon",
    "recent_runs",
    "per_project",
    "reason",
)


def build_helix_summary(
    *,
    n_recent: int = 10,
) -> dict[str, Any]:
    """
    Build HELIX summary across all projects.

    Returns:
        helix_posture: str  # idle | capable | approval_blocked | safety_blocked
        last_helix_run: dict | None
        last_stop_reason: str
        approval_blocked: bool
        safety_blocked: bool
        requires_surgeon: bool
        recent_runs: list[dict]
        per_project: dict[str, dict]
        reason: str
    """
    recent_runs: list[dict[str, Any]] = []
    per_project: dict[str, dict[str, Any]] = {}
    last_helix_run: dict[str, Any] | None = None
    last_stop_reason = ""
    approval_blocked = False
    safety_blocked = False
    requires_surgeon = False

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        tail = read_helix_journal_tail(project_path=path, n=n_recent)
        for r in tail:
            recent_runs.append({**r, "_project": proj_key})
        if tail:
            last = tail[-1]
            if last_helix_run is None or (last.get("finished_at") or "") > (last_helix_run.get("finished_at") or ""):
                last_helix_run = {**last, "_project": proj_key}
                last_stop_reason = last.get("stop_reason") or ""
            per_project[proj_key] = {
                "last_run": tail[-1] if tail else None,
                "recent_count": len(tail),
                "last_stop_reason": tail[-1].get("stop_reason") if tail else "",
                "approval_blocked": bool(tail[-1].get("approval_blocked")) if tail else False,
                "safety_blocked": bool(tail[-1].get("safety_blocked")) if tail else False,
                "requires_surgeon": bool(tail[-1].get("requires_surgeon")) if tail else False,
            }

    recent_runs.sort(key=lambda x: x.get("finished_at") or "", reverse=True)
    recent_runs = recent_runs[:n_recent]

    if last_helix_run:
        approval_blocked = bool(last_helix_run.get("approval_blocked"))
        safety_blocked = bool(last_helix_run.get("safety_blocked"))
        requires_surgeon = bool(last_helix_run.get("requires_surgeon"))

    if approval_blocked:
        posture = "approval_blocked"
        reason = "Last HELIX run stopped; approval required."
    elif safety_blocked:
        posture = "safety_blocked"
        reason = "Last HELIX run stopped; safety blocked."
    elif last_helix_run and last_helix_run.get("pipeline_status") == "completed":
        posture = "capable"
        reason = "HELIX pipeline capable; last run completed."
    elif last_helix_run:
        posture = "idle"
        reason = f"Last run: {last_stop_reason or 'unknown'}."
    else:
        posture = "idle"
        reason = "No recent HELIX runs."

    return {
        "helix_posture": posture,
        "last_helix_run": last_helix_run,
        "last_stop_reason": last_stop_reason,
        "approval_blocked": approval_blocked,
        "safety_blocked": safety_blocked,
        "requires_surgeon": requires_surgeon,
        "recent_runs": recent_runs,
        "per_project": per_project,
        "reason": reason,
    }


def build_helix_summary_safe(
    *,
    n_recent: int = 10,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return build_helix_summary(n_recent=n_recent)
    except Exception:
        return {
            "helix_posture": "error_fallback",
            "last_helix_run": None,
            "last_stop_reason": "",
            "approval_blocked": False,
            "safety_blocked": False,
            "requires_surgeon": False,
            "recent_runs": [],
            "per_project": {},
            "reason": "HELIX summary failed.",
        }
