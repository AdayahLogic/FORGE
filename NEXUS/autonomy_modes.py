from __future__ import annotations

from typing import Any


DEFAULT_AUTONOMY_MODE = "supervised_build"
AUTONOMY_MODES = frozenset(
    {
        "supervised_build",
        "assisted_autopilot",
        "low_risk_autonomous_development",
    }
)


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip().lower()
        if text and text not in out:
            out.append(text)
    return out


def normalize_autonomy_mode(mode: Any) -> str:
    value = str(mode or DEFAULT_AUTONOMY_MODE).strip().lower()
    return value if value in AUTONOMY_MODES else DEFAULT_AUTONOMY_MODE


def get_mode_policy(mode: Any) -> dict[str, Any]:
    normalized = normalize_autonomy_mode(mode)
    policies: dict[str, dict[str, Any]] = {
        "supervised_build": {
            "autonomy_mode": normalized,
            "autonomy_mode_status": "active",
            "autonomy_mode_reason": "Safest default mode. Forge may prepare bounded packages and recommendations, but pauses for approvals and higher-risk progression.",
            "allowed_actions": [
                "prepare_package",
                "recommend_next_step",
                "inspect_existing_state",
                "bounded_low_risk_step",
            ],
            "blocked_actions": [
                "project_switch",
                "auto_continue_pipeline",
                "unbounded_loop",
                "policy_self_modification",
                "mode_self_escalation",
            ],
            "approval_required_actions": [
                "decision",
                "eligibility",
                "release",
                "handoff",
                "execute",
                "project_switch",
            ],
            "escalation_threshold": "low",
        },
        "assisted_autopilot": {
            "autonomy_mode": normalized,
            "autonomy_mode_status": "active",
            "autonomy_mode_reason": "Forge may continue through bounded project steps automatically, but must stop for governance, approval, integrity, or elevated-risk triggers.",
            "allowed_actions": [
                "prepare_package",
                "recommend_next_step",
                "decision",
                "eligibility",
                "release",
                "handoff",
                "execute",
                "evaluate",
                "local_analysis",
                "project_switch",
            ],
            "blocked_actions": [
                "unbounded_loop",
                "policy_self_modification",
                "mode_self_escalation",
            ],
            "approval_required_actions": [
                "release",
                "handoff",
                "execute",
                "project_switch",
            ],
            "escalation_threshold": "guarded",
        },
        "low_risk_autonomous_development": {
            "autonomy_mode": normalized,
            "autonomy_mode_status": "active",
            "autonomy_mode_reason": "Forge may continue only through pre-approved low-risk development loops and must escalate anything ambiguous, blocked, risky, integrity-related, or approval-required.",
            "allowed_actions": [
                "prepare_package",
                "recommend_next_step",
                "decision",
                "eligibility",
                "release",
                "handoff",
                "execute",
                "evaluate",
                "local_analysis",
                "project_switch",
            ],
            "blocked_actions": [
                "policy_self_modification",
                "mode_self_escalation",
                "unbounded_loop",
            ],
            "approval_required_actions": [
                "release",
                "handoff",
                "execute",
                "project_switch",
            ],
            "escalation_threshold": "guarded",
        },
    }
    return dict(policies[normalized])


def build_autonomy_mode_state(*, mode: Any, reason: str | None = None) -> dict[str, Any]:
    policy = get_mode_policy(mode)
    if reason:
        policy["autonomy_mode_reason"] = str(reason).strip()
    return policy


def action_allowed(*, mode: Any, action: str) -> bool:
    normalized_action = str(action or "").strip().lower()
    if normalized_action in ("pause", "escalate", "stop", "operator_review", "continue"):
        return True
    policy = get_mode_policy(mode)
    allowed = _clean_list(policy.get("allowed_actions"))
    blocked = _clean_list(policy.get("blocked_actions"))
    if normalized_action in blocked:
        return False
    return normalized_action in allowed


def evaluate_mode_transition(
    *,
    mode: Any,
    proposed_action: str,
    package: dict[str, Any] | None = None,
    routing_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = normalize_autonomy_mode(mode)
    action = str(proposed_action or "pause").strip().lower()
    pkg = package or {}
    routing = routing_result or {}
    policy = get_mode_policy(normalized_mode)
    package_requires_human = bool(pkg.get("requires_human_approval"))
    aegis_decision = str(pkg.get("aegis_decision") or "").strip().lower()
    handoff_decision = str(((pkg.get("handoff_aegis_result") or {}).get("aegis_decision") or "")).strip().lower()
    risk_band = str(((pkg.get("evaluation_summary") or {}).get("failure_risk_band") or "")).strip().lower()
    local_next = str(((pkg.get("local_analysis_summary") or {}).get("suggested_next_action") or "")).strip().lower()
    routing_action = str(routing.get("selected_action") or "").strip().lower()

    if normalized_mode == "supervised_build" and action in (
        "decision",
        "eligibility",
        "release",
        "handoff",
        "execute",
        "evaluate",
        "local_analysis",
        "project_switch",
    ):
        return {
            **policy,
            "action_allowed": False,
            "requires_operator_approval": True,
            "must_pause": True,
            "must_escalate": False,
            "effective_action": "pause",
            "mode_gate_reason": f"supervised_build_requires_operator_for_{action}",
        }

    if not action_allowed(mode=normalized_mode, action=action):
        return {
            **policy,
            "action_allowed": False,
            "requires_operator_approval": True,
            "must_pause": True,
            "must_escalate": True,
            "effective_action": "operator_review",
            "mode_gate_reason": f"mode_policy_blocks_{action or 'unknown_action'}",
        }

    if package_requires_human or aegis_decision == "approval_required" or handoff_decision == "approval_required":
        return {
            **policy,
            "action_allowed": False,
            "requires_operator_approval": True,
            "must_pause": True,
            "must_escalate": True,
            "effective_action": "operator_review",
            "mode_gate_reason": "approval_required_unresolved",
        }

    if risk_band in ("high", "critical") or local_next in (
        "investigate_failure",
        "initiate_rollback_repair",
        "review_integrity",
    ):
        return {
            **policy,
            "action_allowed": False,
            "requires_operator_approval": True,
            "must_pause": True,
            "must_escalate": True,
            "effective_action": "operator_review",
            "mode_gate_reason": "risk_or_integrity_escalation_required",
        }

    if normalized_mode == "low_risk_autonomous_development":
        confidence_band = str(routing.get("routing_confidence_band") or "").strip().lower()
        if routing_action == "project_switch":
            return {
                **policy,
                "action_allowed": False,
                "requires_operator_approval": True,
                "must_pause": True,
                "must_escalate": True,
                "effective_action": "operator_review",
                "mode_gate_reason": "low_risk_mode_does_not_autoswitch_projects",
            }
        if risk_band not in ("", "low") or confidence_band in ("low", "guarded"):
            return {
                **policy,
                "action_allowed": False,
                "requires_operator_approval": True,
                "must_pause": True,
                "must_escalate": True,
                "effective_action": "operator_review",
                "mode_gate_reason": "low_risk_mode_requires_high_confidence_low_risk",
            }

    return {
        **policy,
        "action_allowed": True,
        "requires_operator_approval": False,
        "must_pause": False,
        "must_escalate": False,
        "effective_action": action or "continue",
        "mode_gate_reason": "mode_policy_allows_action",
    }
