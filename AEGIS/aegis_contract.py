from __future__ import annotations

from datetime import datetime
from typing import Any


_DECISIONS = {"allow", "deny", "approval_required", "error_fallback"}
_SCOPE_DEFAULT = "runtime_dispatch_only"
_ACTION_MODES = {"evaluation", "execution", "mutation"}


def _iso_now() -> str:
    return datetime.now().isoformat()


def _normalize_decision(v: Any) -> str:
    s = "" if v is None else str(v).strip().lower()
    if s in _DECISIONS:
        return s
    # Legacy support: allow/deny only
    if s in {"ok", "allowed", "true"}:
        return "allow"
    if s in {"false", "blocked"}:
        return "deny"
    return "error_fallback"


def _normalize_action_mode(v: Any) -> str:
    s = "" if v is None else str(v).strip().lower()
    if s in _ACTION_MODES:
        return s
    if s in {"exec", "run"}:
        return "execution"
    return "evaluation"


def normalize_aegis_result(aegis_result: Any) -> dict[str, Any]:
    """
    Normalize any incoming AEGIS result into the stable contract shape.
    """
    raw: dict[str, Any] = aegis_result if isinstance(aegis_result, dict) else {}

    decision = _normalize_decision(raw.get("aegis_decision"))
    reason = str(raw.get("aegis_reason") or "").strip()
    scope = str(raw.get("aegis_scope") or _SCOPE_DEFAULT).strip().lower() or _SCOPE_DEFAULT
    action_mode = _normalize_action_mode(raw.get("action_mode"))

    project_name = raw.get("project_name")
    project_path = raw.get("project_path")
    if project_name == "":
        project_name = None
    if project_path == "":
        project_path = None

    requires_human_review = raw.get("requires_human_review")
    if isinstance(requires_human_review, bool):
        req_hr = requires_human_review
    else:
        req_hr = decision == "approval_required"

    ts = raw.get("timestamp")
    if not isinstance(ts, str) or not ts.strip():
        ts = _iso_now()

    approval_required = raw.get("approval_required")
    if approval_required is None:
        approval_required = decision == "approval_required"
    approval_signal_only = raw.get("approval_signal_only")
    if approval_signal_only is None:
        approval_signal_only = True
    approval_reason = raw.get("approval_reason")
    approval_scope = raw.get("approval_scope")
    tool_family = raw.get("tool_family")
    workspace_valid = raw.get("workspace_valid")
    file_guard_status = raw.get("file_guard_status")

    return {
        "aegis_contract_version": "1.0",
        "aegis_decision": decision,
        "aegis_reason": reason,
        "aegis_scope": scope,
        "action_mode": action_mode,
        "project_name": project_name if project_name is not None else None,
        "project_path": project_path if project_path is not None else None,
        "requires_human_review": bool(req_hr),
        "timestamp": ts,
        "approval_required": bool(approval_required),
        "approval_signal_only": bool(approval_signal_only),
        "approval_reason": str(approval_reason) if approval_reason is not None else None,
        "approval_scope": str(approval_scope) if approval_scope is not None else None,
        "tool_family": str(tool_family).strip() or None if tool_family is not None else None,
        "workspace_valid": bool(workspace_valid) if workspace_valid is not None else None,
        "file_guard_status": str(file_guard_status).strip() or None if file_guard_status is not None else None,
    }


def build_aegis_result(
    *,
    aegis_decision: str,
    aegis_reason: str,
    aegis_scope: str = _SCOPE_DEFAULT,
    action_mode: str = "evaluation",
    project_name: str | None = None,
    project_path: str | None = None,
    requires_human_review: bool = False,
    timestamp: str | None = None,
    approval_required: bool | None = None,
    approval_signal_only: bool | None = None,
    approval_reason: str | None = None,
    approval_scope: str | None = None,
    tool_family: str | None = None,
    workspace_valid: bool | None = None,
    file_guard_status: str | None = None,
) -> dict[str, Any]:
    """
    Build a stable AEGIS contract result (the single source of truth shape).
    Phase 13: optional approval metadata and enforcement details (contract remains backward compatible).
    """
    decision = _normalize_decision(aegis_decision)
    mode = _normalize_action_mode(action_mode)
    scope = str(aegis_scope or _SCOPE_DEFAULT).strip().lower() or _SCOPE_DEFAULT

    ts = timestamp if isinstance(timestamp, str) and timestamp.strip() else _iso_now()
    approval_req = approval_required if approval_required is not None else (decision == "approval_required")

    out: dict[str, Any] = {
        "aegis_contract_version": "1.0",
        "aegis_decision": decision,
        "aegis_reason": str(aegis_reason or "").strip(),
        "aegis_scope": scope,
        "action_mode": mode,
        "project_name": project_name if project_name not in ("", None) else None,
        "project_path": project_path if project_path not in ("", None) else None,
        "requires_human_review": bool(requires_human_review) if decision == "approval_required" else bool(requires_human_review),
        "timestamp": ts,
        "approval_required": bool(approval_req),
        "approval_signal_only": bool(approval_signal_only) if approval_signal_only is not None else True,
        "approval_reason": str(approval_reason) if approval_reason is not None else None,
        "approval_scope": str(approval_scope) if approval_scope is not None else None,
        "tool_family": str(tool_family).strip() or None if tool_family is not None else None,
        "workspace_valid": bool(workspace_valid) if workspace_valid is not None else None,
        "file_guard_status": str(file_guard_status).strip() or None if file_guard_status is not None else None,
    }
    return out


def build_aegis_result_safe(**kwargs: Any) -> dict[str, Any]:
    """
    Safe wrapper: never raises.
    """
    try:
        return build_aegis_result(**kwargs)
    except Exception as e:
        return {
            "aegis_contract_version": "1.0",
            "aegis_decision": "error_fallback",
            "aegis_reason": f"AEGIS contract build failed: {e}",
            "aegis_scope": _SCOPE_DEFAULT,
            "action_mode": "evaluation",
            "project_name": None,
            "project_path": None,
            "requires_human_review": True,
            "timestamp": _iso_now(),
            "approval_required": True,
            "approval_signal_only": True,
            "approval_reason": None,
            "approval_scope": None,
            "tool_family": None,
            "workspace_valid": None,
            "file_guard_status": None,
        }

