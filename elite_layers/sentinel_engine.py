from __future__ import annotations

from typing import Any

from NEXUS.production_guardrails import evaluate_guardrails_safe


def _extract_pragmatic_aegis_decision(project_state: dict[str, Any]) -> dict[str, Any] | None:
    last_aegis = project_state.get("last_aegis_decision")
    if isinstance(last_aegis, dict):
        aegis_decision = str(last_aegis.get("aegis_decision") or "").strip().lower()
        if aegis_decision in ("allow", "deny", "approval_required", "error_fallback"):
            return {
                "aegis_decision": aegis_decision,
                "aegis_reason": str(last_aegis.get("aegis_reason") or "").strip(),
            }

    # Legacy fallback: best-effort parsing from dispatch_result.
    dispatch_result = project_state.get("dispatch_result")
    if not isinstance(dispatch_result, dict):
        return None
    status = str(dispatch_result.get("status") or "").strip().lower()
    execution_status = str(dispatch_result.get("execution_status") or "").strip().lower()
    next_action = str(dispatch_result.get("next_action") or "").strip().lower()
    msg = str(dispatch_result.get("message") or "").strip().lower()

    if status == "blocked" or "aegis deny" in msg:
        return {"aegis_decision": "deny", "aegis_reason": dispatch_result.get("message") or ""}
    if execution_status == "queued" or next_action == "human_review" or "approval required" in msg:
        return {"aegis_decision": "approval_required", "aegis_reason": dispatch_result.get("message") or ""}
    return {"aegis_decision": "allow", "aegis_reason": dispatch_result.get("message") or ""}


