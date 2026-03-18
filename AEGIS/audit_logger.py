from __future__ import annotations

from typing import Any

from NEXUS.logging_engine import log_system_event


def log_decision(*, request: dict[str, Any] | None, decision: str, reason: str, approval_route: dict[str, Any] | None = None) -> None:
    """
    Log all AEGIS decisions (best-effort, never raises).
    """
    try:
        req = request or {}
        meta = {
            "runtime_target_id": req.get("runtime_target_id"),
            "environment": req.get("environment"),
            "project_scoped": bool(req.get("project_path")),
            "decision": decision,
        }
        if approval_route:
            meta["approval_route"] = approval_route.get("route") or None
        log_system_event(
            project=req.get("project_name") if isinstance(req.get("project_name"), str) else None,
            subsystem="aegis",
            action="evaluate_action",
            status="ok" if decision == "allow" else "blocked",
            reason=reason,
            metadata=meta,
        )
    except Exception:
        # Never break the execution flow due to logging.
        pass

