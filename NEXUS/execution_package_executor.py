"""
Controlled runtime execution bridge for execution packages.

Executes through a narrow logged runtime boundary, never bypasses package-state
gates or AEGIS, and uses rollback_notes only for rollback guidance logging.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.executor_backends import get_executor_backend, get_executor_backend_status
from NEXUS.executor_backends.contracts import normalize_executor_response_v1
from NEXUS.execution_package_hardening import normalize_rollback_repair, summarize_failure


EXECUTION_RUN_DIRNAME = "execution_runs"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_execution_run_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        state_dir = Path(project_path).resolve() / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        run_dir = state_dir / EXECUTION_RUN_DIRNAME
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    except Exception:
        return None


def _append_log(log_path: Path, lines: list[str]) -> bool:
    try:
        text = "\n".join(lines).strip() + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False


def _receipt(
    *,
    result_status: str,
    exit_code: int | None,
    log_ref: str,
    files_touched_count: int = 0,
    artifacts_written_count: int = 0,
    failure_class: str = "",
    stdout_summary: str = "",
    stderr_summary: str = "",
    rollback_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "result_status": str(result_status or ""),
        "exit_code": exit_code,
        "log_ref": str(log_ref or ""),
        "files_touched_count": max(0, int(files_touched_count or 0)),
        "artifacts_written_count": max(0, int(artifacts_written_count or 0)),
        "failure_class": str(failure_class or ""),
        "stdout_summary": str(stdout_summary or "")[:500],
        "stderr_summary": str(stderr_summary or "")[:500],
        "rollback_summary": dict(rollback_summary or {}),
    }


def _resolve_backend_id(package: dict[str, Any] | None) -> str:
    p = package or {}
    execution_backend_id = str(p.get("execution_executor_backend_id") or "").strip().lower()
    if execution_backend_id:
        return execution_backend_id
    metadata = p.get("metadata")
    if isinstance(metadata, dict):
        return str(metadata.get("executor_backend_id") or "").strip().lower()
    return ""


def _attempt_rollback(*, log_path: Path | None, rollback_notes: list[str] | None) -> dict[str, Any]:
    notes = [str(x) for x in (rollback_notes or []) if str(x).strip()][:20]
    if not notes:
        return {
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "rollback_summary": {"used_notes": False, "notes_count": 0},
        }
    ts = _utc_now_iso()
    ok = bool(log_path) and _append_log(
        log_path,
        ["[rollback] rollback guidance recorded from package rollback_notes:"] + [f"[rollback] {note}" for note in notes],
    )
    if ok:
        return {
            "rollback_status": "completed",
            "rollback_timestamp": ts,
            "rollback_reason": {"code": "rollback_completed", "message": "Rollback guidance recorded from rollback_notes."},
            "rollback_summary": {"used_notes": True, "notes_count": len(notes)},
        }
    return {
        "rollback_status": "failed",
        "rollback_timestamp": ts,
        "rollback_reason": {"code": "rollback_failed", "message": "Failed to record rollback guidance from rollback_notes."},
        "rollback_summary": {"used_notes": True, "notes_count": len(notes)},
    }


def _map_executor_response_to_execution_result(
    *,
    execution_id: str,
    target_id: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_executor_response_v1(response)
    adapter_status = str(normalized.get("adapter_status") or "").strip().lower()
    if not normalized.get("backend_id") or adapter_status != "active":
        failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": "Controlled executor adapter is unavailable."},
            "execution_receipt": _receipt(
                result_status="failed",
                exit_code=normalized.get("exit_code"),
                log_ref=str(normalized.get("log_ref") or ""),
                files_touched_count=normalized.get("files_touched_count") or 0,
                artifacts_written_count=normalized.get("artifacts_written_count") or 0,
                failure_class="runtime_start_failure",
                stdout_summary=str(normalized.get("stdout_summary") or ""),
                stderr_summary=str(normalized.get("stderr_summary") or ""),
                rollback_summary=normalized.get("rollback_summary") or {},
            ),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": failure_summary,
            "rollback_repair": normalize_rollback_repair(None),
            "runtime_artifact": dict(normalized.get("runtime_artifact") or {}),
            "execution_finished_at": _utc_now_iso(),
        }

    result_status = str(normalized.get("result_status") or "").strip().lower()
    failure_class = str(normalized.get("failure_class") or "").strip().lower()
    if result_status == "succeeded" and not failure_class:
        return {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "Package executed through the controlled runtime boundary."},
            "execution_receipt": _receipt(
                result_status="succeeded",
                exit_code=normalized.get("exit_code"),
                log_ref=str(normalized.get("log_ref") or ""),
                files_touched_count=normalized.get("files_touched_count") or 0,
                artifacts_written_count=normalized.get("artifacts_written_count") or 0,
                stdout_summary=str(normalized.get("stdout_summary") or ""),
                stderr_summary=str(normalized.get("stderr_summary") or ""),
                rollback_summary=normalized.get("rollback_summary") or {},
            ),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": summarize_failure(failure_class="", timestamp=""),
            "rollback_repair": normalize_rollback_repair(None),
            "runtime_artifact": dict(normalized.get("runtime_artifact") or {
                "artifact_type": "execution_log",
                "execution_id": execution_id,
                "log_ref": str(normalized.get("log_ref") or ""),
                "runtime_target_id": target_id,
            }),
            "execution_finished_at": _utc_now_iso(),
        }

    if failure_class not in ("runtime_execution_failure", "rollback_failure"):
        failure_class = "runtime_start_failure"
    rollback_status = "failed" if failure_class == "rollback_failure" else "not_needed"
    rollback_repair = normalize_rollback_repair(None)
    if failure_class == "rollback_failure":
        rollback_repair = normalize_rollback_repair(
            {
                "rollback_repair_status": "pending",
                "rollback_repair_timestamp": _utc_now_iso(),
                "rollback_repair_reason": {
                    "code": "rollback_repair_required",
                    "message": "Rollback repair requires manual handling after rollback failure.",
                },
            }
        )
    failure_summary = summarize_failure(failure_class=failure_class, timestamp=_utc_now_iso())
    return {
        "execution_status": "failed",
        "execution_reason": {
            "code": "runtime_execution_failed" if failure_class != "runtime_start_failure" else "runtime_start_failed",
            "message": "Controlled executor execution failed." if failure_class != "runtime_start_failure" else "Controlled executor failed to start correctly.",
        },
        "execution_receipt": _receipt(
            result_status="failed",
            exit_code=normalized.get("exit_code"),
            log_ref=str(normalized.get("log_ref") or ""),
            files_touched_count=normalized.get("files_touched_count") or 0,
            artifacts_written_count=normalized.get("artifacts_written_count") or 0,
            failure_class=failure_class,
            stdout_summary=str(normalized.get("stdout_summary") or ""),
            stderr_summary=str(normalized.get("stderr_summary") or ""),
            rollback_summary=normalized.get("rollback_summary") or {},
        ),
        "rollback_status": rollback_status,
        "rollback_timestamp": _utc_now_iso() if rollback_status == "failed" else "",
        "rollback_reason": {"code": "rollback_failed", "message": "Rollback/reporting failed."} if rollback_status == "failed" else {"code": "", "message": ""},
        "failure_summary": failure_summary,
        "rollback_repair": rollback_repair,
        "runtime_artifact": dict(normalized.get("runtime_artifact") or {
            "artifact_type": "execution_log",
            "execution_id": execution_id,
            "log_ref": str(normalized.get("log_ref") or ""),
            "runtime_target_id": target_id,
        }),
        "execution_finished_at": _utc_now_iso(),
    }


def execute_execution_package(
    *,
    project_path: str | None,
    package: dict[str, Any] | None,
    execution_id: str,
    execution_actor: str,
) -> dict[str, Any]:
    """Execute through a controlled runtime boundary and return a summary-only result."""
    p = package or {}
    target_id = str(p.get("execution_executor_target_id") or p.get("handoff_executor_target_id") or p.get("runtime_target_id") or "local").strip().lower()
    backend_id = _resolve_backend_id(p)
    run_dir = _get_execution_run_dir(project_path)
    if not run_dir:
        failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": "Execution run directory unavailable."},
            "execution_receipt": _receipt(result_status="failed", exit_code=None, log_ref="", failure_class="runtime_start_failure"),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": failure_summary,
            "rollback_repair": normalize_rollback_repair(None),
            "runtime_artifact": {},
            "execution_finished_at": _utc_now_iso(),
        }

    log_path = run_dir / f"{execution_id}.log"
    started_at = _utc_now_iso()
    _append_log(
        log_path,
        [
            f"[start] execution_id={execution_id}",
            f"[start] actor={execution_actor}",
            f"[start] target={target_id}",
            f"[start] backend={backend_id or 'default'}",
            f"[start] package_id={p.get('package_id')}",
            f"[start] started_at={started_at}",
        ],
    )

    if backend_id == "openclaw":
        backend_status = get_executor_backend_status(backend_id)
        if str(backend_status.get("adapter_status") or "").strip().lower() != "active":
            _append_log(log_path, [f"[error] executor_backend_inactive={backend_id}"])
            failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
            return {
                "execution_status": "failed",
                "execution_reason": {"code": "runtime_start_failed", "message": "Controlled executor backend is inactive."},
                "execution_receipt": _receipt(
                    result_status="failed",
                    exit_code=None,
                    log_ref=str(log_path),
                    artifacts_written_count=1,
                    failure_class="runtime_start_failure",
                    stderr_summary=f"backend_inactive:{backend_id}",
                ),
                "rollback_status": "not_needed",
                "rollback_timestamp": "",
                "rollback_reason": {"code": "", "message": ""},
                "failure_summary": failure_summary,
                "rollback_repair": normalize_rollback_repair(None),
                "runtime_artifact": {},
                "execution_finished_at": _utc_now_iso(),
            }
        backend = get_executor_backend(backend_id)
        executor = (backend or {}).get("executor")
        if not callable(executor):
            _append_log(log_path, [f"[error] executor_backend_missing={backend_id}"])
            failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
            return {
                "execution_status": "failed",
                "execution_reason": {"code": "runtime_start_failed", "message": "Controlled executor backend unavailable."},
                "execution_receipt": _receipt(
                    result_status="failed",
                    exit_code=None,
                    log_ref=str(log_path),
                    artifacts_written_count=1,
                    failure_class="runtime_start_failure",
                    stderr_summary=f"backend_missing:{backend_id}",
                ),
                "rollback_status": "not_needed",
                "rollback_timestamp": "",
                "rollback_reason": {"code": "", "message": ""},
                "failure_summary": failure_summary,
                "rollback_repair": normalize_rollback_repair(None),
                "runtime_artifact": {},
                "execution_finished_at": _utc_now_iso(),
            }
        try:
            backend_response = executor(
                project_path=project_path,
                package=p,
                execution_id=execution_id,
                execution_actor=execution_actor,
                log_path=str(log_path),
            )
        except Exception as e:
            backend_response = {
                "status": "error",
                "result_status": "failed",
                "exit_code": None,
                "stdout_summary": "",
                "stderr_summary": str(e),
                "log_ref": str(log_path),
                "files_touched_count": 0,
                "artifacts_written_count": 1,
                "failure_class": "runtime_start_failure",
                "runtime_artifact": {},
                "rollback_summary": {},
                "adapter_status": "error",
                "backend_id": backend_id,
            }
        return _map_executor_response_to_execution_result(
            execution_id=execution_id,
            target_id=target_id,
            response=backend_response,
        )

    try:
        proc = subprocess.run(
            ["cmd", "/c", "echo", f"FORGE controlled execution bridge {execution_id} target={target_id}"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_path or None,
            check=False,
        )
    except Exception as e:
        _append_log(log_path, [f"[error] runtime_start_failure={e}"])
        failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": "Controlled runtime boundary failed to start."},
            "execution_receipt": _receipt(
                result_status="failed",
                exit_code=None,
                log_ref=str(log_path),
                artifacts_written_count=1,
                failure_class="runtime_start_failure",
                stderr_summary=str(e),
            ),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": failure_summary,
            "rollback_repair": normalize_rollback_repair(None),
            "runtime_artifact": {},
            "execution_finished_at": _utc_now_iso(),
        }

    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()
    _append_log(
        log_path,
        [
            f"[result] exit_code={proc.returncode}",
            f"[stdout] {stdout_text}",
            f"[stderr] {stderr_text}",
        ],
    )

    if proc.returncode != 0:
        rollback = _attempt_rollback(log_path=log_path, rollback_notes=p.get("rollback_notes"))
        failure_class = "runtime_execution_failure"
        if rollback.get("rollback_status") == "failed":
            failure_class = "rollback_failure"
        rollback_repair = normalize_rollback_repair(None)
        if rollback.get("rollback_status") == "failed":
            rollback_repair = normalize_rollback_repair(
                {
                    "rollback_repair_status": "pending",
                    "rollback_repair_timestamp": rollback.get("rollback_timestamp") or _utc_now_iso(),
                    "rollback_repair_reason": {
                        "code": "rollback_repair_required",
                        "message": "Rollback repair requires manual handling after rollback failure.",
                    },
                }
            )
        return {
            "execution_status": "rolled_back" if rollback.get("rollback_status") == "completed" else "failed",
            "execution_reason": {
                "code": "rolled_back" if rollback.get("rollback_status") == "completed" else "runtime_execution_failed",
                "message": "Runtime execution failed; rollback guidance recorded." if rollback.get("rollback_status") == "completed" else "Runtime execution failed.",
            },
            "execution_receipt": _receipt(
                result_status="failed",
                exit_code=proc.returncode,
                log_ref=str(log_path),
                artifacts_written_count=1,
                failure_class=failure_class,
                stdout_summary=stdout_text,
                stderr_summary=stderr_text,
                rollback_summary=rollback.get("rollback_summary") or {},
            ),
            "rollback_status": rollback.get("rollback_status") or "not_needed",
            "rollback_timestamp": rollback.get("rollback_timestamp") or "",
            "rollback_reason": rollback.get("rollback_reason") or {"code": "", "message": ""},
            "failure_summary": summarize_failure(failure_class=failure_class, timestamp=_utc_now_iso()),
            "rollback_repair": rollback_repair,
            "runtime_artifact": {
                "artifact_type": "execution_log",
                "execution_id": execution_id,
                "log_ref": str(log_path),
                "runtime_target_id": target_id,
            },
            "execution_finished_at": _utc_now_iso(),
        }

    return {
        "execution_status": "succeeded",
        "execution_reason": {"code": "succeeded", "message": "Package executed through the controlled runtime boundary."},
        "execution_receipt": _receipt(
            result_status="succeeded",
            exit_code=proc.returncode,
            log_ref=str(log_path),
            artifacts_written_count=1,
            stdout_summary=stdout_text,
            stderr_summary=stderr_text,
        ),
        "rollback_status": "not_needed",
        "rollback_timestamp": "",
        "rollback_reason": {"code": "", "message": ""},
        "failure_summary": summarize_failure(failure_class="", timestamp=""),
        "rollback_repair": normalize_rollback_repair(None),
        "runtime_artifact": {
            "artifact_type": "execution_log",
            "execution_id": execution_id,
            "log_ref": str(log_path),
            "runtime_target_id": target_id,
        },
        "execution_finished_at": _utc_now_iso(),
    }


def execute_execution_package_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return execute_execution_package(**kwargs)
    except Exception as e:
        failure_summary = summarize_failure(failure_class="runtime_start_failure", timestamp=_utc_now_iso())
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": f"Controlled runtime execution failed: {e}"},
            "execution_receipt": _receipt(result_status="failed", exit_code=None, log_ref="", failure_class="runtime_start_failure", stderr_summary=str(e)),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": failure_summary,
            "rollback_repair": normalize_rollback_repair(None),
            "runtime_artifact": {},
            "execution_finished_at": _utc_now_iso(),
        }
