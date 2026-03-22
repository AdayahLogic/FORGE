"""
Execution package hardening helpers.

Minimal additive helpers for Phase 8:
- package-local retry/idempotency defaults
- failure and recovery summaries
- post-execution integrity verification

No autonomy, no automatic retry, no automatic rollback repair.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


VALID_EXECUTION_FAILURE_CLASSES = (
    "preflight_block",
    "aegis_block",
    "duplicate_success_block",
    "retry_not_authorized",
    "retry_exhausted",
    "runtime_start_failure",
    "runtime_execution_failure",
    "rollback_failure",
    "rollback_repair_failure",
    "integrity_verification_failure",
)

VALID_FAILURE_STAGES = ("", "preflight", "execution", "rollback", "verification")
VALID_FAILURE_SEVERITIES = ("", "none", "low", "medium", "high")
VALID_RECOVERY_STATUSES = (
    "not_needed",
    "retry_ready",
    "retry_blocked",
    "repair_required",
    "repaired",
    "verification_failed",
)
VALID_RECOVERY_ACTIONS = ("none", "retry_execution", "repair_rollback", "verify_integrity", "stop")
VALID_ROLLBACK_REPAIR_STATUSES = ("not_needed", "pending", "completed", "failed")
VALID_INTEGRITY_STATUSES = ("not_verified", "verified", "issues_detected", "verification_failed")
VALID_IDEMPOTENCY_STATUSES = ("active", "duplicate_success_blocked", "retry_window_open")
VALID_RETRY_POLICY_STATUSES = ("default_no_retry", "retry_authorized", "retry_exhausted")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    s = str(value or "").strip().lower()
    return s if s in allowed else default


def _normalized_command_signature(command_request: dict[str, Any] | None) -> str:
    req = command_request or {}
    parts = [
        str(req.get("request_type") or "").strip().lower(),
        str(req.get("task_type") or "").strip().lower(),
        str(req.get("summary") or "").strip().lower(),
        str(req.get("priority") or "").strip().lower(),
    ]
    return "|".join(parts)


def derive_idempotency_key(package: dict[str, Any] | None) -> str:
    p = package or {}
    package_id = str(p.get("package_id") or "").strip().lower()
    runtime_target_id = str(
        p.get("handoff_executor_target_id")
        or p.get("execution_executor_target_id")
        or p.get("runtime_target_id")
        or ""
    ).strip().lower()
    command_signature = _normalized_command_signature(p.get("command_request"))
    raw = f"{package_id}|{command_signature}|{runtime_target_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_retry_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    max_retry_attempts = value.get("max_retry_attempts")
    retry_count = value.get("retry_count")
    try:
        max_retry_attempts = max(0, int(max_retry_attempts or 0))
    except Exception:
        max_retry_attempts = 0
    try:
        retry_count = max(0, int(retry_count or 0))
    except Exception:
        retry_count = 0
    status = _normalize_enum(value.get("policy_status"), VALID_RETRY_POLICY_STATUSES, "default_no_retry")
    if retry_count >= max_retry_attempts and max_retry_attempts > 0 and status == "retry_authorized":
        status = "retry_exhausted"
    return {
        "policy_status": status,
        "max_retry_attempts": max_retry_attempts,
        "retry_count": retry_count,
        "retry_authorized": bool(value.get("retry_authorized", False)),
        "retry_authorization_id": str(value.get("retry_authorization_id") or ""),
        "retry_reason": _normalize_reason(value.get("retry_reason")),
    }


def normalize_idempotency(value: Any, *, package: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "idempotency_key": str(value.get("idempotency_key") or derive_idempotency_key(package)),
        "idempotency_status": _normalize_enum(value.get("idempotency_status"), VALID_IDEMPOTENCY_STATUSES, "active"),
        "last_success_execution_id": str(value.get("last_success_execution_id") or ""),
        "duplicate_success_blocked": bool(value.get("duplicate_success_blocked", False)),
    }


def normalize_failure_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "failure_stage": _normalize_enum(value.get("failure_stage"), VALID_FAILURE_STAGES, ""),
        "failure_class": _normalize_enum(value.get("failure_class"), VALID_EXECUTION_FAILURE_CLASSES, ""),
        "failure_severity": _normalize_enum(value.get("failure_severity"), VALID_FAILURE_SEVERITIES, ""),
        "last_failure_at": str(value.get("last_failure_at") or ""),
    }


def normalize_recovery_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "recovery_status": _normalize_enum(value.get("recovery_status"), VALID_RECOVERY_STATUSES, "not_needed"),
        "recovery_action": _normalize_enum(value.get("recovery_action"), VALID_RECOVERY_ACTIONS, "none"),
        "recovery_reason": _normalize_reason(value.get("recovery_reason")),
    }


def normalize_rollback_repair(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "rollback_repair_status": _normalize_enum(value.get("rollback_repair_status"), VALID_ROLLBACK_REPAIR_STATUSES, "not_needed"),
        "rollback_repair_timestamp": str(value.get("rollback_repair_timestamp") or ""),
        "rollback_repair_reason": _normalize_reason(value.get("rollback_repair_reason")),
    }


def normalize_integrity_verification(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    summary = value.get("integrity_summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "integrity_status": _normalize_enum(value.get("integrity_status"), VALID_INTEGRITY_STATUSES, "not_verified"),
        "integrity_timestamp": str(value.get("integrity_timestamp") or ""),
        "integrity_reason": _normalize_reason(value.get("integrity_reason")),
        "integrity_summary": {
            "log_ref_present": bool(summary.get("log_ref_present", False)),
            "runtime_artifact_linked": bool(summary.get("runtime_artifact_linked", False)),
            "timestamps_consistent": bool(summary.get("timestamps_consistent", False)),
            "rollback_consistent": bool(summary.get("rollback_consistent", False)),
        },
    }


def build_default_hardening_fields(package: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "retry_policy": normalize_retry_policy(None),
        "idempotency": normalize_idempotency(None, package=package),
        "failure_summary": normalize_failure_summary(None),
        "recovery_summary": normalize_recovery_summary(None),
        "rollback_repair": normalize_rollback_repair(None),
        "integrity_verification": normalize_integrity_verification(None),
    }


def summarize_failure(*, failure_class: str, timestamp: str | None = None) -> dict[str, Any]:
    failure_class = _normalize_enum(failure_class, VALID_EXECUTION_FAILURE_CLASSES, "")
    stage = ""
    severity = ""
    if failure_class in ("preflight_block", "aegis_block", "duplicate_success_block", "retry_not_authorized", "retry_exhausted"):
        stage = "preflight"
        severity = "medium"
    elif failure_class in ("runtime_start_failure", "runtime_execution_failure"):
        stage = "execution"
        severity = "high"
    elif failure_class in ("rollback_failure", "rollback_repair_failure"):
        stage = "rollback"
        severity = "high"
    elif failure_class == "integrity_verification_failure":
        stage = "verification"
        severity = "medium"
    return normalize_failure_summary(
        {
            "failure_stage": stage,
            "failure_class": failure_class,
            "failure_severity": severity,
            "last_failure_at": timestamp or "",
        }
    )


def evaluate_recovery_summary(
    *,
    execution_status: str,
    failure_summary: dict[str, Any] | None,
    retry_policy: dict[str, Any] | None,
    rollback_repair: dict[str, Any] | None,
    integrity_verification: dict[str, Any] | None,
) -> dict[str, Any]:
    failure = normalize_failure_summary(failure_summary)
    retry = normalize_retry_policy(retry_policy)
    repair = normalize_rollback_repair(rollback_repair)
    integrity = normalize_integrity_verification(integrity_verification)
    status = str(execution_status or "").strip().lower()

    if repair.get("rollback_repair_status") in ("pending", "failed"):
        return normalize_recovery_summary(
            {
                "recovery_status": "repair_required",
                "recovery_action": "repair_rollback",
                "recovery_reason": {"code": "rollback_repair_required", "message": "Rollback repair requires manual handling."},
            }
        )

    if status in ("failed", "blocked", "rolled_back"):
        retryable = failure.get("failure_class") in (
            "duplicate_success_block",
            "retry_not_authorized",
            "retry_exhausted",
            "runtime_start_failure",
            "runtime_execution_failure",
            "rollback_failure",
            "rollback_repair_failure",
            "integrity_verification_failure",
        )
        if retryable and retry.get("retry_authorized") and retry.get("retry_count", 0) < retry.get("max_retry_attempts", 0):
            return normalize_recovery_summary(
                {
                    "recovery_status": "retry_ready",
                    "recovery_action": "retry_execution",
                    "recovery_reason": {"code": "retry_ready", "message": "Retry is explicitly authorized for this failed execution package."},
                }
            )
        if retryable:
            code = "retry_exhausted" if retry.get("policy_status") == "retry_exhausted" else "retry_not_authorized"
            return normalize_recovery_summary(
                {
                    "recovery_status": "retry_blocked",
                    "recovery_action": "stop",
                    "recovery_reason": {"code": code, "message": "Retry is blocked unless an explicit future retry policy authorizes it."},
                }
            )

    if integrity.get("integrity_status") in ("issues_detected", "verification_failed"):
        return normalize_recovery_summary(
            {
                "recovery_status": "verification_failed",
                "recovery_action": "verify_integrity",
                "recovery_reason": {"code": "integrity_verification_failed", "message": "Post-execution integrity verification detected issues."},
            }
        )

    return normalize_recovery_summary(None)


def verify_terminal_execution_integrity(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    receipt = p.get("execution_receipt") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    execution_status = str(p.get("execution_status") or "").strip().lower()
    rollback_status = str(p.get("rollback_status") or "").strip().lower()
    started_at = str(p.get("execution_started_at") or "")
    finished_at = str(p.get("execution_finished_at") or "")
    log_ref = str(receipt.get("log_ref") or "")

    runtime_attempted = execution_status in ("succeeded", "failed", "rolled_back")
    log_ref_present = bool(log_ref) if runtime_attempted else True
    runtime_artifact_linked = any(
        isinstance(item, dict)
        and str(item.get("artifact_type") or "").strip().lower() == "execution_log"
        and str(item.get("log_ref") or "").strip() == log_ref
        for item in runtime_artifacts
    ) if runtime_attempted else True
    timestamps_consistent = bool(started_at and finished_at and started_at <= finished_at) if runtime_attempted else bool(finished_at)
    rollback_consistent = True
    if execution_status == "rolled_back":
        rollback_consistent = rollback_status == "completed"
    elif execution_status == "failed":
        rollback_consistent = rollback_status in ("not_needed", "failed", "completed")
    elif execution_status == "succeeded":
        rollback_consistent = rollback_status == "not_needed"
    elif execution_status == "blocked":
        rollback_consistent = rollback_status == "not_needed"

    summary = {
        "log_ref_present": log_ref_present,
        "runtime_artifact_linked": runtime_artifact_linked,
        "timestamps_consistent": timestamps_consistent,
        "rollback_consistent": rollback_consistent,
    }
    ok = all(summary.values())
    status = "verified" if ok else "issues_detected"
    message = "Post-execution integrity verification passed." if ok else "Post-execution integrity verification detected issues."
    if execution_status not in ("succeeded", "failed", "blocked", "rolled_back"):
        status = "not_verified"
        message = "Execution state is not terminal; integrity verification not run."
    return normalize_integrity_verification(
        {
            "integrity_status": status,
            "integrity_timestamp": utc_now_iso() if status != "not_verified" else "",
            "integrity_reason": {
                "code": "verified" if status == "verified" else ("integrity_verification_failure" if status != "not_verified" else ""),
                "message": message,
            },
            "integrity_summary": summary,
        }
    )
