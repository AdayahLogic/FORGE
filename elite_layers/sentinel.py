from __future__ import annotations

from typing import Any


def build_sentinel_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    meta_engine_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    SENTINEL summary: unified threat/risk posture layer.

    Stable output shape:
    {
      "sentinel_status": "...",
      "threat_reason": "...",
      "high_risk_detected": false,
      "review_required": false
    }
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        meta = meta_engine_summary or {}

        priority_project = coord.get("priority_project")
        if not priority_project and states:
            priority_project = sorted(states.keys())[0]

        state = states.get(priority_project or "", {}) if priority_project else {}
        if not isinstance(state, dict):
            state = {}

        guard_result = state.get("guardrail_result") if isinstance(state.get("guardrail_result"), dict) else {}
        guard_launch_allowed = bool(guard_result.get("launch_allowed", False))
        guard_status = str(state.get("guardrail_status") or guard_result.get("guardrail_status") or "none").strip().lower()

        recovery_status = state.get("recovery_status")
        if not recovery_status and isinstance(state.get("recovery_result"), dict):
            recovery_status = state.get("recovery_result", {}).get("recovery_status")
        recovery_status_norm = str(recovery_status or "none").strip().lower()

        safety = meta.get("safety_engine") or {}
        security = meta.get("security_engine") or {}
        compliance = meta.get("compliance_engine") or {}
        risk = meta.get("risk_engine") or {}

        meta_review_required = any(
            isinstance(e, dict) and bool(e.get("review_required", False))
            for e in (safety, security, compliance, risk)
        )
        meta_error_fallback = any(
            isinstance(e, dict) and str(e.get("engine_status") or "").strip().lower() == "error_fallback"
            for e in (safety, security, compliance, risk)
        )

        high_risk_detected = bool(
            not guard_launch_allowed
            or guard_status == "blocked"
            or recovery_status_norm in ("blocked", "repair_required", "error_fallback")
            or meta_error_fallback
            or meta_review_required
        )

        if high_risk_detected:
            sentinel_status = "review_required"
            review_required = True
        else:
            # If guardrails allowed and no recovery risk, keep clear unless meta suggests warnings.
            any_warning = any(
                isinstance(e, dict) and str(e.get("engine_status") or "").strip().lower() == "warning"
                for e in (safety, security, compliance, risk)
            )
            if any_warning:
                sentinel_status = "warning"
                review_required = True
            else:
                sentinel_status = "clear"
                review_required = False

        threat_reason = (
            f"guard_launch_allowed={guard_launch_allowed}; guard_status={guard_status}; "
            f"recovery_status={recovery_status_norm}; meta_review_required={meta_review_required}."
        )

        return {
            "sentinel_status": sentinel_status,
            "threat_reason": threat_reason,
            "high_risk_detected": bool(high_risk_detected),
            "review_required": bool(review_required),
        }
    except Exception:
        return {
            "sentinel_status": "error_fallback",
            "threat_reason": "SENTINEL summary evaluation failed.",
            "high_risk_detected": False,
            "review_required": True,
        }

