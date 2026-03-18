from __future__ import annotations

from typing import Any


def route_to_approval(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Integrate with existing approval flow (best-effort).

    For MVP, we simply return a route marker; actual routing is enforced by
    the execution adapter/dispatcher simulation which sets next_action.
    """
    req = request or {}
    return {
        "route": "human_review",
        "context": {
            "runtime_target_id": req.get("runtime_target_id"),
            "project_path": req.get("project_path"),
        },
    }

