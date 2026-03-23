"""
Meta-engine governance priority resolution.
"""

from __future__ import annotations

from typing import Any


META_ENGINE_PRIORITY = ("sentinel", "veritas", "leviathan", "titan", "helios")


def _extract_status(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict):
        return ""
    for key in ("sentinel_status", "veritas_status", "leviathan_status", "titan_status", "helios_status"):
        if key in summary:
            return str(summary.get(key) or "").strip().lower()
    return ""


def _normalize_engine_signal(engine_name: str, summary: dict[str, Any] | None) -> dict[str, Any]:
    engine = str(engine_name or "").strip().lower()
    data = summary if isinstance(summary, dict) else {}
    engine_status = _extract_status(data)
    reason = ""
    resolution_state = "resolved"
    routing_outcome = "continue"
    engaged = False
    safe_to_resolve = True

    if engine == "sentinel":
        reason = str(data.get("threat_reason") or "").strip()
        review_required = bool(data.get("review_required"))
        high_risk_detected = bool(data.get("high_risk_detected"))
        risk_level = str(data.get("risk_level") or "").strip().lower()
        active_warnings = [str(x).lower() for x in (data.get("active_warnings") or []) if str(x).strip()]
        hard_stop_signal = (
            "aegis deny" in " ".join(active_warnings)
            or "block" in " ".join(active_warnings)
            or "guard_status=blocked" in reason.lower()
            or "deployment_preflight=blocked" in reason.lower()
            or "recovery_status=blocked" in reason.lower()
            or "aegis_decision=deny" in reason.lower()
        )
        if engine_status == "error_fallback":
            engaged = True
            safe_to_resolve = False
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "SENTINEL entered error fallback and requires operator pause."
        elif engine_status == "review_required":
            engaged = True
            if hard_stop_signal:
                resolution_state = "stop"
                routing_outcome = "stop"
                reason = reason or "SENTINEL detected high risk and requires stop."
            elif high_risk_detected or risk_level == "high":
                resolution_state = "pause"
                routing_outcome = "pause"
                reason = reason or "SENTINEL detected elevated risk and requires pause."
            else:
                resolution_state = "pause"
                routing_outcome = "pause"
                reason = reason or "SENTINEL requires review before continuation."
        elif engine_status == "warning":
            engaged = True
            resolution_state = "escalate"
            routing_outcome = "escalate"
            reason = reason or "SENTINEL warning requires escalation."
        elif review_required:
            engaged = True
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "SENTINEL review_required signal requires pause."
    elif engine == "veritas":
        reason = str(data.get("truth_reason") or "").strip()
        contradictions_detected = bool(data.get("contradictions_detected"))
        assumption_review_required = bool(data.get("assumption_review_required"))
        if engine_status == "error_fallback":
            engaged = True
            safe_to_resolve = False
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "VERITAS entered error fallback and requires operator pause."
        elif engine_status == "review_required":
            engaged = True
            resolution_state = "escalate"
            routing_outcome = "escalate"
            reason = reason or "VERITAS contradictions require escalation."
        elif engine_status == "warning" or contradictions_detected or assumption_review_required:
            engaged = True
            resolution_state = "escalate"
            routing_outcome = "escalate"
            reason = reason or "VERITAS requires assumption review."
    elif engine == "leviathan":
        reason = str(data.get("highest_leverage_reason") or data.get("recommended_focus") or "").strip()
        if engine_status == "error_fallback":
            engaged = True
            safe_to_resolve = False
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "LEVIATHAN entered error fallback and requires pause."
        elif engine_status == "waiting":
            engaged = True
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "LEVIATHAN recommends waiting before continuation."
    elif engine == "titan":
        reason = str(data.get("execution_reason") or "").strip()
        if engine_status == "error_fallback":
            engaged = True
            safe_to_resolve = False
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "TITAN entered error fallback and requires pause."
        elif engine_status == "blocked":
            engaged = True
            resolution_state = "stop"
            routing_outcome = "stop"
            reason = reason or "TITAN execution posture is blocked."
        elif engine_status == "waiting":
            engaged = True
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "TITAN requires waiting before execution."
    elif engine == "helios":
        reason = str(data.get("improvement_reason") or "").strip()
        execution_gated = bool(data.get("execution_gated", False))
        requires_review = bool(((data.get("change_proposal") or {}).get("requires_review")))
        if engine_status == "error_fallback":
            engaged = True
            safe_to_resolve = False
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "HELIOS entered error fallback and requires pause."
        elif execution_gated or requires_review or engine_status in ("gated", "review_required", "deferred"):
            engaged = True
            resolution_state = "pause"
            routing_outcome = "pause"
            reason = reason or "HELIOS proposal is gated pending review."

    return {
        "engine": engine.upper(),
        "engine_status": engine_status or "none",
        "engaged": bool(engaged),
        "safe_to_resolve": bool(safe_to_resolve),
        "resolution_state": resolution_state,
        "routing_outcome": routing_outcome,
        "reason": reason,
    }


