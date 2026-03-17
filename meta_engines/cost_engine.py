from __future__ import annotations

from typing import Any


def evaluate_cost_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    runtime_infrastructure_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Compact compute/runtime cost posture (summary placeholder but meaningful).

    Stable output shape:
    {
      "engine_status": "...",
      "engine_reason": "...",
      "review_required": bool
    }
    """
    try:
        states = states_by_project or {}
        rt = runtime_infrastructure_summary or {}
        available = [str(x).strip().lower() for x in (rt.get("available_runtimes") or []) if x is not None]
        future = [str(x).strip().lower() for x in (rt.get("future_runtimes") or []) if x is not None]

        planned_cost_risk = [x for x in future if x in ("cloud_worker", "remote_worker", "container_worker")]

        any_dispatch_future = False
        dispatch_future_targets: set[str] = set()
        for _, st in states.items():
            if not isinstance(st, dict):
                continue
            dps = st.get("dispatch_plan_summary") or {}
            if not isinstance(dps, dict):
                continue
            runtime_target_id = (dps.get("runtime_target_id") or "").strip().lower()
            ready_for_dispatch = bool(dps.get("ready_for_dispatch", False))
            if ready_for_dispatch and runtime_target_id in planned_cost_risk:
                any_dispatch_future = True
                dispatch_future_targets.add(runtime_target_id)

        if planned_cost_risk or any_dispatch_future:
            return {
                "engine_status": "warning",
                "engine_reason": (
                    "Cost posture indicates potential higher-cost execution targets present "
                    f"(future_runtimes risk={planned_cost_risk or '[]'}; dispatch_targets={sorted(dispatch_future_targets)})."
                ),
                "review_required": True,
            }

        if not available:
            return {
                "engine_status": "warning",
                "engine_reason": "No runtime infrastructure data available; cost posture unknown.",
                "review_required": True,
            }

        return {
            "engine_status": "passed",
            "engine_reason": "Cost posture summary indicates current runtimes are primarily local/IDE targets with no higher-cost future workers highlighted.",
            "review_required": False,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Cost engine evaluation failed.",
            "review_required": True,
        }

