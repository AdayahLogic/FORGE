"""
Executor backend response normalization helpers.

ExecutorResponseV1 is the stable adapter-facing shape for controlled executor
backends such as OpenClaw. It is normalized before being mapped into the
existing execution package result contract.
"""

from __future__ import annotations

from typing import Any

from NEXUS.execution_package_hardening import VALID_EXECUTION_FAILURE_CLASSES


VALID_EXECUTOR_STATUSES = ("ok", "error")
VALID_ADAPTER_STATUSES = ("active", "inactive", "error")


def _normalize_failure_class(value: Any, default: str = "") -> str:
    s = str(value or "").strip().lower()
    if s in VALID_EXECUTION_FAILURE_CLASSES:
        return s
    return default if default in VALID_EXECUTION_FAILURE_CLASSES else ""


def build_executor_response_v1(
    *,
    status: str,
    result_status: str,
    exit_code: int | None = None,
    stdout_summary: str = "",
    stderr_summary: str = "",
    log_ref: str = "",
    files_touched_count: int = 0,
    artifacts_written_count: int = 0,
    failure_class: str = "",
    runtime_artifact: dict[str, Any] | None = None,
    rollback_summary: dict[str, Any] | None = None,
    adapter_status: str = "",
    backend_id: str = "",
) -> dict[str, Any]:
    return normalize_executor_response_v1(
        {
            "status": status,
            "result_status": result_status,
            "exit_code": exit_code,
            "stdout_summary": stdout_summary,
            "stderr_summary": stderr_summary,
            "log_ref": log_ref,
            "files_touched_count": files_touched_count,
            "artifacts_written_count": artifacts_written_count,
            "failure_class": failure_class,
            "runtime_artifact": runtime_artifact or {},
            "rollback_summary": rollback_summary or {},
            "adapter_status": adapter_status,
            "backend_id": backend_id,
        }
    )


def normalize_executor_response_v1(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    exit_code = value.get("exit_code")
    if not isinstance(exit_code, int):
        try:
            exit_code = int(exit_code) if exit_code not in (None, "") else None
        except Exception:
            exit_code = None
    status = str(value.get("status") or "").strip().lower()
    if status not in VALID_EXECUTOR_STATUSES:
        status = "error"
    adapter_status = str(value.get("adapter_status") or "").strip().lower()
    if adapter_status not in VALID_ADAPTER_STATUSES:
        adapter_status = "error"
    runtime_artifact = value.get("runtime_artifact")
    if not isinstance(runtime_artifact, dict):
        runtime_artifact = {}
    rollback_summary = value.get("rollback_summary")
    if not isinstance(rollback_summary, dict):
        rollback_summary = {}
    return {
        "status": status,
        "result_status": str(value.get("result_status") or ""),
        "exit_code": exit_code,
        "stdout_summary": str(value.get("stdout_summary") or "")[:500],
        "stderr_summary": str(value.get("stderr_summary") or "")[:500],
        "log_ref": str(value.get("log_ref") or ""),
        "files_touched_count": max(0, int(value.get("files_touched_count") or 0)),
        "artifacts_written_count": max(0, int(value.get("artifacts_written_count") or 0)),
        "failure_class": _normalize_failure_class(value.get("failure_class")),
        "runtime_artifact": runtime_artifact,
        "rollback_summary": rollback_summary,
        "adapter_status": adapter_status,
        "backend_id": str(value.get("backend_id") or "").strip().lower(),
    }
