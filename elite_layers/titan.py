from __future__ import annotations

from typing import Any


def build_titan_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    TITAN summary: summarize existing execution/autonomy posture (no execution).

    Stable output shape:
    {
      "titan_status": "...",
      "execution_mode": "...",
      "next_execution_action": "...",
      "execution_reason": "...",
      "run_permitted": false
    }
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}

        coordination_status = str(coord.get("coordination_status") or "").strip().lower()
        priority_project = coord.get("priority_project")

        if not priority_project and states:
            priority_project = sorted(states.keys())[0]

        state = states.get(priority_project or "", {}) if priority_project else {}
        if not isinstance(state, dict):
            state = {}

        scheduler_result = state.get("scheduler_result") if isinstance(state.get("scheduler_result"), dict) else {}
        reexecution_result = state.get("reexecution_result") if isinstance(state.get("reexecution_result"), dict) else {}
        launch_result = state.get("launch_result") if isinstance(state.get("launch_result"), dict) else {}
        autonomy_result = state.get("autonomy_result") if isinstance(state.get("autonomy_result"), dict) else {}
        guardrail_result = state.get("guardrail_result") if isinstance(state.get("guardrail_result"), dict) else {}

        scheduler_status = (state.get("scheduler_status") or scheduler_result.get("scheduler_status") or "none").strip().lower()
        reexecution_status = (state.get("reexecution_status") or reexecution_result.get("reexecution_status") or "none").strip().lower()
        launch_status = (state.get("launch_status") or launch_result.get("launch_status") or "none").strip().lower()
        autonomy_status = (state.get("autonomy_status") or autonomy_result.get("autonomy_status") or "idle").strip().lower()

        guardrail_status = (state.get("guardrail_status") or guardrail_result.get("guardrail_status") or "none").strip().lower()
        launch_allowed = bool(guardrail_result.get("launch_allowed", False))
        run_permitted_raw = bool(reexecution_result.get("run_permitted", False))

        # Conservative: permitted only when guardrails allow and reexecution says permitted.
        run_permitted = bool(launch_allowed and run_permitted_raw)

        if autonomy_status in ("ran", "blocked"):
            execution_mode = "autonomy"
        elif reexecution_status == "ready":
            execution_mode = "reexecution"
        elif scheduler_status == "scheduled":
            execution_mode = "scheduler"
        elif driver.get("driver_status"):
            execution_mode = "studio_driver"
        else:
            execution_mode = "idle"

        if run_permitted:
            titan_status = "ready"
        elif guardrail_status == "blocked" or (guardrail_result and not launch_allowed):
            titan_status = "blocked"
        elif coordination_status == "waiting" or str(driver.get("driver_status") or "").strip().lower() == "waiting":
            titan_status = "waiting"
        elif scheduler_status in ("scheduled", "none") or reexecution_status in ("waiting", "idle", "none"):
            titan_status = "waiting" if coordination_status == "waiting" else "idle"
        elif not states:
            titan_status = "idle"
        else:
            titan_status = "idle"

        if run_permitted:
            next_execution_action = str(reexecution_result.get("reexecution_action") or "").strip() or str(driver.get("driver_action") or "run_priority_project")
            execution_reason = f"Guardrails allow (launch_allowed={launch_allowed}) and reexecution permits ({reexecution_status})."
        elif guardrail_status == "blocked":
            next_execution_action = "guardrails_blocked"
            execution_reason = guardrail_result.get("guardrail_reason") or "Guardrails blocked execution."
        elif not reexecution_result:
            next_execution_action = "reexecution_unknown"
            execution_reason = "Reexecution signals not available; conservative run_permitted=False."
        else:
            next_execution_action = str(reexecution_result.get("reexecution_action") or "").strip() or "defer"
            execution_reason = (
                f"Run not permitted by current posture: guardrail_status={guardrail_status}, "
                f"reexecution_status={reexecution_status}, scheduler_status={scheduler_status}, "
                f"autonomy_status={autonomy_status}."
            )

        if not priority_project:
            titan_status = "error_fallback"
            execution_mode = execution_mode or "idle"
            next_execution_action = "idle"
            execution_reason = "No priority project found for TITAN summary."
            run_permitted = False

        return {
            "titan_status": titan_status,
            "execution_mode": execution_mode,
            "next_execution_action": next_execution_action,
            "execution_reason": execution_reason,
            "run_permitted": bool(run_permitted),
        }
    except Exception:
        return {
            "titan_status": "error_fallback",
            "execution_mode": "idle",
            "next_execution_action": "idle",
            "execution_reason": "TITAN summary evaluation failed.",
            "run_permitted": False,
        }