def resolve_meta_engine_governance(
    *,
    titan_summary: dict[str, Any] | None = None,
    leviathan_summary: dict[str, Any] | None = None,
    helios_summary: dict[str, Any] | None = None,
    veritas_summary: dict[str, Any] | None = None,
    sentinel_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engines = {
        "sentinel": sentinel_summary or {},
        "veritas": veritas_summary or {},
        "leviathan": leviathan_summary or {},
        "titan": titan_summary or {},
        "helios": helios_summary or {},
    }
    engine_signals = {
        engine_name.upper(): _normalize_engine_signal(engine_name, engines.get(engine_name))
        for engine_name in META_ENGINE_PRIORITY
    }
    involved = [
        engine_name.upper()
        for engine_name in META_ENGINE_PRIORITY
        if bool((engine_signals.get(engine_name.upper()) or {}).get("engaged"))
    ]

    if not involved:
        return {
            "status": "resolved",
            "conflict_type": "none",
            "involved_engines": [],
            "winning_priority": "",
            "resolution_basis": "no_active_governance_conflict",
            "resolution_state": "resolved",
            "routing_outcome": "continue",
            "reason": "No active governance or meta-engine conflict signals detected.",
            "governance_trace": {
                "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
                "engine_signals": engine_signals,
            },
        }

    highest = involved[0]
    highest_signal = engine_signals.get(highest) or {}

    if not bool(highest_signal.get("safe_to_resolve")):
        return {
            "status": "unresolved",
            "conflict_type": "unsafe_governance_conflict",
            "involved_engines": involved,
            "winning_priority": highest,
            "resolution_basis": "highest_priority_signal_not_safe_to_resolve",
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "reason": str(highest_signal.get("reason") or f"{highest} could not be safely resolved."),
            "governance_trace": {
                "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
                "engine_signals": engine_signals,
            },
        }

    conflict_type = "single_engine_directive"
    resolution_basis = "single_engine_governance_signal"
    if len(involved) > 1:
        conflict_type = "priority_resolved_governance_conflict"
        resolution_basis = "priority_order"

    return {
        "status": "resolved",
        "conflict_type": conflict_type,
        "involved_engines": involved,
        "winning_priority": highest,
        "resolution_basis": resolution_basis,
        "resolution_state": str(highest_signal.get("resolution_state") or "resolved"),
        "routing_outcome": str(highest_signal.get("routing_outcome") or "continue"),
        "reason": str(highest_signal.get("reason") or f"{highest} selected by governance priority."),
        "governance_trace": {
            "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
            "engine_signals": engine_signals,
        },
    }


def resolve_meta_engine_governance_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return resolve_meta_engine_governance(**kwargs)
    except Exception as e:
        return {
            "status": "unresolved",
            "conflict_type": "resolver_error",
            "involved_engines": [],
            "winning_priority": "",
            "resolution_basis": "resolver_exception",
            "resolution_state": "pause",
            "routing_outcome": "pause",
            "reason": f"Meta-engine governance resolution failed: {e}",
            "governance_trace": {
                "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
                "engine_signals": {},
            },
        }
