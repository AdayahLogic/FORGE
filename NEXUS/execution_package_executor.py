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
    run_dir = _get_execution_run_dir(project_path)
    if not run_dir:
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": "Execution run directory unavailable."},
            "execution_receipt": _receipt(result_status="failed", exit_code=None, log_ref="", failure_class="runtime_start_failure"),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
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
            f"[start] package_id={p.get('package_id')}",
            f"[start] started_at={started_at}",
        ],
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
        return {
            "execution_status": "failed",
            "execution_reason": {"code": "runtime_start_failed", "message": f"Controlled runtime execution failed: {e}"},
            "execution_receipt": _receipt(result_status="failed", exit_code=None, log_ref="", failure_class="runtime_start_failure", stderr_summary=str(e)),
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "runtime_artifact": {},
            "execution_finished_at": _utc_now_iso(),
        }
