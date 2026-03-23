"""
NEXUS execution authority model.

Defines the bounded responsibilities of core FORGE components and offers a
deterministic enforcement helper that can be attached to records/packages.
"""

from __future__ import annotations

from typing import Any


AUTHORITY_MODEL_VERSION = "1.0"
AUTHORITY_DENIAL_STATUS = "denied"
ACTOR_COMPONENT_HINTS: dict[str, str] = {
    "nexus": "nexus",
    "workflow": "nexus",
    "helix": "helix",
    "helios": "helios",
    "aegis": "aegis",
    "openclaw": "openclaw",
    "nemoclaw": "nemoclaw",
    "abacus": "abacus",
    "cursor": "cursor_bridge",
}

COMPONENT_AUTHORITIES: dict[str, dict[str, Any]] = {
    "nexus": {
        "role": "orchestration_only",
        "allowed_actions": {
            "orchestrate_workflow",
            "route_dispatch",
            "build_execution_package",
            "record_learning",
            "enforce_contracts",
            "read_project_memory",
            "read_cross_project_memory",
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
    "helios": {
        "role": "advisory_planning_only",
        "allowed_actions": {
            "read_project_memory",
            "read_cross_project_memory",
            "recommend_next_action",
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
            "write_project_memory",
            "write_cross_project_memory",
        },
    },
    "abacus": {
        "role": "evaluation_only",
        "allowed_actions": {
            "evaluate_execution",
            "score_execution",
            "write_project_memory",
            "write_cross_project_memory",
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


def infer_component_name(value: Any) -> str:
    text = _normalize_component_name(value)
    if not text:
        return ""
    if text in COMPONENT_AUTHORITIES:
        return text
    for hint, component_name in ACTOR_COMPONENT_HINTS.items():
        if hint in text:
            return component_name
    return text


def build_authority_denial(
    *,
    denied_action: str | None,
    actor: str | None,
    authority_trace: dict[str, Any] | None,
    required_role: str | None = None,
    allowed_roles: list[str] | tuple[str, ...] | set[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    roles = [str(item).strip() for item in (allowed_roles or []) if str(item).strip()]
    return {
        "status": AUTHORITY_DENIAL_STATUS,
        "denied_action": str(denied_action or "").strip().lower(),
        "actor": str(actor or (authority_trace or {}).get("component_name") or "").strip(),
        "required_role": str(required_role or "").strip(),
        "allowed_roles": roles,
        "reason": str(reason or (authority_trace or {}).get("decision_reason") or "").strip(),
        "authority_trace": dict(authority_trace or {}),
    }


def enforce_component_authority(
    *,
    component_name: str | None = None,
    actor: str | None = None,
    requested_actions: list[str] | tuple[str, ...] | set[str] | str | None = None,
    allowed_components: list[str] | tuple[str, ...] | set[str] | None = None,
    authority_context: dict[str, Any] | None = None,
    denied_action: str | None = None,
    reason_override: str | None = None,
) -> dict[str, Any]:
    component = _normalize_component_name(component_name) or infer_component_name(actor)
    allowed_component_list = [_normalize_component_name(item) for item in (allowed_components or []) if _normalize_component_name(item)]
    base_context = dict(authority_context or {})
    if allowed_component_list:
        base_context["allowed_components"] = allowed_component_list

    authority_trace = evaluate_component_authority(
        component_name=component,
        requested_actions=requested_actions,
        authority_context=base_context,
    )
    requested = _normalize_requested_actions(requested_actions)
    denial_action = str(denied_action or (authority_trace.get("denied_actions") or requested or [""])[0]).strip().lower()

    if allowed_component_list and component not in allowed_component_list:
        allowed_roles = [
            str((COMPONENT_AUTHORITIES.get(item) or {}).get("role") or "").strip()
            for item in allowed_component_list
            if str((COMPONENT_AUTHORITIES.get(item) or {}).get("role") or "").strip()
        ]
        reason = str(
            reason_override
            or f"Actor '{actor or component}' is not authorized for '{denial_action or 'requested_action'}'; allowed components: {', '.join(allowed_component_list)}."
        )
        authority_trace = {
            **authority_trace,
            "authority_status": "blocked",
            "violation_detected": True,
            "decision_reason": reason,
        }
        return {
            "status": AUTHORITY_DENIAL_STATUS,
            "actor": str(actor or component or "").strip(),
            "component_name": component,
            "authority_trace": authority_trace,
            "authority_denial": build_authority_denial(
                denied_action=denial_action,
                actor=actor or component,
                authority_trace=authority_trace,
                allowed_roles=allowed_roles,
                reason=reason,
            ),
        }

    if authority_trace.get("authority_status") != "authorized":
        role = str(authority_trace.get("component_role") or "").strip()
        reason = str(reason_override or authority_trace.get("decision_reason") or "")
        authority_trace = {
            **authority_trace,
            "decision_reason": reason,
        }
        return {
            "status": AUTHORITY_DENIAL_STATUS,
            "actor": str(actor or component or "").strip(),
            "component_name": component,
            "authority_trace": authority_trace,
            "authority_denial": build_authority_denial(
                denied_action=denial_action,
                actor=actor or component,
                authority_trace=authority_trace,
                required_role=role,
                reason=reason,
            ),
        }

    return {
        "status": "authorized",
        "actor": str(actor or component or "").strip(),
        "component_name": component,
        "authority_trace": authority_trace,
        "authority_denial": {},
    }


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


def enforce_component_authority_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return enforce_component_authority(**kwargs)
    except Exception as e:
        authority_trace = evaluate_component_authority_safe(
            component_name=kwargs.get("component_name"),
            requested_actions=kwargs.get("requested_actions"),
            authority_context=kwargs.get("authority_context"),
        )
        reason = f"Authority enforcement failed: {e}"
        authority_trace = {
            **authority_trace,
            "authority_status": "blocked",
            "violation_detected": True,
            "decision_reason": reason,
        }
        actor = str(kwargs.get("actor") or kwargs.get("component_name") or "").strip()
        denial_action = str(kwargs.get("denied_action") or (_normalize_requested_actions(kwargs.get("requested_actions")) or [""])[0]).strip().lower()
        return {
            "status": AUTHORITY_DENIAL_STATUS,
            "actor": actor,
            "component_name": _normalize_component_name(kwargs.get("component_name")) or infer_component_name(actor),
            "authority_trace": authority_trace,
            "authority_denial": build_authority_denial(
                denied_action=denial_action,
                actor=actor,
                authority_trace=authority_trace,
                reason=reason,
            ),
        }
