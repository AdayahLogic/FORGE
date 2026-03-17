from __future__ import annotations

from typing import Any

from NEXUS.runtime_target_registry import get_runtime_target_summary


def build_runtime_infrastructure_summary(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Runtime infrastructure summary (operationally honest, local-first).

    Stable output shape:
    {
      "runtime_infrastructure_status": "...",
      "available_runtimes": [],
      "future_runtimes": [],
      "reason": "..."
    }
    """
    rt = runtime_target_summary or {}
    if not runtime_target_summary:
        rt = get_runtime_target_summary()

    available_runtimes = [str(x).strip() for x in (rt.get("active_names") or []) if x is not None]
    future_runtimes = [str(x).strip() for x in (rt.get("planned_names") or []) if x is not None]

    # In this sprint we don't attempt to "detect" external systems; we summarize
    # what the runtime registry expects and what is marked active.
    core_local_targets = {a.lower() for a in ("local", "cursor", "codex")}
    available_lower = {a.lower() for a in available_runtimes}

    if available_runtimes and available_lower.intersection(core_local_targets):
        status = "available"
        reason = f"Active runtime targets available: {sorted(available_runtimes)}."
    elif available_runtimes:
        status = "limited"
        reason = f"Active runtime targets limited: {sorted(available_runtimes)}."
    else:
        status = "error_fallback"
        reason = "No active runtime targets found in registry."

    return {
        "runtime_infrastructure_status": status,
        "available_runtimes": available_runtimes,
        "future_runtimes": future_runtimes,
        "reason": reason,
    }


def build_runtime_infrastructure_summary_safe(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_runtime_infrastructure_summary(runtime_target_summary=runtime_target_summary, **kwargs)
    except Exception:
        return {
            "runtime_infrastructure_status": "error_fallback",
            "available_runtimes": [],
            "future_runtimes": [],
            "reason": "Runtime infrastructure summary evaluation failed.",
        }

