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
) -> dict[str, Any]:
    """
    Build a stable AEGIS contract result (the single source of truth shape).
    """
    decision = _normalize_decision(aegis_decision)
    mode = _normalize_action_mode(action_mode)
    scope = str(aegis_scope or _SCOPE_DEFAULT).strip().lower() or _SCOPE_DEFAULT

    ts = timestamp if isinstance(timestamp, str) and timestamp.strip() else _iso_now()

    return {
        "aegis_contract_version": "1.0",
        "aegis_decision": decision,
        "aegis_reason": str(aegis_reason or "").strip(),
        "aegis_scope": scope,
        "action_mode": mode,
        "project_name": project_name if project_name not in ("", None) else None,
        "project_path": project_path if project_path not in ("", None) else None,
        "requires_human_review": bool(requires_human_review) if decision == "approval_required" else bool(requires_human_review),
        "timestamp": ts,
    }


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
        }

