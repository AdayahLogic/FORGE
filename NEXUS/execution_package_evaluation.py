"""
Abacus execution-package evaluation layer.

Evaluation is explicit, downstream-only, and derives from existing package-local
execution facts. It never changes execution authority or any non-evaluation
package state.
"""

from __future__ import annotations

from typing import Any


TERMINAL_EXECUTION_STATUSES = ("succeeded", "failed", "rolled_back")
EVALUATION_REASON_CODES = (
    "completed",
    "execution_not_complete",
    "missing_execution_data",
    "integrity_failed",
    "error_fallback",
)
POSITIVE_SCORE_BANDS = ("critical", "weak", "mixed", "strong", "excellent")
RISK_SCORE_BANDS = ("low", "guarded", "elevated", "high", "critical")


def _clamp_score(value: Any) -> int:
    try:
        n = int(round(float(value)))
    except Exception:
        n = 0
    return max(0, min(100, n))


def _positive_band(score: Any) -> str:
    n = _clamp_score(score)
    if n < 20:
        return "critical"
    if n < 40:
        return "weak"
    if n < 60:
        return "mixed"
    if n < 80:
        return "strong"
    return "excellent"


def _risk_band(score: Any) -> str:
    n = _clamp_score(score)
    if n < 20:
        return "low"
    if n < 40:
        return "guarded"
    if n < 60:
        return "elevated"
    if n < 80:
        return "high"
    return "critical"


def normalize_evaluation_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    code = str(value.get("code") or "").strip().lower()
    if code not in EVALUATION_REASON_CODES:
        code = ""
    return {
        "code": code,
        "message": str(value.get("message") or ""),
    }


def normalize_evaluation_basis(value: Any) -> dict[str, str]:
    data = value if isinstance(value, dict) else {}
    return {
        "source_execution_status": str(data.get("source_execution_status") or "").strip().lower(),
        "source_rollback_status": str(data.get("source_rollback_status") or "").strip().lower(),
        "source_integrity_status": str(data.get("source_integrity_status") or "").strip().lower(),
        "source_recovery_status": str(data.get("source_recovery_status") or "").strip().lower(),
        "source_failure_class": str(data.get("source_failure_class") or "").strip().lower(),
        "source_failure_stage": str(data.get("source_failure_stage") or "").strip().lower(),
    }


