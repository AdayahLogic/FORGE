"""
Failure handling and conflict escalation summaries.
"""

from __future__ import annotations

from typing import Any


def build_failure_handling_summary(
    *,
    stage_results: list[dict[str, Any]] | None = None,
    pipeline_status: str | None = None,
    stop_reason: str | None = None,
    authority_trace: dict[str, Any] | None = None,
    contract_validation: dict[str, Any] | None = None,
    governance_conflict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = [dict(item) for item in (stage_results or []) if isinstance(item, dict)]
    authority = authority_trace or {}
    contract = contract_validation or {}
    conflict = governance_conflict or {}
    stage_failures = [
        {
            "stage": str(item.get("stage") or ""),
            "stage_status": str(item.get("stage_status") or ""),
            "reason": str(item.get("repair_reason") or item.get("output_summary") or "")[:300],
        }
        for item in results
        if str(item.get("stage_status") or "").strip().lower() in ("issues_detected", "error_fallback", "repair_recommended")
    ][:10]

    system_pause_required = bool(
        authority.get("violation_detected")
        or contract.get("contract_status") == "invalid"
        or conflict.get("system_pause_required")
    )
    if system_pause_required:
        recovery_pipeline = ["pause_system", "await_operator_review", "resolve_conflict", "resume_when_approved"]
        failure_pipeline_status = "system_pause_required"
        conflict_status = "unresolved_conflict"
    elif stage_failures or str(pipeline_status or "").strip().lower() in ("blocked", "error_fallback"):
        recovery_pipeline = ["collect_failure_evidence", "re-run_governance_checks", "prepare_recovery_package", "await_review"]
        failure_pipeline_status = "recovery_required"
        conflict_status = "resolved_or_none"
    else:
        recovery_pipeline = ["none_required"]
        failure_pipeline_status = "healthy"
        conflict_status = "resolved_or_none"

    return {
        "failure_pipeline_status": failure_pipeline_status,
        "recovery_pipeline": recovery_pipeline,
        "stage_failures": stage_failures,
        "authority_violation_detected": bool(authority.get("violation_detected")),
        "contract_status": str(contract.get("contract_status") or ""),
        "stop_reason": str(stop_reason or ""),
        "conflict_status": conflict_status,
        "system_pause_required": system_pause_required,
        "pause_reason": str(conflict.get("resolution_reason") or authority.get("decision_reason") or stop_reason or ""),
    }

