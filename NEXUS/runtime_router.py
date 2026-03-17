"""
NEXUS runtime routing evaluation layer.

Deterministic routing hints for runtime selection without replacing the existing
execution bridge / runtime target selector. Evaluation only; no execution.
"""

from __future__ import annotations

from typing import Any


def route_runtime(
    *,
    active_project: str | None = None,
    runtime_node: str | None = None,
    task_type: str | None = None,
    patch_request: dict[str, Any] | None = None,
    purpose: str | None = None,
    primary_tool: str | None = None,
    secondary_tool: str | None = None,
) -> dict[str, Any]:
    """
    Return stable shape:
    {
      runtime_router_status, selected_runtime, fallback_runtime,
      routing_reason, requires_human_review
    }
    """
    node = (runtime_node or "").strip().lower()
    tt = (task_type or "").strip().lower()
    p = (purpose or "").strip().lower()
    tool1 = (primary_tool or "").strip().lower()
    tool2 = (secondary_tool or "").strip().lower()
    has_patch = bool(patch_request) and isinstance(patch_request, dict)

    fallback = "local"

    # Repo-aware changes: prefer Cursor.
    if tool1 in ("file_modification", "diff_patch") or tool2 in ("file_modification", "diff_patch") or has_patch:
        return {
            "runtime_router_status": "routed",
            "selected_runtime": "cursor",
            "fallback_runtime": fallback,
            "routing_reason": "Repository-aware change requested (file_modification/diff_patch/patch_request).",
            "requires_human_review": True,
        }

    # Drafting/refactor/generation: prefer Codex (isolated drafting).
    if node == "coder" or tt in ("coding", "coder", "refactor", "generation", "drafting"):
        return {
            "runtime_router_status": "routed",
            "selected_runtime": "codex",
            "fallback_runtime": fallback,
            "routing_reason": "Isolated generation/refactor drafting request (coder/generation).",
            "requires_human_review": True,
        }

    # Default safe local.
    return {
        "runtime_router_status": "fallback_selected",
        "selected_runtime": fallback,
        "fallback_runtime": fallback,
        "routing_reason": "Defaulted to safe local runtime.",
        "requires_human_review": False,
    }


def route_runtime_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return route_runtime(**kwargs)
    except Exception:
        return {
            "runtime_router_status": "error_fallback",
            "selected_runtime": "local",
            "fallback_runtime": "local",
            "routing_reason": "Runtime routing failed.",
            "requires_human_review": True,
        }

