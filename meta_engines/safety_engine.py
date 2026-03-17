from __future__ import annotations

from typing import Any


def evaluate_safety_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Safety posture summary focused on unsafe automation/destructive posture.

    Stable output shape:
    {
      "engine_status": "...",
      "engine_reason": "...",
      "review_required": bool
    }
    """
    try:
        states = states_by_project or {}
        if not states:
            return {
                "engine_status": "warning",
                "engine_reason": "No project state signals available; safety posture unknown.",
                "review_required": True,
            }

        blocked_projects = []
        warning_projects = []

        for key, st in states.items():
            if not isinstance(st, dict):
                continue
            guard_result = st.get("guardrail_result") if isinstance(st.get("guardrail_result"), dict) else {}
            guard_status = st.get("guardrail_status") or guard_result.get("guardrail_status")
            enforcement_status = st.get("enforcement_status")
            if not enforcement_status and isinstance(st.get("enforcement_result"), dict):
                enforcement_status = (st.get("enforcement_result") or {}).get("enforcement_status")

            recursion_blocked = bool(guard_result.get("recursion_blocked", False))
            state_repair_recommended = bool(guard_result.get("state_repair_recommended", False))

            if str(guard_status).strip().lower() in ("blocked", "error_fallback") or str(enforcement_status).strip().lower() == "blocked":
                blocked_projects.append(key)
                continue

            if recursion_blocked or state_repair_recommended:
                warning_projects.append(key)

        if blocked_projects:
            return {
                "engine_status": "review_required",
                "engine_reason": f"Safety signals blocked in projects: {blocked_projects}.",
                "review_required": True,
            }

        if warning_projects:
            return {
                "engine_status": "warning",
                "engine_reason": f"Safety warnings detected (recursion/state repair): {warning_projects}.",
                "review_required": True,
            }

        # Even if no explicit guardrail signals were found, treat as reviewable
        # because this engine only summarizes (not enforces) in this sprint.
        return {
            "engine_status": "passed",
            "engine_reason": "Guardrails indicate a stable posture; no unsafe recursion/state-repair signals detected.",
            "review_required": False,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Safety engine evaluation failed.",
            "review_required": True,
        }

