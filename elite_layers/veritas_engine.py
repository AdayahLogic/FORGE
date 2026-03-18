from __future__ import annotations

from typing import Any

from NEXUS.production_guardrails import evaluate_guardrails_safe
from NEXUS.state_validator import validate_project_state_safe


def _extract_prism_recommendation(project_state: dict[str, Any]) -> dict[str, Any] | None:
    prism_result = project_state.get("prism_result")
    if not isinstance(prism_result, dict):
        return None
    prism_status = prism_result.get("prism_status")
    recommendation = prism_result.get("recommendation")
    if prism_status is None and recommendation is None:
        return None
    return {
        "prism_status": prism_status,
        "recommendation": recommendation,
    }


def _extract_aegis_decision(project_state: dict[str, Any]) -> dict[str, Any] | None:
    """
    Best-effort derivation of AEGIS decision/result from persisted execution outputs.

    We don't persist aegis_decision directly; runtime_dispatcher stores the outcome
    inside dispatch_result + next_action/hints.
    """
    dispatch_result = project_state.get("dispatch_result")
    if not isinstance(dispatch_result, dict):
        return None

    status = str(dispatch_result.get("status") or "").strip().lower()
    execution_status = str(dispatch_result.get("execution_status") or "").strip().lower()
    next_action = str(dispatch_result.get("next_action") or "").strip().lower()
    msg = str(dispatch_result.get("message") or "").strip().lower()

    if status == "blocked" or "aegis deny" in msg:
        return {"aegis_decision": "deny", "aegis_reason": dispatch_result.get("message") or ""}

    # For approval_required, runtime_dispatcher uses status="skipped" + execution_status="queued".
    if execution_status == "queued" or next_action == "human_review" or "approval required" in msg:
        return {"aegis_decision": "approval_required", "aegis_reason": dispatch_result.get("message") or ""}

    if status in ("accepted", "ok", "allowed") or msg == "":
        return {"aegis_decision": "allow", "aegis_reason": dispatch_result.get("message") or ""}

    return {"aegis_decision": "unknown", "aegis_reason": dispatch_result.get("message") or ""}


