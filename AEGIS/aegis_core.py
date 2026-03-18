from __future__ import annotations

from datetime import datetime
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
    # AEGIS scope in this MVP is limited to runtime dispatch gating.
    aegis_scope = "runtime_dispatch_only"

    # Action mode is used to determine how to handle missing project scope.
    action_mode = str(req.get("action_mode") or "").strip().lower()
    if not action_mode:
        # Best-effort inference from action string.
        action = str(req.get("action") or "").strip().lower()
        if action in ("adapter_dispatch_call", "runtime_dispatch_call", "adapter_dispatch"):
            action_mode = "execution"
        elif action in ("mutation", "file_mutation", "patch_mutation"):
            action_mode = "mutation"
        else:
            action_mode = "evaluation"

    # Environment is used by policy rules.
    req_env = dict(req)
    req_env["environment"] = environment_controller.determine_environment(req_env)
    req_env["action_mode"] = action_mode
    req_env["aegis_scope"] = aegis_scope

    # 1) policy_engine
    policy_res = policy_engine.evaluate_policy(req_env)
    decision = policy_res.get("decision") or "allow"
    reason = policy_res.get("reason") or ""
    decision_norm = str(decision).strip().lower()
    allowed_decisions = {"allow", "deny", "approval_required", "error_fallback"}
    if decision_norm not in allowed_decisions:
        decision_norm = "error_fallback"
    decision = decision_norm

    # 2) workspace_manager (skip in evaluation mode when project_path is missing)
    project_path = req_env.get("project_path")
    if not (action_mode == "evaluation" and not project_path):
        ws_res = workspace_manager.validate_workspace(req_env)
        if not ws_res.get("ok", False):
            decision = "deny"
            reason = ws_res.get("reason") or "Workspace validation failed."

    # 3) approval_gateway (only for approval_required)
    approval_route: dict[str, Any] | None = None
    if decision == "approval_required":
        approval_route = approval_gateway.route_to_approval(req_env)
        # Honest marker wording for downstream display.
        reason = f"{reason} (routing marker only; not a full approval service)."

    # 4) audit_logger (always)
    audit_logger.log_decision(
        request=req_env,
        decision=decision,
        reason=reason,
        approval_route=approval_route,
    )

    requires_human_review = bool(decision == "approval_required" or req.get("requires_human_approval"))

    return {
        "aegis_decision": decision,
        "aegis_reason": reason,
        "aegis_scope": aegis_scope,
        "action_mode": action_mode,
        "project_name": req.get("project_name"),
        "project_path": req.get("project_path"),
        "requires_human_review": requires_human_review,
        "timestamp": datetime.now().isoformat(),
    }


def evaluate_action_safe(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Safe wrapper: never raises.
    """
    try:
        return evaluate_action(request or {})
    except Exception as e:
        # Conservative behavior: propagate error_fallback as AEGIS decision.
        return {
            "aegis_decision": "error_fallback",
            "aegis_reason": f"AEGIS evaluation failed: {e}",
            "aegis_scope": "runtime_dispatch_only",
            "action_mode": "execution",
            "project_name": (request or {}).get("project_name"),
            "project_path": (request or {}).get("project_path"),
            "requires_human_review": True,
            "timestamp": datetime.now().isoformat(),
        }

