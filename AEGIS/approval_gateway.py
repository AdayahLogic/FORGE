from __future__ import annotations

from typing import Any


def route_to_approval(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Route/mark the action for human approval in the existing workflow.

    IMPORTANT: This is an approval *routing marker/signal* for the workflow.
    It is not a full approval service or decision authority.

    Phase 13: structured approval metadata for AEGIS output.
    """
    req = request or {}
    context = {
        "runtime_target_id": req.get("runtime_target_id"),
        "project_path": req.get("project_path"),
        "tool_family": req.get("tool_family"),
    }
    return {
        "route": "human_review",
        "marker_only": True,
        "marker_reason": "AEGIS approval_required signal (routing marker only; not a full approval service).",
        "context": context,
        "approval_signal_only": True,
        "approval_reason": "Approval required by policy; routing marker only.",
        "approval_scope": "runtime_dispatch_only",
    }

