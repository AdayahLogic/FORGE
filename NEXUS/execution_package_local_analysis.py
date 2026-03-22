"""
NemoClaw execution-package local intelligence layer.

Advisory-only analysis derived deterministically from package-local execution
state and persisted evaluation fields. This layer never changes execution
authority or any non-local-analysis package state.
"""

from __future__ import annotations

from typing import Any


TERMINAL_EXECUTION_STATUSES = ("succeeded", "failed", "rolled_back")
LOCAL_ANALYSIS_REASON_CODES = (
    "completed",
    "evaluation_not_completed",
    "execution_not_terminal",
    "missing_evaluation_data",
    "error_fallback",
)
LOCAL_ANALYSIS_CONFIDENCE_BANDS = ("low", "guarded", "moderate", "high")
LOCAL_ANALYSIS_NEXT_ACTIONS = (
    "review_integrity",
    "initiate_rollback_repair",
    "re_evaluate_package",
    "no_action_required",
    "investigate_failure",
)


def _clamp_score(value: Any) -> int:
    try:
        n = int(round(float(value)))
    except Exception:
        n = 0
    return max(0, min(100, n))


def _confidence_band(score: Any) -> str:
    n = _clamp_score(score)
    if n < 30:
        return "low"
    if n < 55:
        return "guarded"
    if n < 80:
        return "moderate"
    return "high"


def normalize_local_analysis_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    code = str(value.get("code") or "").strip().lower()
    if code not in LOCAL_ANALYSIS_REASON_CODES:
        code = ""
    return {
        "code": code,
        "message": str(value.get("message") or ""),
    }


def normalize_local_analysis_basis(value: Any) -> dict[str, str]:
    data = value if isinstance(value, dict) else {}
    return {
        "source_decision_status": str(data.get("source_decision_status") or "").strip().lower(),
        "source_eligibility_status": str(data.get("source_eligibility_status") or "").strip().lower(),
        "source_release_status": str(data.get("source_release_status") or "").strip().lower(),
        "source_handoff_status": str(data.get("source_handoff_status") or "").strip().lower(),
        "source_execution_status": str(data.get("source_execution_status") or "").strip().lower(),
        "source_rollback_status": str(data.get("source_rollback_status") or "").strip().lower(),
        "source_integrity_status": str(data.get("source_integrity_status") or "").strip().lower(),
        "source_recovery_status": str(data.get("source_recovery_status") or "").strip().lower(),
        "source_evaluation_status": str(data.get("source_evaluation_status") or "").strip().lower(),
        "source_failure_class": str(data.get("source_failure_class") or "").strip().lower(),
        "source_failure_stage": str(data.get("source_failure_stage") or "").strip().lower(),
    }