def build_sentinel_engine_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    meta_engine_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    SENTINEL consolidation engine: stronger unified threat/risk posture.
    Deterministic and explainable; never raises.
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        meta = meta_engine_summary or {}
        driver = studio_driver_summary or {}

        prj = (project_name or coord.get("priority_project") or "").strip()
        if not prj and states:
            prj = sorted(states.keys())[0]

        project_state = states.get(prj, {}) if prj else {}
        if not isinstance(project_state, dict):
            project_state = {}

        # Production guardrails signal (baseline risk posture).
        guard_result = project_state.get("guardrail_result") if isinstance(project_state.get("guardrail_result"), dict) else {}
        guard_status = str(project_state.get("guardrail_status") or guard_result.get("guardrail_status") or "").strip().lower()
        launch_allowed = bool(guard_result.get("launch_allowed", False)) if isinstance(guard_result, dict) else False

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
                launch_allowed = bool(guard_result.get("launch_allowed", False))

        guard_reason = str(guard_result.get("guardrail_reason") or "").strip()

        # Recovery and deployment preflight posture.
        recovery_status = str((project_state.get("recovery_result") or {}).get("recovery_status") or project_state.get("recovery_status") or "").strip().lower()
        deployment_preflight = project_state.get("deployment_preflight_result") or {}
        deployment_preflight_status = ""
        if isinstance(deployment_preflight, dict):
            deployment_preflight_status = str(deployment_preflight.get("deployment_preflight_status") or "").strip().lower()
        deployment_preflight_status = deployment_preflight_status or "none"

        # Meta engine outputs (safety/security/compliance/risk).
        safety_engine = meta.get("safety_engine") or {}
        security_engine = meta.get("security_engine") or {}
        compliance_engine = meta.get("compliance_engine") or {}
        risk_engine = meta.get("risk_engine") or {}

        def _engine_status(v: Any) -> str:
            if not isinstance(v, dict):
                return ""
            return str(v.get("engine_status") or "").strip().lower()

        safety_status = _engine_status(safety_engine)
        security_status = _engine_status(security_engine)
        compliance_status = _engine_status(compliance_engine)
        risk_status = _engine_status(risk_engine)

        meta_error_fallback = any(
            _engine_status(v) == "error_fallback" for v in (safety_engine, security_engine, compliance_engine, risk_engine)
        )
        meta_review_required = any(
            isinstance(v, dict) and bool(v.get("review_required", False))
            for v in (safety_engine, security_engine, compliance_engine, risk_engine)
        )
        any_warning = any(
            _engine_status(v) == "warning" for v in (safety_engine, security_engine, compliance_engine, risk_engine)
        )

        # AEGIS decision signal.
        aegis_res = _extract_pragmatic_aegis_decision(project_state) or {}
        aegis_decision = aegis_res.get("aegis_decision") or None

        # AEGIS denial is an immediate high-risk gate in this MVP.
        aegis_high = aegis_decision in ("deny", "error_fallback")
        aegis_approval_required = aegis_decision == "approval_required"

        high_risk_detected = bool(
            aegis_high
            or not launch_allowed
            or guard_status == "blocked"
            or recovery_status in ("blocked", "repair_required", "error_fallback")
            or deployment_preflight_status in ("blocked", "error_fallback")
            or meta_error_fallback
            or meta_review_required
        )

        # review_required is a stronger gating than just "warning".
        review_required = bool(
            aegis_high
            or guard_status == "blocked"
            or deployment_preflight_status == "blocked"
            or recovery_status in ("blocked", "repair_required", "error_fallback")
            or aegis_approval_required
            or meta_review_required
        )

        if high_risk_detected:
            risk_level = "high"
        elif review_required:
            risk_level = "medium"
        elif any_warning:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Sentinel status mapping.
        if meta_error_fallback:
            sentinel_status = "error_fallback"
        elif review_required:
            sentinel_status = "review_required"
        elif any_warning or risk_level == "medium":
            sentinel_status = "warning"
        else:
            sentinel_status = "clear"

        # Active warnings list (small and stable).
        active_warnings: list[str] = []
        if aegis_decision == "deny":
            active_warnings.append("AEGIS deny: execution routed to stop/block.")
        elif aegis_decision == "error_fallback":
            active_warnings.append("AEGIS error_fallback: conservative gating applied.")
        elif aegis_approval_required:
            active_warnings.append("AEGIS approval_required: routing marker indicates human review.")
        if not launch_allowed or guard_status == "blocked":
            active_warnings.append("Production guardrails block launch/action.")
        if recovery_status in ("blocked", "repair_required", "error_fallback"):
            active_warnings.append(f"Recovery posture indicates risk: {recovery_status}.")
        if deployment_preflight_status in ("blocked", "error_fallback"):
            active_warnings.append(f"Deployment preflight indicates risk: {deployment_preflight_status}.")
        if meta_review_required:
            active_warnings.append("Meta engine review_required present in safety/security/compliance/risk.")
        if any_warning and not active_warnings:
            active_warnings.append("Meta engines report warning posture.")
        if guard_reason and len(active_warnings) < 4 and sentinel_status != "error_fallback":
            active_warnings.append(f"Guardrail reason: {guard_reason}")

        threat_reason = (
            f"guard_status={guard_status or 'none'}; launch_allowed={launch_allowed}; "
            f"recovery_status={recovery_status or 'none'}; deployment_preflight={deployment_preflight_status}; "
            f"meta_review_required={meta_review_required}; meta_error_fallback={meta_error_fallback}; "
            f"aegis_decision={aegis_decision or 'none'}."
        )

        return {
            "sentinel_status": sentinel_status,
            "threat_reason": threat_reason,
            "high_risk_detected": bool(high_risk_detected),
            "review_required": bool(review_required),
            "risk_level": risk_level if risk_level in ("low", "medium", "high") else "unknown",
            "active_warnings": active_warnings[:8],
            "source_signals": {
                "safety_engine": safety_engine or None,
                "security_engine": security_engine or None,
                "compliance_engine": compliance_engine or None,
                "risk_engine": risk_engine or None,
                "aegis_decision": aegis_decision,
                "deployment_preflight": deployment_preflight if isinstance(deployment_preflight, dict) else None,
            },
        }
    except Exception:
        return {
            "sentinel_status": "error_fallback",
            "threat_reason": "SENTINEL consolidation failed.",
            "high_risk_detected": False,
            "review_required": True,
            "risk_level": "unknown",
            "active_warnings": [],
            "source_signals": {
                "safety_engine": None,
                "security_engine": None,
                "compliance_engine": None,
                "risk_engine": None,
                "aegis_decision": None,
                "deployment_preflight": None,
            },
        }

