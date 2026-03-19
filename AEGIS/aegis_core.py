from __future__ import annotations

from typing import Any

from AEGIS import approval_gateway, audit_logger, environment_controller, policy_engine, workspace_manager
from AEGIS.aegis_contract import build_aegis_result, build_aegis_result_safe


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

    tool_family = str(req.get("tool_family") or "").strip() or None

    # Environment is used by policy rules.
    req_env = dict(req)
    req_env["environment"] = environment_controller.determine_environment(req_env)
    req_env["action_mode"] = action_mode
    req_env["aegis_scope"] = aegis_scope
    if tool_family:
        req_env["tool_family"] = tool_family

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
    workspace_valid: bool | None = None
    if not (action_mode == "evaluation" and not project_path):
        ws_res = workspace_manager.validate_workspace(req_env)
        workspace_valid = bool(ws_res.get("ok", False))
        if not workspace_valid:
            decision = "deny"
            reason = ws_res.get("reason") or "Workspace validation failed."

    # 2b) file_guard for mutation/file paths when candidate paths provided (Phase 13)
    file_guard_status: str | None = None
    if decision == "allow" and (action_mode == "mutation" or tool_family in ("file_read", "file_write")):
        candidate_paths = req.get("candidate_paths") or req.get("requested_writes") or req.get("requested_reads")
        if candidate_paths:
            try:
                from AEGIS.file_guard import evaluate_file_guard_safe
                fg = evaluate_file_guard_safe(
                    project_path=project_path,
                    action_mode=action_mode,
                    requested_reads=req.get("requested_reads") or (candidate_paths if tool_family == "file_read" else []),
                    requested_writes=req.get("requested_writes") or (candidate_paths if action_mode == "mutation" or tool_family == "file_write" else []),
                )
                file_guard_status = fg.get("file_guard_status")
                if file_guard_status in ("deny", "error_fallback"):
                    decision = "deny"
                    reason = fg.get("file_guard_reason") or "File guard denied."
            except Exception:
                file_guard_status = "error_fallback"
                decision = "deny"
                reason = "File guard evaluation failed."

    # 3) approval_gateway (only for approval_required)
    approval_route: dict[str, Any] | None = None
    approval_signal_only: bool = True
    approval_reason: str | None = None
    approval_scope: str | None = None
    if decision == "approval_required":
        approval_route = approval_gateway.route_to_approval(req_env)
        approval_signal_only = bool(approval_route.get("approval_signal_only", True))
        approval_reason = approval_route.get("approval_reason")
        approval_scope = approval_route.get("approval_scope")
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

    return build_aegis_result(
        aegis_decision=decision,
        aegis_reason=reason,
        aegis_scope=aegis_scope,
        action_mode=action_mode,
        project_name=req.get("project_name"),
        project_path=req.get("project_path"),
        requires_human_review=requires_human_review,
        approval_required=(decision == "approval_required"),
        approval_signal_only=approval_signal_only,
        approval_reason=approval_reason,
        approval_scope=approval_scope,
        tool_family=tool_family,
        workspace_valid=workspace_valid,
        file_guard_status=file_guard_status,
    )


def evaluate_action_safe(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Safe wrapper: never raises.
    """
    try:
        return evaluate_action(request or {})
    except Exception as e:
        return build_aegis_result_safe(
            aegis_decision="error_fallback",
            aegis_reason=f"AEGIS evaluation failed: {e}",
            aegis_scope="runtime_dispatch_only",
            action_mode="execution",
            project_name=(request or {}).get("project_name"),
            project_path=(request or {}).get("project_path"),
            requires_human_review=True,
        )

