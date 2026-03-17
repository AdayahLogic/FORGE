from __future__ import annotations

from typing import Any


def build_portfolio_summary(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build a portfolio/studio-level management summary.

    Complement the studio coordinator; do not replace orchestration logic.

    Stable output shape:
    {
      "portfolio_status": "...",
      "total_projects": 0,
      "active_projects": 0,
      "blocked_projects": 0,
      "priority_project": None,
      "portfolio_reason": "..."
    }
    """
    states = states_by_project or {}
    coord = studio_coordination_summary or {}
    driver = studio_driver_summary or {}

    total_projects = len(states) if isinstance(states, dict) else 0
    active_projects = int(coord.get("active_project_count") or 0)
    blocked_projects = int(coord.get("blocked_project_count") or 0)
    priority_project = coord.get("priority_project")

    coordination_status = str(coord.get("coordination_status") or "").strip().lower()
    driver_status = str(driver.get("driver_status") or "").strip().lower()
    execution_permitted = bool(driver.get("execution_permitted", False))

    if not coordination_status:
        portfolio_status = "error_fallback"
        reason = "Studio coordination summary missing; portfolio status requires review."
    elif execution_permitted or (coordination_status == "ready" and driver_status == "ready"):
        portfolio_status = "active"
        reason = f"Driver permits execution (driver_status={driver_status}); priority={priority_project}."
    elif coordination_status == "waiting":
        portfolio_status = "waiting"
        reason = f"Studio coordination is waiting; priority={priority_project}."
    elif coordination_status in ("idle", ""):
        portfolio_status = "idle"
        reason = f"Studio coordination idle; priority={priority_project}."
    else:
        portfolio_status = "error_fallback"
        reason = f"Unrecognized coordination_status='{coordination_status}'; portfolio status requires review."

    return {
        "portfolio_status": portfolio_status,
        "total_projects": int(total_projects),
        "active_projects": int(active_projects),
        "blocked_projects": int(blocked_projects),
        "priority_project": priority_project if priority_project else None,
        "portfolio_reason": str(reason),
    }


def build_portfolio_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_portfolio_summary(
            states_by_project=states_by_project,
            studio_coordination_summary=studio_coordination_summary,
            studio_driver_summary=studio_driver_summary,
            **kwargs,
        )
    except Exception:
        return {
            "portfolio_status": "error_fallback",
            "total_projects": 0,
            "active_projects": 0,
            "blocked_projects": 0,
            "priority_project": None,
            "portfolio_reason": "Portfolio summary evaluation failed.",
        }