def build_veritas_engine_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    VERITAS consolidation engine: stronger truth/contradiction/assumption audit visibility.
    Deterministic and explainable; never raises.
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}

        prj = (project_name or coord.get("priority_project") or "").strip()
        if not prj and states:
            prj = sorted(states.keys())[0]

        project_state = states.get(prj, {}) if prj else {}
        if not isinstance(project_state, dict):
            project_state = {}

        # 1) State validator signal.
        state_validation = validate_project_state_safe(state=project_state)
        validation_status = str(state_validation.get("validation_status") or "").strip().lower()
        state_repair_recommended = bool(state_validation.get("state_repair_recommended", False))
        validation_issues = state_validation.get("issues") or []

        # 2) Production guardrails signal.
        guard_result = project_state.get("guardrail_result") if isinstance(project_state.get("guardrail_result"), dict) else {}
        guard_status = str(project_state.get("guardrail_status") or guard_result.get("guardrail_status") or "").strip().lower()

        # If guardrails weren't computed/persisted, compute from nearby signals.
        if not guard_result:
            qe = project_state.get("review_queue_entry") or {}
            rec = project_state.get("recovery_result") or {}
            rex = project_state.get("reexecution_result") or {}
            guard_result_safe = evaluate_guardrails_safe(
                autonomous_launch=False,
                project_state=project_state,
                review_queue_entry=qe if isinstance(qe, dict) else {},
                recovery_result=rec if isinstance(rec, dict) else {},
                reexecution_result=rex if isinstance(rex, dict) else {},
                studio_driver_result=driver,
                target_project=prj,
                states_by_project={prj: project_state} if prj else {},
                execution_attempted=False,
            )
            if isinstance(guard_result_safe, dict):
                guard_result = guard_result_safe
                guard_status = str(guard_result.get("guardrail_status") or "").strip().lower()

        guard_reason = str(guard_result.get("guardrail_reason") or "").strip()
        recursion_blocked = bool(guard_result.get("recursion_blocked", False))
        guard_state_repair_recommended = bool(guard_result.get("state_repair_recommended", False))
        launch_allowed = bool(guard_result.get("launch_allowed", False))

        # 3) PRISM signal.
        prism_rec = _extract_prism_recommendation(project_state)
        prism_status = str(prism_rec.get("prism_status") or "").strip().lower() if prism_rec else ""
        prism_recommendation = prism_rec.get("recommendation") if prism_rec else None

        # 4) AEGIS decision signal.
        aegis_decision_res = _extract_aegis_decision(project_state)
        aegis_decision = aegis_decision_res.get("aegis_decision") if aegis_decision_res else None

        # Optional recovery/launch posture (used as context only).
        recovery_status = str((project_state.get("recovery_result") or {}).get("recovery_status") or project_state.get("recovery_status") or "").strip().lower()
        launch_status = str((project_state.get("launch_result") or {}).get("launch_status") or project_state.get("launch_status") or "").strip().lower()

        # Contradictions and assumption readiness.
        contradictions_detected = bool(
            recursion_blocked
            or state_repair_recommended
            or guard_state_repair_recommended
            or (recovery_status in ("repair_required", "blocked") and validation_status in ("passed", "warning"))
        )

        # Assumption review required: validation/guardrails issues, AEGIS approval gate, or PRISM insufficiency.
        assumption_review_required = bool(
            validation_status in ("blocked", "warning", "error_fallback")
            or guard_status in ("blocked", "warning", "error_fallback")
            or aegis_decision in ("approval_required", "deny")
            or prism_status in ("insufficient_input", "error_fallback", "unknown")
        )

        # Determine status vocabulary.
        any_error_fallback = validation_status == "error_fallback" or guard_status == "error_fallback"
        if any_error_fallback:
            veritas_status = "error_fallback"
        elif validation_status == "blocked" or guard_status == "blocked" or aegis_decision == "deny" or contradictions_detected:
            # "deny" and hard contradictions are treated as review_required.
            veritas_status = "review_required"
        elif assumption_review_required:
            veritas_status = "warning"
        else:
            veritas_status = "trusted"

        # Truth confidence: deterministic from completeness of key signals.
        # high: validation passed + guardrails passed + AEGIS allow
        # medium: one of those is warning/uncertain
        # low: review_required/error_fallback or PRISM insufficient
        if veritas_status in ("error_fallback", "review_required"):
            truth_confidence = "low"
        elif veritas_status == "warning":
            truth_confidence = "medium"
        else:
            truth_confidence = "high"

        truth_reason = (
            f"validation_status={validation_status}; guard_status={guard_status or 'none'}; "
            f"launch_allowed={launch_allowed}; contradictions={contradictions_detected}; "
            f"prism_status={prism_status or 'none'}; aegis_decision={aegis_decision or 'none'}; "
            f"recovery_status={recovery_status or 'none'}; launch_status={launch_status or 'none'}."
        )

        # Issues list: include compact, explainable items.
        issues_out: list[Any] = []
        if isinstance(validation_issues, list) and validation_issues:
            issues_out.extend(validation_issues[:5])
        if guard_reason and len(issues_out) < 5:
            issues_out.append({"code": "guardrail_reason", "message": guard_reason, "severity": guard_status or "none"})
        if prism_rec and prism_status == "insufficient_input" and len(issues_out) < 5:
            issues_out.append({"code": "prism_insufficient_input", "message": "PRISM did not have enough inputs for a recommendation.", "severity": "warning"})
        if aegis_decision in ("deny", "approval_required") and len(issues_out) < 5:
            issues_out.append({"code": "aegis_gate", "message": f"AEGIS decision={aegis_decision}.", "severity": "blocked" if aegis_decision == "deny" else "warning"})

        # Source signals snapshot (stable keys).
        return {
            "veritas_status": veritas_status,
            "truth_reason": truth_reason,
            "contradictions_detected": bool(contradictions_detected),
            "assumption_review_required": bool(assumption_review_required),
            "truth_confidence": truth_confidence,
            "issues": issues_out,
            "source_signals": {
                "state_validator": {
                    "validation_status": validation_status,
                    "state_repair_recommended": state_repair_recommended,
                }
                if isinstance(state_validation, dict)
                else None,
                "guardrails": {
                    "guardrail_status": guard_status or None,
                    "launch_allowed": launch_allowed,
                    "recursion_blocked": recursion_blocked,
                }
                if isinstance(guard_result, dict)
                else None,
                "prism_recommendation": prism_rec,
                "aegis_decision": aegis_decision,
            },
        }
    except Exception:
        return {
            "veritas_status": "error_fallback",
            "truth_reason": "VERITAS consolidation failed.",
            "contradictions_detected": False,
            "assumption_review_required": True,
            "truth_confidence": "low",
            "issues": [],
            "source_signals": {
                "state_validator": None,
                "guardrails": None,
                "prism_recommendation": None,
                "aegis_decision": None,
            },
        }

