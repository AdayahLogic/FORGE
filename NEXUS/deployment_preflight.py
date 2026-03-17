"""
NEXUS deployment preflight evaluation.

Evaluation only: provides a deployment readiness signal. Does not trigger any
deployment action.
"""

from __future__ import annotations

from typing import Any


def evaluate_deployment_preflight(
    *,
    active_project: str | None = None,
    project_state: dict[str, Any] | None = None,
    guardrail_result: dict[str, Any] | None = None,
    launch_result: dict[str, Any] | None = None,
    runtime_router_result: dict[str, Any] | None = None,
    model_router_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Stable shape:
    {
      deployment_preflight_status,
      deployment_action,
      deployment_reason,
      deployment_allowed,
      review_required
    }
    """
    s = project_state or {}
    gr = guardrail_result or {}
    lr = launch_result or {}

    # Default: blocked or review_required; never triggers deployment.
    base = {
        "deployment_preflight_status": "blocked",
        "deployment_action": "none",
        "deployment_reason": "Deployment is evaluation-only and blocked by default.",
        "deployment_allowed": False,
        "review_required": True,
    }

    # Guardrails must be healthy.
    if gr and gr.get("launch_allowed") is False:
        return {
            **base,
            "deployment_preflight_status": "blocked",
            "deployment_reason": gr.get("guardrail_reason") or "Guardrails blocked execution; deployment preflight blocked.",
            "review_required": True,
        }

    # If we have evidence of a recent successful bounded run, allow "review_required".
    last_run = s.get("last_run_summary") if isinstance(s.get("last_run_summary"), dict) else {}
    has_artifacts = bool(s.get("implementation_file_path") or s.get("test_report_path") or s.get("docs_output_path"))
    ran = bool(lr.get("execution_started")) or bool(last_run.get("run_id")) or bool(last_run.get("runtime_execution_status"))

    if ran and has_artifacts:
        return {
            "deployment_preflight_status": "review_required",
            "deployment_action": "request_human_review",
            "deployment_reason": "Preflight suggests artifacts exist; deployment remains review-required.",
            "deployment_allowed": False,
            "review_required": True,
        }

    # Otherwise: blocked but with a more specific reason.
    if not ran:
        return {
            **base,
            "deployment_reason": "No recent execution evidence; deployment preflight blocked.",
        }
    if not has_artifacts:
        return {
            **base,
            "deployment_reason": "No deployment artifacts detected (implementation/tests/docs); deployment preflight blocked.",
        }

    return base


def evaluate_deployment_preflight_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return evaluate_deployment_preflight(**kwargs)
    except Exception:
        return {
            "deployment_preflight_status": "error_fallback",
            "deployment_action": "stop",
            "deployment_reason": "Deployment preflight evaluation failed.",
            "deployment_allowed": False,
            "review_required": True,
        }

