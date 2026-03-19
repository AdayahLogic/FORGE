from __future__ import annotations

from typing import Any

from AEGIS.environment_controller import ENV_LOCAL_DEV, ENV_PRODUCTION, ENV_STAGING


# Phase 7 v1 (MVP): dict-based policy model.
# Phase 13: extended with action/tool families (evaluation, runtime_dispatch, file_read, file_write, shell_*, git_status).
DEFAULT_POLICY: dict[str, Any] = {
    "deny_when_missing_project_path": True,
    "approval_required_in_production": True,
    "approval_required_for_external_runtimes": ["cloud_worker", "remote_worker", "container_worker"],
    "approval_required_in_staging": False,
    "allowed_tool_families": ["evaluation", "runtime_dispatch", "file_read", "file_write", "shell_test", "shell_lint", "shell_build", "git_status"],
}


def evaluate_policy(request: dict[str, Any] | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Return stable policy decision:
    {
      "decision": "allow" | "deny" | "approval_required",
      "reason": "..."
    }
    """
    req = request or {}
    pol = policy or DEFAULT_POLICY

    action_mode = str(req.get("action_mode") or "execution").strip().lower()
    tool_family = str(req.get("tool_family") or "").strip().lower()
    project_path = req.get("project_path")
    environment = str(req.get("environment") or "").strip().lower()
    runtime_target_id = str(req.get("runtime_target_id") or "").strip().lower()

    # Tool family allowlist: unknown family is deny for tool requests.
    if tool_family:
        allowed = [str(x).strip().lower() for x in (pol.get("allowed_tool_families") or []) if str(x).strip()]
        if allowed and tool_family not in allowed:
            return {"decision": "deny", "reason": f"AEGIS policy: tool_family '{tool_family}' not in allowlist."}

    # Action-mode-aware missing project scope behavior:
    # - evaluation: allow (do not auto-deny) because we may be doing inspection only
    # - execution/mutation: deny by default to avoid unsafe workspace operations
    # - file_write: require project_path
    if pol.get("deny_when_missing_project_path", True) and not project_path:
        if action_mode == "evaluation":
            return {
                "decision": "allow",
                "reason": "AEGIS policy: missing project_path in evaluation mode; allowing evaluation without workspace scoping.",
            }
        if action_mode in ("file_read", "file_write") or tool_family in ("file_read", "file_write"):
            return {"decision": "deny", "reason": "AEGIS policy: file_read/file_write require project_path."}
        return {"decision": "deny", "reason": "AEGIS policy: missing project_path; refusing to scope workspace for execution/mutation."}

    # Production/staging/external runtime (unchanged)
    if environment == ENV_PRODUCTION and pol.get("approval_required_in_production", True):
        return {"decision": "approval_required", "reason": "AEGIS policy: approval required in production."}

    if environment == ENV_STAGING and pol.get("approval_required_in_staging", False):
        return {"decision": "approval_required", "reason": "AEGIS policy: approval required in staging."}

    external_runtimes = [str(x).strip().lower() for x in (pol.get("approval_required_for_external_runtimes") or []) if str(x).strip()]
    if runtime_target_id in external_runtimes:
        return {"decision": "approval_required", "reason": f"AEGIS policy: approval required for runtime '{runtime_target_id}'."}

    # Shell/git families: allow in local_dev within scope; in production require approval (already handled above).
    if tool_family in ("shell_test", "shell_lint", "shell_build", "git_status"):
        if environment == ENV_LOCAL_DEV and project_path:
            return {"decision": "allow", "reason": "AEGIS policy: allowlisted shell/git family in local_dev with project scope."}
        if environment in (ENV_STAGING, ENV_PRODUCTION):
            return {"decision": "approval_required", "reason": f"AEGIS policy: shell/git family '{tool_family}' requires approval outside local_dev."}

    return {"decision": "allow", "reason": "AEGIS policy allows the action under current MVP rules."}