def normalize_evaluation_summary(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    execution_quality_score = _clamp_score(data.get("execution_quality_score"))
    integrity_score = _clamp_score(data.get("integrity_score"))
    rollback_quality = _clamp_score(data.get("rollback_quality"))
    failure_risk_score = _clamp_score(data.get("failure_risk_score"))

    execution_quality_band = str(data.get("execution_quality_band") or _positive_band(execution_quality_score)).strip().lower()
    if execution_quality_band not in POSITIVE_SCORE_BANDS:
        execution_quality_band = _positive_band(execution_quality_score)

    integrity_band = str(data.get("integrity_band") or _positive_band(integrity_score)).strip().lower()
    if integrity_band not in POSITIVE_SCORE_BANDS:
        integrity_band = _positive_band(integrity_score)

    rollback_quality_band = str(data.get("rollback_quality_band") or _positive_band(rollback_quality)).strip().lower()
    if rollback_quality_band not in POSITIVE_SCORE_BANDS:
        rollback_quality_band = _positive_band(rollback_quality)

    failure_risk_band = str(data.get("failure_risk_band") or _risk_band(failure_risk_score)).strip().lower()
    if failure_risk_band not in RISK_SCORE_BANDS:
        failure_risk_band = _risk_band(failure_risk_score)

    return {
        "execution_quality_score": execution_quality_score,
        "integrity_score": integrity_score,
        "rollback_quality": rollback_quality,
        "failure_risk_score": failure_risk_score,
        "execution_quality_band": execution_quality_band,
        "integrity_band": integrity_band,
        "rollback_quality_band": rollback_quality_band,
        "failure_risk_band": failure_risk_band,
        "evaluator_summary": str(data.get("evaluator_summary") or ""),
    }


def _build_basis(package: dict[str, Any] | None) -> dict[str, str]:
    p = package or {}
    return normalize_evaluation_basis(
        {
            "source_execution_status": p.get("execution_status"),
            "source_rollback_status": p.get("rollback_status"),
            "source_integrity_status": ((p.get("integrity_verification") or {}).get("integrity_status") or ""),
            "source_recovery_status": ((p.get("recovery_summary") or {}).get("recovery_status") or ""),
            "source_failure_class": ((p.get("failure_summary") or {}).get("failure_class") or ""),
            "source_failure_stage": ((p.get("failure_summary") or {}).get("failure_stage") or ""),
        }
    )


def _score_execution_quality(execution_status: str, integrity_status: str, recovery_status: str) -> int:
    base = {"succeeded": 92, "rolled_back": 58, "failed": 24}.get(execution_status, 0)
    if integrity_status == "verified":
        base += 4
    elif integrity_status == "issues_detected":
        base -= 12
    elif integrity_status == "verification_failed":
        base -= 20
    if recovery_status == "repair_required":
        base -= 12
    elif recovery_status == "retry_ready":
        base -= 6
    elif recovery_status == "retry_blocked":
        base -= 10
    return _clamp_score(base)


def _score_integrity(integrity_status: str) -> int:
    return _clamp_score(
        {
            "verified": 96,
            "issues_detected": 38,
            "verification_failed": 8,
            "not_verified": 52,
        }.get(integrity_status, 52)
    )


def _score_rollback(rollback_status: str, rollback_repair_status: str) -> int:
    base = {
        "not_needed": 90,
        "completed": 84,
        "failed": 8,
    }.get(rollback_status, 45)
    if rollback_repair_status == "pending":
        base -= 16
    elif rollback_repair_status == "failed":
        base -= 24
    return _clamp_score(base)


def _score_failure_risk(
    execution_status: str,
    integrity_status: str,
    recovery_status: str,
    rollback_status: str,
    rollback_repair_status: str,
    failure_class: str,
) -> int:
    score = {"succeeded": 12, "rolled_back": 48, "failed": 78}.get(execution_status, 85)
    if integrity_status == "issues_detected":
        score += 12
    elif integrity_status == "verification_failed":
        score += 22
    if recovery_status == "repair_required":
        score += 15
    elif recovery_status == "retry_ready":
        score += 8
    elif recovery_status == "retry_blocked":
        score += 6
    if rollback_status == "failed":
        score += 14
    if rollback_repair_status == "pending":
        score += 10
    elif rollback_repair_status == "failed":
        score += 18
    if failure_class == "rollback_failure":
        score += 12
    elif failure_class in ("runtime_execution_failure", "runtime_start_failure"):
        score += 8
    if execution_status == "succeeded" and integrity_status == "verified" and rollback_status == "not_needed":
        score = min(score, 10)
    return _clamp_score(score)


def _build_summary(
    *,
    execution_status: str,
    rollback_status: str,
    integrity_status: str,
    recovery_status: str,
    failure_class: str,
    failure_stage: str,
    rollback_repair_status: str,
) -> dict[str, Any]:
    execution_quality_score = _score_execution_quality(execution_status, integrity_status, recovery_status)
    integrity_score = _score_integrity(integrity_status)
    rollback_quality = _score_rollback(rollback_status, rollback_repair_status)
    failure_risk_score = _score_failure_risk(
        execution_status,
        integrity_status,
        recovery_status,
        rollback_status,
        rollback_repair_status,
        failure_class,
    )
    integrity_phrase = integrity_status or "not_verified"
    recovery_phrase = recovery_status or "not_needed"
    failure_phrase = failure_class or "none"
    summary_text = (
        f"Execution {execution_status or 'unknown'}; integrity {integrity_phrase}; "
        f"rollback {rollback_status or 'unknown'}; recovery {recovery_phrase}; "
        f"failure_class {failure_phrase}; failure_stage {failure_stage or 'none'}."
    )
    return normalize_evaluation_summary(
        {
            "execution_quality_score": execution_quality_score,
            "integrity_score": integrity_score,
            "rollback_quality": rollback_quality,
            "failure_risk_score": failure_risk_score,
            "evaluator_summary": summary_text,
        }
    )


def evaluate_execution_package(package: dict[str, Any] | None) -> dict[str, Any]:
    """Return evaluation fields derived from existing package-local facts only."""
    p = package or {}
    basis = _build_basis(p)
    execution_status = basis.get("source_execution_status") or ""
    rollback_status = basis.get("source_rollback_status") or ""
    integrity_status = basis.get("source_integrity_status") or ""
    recovery_status = basis.get("source_recovery_status") or ""
    failure_class = basis.get("source_failure_class") or ""
    failure_stage = basis.get("source_failure_stage") or ""
    rollback_repair_status = str(((p.get("rollback_repair") or {}).get("rollback_repair_status") or "")).strip().lower()

    if not execution_status:
        return {
            "evaluation_status": "blocked",
            "evaluation_reason": {
                "code": "missing_execution_data",
                "message": "Execution package is missing execution status required for evaluation.",
            },
            "evaluation_basis": basis,
            "evaluation_summary": normalize_evaluation_summary(None),
        }

    if execution_status not in TERMINAL_EXECUTION_STATUSES:
        return {
            "evaluation_status": "blocked",
            "evaluation_reason": {
                "code": "execution_not_complete",
                "message": "Evaluation is allowed only after terminal execution states are reached.",
            },
            "evaluation_basis": basis,
            "evaluation_summary": normalize_evaluation_summary(None),
        }

    reason_code = "completed"
    reason_message = "Abacus evaluation completed from package-local execution facts."
    if integrity_status in ("issues_detected", "verification_failed"):
        reason_code = "integrity_failed"
        reason_message = "Abacus evaluation completed and detected integrity issues in package-local execution facts."

    return {
        "evaluation_status": "completed",
        "evaluation_reason": {
            "code": reason_code,
            "message": reason_message,
        },
        "evaluation_basis": basis,
        "evaluation_summary": _build_summary(
            execution_status=execution_status,
            rollback_status=rollback_status,
            integrity_status=integrity_status,
            recovery_status=recovery_status,
            failure_class=failure_class,
            failure_stage=failure_stage,
            rollback_repair_status=rollback_repair_status,
        ),
    }


def evaluate_execution_package_safe(package: dict[str, Any] | None) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return evaluate_execution_package(package)
    except Exception as e:
        return {
            "evaluation_status": "error_fallback",
            "evaluation_reason": {
                "code": "error_fallback",
                "message": str(e),
            },
            "evaluation_basis": normalize_evaluation_basis(None),
            "evaluation_summary": normalize_evaluation_summary(None),
        }
