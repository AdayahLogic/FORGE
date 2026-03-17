from __future__ import annotations

from typing import Any

from NEXUS.agent_policy_registry import AGENT_POLICY_REGISTRY


def evaluate_policy_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Policy posture summary using existing NEXUS policy/execution layers (summary-only).

    Stable output shape:
    {
      "engine_status": "...",
      "engine_reason": "...",
      "review_required": bool
    }
    """
    try:
        states = states_by_project or {}

        active_agents = [a for a, v in AGENT_POLICY_REGISTRY.items() if (v or {}).get("policy_status") == "active"]
        planned_agents = [a for a, v in AGENT_POLICY_REGISTRY.items() if (v or {}).get("policy_status") == "planned"]

        blocked_seen = []
        warning_seen = []
        for key, st in states.items():
            if not isinstance(st, dict):
                continue
            enforcement_result = st.get("enforcement_result") if isinstance(st.get("enforcement_result"), dict) else {}
            enforcement_status = st.get("enforcement_status") or enforcement_result.get("enforcement_status")

            governance_result = st.get("governance_result") if isinstance(st.get("governance_result"), dict) else {}
            governance_status = st.get("governance_status") or governance_result.get("governance_status")

            guard_result = st.get("guardrail_result") if isinstance(st.get("guardrail_result"), dict) else {}
            guard_status = st.get("guardrail_status") or guard_result.get("guardrail_status")

            if str(enforcement_status).strip().lower() == "blocked" or str(governance_status).strip().lower() == "blocked":
                blocked_seen.append(key)
                continue
            if str(guard_status).strip().lower() == "warning":
                warning_seen.append(key)

        if blocked_seen:
            return {
                "engine_status": "review_required",
                "engine_reason": f"Policy posture shows blocked enforcement/governance in: {blocked_seen}.",
                "review_required": True,
            }

        if not active_agents and not planned_agents:
            return {
                "engine_status": "review_required",
                "engine_reason": "No agent policy entries found; policy posture requires review (placeholder summarizer).",
                "review_required": True,
            }

        if warning_seen:
            return {
                "engine_status": "warning",
                "engine_reason": f"Policy posture indicates guardrail warnings in: {warning_seen}.",
                "review_required": True,
            }

        return {
            "engine_status": "passed",
            "engine_reason": (
                "Policy posture summary indicates policy coverage present "
                f"(active_agents={len(active_agents)}, planned_agents={len(planned_agents)}), "
                "and no blocked enforcement/governance signals detected in provided state."
            ),
            "review_required": False,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Policy engine evaluation failed.",
            "review_required": True,
        }

