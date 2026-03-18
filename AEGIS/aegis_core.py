from __future__ import annotations

from typing import Any

from AEGIS import approval_gateway, audit_logger, environment_controller, policy_engine, workspace_manager


def evaluate_action(request: dict[str, Any]) -> dict[str, Any]:
    """
    AEGIS MVP core: evaluate a requested action and return allow/deny/approval_required.

    Required call chain (per spec):
      - policy_engine
      - workspace_manager
      - approval_gateway
      - audit_logger
    """
    req = request or {}
    # Environment is used by policy rules.
    req_env = dict(req)
    req_env["environment"] = environment_controller.determine_environment(req_env)

    # 1) policy_engine
    policy_res = policy_engine.evaluate_policy(req_env)
    decision = policy_res.get("decision") or "allow"
    reason = policy_res.get("reason") or ""

    # 2) workspace_manager
    ws_res = workspace_manager.validate_workspace(req_env)
    if not ws_res.get("ok", False):
        decision = "deny"
        reason = ws_res.get("reason") or "Workspace validation failed."

    # 3) approval_gateway (only for approval_required)
    approval_route: dict[str, Any] | None = None
    if decision == "approval_required":
        approval_route = approval_gateway.route_to_approval(req_env)

    # 4) audit_logger (always)
    audit_logger.log_decision(
        request=req_env,
        decision=decision,
        reason=reason,
        approval_route=approval_route,
    )

    return {
        "aegis_decision": decision,
        "aegis_reason": reason,
        "approval_route": approval_route,
    }


def evaluate_action_safe(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Safe wrapper: never raises.
    """
    try:
        return evaluate_action(request or {})
    except Exception as e:
        # Conservative behavior: stop execution if AEGIS fails.
        return {
            "aegis_decision": "deny",
            "aegis_reason": f"AEGIS evaluation failed: {e}",
            "approval_route": None,
        }

