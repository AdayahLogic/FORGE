"""
NEXUS autonomy summary layer (Phase 20).

Builds bounded autonomy visibility for dashboard and command surface.
Read-only; reflects execution environment posture; no execution capability.
"""

from __future__ import annotations

from typing import Any

from NEXUS.autonomy_registry import read_autonomy_journal_tail
from NEXUS.registry import PROJECTS


# Canonical keys for autonomy summary (shape consistency).
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


def build_autonomy_summary(
    *,
    n_recent: int = 10,
    execution_environment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build autonomy summary across all projects.

    Returns:
        autonomy_posture: str  # idle | capable | approval_blocked | safety_blocked
        last_autonomy_run: dict | None
        last_stop_reason: str
        autonomy_capable: bool
        approval_blocked: bool
        recent_runs: list[dict]
        per_project: dict[str, dict]
        reason: str
    """
    recent_runs: list[dict[str, Any]] = []
    per_project: dict[str, dict[str, Any]] = {}
    last_autonomy_run: dict[str, Any] | None = None
    last_stop_reason = ""
    autonomy_capable = False
    approval_blocked = False


    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        tail = read_autonomy_journal_tail(project_path=path, n=n_recent)
        for r in tail:
            recent_runs.append({**r, "_project": proj_key})
        if tail:
            last = tail[-1]
            if last_autonomy_run is None or (last.get("finished_at") or "") > (last_autonomy_run.get("finished_at") or ""):
                last_autonomy_run = {**last, "_project": proj_key}
                last_stop_reason = last.get("stop_reason") or ""
            per_project[proj_key] = {
                "last_run": tail[-1] if tail else None,
                "recent_count": len(tail),
                "last_stop_reason": tail[-1].get("stop_reason") if tail else "",
                "approval_blocked": bool(tail[-1].get("approval_blocked")) if tail else False,
                "safety_blocked": bool(tail[-1].get("safety_blocked")) if tail else False,
            }

    recent_runs.sort(key=lambda x: x.get("finished_at") or "", reverse=True)
    recent_runs = recent_runs[:n_recent]

    if last_autonomy_run:
        approval_blocked = bool(last_autonomy_run.get("approval_blocked"))
        safety_blocked = bool(last_autonomy_run.get("safety_blocked"))
        if not approval_blocked and not safety_blocked and last_autonomy_run.get("autonomy_status") == "completed":
            autonomy_capable = True
        elif not approval_blocked and not safety_blocked:
            autonomy_capable = True

    if approval_blocked:
        posture = "approval_blocked"
        reason = "Last autonomy run stopped; approval required."
    elif last_autonomy_run and last_autonomy_run.get("safety_blocked"):
        posture = "safety_blocked"
        reason = "Last autonomy run stopped; safety blocked."
    elif autonomy_capable:
        posture = "capable"
        reason = "Bounded autonomy capable; no approval gate."
    else:
        posture = "idle"
        reason = "No recent autonomy runs or idle."

    # Phase 17: surface execution environment posture (do not treat planned as active).
    exec_env = execution_environment_summary or {}
    exec_env_posture = {
        "execution_environment_status": exec_env.get("execution_environment_status"),
        "active_environments": exec_env.get("active_environments") or [],
        "planned_environments": exec_env.get("planned_environments") or [],
        "reason": exec_env.get("reason", ""),
    }

    return {
        "autonomy_posture": posture,
        "last_autonomy_run": last_autonomy_run,
        "last_stop_reason": last_stop_reason,
        "autonomy_capable": autonomy_capable,
        "approval_blocked": approval_blocked,
        "recent_runs": recent_runs,
        "per_project": per_project,
        "execution_environment_posture": exec_env_posture,
        "reason": reason,
    }


def build_autonomy_summary_safe(
    *,
    n_recent: int = 10,
    execution_environment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return build_autonomy_summary(
            n_recent=n_recent,
            execution_environment_summary=execution_environment_summary,
        )
    except Exception:
        return {
            "autonomy_posture": "error_fallback",
            "last_autonomy_run": None,
            "last_stop_reason": "",
            "autonomy_capable": False,
            "approval_blocked": False,
            "recent_runs": [],
            "per_project": {},
            "execution_environment_posture": {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "reason": "",
            },
            "reason": "Autonomy summary failed.",
        }
