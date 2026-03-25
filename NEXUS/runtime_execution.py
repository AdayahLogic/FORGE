"""
NEXUS runtime execution result normalization.

Shared helpers for building a stable execution-oriented result schema for all
runtime adapters and dispatcher paths. Planning/dispatch only; no real execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _build_runtime_cost_tracking(
    *,
    runtime: str,
    status: str,
    artifacts: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact_count = len(artifacts or [])
    error_count = len(errors or [])
    estimated_tokens = 120 + (artifact_count * 60) + (error_count * 40)
    if str(status or "").strip().lower() in {"error", "blocked"}:
        estimated_tokens += 40
    estimated_cost = round((estimated_tokens / 1000.0) * 0.004, 6)
    return {
        "cost_estimate": estimated_cost,
        "cost_unit": "usd_estimated",
        "cost_source": "runtime_execution",
        "cost_breakdown": {
            "model": f"{str(runtime or 'runtime').strip().lower()}_runtime_estimator",
            "estimated_tokens": estimated_tokens,
            "estimated_cost": estimated_cost,
        },
    }


def build_runtime_execution_result(
    *,
    runtime: str,
    status: str,
    message: str,
    execution_status: str = "not_started",
    execution_mode: str = "safe_simulation",
    next_action: str = "none",
    artifacts: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a normalized runtime execution result.

    Schema (stable):
    - runtime: string
    - status: accepted | skipped | no_adapter | error | blocked
    - message: human-readable
    - execution_status: not_started | simulated_execution | queued | blocked | failed
    - execution_mode: safe_simulation | manual_only | direct_local | external_runtime
    - next_action: small hint for next step
    - artifacts: list
    - errors: list
    """
    result = {
        "runtime": runtime,
        "status": status,
        "message": message,
        "execution_status": execution_status,
        "execution_mode": execution_mode,
        "next_action": next_action,
        "artifacts": artifacts or [],
        "errors": errors or [],
        "cost_tracking": _build_runtime_cost_tracking(
            runtime=runtime,
            status=status,
            artifacts=artifacts,
            errors=errors,
        ),
    }
    if isinstance(extra_fields, dict):
        result.update(extra_fields)
    return result


def build_runtime_target_selection_snapshot(selection: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize the execution target-selection contract for persistence on dispatch results.
    """
    payload = selection if isinstance(selection, dict) else {}
    return {
        "status": str(payload.get("status") or "").strip().lower(),
        "selected_target_id": str(payload.get("selected_target_id") or "").strip().lower(),
        "candidate_target_ids": [str(item).strip().lower() for item in (payload.get("candidate_target_ids") or []) if str(item).strip()],
        "target_type": str(payload.get("target_type") or "").strip().lower(),
        "capability_match": bool(payload.get("capability_match")),
        "readiness_status": str(payload.get("readiness_status") or "").strip().lower(),
        "availability_status": str(payload.get("availability_status") or "").strip().lower(),
        "denial_reason": str(payload.get("denial_reason") or "").strip(),
        "selection_reason": str(payload.get("selection_reason") or "").strip(),
        "routing_outcome": str(payload.get("routing_outcome") or "").strip().lower(),
        "governance_trace": dict(payload.get("governance_trace") or {}),
        "recorded_at": str(payload.get("recorded_at") or datetime.now().isoformat()),
    }


def build_runtime_execution_error(
    *,
    runtime: str,
    message: str,
    error: str | None = None,
    execution_mode: str = "safe_simulation",
) -> dict[str, Any]:
    """Build a normalized error result."""
    errs: list[dict[str, Any]] = []
    if error:
        errs.append({"error": error})
    return build_runtime_execution_result(
        runtime=runtime,
        status="error",
        message=message,
        execution_status="failed",
        execution_mode=execution_mode,
        next_action="human_review",
        errors=errs,
    )


def build_runtime_execution_skipped(
    *,
    runtime: str,
    message: str,
    reason: str = "not_ready",
    execution_mode: str = "safe_simulation",
) -> dict[str, Any]:
    """Build a normalized skipped result."""
    return build_runtime_execution_result(
        runtime=runtime,
        status="skipped",
        message=message,
        execution_status="not_started",
        execution_mode=execution_mode,
        next_action="none",
        errors=[{"reason": reason}] if reason else [],
    )

