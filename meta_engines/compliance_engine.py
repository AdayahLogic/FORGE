from __future__ import annotations

from typing import Any

from NEXUS.agent_policy_registry import AGENT_POLICY_REGISTRY


def evaluate_compliance_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Compliance readiness placeholder summary focused on license/TOS/privacy readiness.

    This engine is summary-oriented in Sprint 5 and does not claim enforcement.
    Stable output shape:
    {
      "engine_status": "...",
      "engine_reason": "...",
      "review_required": bool
    }
    """
    try:
        states = states_by_project or {}

        active_policy_agents = [a for a, v in AGENT_POLICY_REGISTRY.items() if (v or {}).get("policy_status") == "active"]
        planned_policy_agents = [a for a, v in AGENT_POLICY_REGISTRY.items() if (v or {}).get("policy_status") == "planned"]

        if not active_policy_agents and not planned_policy_agents:
            return {
                "engine_status": "review_required",
                "engine_reason": "No agent policy entries found; license/TOS/privacy readiness requires review (placeholder).",
                "review_required": True,
            }

        # If any project is blocked by enforcement/governance, mark compliance as review-required.
        blocked_seen = []
        for key, st in states.items():
            if not isinstance(st, dict):
                continue
            enforcement_result = st.get("enforcement_result") if isinstance(st.get("enforcement_result"), dict) else {}
            enforcement_status = st.get("enforcement_status") or enforcement_result.get("enforcement_status")

            governance_result = st.get("governance_result") if isinstance(st.get("governance_result"), dict) else {}
            governance_status = st.get("governance_status") or governance_result.get("governance_status")
            if str(enforcement_status).strip().lower() == "blocked" or str(governance_status).strip().lower() == "blocked":
                blocked_seen.append(key)

        if blocked_seen:
            return {
                "engine_status": "review_required",
                "engine_reason": f"Compliance readiness needs review due to blocked enforcement/governance in: {blocked_seen}.",
                "review_required": True,
            }

        return {
            "engine_status": "warning",
            "engine_reason": (
                "Compliance is summarized as placeholder readiness: agent policy coverage present "
                f"(active_agents={len(active_policy_agents)}, planned_agents={len(planned_policy_agents)}), "
                "but license/TOS/privacy checks are not fully enumerated in this sprint."
            ),
            "review_required": True,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Compliance engine evaluation failed.",
            "review_required": True,
        }

