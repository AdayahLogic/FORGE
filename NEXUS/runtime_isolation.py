"""
NEXUS runtime isolation and sandbox posture layer (Phase 40).

Defines a normalized runtime isolation / sandbox contract. Honest posture reporting:
- Does NOT claim container/VM isolation when it does not exist.
- Does NOT fake network enforcement; uses posture fields only.
- Makes runtime safety materially stronger and more explicit.

Read-only; no execution capability. Consumes execution environment registry
and summaries; produces isolation posture for dashboard, release readiness,
and operator visibility.
"""

from __future__ import annotations

from typing import Any

# -----------------------------------------------------------------------------
# Isolation posture contract
# -----------------------------------------------------------------------------
# isolation_posture: "weak" | "bounded" | "restricted" | "isolated_planned" | "error_fallback"
# Scope statuses: "unrestricted" | "policy_bounded" | "restricted" | "planned" | "unknown"
# -----------------------------------------------------------------------------

ISOLATION_POSTURE_VALUES = ("weak", "bounded", "restricted", "isolated_planned", "error_fallback")
SCOPE_STATUS_VALUES = ("unrestricted", "policy_bounded", "restricted", "planned", "unknown")


def build_runtime_isolation_posture(
    *,
    execution_environment_summary: dict[str, Any] | None = None,
    runtime_target_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build normalized runtime isolation / sandbox posture.

    Consumes execution environment summary and runtime target summary.
    Returns honest posture: weak/bounded when only policy-level restrictions exist.
    Does NOT claim true isolation.

    Returns:
        isolation_posture: str
        file_scope_status: str
        network_scope_status: str
        secret_scope_status: str
        connector_scope_status: str
        mutation_scope_status: str
        rollback_posture: str
        isolation_reason: str
        runtime_restrictions: list[str]
        allowed_execution_domains: list[str]
        blocked_execution_domains: list[str]
        destructive_risk_posture: str
        generated_at: str
    """
    from datetime import datetime
    from NEXUS.execution_environment_registry import (
        list_active_environments,
        get_environment_definition,
        RUNTIME_TARGET_TO_ENVIRONMENT,
    )
    from NEXUS.runtime_target_registry import get_runtime_target_summary
    from NEXUS.registry import PROJECTS

    now = datetime.now().isoformat()
    exec_summary = execution_environment_summary or {}
    rt_summary = runtime_target_summary or get_runtime_target_summary()

    active_envs = exec_summary.get("active_environments") or list_active_environments()
    if not active_envs:
        return _fallback_isolation_posture(
            reason="No active execution environments.",
            generated_at=now,
        )

    # Derive posture from active environments (honest: no real isolation yet)
    worst_isolation = "weak"
    file_scope = "policy_bounded"
    network_scope = "unrestricted"
    secret_scope = "unknown"
    connector_scope = "unknown"
    mutation_scope = "policy_bounded"
    rollback_posture = "none"
    destructive_risk = "elevated"
    restrictions: list[str] = []
    allowed_domains: list[str] = []
    blocked_domains: list[str] = []

    for env_id in active_envs:
        env_def = get_environment_definition(env_id) or {}
        iso_level = str(env_def.get("isolation_level") or "none").strip().lower()
        mut_posture = str(env_def.get("mutation_posture") or "allowed").strip().lower()
        net_posture = str(env_def.get("network_posture") or "allowed").strip().lower()
        bounded = bool(env_def.get("bounded_execution", False))

        if iso_level in ("planned_isolated", "planned_container", "planned_external"):
            worst_isolation = _worst_isolation(worst_isolation, "isolated_planned")
        elif iso_level == "bounded":
            worst_isolation = _worst_isolation(worst_isolation, "bounded")
        else:
            worst_isolation = _worst_isolation(worst_isolation, "weak")

        if mut_posture in ("planned_restricted", "planned_none"):
            mutation_scope = "planned"
        elif mut_posture == "bounded":
            mutation_scope = "policy_bounded"
            restrictions.append("Mutation bounded by tool gateway and AEGIS.")
        else:
            mutation_scope = "unrestricted" if mutation_scope != "policy_bounded" else mutation_scope

        if net_posture in ("planned_restricted", "planned_none"):
            network_scope = "planned" if network_scope == "unrestricted" else network_scope
        elif net_posture == "restricted":
            network_scope = "restricted"
        else:
            network_scope = "unrestricted"
            restrictions.append("Network outbound: no runtime enforcement; policy-only.")

        if bounded:
            restrictions.append("Execution bounded by AEGIS and file_guard.")
            file_scope = "policy_bounded"

    # Project-scoped paths for allowed_execution_domains (honest: policy intent, not enforcement)
    project_paths = [str(p.get("path", "")) for p in PROJECTS.values() if p.get("path")]
    if project_paths:
        allowed_domains = project_paths[:10]
        restrictions.append("Project-scoped paths preferred; enforcement via policy.")

    # Secret/connector: no actual scoping implemented; honest unknown
    if not any(s in str(secret_scope) for s in ("restricted", "planned", "policy")):
        restrictions.append("Secret scope: not explicitly scoped; broad credential risk possible.")
    if not any(c in str(connector_scope) for c in ("restricted", "planned", "policy")):
        restrictions.append("Connector scope: not explicitly scoped; visibility limited.")

    # Rollback: no snapshot/rollback infra; honest none
    if rollback_posture == "none":
        restrictions.append("Rollback/snapshot: not implemented; destructive actions irreversible.")
        destructive_risk = "elevated"

    # Isolation reason
    if worst_isolation == "weak":
        isolation_reason = (
            "Active environments have no real isolation. "
            "Restrictions are policy-level (AEGIS, tool gateway, file_guard). "
            "No container/VM sandbox."
        )
    elif worst_isolation == "bounded":
        isolation_reason = (
            "Active environments are bounded by policy. "
            "No true runtime isolation; mutation and execution constrained by tool gateway."
        )
    elif worst_isolation == "isolated_planned":
        isolation_reason = (
            "Some planned environments would provide isolation; none active. "
            "Current execution remains policy-bounded."
        )
    else:
        isolation_reason = f"Isolation posture: {worst_isolation}. See runtime_restrictions."

    return {
        "isolation_posture": worst_isolation,
        "file_scope_status": file_scope,
        "network_scope_status": network_scope,
        "secret_scope_status": secret_scope,
        "connector_scope_status": connector_scope,
        "mutation_scope_status": mutation_scope,
        "rollback_posture": rollback_posture,
        "isolation_reason": isolation_reason,
        "runtime_restrictions": restrictions,
        "allowed_execution_domains": allowed_domains,
        "blocked_execution_domains": blocked_domains,
        "destructive_risk_posture": destructive_risk,
        "generated_at": now,
    }


def _worst_isolation(a: str, b: str) -> str:
    """Return the least-safe isolation posture (weakest isolation) for conservative reporting."""
    order = {"weak": 0, "bounded": 1, "restricted": 2, "isolated_planned": 3, "error_fallback": -1}
    va = order.get(a, 0)
    vb = order.get(b, 0)
    if va < 0 or vb < 0:
        return "error_fallback"
    return a if va <= vb else b


def build_runtime_isolation_posture_safe(
    *,
    execution_environment_summary: dict[str, Any] | None = None,
    runtime_target_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_runtime_isolation_posture(
            execution_environment_summary=execution_environment_summary,
            runtime_target_summary=runtime_target_summary,
        )
    except Exception:
        from datetime import datetime
        return _fallback_isolation_posture(
            reason="Runtime isolation posture evaluation failed.",
            generated_at=datetime.now().isoformat(),
        )


def _fallback_isolation_posture(reason: str, generated_at: str) -> dict[str, Any]:
    """Error fallback shape; preserves contract."""
    return {
        "isolation_posture": "error_fallback",
        "file_scope_status": "unknown",
        "network_scope_status": "unknown",
        "secret_scope_status": "unknown",
        "connector_scope_status": "unknown",
        "mutation_scope_status": "unknown",
        "rollback_posture": "unknown",
        "isolation_reason": reason,
        "runtime_restrictions": [reason],
        "allowed_execution_domains": [],
        "blocked_execution_domains": [],
        "destructive_risk_posture": "unknown",
        "generated_at": generated_at,
    }


def is_isolation_weak_or_unclear(posture: dict[str, Any] | None) -> bool:
    """True if isolation posture is weak, error_fallback, or missing."""
    if not posture or not isinstance(posture, dict):
        return True
    p = str(posture.get("isolation_posture") or "").strip().lower()
    return p in ("weak", "error_fallback", "")
