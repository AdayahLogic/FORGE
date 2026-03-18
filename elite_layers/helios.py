from __future__ import annotations

from typing import Any

from NEXUS.change_safety_gate import evaluate_change_gate_safe
from NEXUS.regression_checks import run_regression_checks_safe
from NEXUS.self_improvement_engine import build_self_improvement_backlog_safe, select_next_improvement_safe


def build_helios_summary_safe(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    live_regression: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    HELIOS summary: self-improvement planning / gating layer.

    Stable output shape:
    {
      "helios_status": "...",
      "selected_improvement": null,
      "improvement_category": null,
      "improvement_reason": "...",
      "execution_gated": true
    }
    """
    try:
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}
        dash = dashboard_summary or {}

        priority_project = coord.get("priority_project")
        target_project = project_name or priority_project or "jarvis"

        # Build deterministic backlog; use a minimal dashboard stub if needed.
        if not dash:
            dash = {"guardrail_status_count": (kwargs.get("guardrail_status_count") or {})}

        backlog_items = build_self_improvement_backlog_safe(
            dashboard_summary=dash,
            studio_coordination_summary=coord,
            driver_summary=driver,
        )
        selected = select_next_improvement_safe(backlog_items=backlog_items)

        selected_item_id = selected.get("selected_item_id")
        selected_item = None
        for it in backlog_items:
            if isinstance(it, dict) and it.get("item_id") == selected_item_id:
                selected_item = it
                break

        if not selected_item:
            return {
                "helios_status": "idle",
                "selected_improvement": None,
                "improvement_category": None,
                "improvement_reason": "No self-improvement candidate selected.",
                "execution_gated": True,
            }

        improvement_category = selected_item.get("category")
        target_area = selected_item.get("target_area")
        category = selected_item.get("category")
        priority = selected_item.get("priority")

        # Regression checks: by default do live checks; callers can disable.
        regression = {"regression_status": "none", "regression_reason": "Regression checks not run."}
        if live_regression:
            regression = run_regression_checks_safe(project_name=str(target_project or "jarvis"))

        gate = evaluate_change_gate_safe(
            target_area=target_area,
            category=category,
            priority=priority,
            project_name=str(target_project or "jarvis"),
            core_files_touched=False,
        )

        execution_allowed = bool(gate.get("execution_allowed", False))
        execution_gated = not execution_allowed

        gate_status = gate.get("change_gate_status") or "blocked"
        regression_status = regression.get("regression_status") or "none"

        helios_status = "gated" if execution_gated else "planned"

        return {
            "helios_status": helios_status,
            "selected_improvement": selected_item,
            "improvement_category": improvement_category,
            "improvement_reason": (
                f"Selected={selected_item.get('item_id')}; regression={regression_status}; "
                f"change_gate={gate_status}; execution_allowed={execution_allowed}."
            ),
            "execution_gated": bool(execution_gated),
        }
    except Exception:
        return {
            "helios_status": "error_fallback",
            "selected_improvement": None,
            "improvement_category": None,
            "improvement_reason": "HELIOS summary evaluation failed.",
            "execution_gated": True,
        }