def normalize_local_analysis_summary(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    confidence_score = _clamp_score(data.get("confidence_score"))
    confidence_band = str(data.get("confidence_band") or _confidence_band(confidence_score)).strip().lower()
    if confidence_band not in LOCAL_ANALYSIS_CONFIDENCE_BANDS:
        confidence_band = _confidence_band(confidence_score)
    suggested_next_action = str(data.get("suggested_next_action") or "").strip().lower()
    if suggested_next_action not in LOCAL_ANALYSIS_NEXT_ACTIONS:
        suggested_next_action = ""
    return {
        "recommendation_summary": str(data.get("recommendation_summary") or ""),
        "confidence_score": confidence_score,
        "confidence_band": confidence_band,
        "risk_interpretation": str(data.get("risk_interpretation") or ""),
        "execution_evaluation_interpretation": str(data.get("execution_evaluation_interpretation") or ""),
        "suggested_next_action": suggested_next_action,
        "analysis_summary": str(data.get("analysis_summary") or ""),
    }


def _build_basis(package: dict[str, Any] | None) -> dict[str, str]:
    p = package or {}
    return normalize_local_analysis_basis(
        {
            "source_decision_status": p.get("decision_status"),
            "source_eligibility_status": p.get("eligibility_status"),
            "source_release_status": p.get("release_status"),
            "source_handoff_status": p.get("handoff_status"),
            "source_execution_status": p.get("execution_status"),
            "source_rollback_status": p.get("rollback_status"),
            "source_integrity_status": ((p.get("integrity_verification") or {}).get("integrity_status") or ""),
            "source_recovery_status": ((p.get("recovery_summary") or {}).get("recovery_status") or ""),
            "source_evaluation_status": p.get("evaluation_status"),
            "source_failure_class": ((p.get("failure_summary") or {}).get("failure_class") or ""),
            "source_failure_stage": ((p.get("failure_summary") or {}).get("failure_stage") or ""),
        }
    )


def _derive_confidence_score(
    *,
    integrity_score: Any,
    failure_risk_score: Any,
    execution_quality_score: Any,
) -> int:
    integrity = _clamp_score(integrity_score)
    failure_risk = _clamp_score(failure_risk_score)
    execution_quality = _clamp_score(execution_quality_score)
    return _clamp_score(round((integrity + execution_quality + (100 - failure_risk)) / 3))


def _derive_suggested_next_action(
    *,
    execution_status: str,
    integrity_status: str,
    recovery_status: str,
    rollback_repair_status: str,
    failure_risk_score: int,
) -> str:
    if execution_status not in TERMINAL_EXECUTION_STATUSES:
        return "re_evaluate_package"
    if rollback_repair_status in ("pending", "failed") or recovery_status == "repair_required":
        return "initiate_rollback_repair"
    if integrity_status in ("issues_detected", "verification_failed", "not_verified"):
        return "review_integrity"
    if execution_status in ("failed", "rolled_back"):
        return "investigate_failure"
    if failure_risk_score >= 60:
        return "review_integrity"
    return "no_action_required"


def _build_risk_interpretation(failure_risk_score: int, integrity_status: str, recovery_status: str) -> str:
    posture = "low"
    if failure_risk_score >= 75:
        posture = "critical"
    elif failure_risk_score >= 55:
        posture = "high"
    elif failure_risk_score >= 30:
        posture = "elevated"
    integrity_phrase = integrity_status or "unknown"
    recovery_phrase = recovery_status or "not_needed"
    return f"Risk posture {posture}; integrity {integrity_phrase}; recovery {recovery_phrase}."


def _build_execution_evaluation_interpretation(
    *,
    execution_status: str,
    evaluation_reason_code: str,
    execution_quality_score: int,
    integrity_score: int,
) -> str:
    return (
        f"Execution {execution_status or 'unknown'} with evaluation {evaluation_reason_code or 'unknown'}; "
        f"execution_quality={execution_quality_score}; integrity_score={integrity_score}."
    )


def _build_recommendation_summary(
    *,
    execution_status: str,
    suggested_next_action: str,
    confidence_band: str,
) -> str:
    return (
        f"NemoClaw recommends {suggested_next_action or 're_evaluate_package'} for "
        f"{execution_status or 'unknown'} execution state with {confidence_band or 'low'} confidence."
    )


def analyze_execution_package_locally(package: dict[str, Any] | None) -> dict[str, Any]:
    """Return advisory local analysis using package-local and persisted evaluation fields only."""
    p = package or {}
    basis = _build_basis(p)
    execution_status = basis.get("source_execution_status") or ""
    evaluation_status = basis.get("source_evaluation_status") or ""
    evaluation_summary = p.get("evaluation_summary") or {}
    integrity_score = _clamp_score(evaluation_summary.get("integrity_score"))
    failure_risk_score = _clamp_score(evaluation_summary.get("failure_risk_score"))
    execution_quality_score = _clamp_score(evaluation_summary.get("execution_quality_score"))

    if evaluation_status != "completed":
        return {
            "local_analysis_status": "blocked",
            "local_analysis_reason": {
                "code": "evaluation_not_completed",
                "message": "NemoClaw local analysis requires persisted evaluation_status='completed'.",
            },
            "local_analysis_basis": basis,
            "local_analysis_summary": normalize_local_analysis_summary(
                {
                    "recommendation_summary": "Persisted evaluation must complete before advisory analysis.",
                    "confidence_score": 0,
                    "risk_interpretation": "Risk posture unavailable until evaluation completes.",
                    "execution_evaluation_interpretation": "Evaluation status is not completed.",
                    "suggested_next_action": "re_evaluate_package",
                    "analysis_summary": "NemoClaw analysis blocked pending completed evaluation.",
                }
            ),
        }

    if execution_status not in TERMINAL_EXECUTION_STATUSES:
        return {
            "local_analysis_status": "blocked",
            "local_analysis_reason": {
                "code": "execution_not_terminal",
                "message": "NemoClaw local analysis requires a terminal execution_status.",
            },
            "local_analysis_basis": basis,
            "local_analysis_summary": normalize_local_analysis_summary(
                {
                    "recommendation_summary": "Execution must reach a terminal state before advisory analysis.",
                    "confidence_score": 0,
                    "risk_interpretation": "Risk posture unavailable until execution is terminal.",
                    "execution_evaluation_interpretation": "Execution status is not terminal.",
                    "suggested_next_action": "re_evaluate_package",
                    "analysis_summary": "NemoClaw analysis blocked pending terminal execution state.",
                }
            ),
        }

    if not isinstance(evaluation_summary, dict) or not evaluation_summary:
        return {
            "local_analysis_status": "blocked",
            "local_analysis_reason": {
                "code": "missing_evaluation_data",
                "message": "Persisted evaluation_summary is required for NemoClaw local analysis.",
            },
            "local_analysis_basis": basis,
            "local_analysis_summary": normalize_local_analysis_summary(
                {
                    "recommendation_summary": "Persisted evaluation summary is missing.",
                    "confidence_score": 0,
                    "risk_interpretation": "Risk posture unavailable because evaluation summary is missing.",
                    "execution_evaluation_interpretation": "Evaluation summary is absent.",
                    "suggested_next_action": "re_evaluate_package",
                    "analysis_summary": "NemoClaw analysis blocked because persisted evaluation summary is missing.",
                }
            ),
        }

    integrity_status = basis.get("source_integrity_status") or ""
    recovery_status = basis.get("source_recovery_status") or ""
    rollback_repair_status = str(((p.get("rollback_repair") or {}).get("rollback_repair_status") or "")).strip().lower()
    evaluation_reason_code = str(((p.get("evaluation_reason") or {}).get("code") or "")).strip().lower()
    confidence_score = _derive_confidence_score(
        integrity_score=integrity_score,
        failure_risk_score=failure_risk_score,
        execution_quality_score=execution_quality_score,
    )
    confidence_band = _confidence_band(confidence_score)
    suggested_next_action = _derive_suggested_next_action(
        execution_status=execution_status,
        integrity_status=integrity_status,
        recovery_status=recovery_status,
        rollback_repair_status=rollback_repair_status,
        failure_risk_score=failure_risk_score,
    )
    risk_interpretation = _build_risk_interpretation(failure_risk_score, integrity_status, recovery_status)
    execution_interpretation = _build_execution_evaluation_interpretation(
        execution_status=execution_status,
        evaluation_reason_code=evaluation_reason_code,
        execution_quality_score=execution_quality_score,
        integrity_score=integrity_score,
    )
    recommendation_summary = _build_recommendation_summary(
        execution_status=execution_status,
        suggested_next_action=suggested_next_action,
        confidence_band=confidence_band,
    )
    analysis_summary = (
        f"{recommendation_summary} {risk_interpretation} "
        f"{execution_interpretation}"
    )

    return {
        "local_analysis_status": "completed",
        "local_analysis_reason": {
            "code": "completed",
            "message": "NemoClaw local analysis completed from package-local and persisted evaluation state.",
        },
        "local_analysis_basis": basis,
        "local_analysis_summary": normalize_local_analysis_summary(
            {
                "recommendation_summary": recommendation_summary,
                "confidence_score": confidence_score,
                "confidence_band": confidence_band,
                "risk_interpretation": risk_interpretation,
                "execution_evaluation_interpretation": execution_interpretation,
                "suggested_next_action": suggested_next_action,
                "analysis_summary": analysis_summary,
            }
        ),
    }


def analyze_execution_package_locally_safe(package: dict[str, Any] | None) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return analyze_execution_package_locally(package)
    except Exception as e:
        return {
            "local_analysis_status": "error_fallback",
            "local_analysis_reason": {
                "code": "error_fallback",
                "message": str(e),
            },
            "local_analysis_basis": normalize_local_analysis_basis(None),
            "local_analysis_summary": normalize_local_analysis_summary(None),
        }
