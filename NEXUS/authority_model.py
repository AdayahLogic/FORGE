"""
NEXUS execution authority model.

Defines the bounded responsibilities of core FORGE components and offers a
deterministic enforcement helper that can be attached to records/packages.
"""

from __future__ import annotations

from typing import Any


AUTHORITY_MODEL_VERSION = "1.0"

COMPONENT_AUTHORITIES: dict[str, dict[str, Any]] = {
    "nexus": {
        "role": "orchestration_only",
        "allowed_actions": {
            "orchestrate_workflow",
            "route_dispatch",
            "build_execution_package",
            "record_learning",
            "enforce_contracts",
        },
    },
    "helix": {
        "role": "generation_only",
        "allowed_actions": {
            "generate_plan",
            "generate_code",
            "validate_generation",
            "produce_risk_flags",
            "package_generation_output",
        },
    },
    "aegis": {
        "role": "approval_authority",
        "allowed_actions": {
            "approve_execution",
            "deny_execution",
            "require_review",
            "enforce_policy",
        },
    },
    "openclaw": {
        "role": "execution_only",
        "allowed_actions": {
            "execute_package",
            "produce_execution_receipt",
        },
    },
    "nemoclaw": {
        "role": "advisory_only",
        "allowed_actions": {
            "analyze_locally",
            "recommend_next_action",
        },
    },
    "abacus": {
        "role": "evaluation_only",
        "allowed_actions": {
            "evaluate_execution",
            "score_execution",
        },
    },
    "cursor_bridge": {
        "role": "generation_bridge_only",
        "allowed_actions": {
            "prepare_ide_handoff",
            "package_generation_output",
        },
    },
}


def _normalize_component_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_requested_actions(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = str(item or "").strip().lower()
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def evaluate_component_authority(
    *,
    component_name: str | None,
    requested_actions: list[str] | tuple[str, ...] | set[str] | str | None = None,
    authority_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deterministically evaluate whether a component is acting within its role.
    """
    component = _normalize_component_name(component_name)
    requested = _normalize_requested_actions(requested_actions)
    profile = COMPONENT_AUTHORITIES.get(component, {})
    allowed = sorted(str(x) for x in (profile.get("allowed_actions") or set()))
    denied = [action for action in requested if action not in allowed]
    status = "authorized" if component and not denied else "blocked"
    role = str(profile.get("role") or "unknown")

    if not component:
        reason = "Component name is required to evaluate authority."
    elif not profile:
        reason = f"Authority model has no profile for component '{component}'."
    elif denied:
        reason = f"Component '{component}' exceeded authority for action(s): {', '.join(denied)}."
    else:
        reason = f"Component '{component}' remained within role '{role}'."

    return {
        "authority_model_version": AUTHORITY_MODEL_VERSION,
        "component_name": component,
        "component_role": role,
        "requested_actions": requested,
        "allowed_actions": allowed,
        "denied_actions": denied,
        "authority_status": status,
        "violation_detected": bool(denied),
        "decision_reason": reason,
        "authority_context": dict(authority_context or {}),
    }


def evaluate_component_authority_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return evaluate_component_authority(**kwargs)
    except Exception as e:
        return {
            "authority_model_version": AUTHORITY_MODEL_VERSION,
            "component_name": _normalize_component_name(kwargs.get("component_name")),
            "component_role": "unknown",
            "requested_actions": _normalize_requested_actions(kwargs.get("requested_actions")),
            "allowed_actions": [],
            "denied_actions": [],
            "authority_status": "blocked",
            "violation_detected": True,
            "decision_reason": f"Authority evaluation failed: {e}",
            "authority_context": dict(kwargs.get("authority_context") or {}),
        }
