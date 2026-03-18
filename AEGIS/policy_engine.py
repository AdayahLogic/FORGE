from __future__ import annotations

from typing import Any

from AEGIS.environment_controller import ENV_PRODUCTION, ENV_STAGING


# Phase 7 v1 (MVP): dict-based policy model.
# Rules are intentionally simple and conservative to avoid breaking flow.
DEFAULT_POLICY: dict[str, Any] = {
    "deny_when_missing_project_path": True,
    "approval_required_in_production": True,
    "approval_required_for_external_runtimes": ["cloud_worker", "remote_worker", "container_worker"],
    "approval_required_in_staging": False,
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

    project_path = req.get("project_path")
    if pol.get("deny_when_missing_project_path", True) and not project_path:
        return {"decision": "deny", "reason": "Missing project_path; refusing to scope workspace."}

    environment = str(req.get("environment") or "").strip().lower()
    runtime_target_id = str(req.get("runtime_target_id") or "").strip().lower()

    if environment == ENV_PRODUCTION and pol.get("approval_required_in_production", True):
        return {"decision": "approval_required", "reason": "AEGIS policy: approval required in production."}

    if environment == ENV_STAGING and pol.get("approval_required_in_staging", False):
        return {"decision": "approval_required", "reason": "AEGIS policy: approval required in staging."}

    external_runtimes = [str(x).strip().lower() for x in (pol.get("approval_required_for_external_runtimes") or []) if str(x).strip()]
    if runtime_target_id in external_runtimes:
        return {"decision": "approval_required", "reason": f"AEGIS policy: approval required for runtime '{runtime_target_id}'."}

    return {"decision": "allow", "reason": "AEGIS policy allows the action under current MVP rules."}

