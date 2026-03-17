from __future__ import annotations

from typing import Any


def evaluate_risk_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Operational risk posture summary.

    This engine summarizes risk posture signals only (no enforcement).
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
                "engine_reason": "No project state signals available; operational risk posture unknown.",
                "review_required": True,
            }

        review_required_projects = []
        warning_projects = []

        for key, st in states.items():
            if not isinstance(st, dict):
                continue

            enforcement_result = st.get("enforcement_result") if isinstance(st.get("enforcement_result"), dict) else {}
            enforcement_status = st.get("enforcement_status") or enforcement_result.get("enforcement_status")

            governance_result = st.get("governance_result") if isinstance(st.get("governance_result"), dict) else {}
            governance_status = st.get("governance_status") or governance_result.get("governance_status")
            recovery_result = st.get("recovery_result") if isinstance(st.get("recovery_result"), dict) else {}
            recovery_status = st.get("recovery_status") or recovery_result.get("recovery_status")
            guard_result = st.get("guardrail_result") if isinstance(st.get("guardrail_result"), dict) else {}
            guard_state_repair_recommended = bool(guard_result.get("state_repair_recommended", False))

            # Change gate is planning/visibility; blocked/review-required indicates risk posture.
            change_gate_result = st.get("change_gate_result") if isinstance(st.get("change_gate_result"), dict) else {}
            change_gate_status = st.get("change_gate_status") or change_gate_result.get("change_gate_status")
            if str(change_gate_status).strip().lower() in ("review_required", "blocked"):
                review_required_projects.append(key)
                continue

            repair_required = bool(recovery_result.get("repair_required", False)) or str(recovery_status).strip().lower() == "repair_required"
            if str(enforcement_status).strip().lower() == "blocked" or str(governance_status).strip().lower() == "blocked":
                review_required_projects.append(key)
                continue

            if repair_required or guard_state_repair_recommended:
                warning_projects.append(key)

        if review_required_projects:
            return {
                "engine_status": "review_required",
                "engine_reason": f"Operational risk signals require review in: {review_required_projects}.",
                "review_required": True,
            }

        if warning_projects:
            return {
                "engine_status": "warning",
                "engine_reason": f"Operational risk warnings present in: {warning_projects}.",
                "review_required": True,
            }

        return {
            "engine_status": "passed",
            "engine_reason": "No high-risk operational signals detected from recovery/governance/enforcement/change-gate summaries.",
            "review_required": False,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Risk engine evaluation failed.",
            "review_required": True,
        }

