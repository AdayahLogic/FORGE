from __future__ import annotations

from typing import Any


def _safe_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _exec_via_executor(*, selected_path: str, selected_project: str | None, dash: dict[str, Any], helios_summary: dict[str, Any] | None) -> dict[str, Any]:
    """Call studio_loop_executor exactly once; never recurse."""
    from studio_loop_executor import execute_selected_path_safe

    return execute_selected_path_safe(
        selected_path=selected_path,
        selected_project=selected_project,
        dashboard_summary=dash,
        helios_summary=helios_summary or {},
        studio_driver_summary=(dash.get("studio_driver_summary") or {}),
        portfolio_summary=(dash.get("portfolio_summary") or {}),
    )


def run_studio_loop_tick(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    helios_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    One-tick, bounded controlled studio loop.

    One selected path + one bounded follow-through action, then stop.
    """
    try:
        dash = dashboard_summary or {}
        studio_coordination_summary = dash.get("studio_coordination_summary") or {}
        studio_driver_summary = dash.get("studio_driver_summary") or {}
        portfolio_summary = dash.get("portfolio_summary") or {}

        helios = helios_summary or dash.get("helios_summary") or {}
        change_proposal = helios.get("change_proposal") or {}

        selected_project_from_coord = studio_coordination_summary.get("priority_project") or portfolio_summary.get("priority_project") or None
        selected_project_from_driver = studio_driver_summary.get("target_project")

        # Rule 1: HELIOS proposal review
        risk_level = change_proposal.get("risk_level")
        blocked_by = _safe_list(change_proposal.get("blocked_by"))
        recommended_path = str(change_proposal.get("recommended_path") or "")
        scope_level = str(change_proposal.get("scope_level") or "")
        change_type = str(change_proposal.get("change_type") or "")

        high_value = bool(scope_level == "high" or change_type in ("hardening", "policy", "monitoring", "runtime"))
        helios_low_medium = risk_level in ("low", "medium")
        helios_not_blocked = len(blocked_by) == 0
        helios_propose_review_ok = high_value and helios_low_medium and helios_not_blocked and recommended_path != "defer"

        if helios_propose_review_ok:
            executor_res = _exec_via_executor(
                selected_path="helios_proposal_review",
                selected_project=selected_project_from_coord,
                dash=dash,
                helios_summary=helios,
            )
            return {
                "studio_loop_status": "ran",
                "selected_path": "helios_proposal_review",
                "selected_project": selected_project_from_coord,
                "loop_reason": f"HELIOS proposal selected (risk={risk_level}, blocked_by=0, recommended_path={recommended_path}).",
                "execution_started": bool(executor_res.get("execution_started", False)),
                "bounded_execution": True,
                "executed_command": executor_res.get("executed_command"),
                "executed_result_summary": executor_res.get("executed_result_summary"),
                "stop_reason": "One tick complete; review surfaced only (no execution).",
            }

        # Rule 2: Project cycle when execution is permitted
        execution_permitted = bool(studio_driver_summary.get("execution_permitted", False))
        driver_action = str(studio_driver_summary.get("driver_action") or "").strip().lower()
        driver_allows_cycle = execution_permitted and driver_action in ("run_priority_project", "resume_priority_project")

        if driver_allows_cycle:
            executor_res = _exec_via_executor(
                selected_path="project_cycle",
                selected_project=selected_project_from_driver,
                dash=dash,
                helios_summary=helios,
            )
            exec_started = bool(executor_res.get("execution_started", False))
            status = "ran" if exec_started else "gated"
            return {
                "studio_loop_status": status,
                "selected_path": "project_cycle",
                "selected_project": selected_project_from_driver,
                "loop_reason": f"Studio driver permits execution (driver_action={driver_action}, execution_permitted={execution_permitted}).",
                "execution_started": exec_started,
                "bounded_execution": True,
                "executed_command": executor_res.get("executed_command"),
                "executed_result_summary": executor_res.get("executed_result_summary"),
                "stop_reason": "One tick complete; bounded project cycle step finished (or was gated).",
            }

        # Rule 3: Genesis generation when opportunity-starved
        portfolio_status = str(portfolio_summary.get("portfolio_status") or "").strip().lower()
        if portfolio_status in ("idle", "waiting"):
            executor_res = _exec_via_executor(
                selected_path="genesis_generation",
                selected_project=selected_project_from_coord,
                dash=dash,
                helios_summary=helios,
            )
            return {
                "studio_loop_status": "ran",
                "selected_path": "genesis_generation",
                "selected_project": selected_project_from_coord,
                "loop_reason": f"Portfolio indicates idle/opportunity-starved (portfolio_status={portfolio_status}).",
                "execution_started": False,
                "bounded_execution": True,
                "executed_command": executor_res.get("executed_command"),
                "executed_result_summary": executor_res.get("executed_result_summary"),
                "stop_reason": "One tick complete; GENESIS evaluation-only step ran.",
            }

        # If HELIOS had a high-value proposal but it did not pass gates, report gated.
        if high_value:
            return {
                "studio_loop_status": "gated",
                "selected_path": "idle",
                "selected_project": selected_project_from_coord,
                "loop_reason": "HELIOS proposed an internal hardening action but gates blocked review/execution (risk/blocked_by/recommended_path).",
                "execution_started": False,
                "bounded_execution": True,
                "executed_command": None,
                "executed_result_summary": None,
                "stop_reason": "One tick complete; gates prevented next action.",
            }

        return {
            "studio_loop_status": "idle",
            "selected_path": "idle",
            "selected_project": None,
            "loop_reason": "No bounded path satisfied selection rules.",
            "execution_started": False,
            "bounded_execution": True,
            "executed_command": None,
            "executed_result_summary": None,
            "stop_reason": "One tick complete; idle.",
        }
    except Exception as e:
        return {
            "studio_loop_status": "error_fallback",
            "selected_path": "idle",
            "selected_project": None,
            "loop_reason": f"Studio loop tick failed: {e}",
            "execution_started": False,
            "bounded_execution": True,
            "executed_command": None,
            "executed_result_summary": None,
            "stop_reason": "Safe fallback; no execution performed.",
        }


def run_studio_loop_tick_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return run_studio_loop_tick(**kwargs)
    except Exception:
        return {
            "studio_loop_status": "error_fallback",
            "selected_path": "idle",
            "selected_project": None,
            "loop_reason": "Studio loop evaluation failed.",
            "execution_started": False,
            "bounded_execution": True,
            "executed_command": None,
            "executed_result_summary": None,
            "stop_reason": "Safe fallback; no execution performed.",
        }

