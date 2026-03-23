"""
NEXUS runtime execution result normalization.

Shared helpers for building a stable execution-oriented result schema for all
runtime adapters and dispatcher paths. Planning/dispatch only; no real execution.
"""

from __future__ import annotations

from typing import Any


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
    }
    if isinstance(extra_fields, dict):
        result.update(extra_fields)
    return result


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

