from __future__ import annotations

from typing import Any

from portfolio_manager import build_portfolio_summary_safe


def build_leviathan_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    portfolio_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    LEVIATHAN summary: strategic leverage / prioritization layer.

    Stable output shape:
    {
      "leviathan_status": "...",
      "highest_leverage_project": null,
      "highest_leverage_reason": "...",
      "recommended_focus": "...",
      "defer_projects": []
    }
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}

        if not portfolio_summary:
            portfolio_summary = build_portfolio_summary_safe(
                states_by_project=states,
                studio_coordination_summary=coord,
                studio_driver_summary=driver,
            )

        priority_project = portfolio_summary.get("priority_project")
        portfolio_status = str(portfolio_summary.get("portfolio_status") or "").strip().lower()

        project_order = coord.get("project_order") or []
        if not isinstance(project_order, list):
            project_order = []

        defer_projects: list[str] = []
        if project_order and priority_project:
            defer_projects = [p for p in project_order if p != priority_project]
        elif states and priority_project:
            defer_projects = [k for k in sorted(states.keys()) if k != priority_project]

        if portfolio_status == "active":
            leviathan_status = "focused"
            recommended_focus = f"Focus execution on priority project '{priority_project}'."
        elif portfolio_status == "waiting":
            leviathan_status = "waiting"
            recommended_focus = f"Wait for coordination; priority='{priority_project}'."
        elif portfolio_status == "idle":
            leviathan_status = "idle"
            recommended_focus = f"Idle posture; priority='{priority_project}'."
        else:
            leviathan_status = "error_fallback"
            recommended_focus = "Portfolio status requires review."

        return {
            "leviathan_status": leviathan_status,
            "highest_leverage_project": priority_project if priority_project else None,
            "highest_leverage_reason": str(portfolio_summary.get("portfolio_reason") or ""),
            "recommended_focus": recommended_focus,
            "defer_projects": defer_projects,
        }
    except Exception:
        return {
            "leviathan_status": "error_fallback",
            "highest_leverage_project": None,
            "highest_leverage_reason": "LEVIATHAN summary evaluation failed.",
            "recommended_focus": "Review required.",
            "defer_projects": [],
        }

