"""
NEXUS production guardrails.

Deterministic safety checks before autonomy: recursion, state consistency,
and target support. No external dependencies; plain dicts; never raises in safe wrapper.
"""

from __future__ import annotations

from typing import Any
import os

from NEXUS.state_validator import validate_project_state_safe


def evaluate_guardrails(
    *,
    autonomous_launch: bool = False,
    project_state: dict[str, Any] | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    recovery_result: dict[str, Any] | None = None,
    reexecution_result: dict[str, Any] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
    target_project: str | None = None,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Evaluate launch safety. Returns stable shape:
    guardrail_status, guardrail_reason, launch_allowed, recursion_blocked, state_repair_recommended.
    """
    # Defaults must always be stable/non-None.
    base = {
        "guardrail_status": "passed",
        "guardrail_reason": "Guardrails passed.",
        "launch_allowed": True,
        "recursion_blocked": False,
        "state_repair_recommended": False,
    }

    qe = review_queue_entry or {}
    rec = recovery_result or {}
    rex = reexecution_result or {}
    driver = studio_driver_result or {}
    states = states_by_project or {}

    # 0) Validate project state (if provided). Integrate without removing existing logic.
    validation = validate_project_state_safe(project_state or {})
    v_status = (validation.get("validation_status") or "").strip().lower()
    if v_status == "blocked":
        return {
            **base,
            "guardrail_status": "blocked",
            "guardrail_reason": validation.get("validation_reason") or "Blocked by state validation.",
            "launch_allowed": False,
            "state_repair_recommended": bool(validation.get("state_repair_recommended")),
        }
    if v_status == "warning":
        base = {
            **base,
            "guardrail_status": "warning",
            "guardrail_reason": validation.get("validation_reason") or "State validation warning.",
            "state_repair_recommended": bool(validation.get("state_repair_recommended")),
        }

    # 0b) Environment check (only when an execution attempt is being made).
    if kwargs.get("execution_attempted", False) and not os.environ.get("OPENAI_API_KEY"):
        return {
            **base,
            "guardrail_status": "blocked",
            "guardrail_reason": "OPENAI_API_KEY missing; execution not allowed.",
            "launch_allowed": False,
        }

    # 1) Nested autonomous launch: if we're already in an autonomous run, block.
    if autonomous_launch and kwargs.get("launch_attempted", False):
        return {
            **base,
            "guardrail_status": "blocked",
            "guardrail_reason": "Nested autonomous launch blocked by no-recursion guard.",
            "launch_allowed": False,
            "recursion_blocked": True,
        }

    # 2) Contradictory state: queue_status == "cleared" but recovery still says await_approval / await_review
    queue_status = (qe.get("queue_status") or "").strip().lower()
    rec_status = (rec.get("recovery_status") or "").strip().lower()
    rec_action = (rec.get("recovery_action") or "").strip().lower()
    if queue_status == "cleared" and rec_status in ("waiting", "blocked") and rec_action in ("await_approval", "await_review"):
        return {
            **base,
            "guardrail_status": "warning",
            "guardrail_reason": "Queue cleared but recovery still indicates await_approval/await_review; state repair recommended.",
            "launch_allowed": False,
            "state_repair_recommended": True,
        }

    # 3) Studio driver wants to run but target project state lacks scheduler/recovery support (consistency check)
    if driver.get("execution_permitted") and target_project:
        state = states.get(target_project) or {}
        sched = (state.get("scheduler_result") or {}).get("scheduler_status") or ""
        r_status = (state.get("resume_result") or {}).get("resume_status") or ""
        sched_lower = sched.strip().lower() if isinstance(sched, str) else ""
        r_lower = r_status.strip().lower() if isinstance(r_status, str) else ""
        if sched_lower != "scheduled" and r_lower != "resumable":
            return {
                **base,
                "guardrail_status": "warning",
                "guardrail_reason": f"Target project '{target_project}' has no scheduler/resumable support; launch not allowed.",
                "launch_allowed": False,
            }

    # 4) Default: passed
    return base


def evaluate_guardrails_safe(
    autonomous_launch: bool = False,
    project_state: dict[str, Any] | None = None,
    review_queue_entry: dict[str, Any] | None = None,
    recovery_result: dict[str, Any] | None = None,
    reexecution_result: dict[str, Any] | None = None,
    studio_driver_result: dict[str, Any] | None = None,
    target_project: str | None = None,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    launch_attempted: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluate guardrails; never raises. On exception returns error_fallback result."""
    try:
        return evaluate_guardrails(
            autonomous_launch=autonomous_launch,
            project_state=project_state,
            review_queue_entry=review_queue_entry,
            recovery_result=recovery_result,
            reexecution_result=reexecution_result,
            studio_driver_result=studio_driver_result,
            target_project=target_project,
            states_by_project=states_by_project,
            launch_attempted=launch_attempted,
            **kwargs,
        )
    except Exception:
        return {
            "guardrail_status": "error_fallback",
            "guardrail_reason": "Guardrail evaluation failed.",
            "launch_allowed": False,
            "recursion_blocked": False,
            "state_repair_recommended": False,
        }
