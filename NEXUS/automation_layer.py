"""
NEXUS automation evaluation layer.

Evaluates dispatch/execution outcomes and recommends the next safe orchestration
action. Recommendation-only: no execution, no side effects.
"""

from __future__ import annotations

from typing import Any


def evaluate_automation_outcome(
    *,
    dispatch_status: str | None = None,
    runtime_execution_status: str | None = None,
    dispatch_result: dict[str, Any] | None = None,
    dispatch_plan: dict[str, Any] | None = None,
    dispatch_plan_summary: dict[str, Any] | None = None,
    active_project: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate current automation outcome and recommend next action.

    Returns stable schema:
    {
      "automation_status": "...",
      "recommended_action": "...",
      "reason": "...",
      "human_review_required": bool,
      "fallback_runtime_target": str | None,
      "followup_items": list
    }
    """
    ds = (dispatch_status or "").strip().lower()
    es = (runtime_execution_status or "").strip().lower()
    dr = dispatch_result or {}
    dps = dispatch_plan_summary or {}

    fallback_runtime_target = None
    followup_items: list[dict[str, Any]] = []

    # Core rules (compact, centralized)
    if ds == "accepted" and es == "simulated_execution":
        return {
            "automation_status": "followup_recommended",
            "recommended_action": "await_runtime_enablement",
            "reason": "Runtime accepted dispatch but execution is simulated in this step.",
            "human_review_required": False,
            "fallback_runtime_target": None,
            "followup_items": [],
        }

    if ds == "skipped":
        return {
            "automation_status": "human_review_required",
            "recommended_action": "inspect_dispatch_readiness",
            "reason": "Dispatch skipped; dispatch plan not ready for dispatch.",
            "human_review_required": True,
            "fallback_runtime_target": None,
            "followup_items": [
                {"item": "Review dispatch_plan_summary and readiness fields."},
            ],
        }

    if ds == "no_adapter":
        fallback_runtime_target = "local"
        return {
            "automation_status": "fallback_recommended",
            "recommended_action": "select_supported_runtime",
            "reason": "No runtime adapter available for selected runtime target.",
            "human_review_required": True,
            "fallback_runtime_target": fallback_runtime_target,
            "followup_items": [
                {"item": "Select a supported runtime target (local/cursor/codex)."},
            ],
        }

    if ds == "error":
        msg = str(dr.get("message") or "Dispatch error.")
        return {
            "automation_status": "human_review_required",
            "recommended_action": "inspect_dispatch_error",
            "reason": msg,
            "human_review_required": True,
            "fallback_runtime_target": None,
            "followup_items": [
                {"item": "Inspect dispatch_result.errors and runtime logs if available."},
            ],
        }

    if es == "blocked":
        return {
            "automation_status": "human_review_required",
            "recommended_action": "review_runtime_blockers",
            "reason": "Runtime execution is blocked.",
            "human_review_required": True,
            "fallback_runtime_target": None,
            "followup_items": [
                {"item": "Review policy/approval requirements and unblock safely."},
            ],
        }

    # Default: no-op / unknown
    summary_hint = dps.get("dispatch_planning_status") or ""
    return {
        "automation_status": "no_action",
        "recommended_action": "none",
        "reason": f"No automation action required. {summary_hint}".strip(),
        "human_review_required": False,
        "fallback_runtime_target": None,
        "followup_items": followup_items,
    }


def evaluate_automation_outcome_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises, returns error_fallback on exception."""
    try:
        return evaluate_automation_outcome(**kwargs)
    except Exception as e:
        return {
            "automation_status": "error_fallback",
            "recommended_action": "inspect_automation_error",
            "reason": str(e),
            "human_review_required": True,
            "fallback_runtime_target": None,
            "followup_items": [{"item": "Automation evaluation failed; inspect error."}],
        }

