"""
NEXUS change safety gate for self-improvement work (planning only).

Evaluates whether a self-improvement change should be reviewed/blocked
before any execution. No actual changes are performed.
"""

from __future__ import annotations

from typing import Any


CORE_TARGET_KEYWORDS = [
    "workflow",
    "command_surface",
    "launcher",
    "autonomous",
    "autonomy",
    "reexecution",
    "registry",
    "execution_policy",
    "runtime_dispatcher",
    "production_guardrails",
    "governance",
    "enforcement",
    "studio_driver",
    "cycle_scheduler",
    "state",
]


def _is_core_area(target_area: str | None = None) -> bool:
    ta = (target_area or "").strip().lower()
    if not ta:
        return False
    return any(k in ta for k in CORE_TARGET_KEYWORDS)


def evaluate_change_gate(
    *,
    target_area: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    project_name: str | None = None,
    core_files_touched: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Return stable gate result:
    {
      change_gate_status,
      change_gate_reason,
      execution_allowed,
      review_required
    }
    """
    ta = (target_area or "").strip()
    cat = (category or "").strip().lower()
    pr = (priority or "").strip().lower()
    pn = (project_name or "").strip().lower()

    core_touch = bool(core_files_touched) or _is_core_area(ta)

    # Conservative defaults: self-improvement should not execute in this sprint.
    if core_touch or pr == "high":
        return {
            "change_gate_status": "review_required",
            "change_gate_reason": "Target area is core/high-risk; review required; execution not allowed.",
            "execution_allowed": False,
            "review_required": True,
        }

    # Low-risk: still keep execution disabled (planning-only sprint).
    if cat in ("monitoring", "productization", "hardening", "runtime"):
        return {
            "change_gate_status": "allowed" if pr in ("low", "medium") else "review_required",
            "change_gate_reason": "Non-core change; planning allowed but execution remains disabled in this sprint.",
            "execution_allowed": False,
            "review_required": pr in ("medium", "low") is False,
        }

    # Unknown category: block conservatively.
    return {
        "change_gate_status": "blocked",
        "change_gate_reason": "Unknown/unspecified change category; blocked for safety.",
        "execution_allowed": False,
        "review_required": True,
    }


def evaluate_change_gate_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        res = evaluate_change_gate(**kwargs)
        # Ensure required stable defaults.
        res.setdefault("change_gate_status", "blocked")
        res.setdefault("change_gate_reason", "")
        res.setdefault("execution_allowed", False)
        res.setdefault("review_required", True)
        return res
    except Exception:
        return {
            "change_gate_status": "error_fallback",
            "change_gate_reason": "Change gate evaluation failed.",
            "execution_allowed": False,
            "review_required": True,
        }

