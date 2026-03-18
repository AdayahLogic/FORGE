from __future__ import annotations

from typing import Any

from NEXUS.production_guardrails import evaluate_guardrails_safe
from NEXUS.state_validator import validate_project_state_safe


def build_veritas_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    meta_engine_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    VERITAS summary: truth/contradiction/assumption audit visibility.

    Stable output shape:
    {
      "veritas_status": "...",
      "truth_reason": "...",
      "contradictions_detected": false,
      "assumption_review_required": false,
      "issues": []
    }
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}
        meta = meta_engine_summary or {}

        priority_project = coord.get("priority_project")
        if not priority_project and states:
            priority_project = sorted(states.keys())[0]

        state = states.get(priority_project or "", {}) if priority_project else {}
        if not isinstance(state, dict):
            state = {}

        validation = validate_project_state_safe(state=state)
        validation_status = str(validation.get("validation_status") or "").strip().lower()
        issues = validation.get("issues") or []

        guard_result = state.get("guardrail_result") if isinstance(state.get("guardrail_result"), dict) else {}
        guard_status = state.get("guardrail_status") if isinstance(state.get("guardrail_status"), str) else guard_result.get("guardrail_status")

        # If guardrails were not computed/persisted, compute safely from existing signals.
        if not guard_result:
            try:
                qe = state.get("review_queue_entry") or {}
                rec = state.get("recovery_result") or {}
                rex = state.get("reexecution_result") or {}
                gr = evaluate_guardrails_safe(
                    autonomous_launch=False,
                    project_state=state,
                    review_queue_entry=qe if isinstance(qe, dict) else {},
                    recovery_result=rec if isinstance(rec, dict) else {},
                    reexecution_result=rex if isinstance(rex, dict) else {},
                    studio_driver_result=driver,
                    target_project=priority_project,
                    states_by_project={priority_project: state} if priority_project else {},
                    execution_attempted=False,
                )
                guard_result = gr if isinstance(gr, dict) else {}
                guard_status = guard_result.get("guardrail_status")
            except Exception:
                guard_result = {}
                guard_status = None

        guard_status_norm = str(guard_status or "").strip().lower()
        state_repair_recommended = bool(guard_result.get("state_repair_recommended", False))
        recursion_blocked = bool(guard_result.get("recursion_blocked", False))
        guard_launch_allowed = bool(guard_result.get("launch_allowed", False))

        contradictions_detected = bool(state_repair_recommended or recursion_blocked)
        # Also treat specific validation codes as contradictions.
        for it in issues:
            if isinstance(it, dict) and it.get("code") in ("queue_cleared_recovery_waiting", "scheduled_but_run_not_permitted", "launched_but_not_started"):
                contradictions_detected = True

        # Meta engines for assumption readiness: safety/security/compliance/risk.
        engines = ["safety_engine", "security_engine", "compliance_engine", "risk_engine"]
        any_meta_review_required = any(
            isinstance(meta.get(e), dict) and bool(meta.get(e, {}).get("review_required", False))
            for e in engines
        )

        assumption_review_required = bool(
            validation_status in ("blocked", "warning") or guard_status_norm in ("blocked", "warning") or any_meta_review_required
        )

        if validation_status == "passed" and guard_status_norm == "passed" and not any_meta_review_required and not contradictions_detected:
            veritas_status = "trusted"
        elif validation_status == "blocked" or guard_status_norm == "blocked" or any_meta_review_required:
            veritas_status = "review_required"
        elif validation_status in ("warning",) or guard_status_norm == "warning" or contradictions_detected:
            veritas_status = "warning"
        else:
            veritas_status = "warning"

        truth_reason = (
            f"validation={validation_status}; guardrail_status={guard_status_norm or 'none'}; "
            f"contradictions={contradictions_detected}; meta_review_required={any_meta_review_required}; "
            f"launch_allowed={guard_launch_allowed}."
        )

        # Keep issues compact: include validation issues + a small guardrail note.
        issues_out: list[Any] = issues if isinstance(issues, list) else []
        if guard_result and guard_result.get("guardrail_reason") and len(issues_out) < 3:
            issues_out.append({"code": "guardrail_reason", "message": guard_result.get("guardrail_reason"), "severity": guard_status_norm or "none"})

        return {
            "veritas_status": veritas_status,
            "truth_reason": truth_reason,
            "contradictions_detected": bool(contradictions_detected),
            "assumption_review_required": bool(assumption_review_required),
            "issues": issues_out,
        }
    except Exception:
        return {
            "veritas_status": "error_fallback",
            "truth_reason": "VERITAS summary evaluation failed.",
            "contradictions_detected": False,
            "assumption_review_required": True,
            "issues": [],
        }

