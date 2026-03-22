"""
OpenClaw controlled executor backend.

This adapter is execution-boundary only. It does not route, plan, or decide.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from NEXUS.executor_backends.contracts import build_executor_response_v1


ADAPTER_STATUS = "active"
BACKEND_ID = "openclaw"


def get_adapter_status() -> dict[str, Any]:
    return {
        "backend_id": BACKEND_ID,
        "adapter_status": ADAPTER_STATUS,
        "controlled_executor_only": True,
    }


def _append_log(log_path: str | None, lines: list[str]) -> None:
    if not log_path:
        return
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(("\n".join(lines).strip() + "\n"))
    except Exception:
        pass


def execute_openclaw_package(
    *,
    project_path: str | None,
    package: dict[str, Any] | None,
    execution_id: str,
    execution_actor: str,
    log_path: str | None,
) -> dict[str, Any]:
    p = package or {}
    target_id = str(p.get("execution_executor_target_id") or p.get("handoff_executor_target_id") or "openclaw").strip().lower()
    _append_log(
        log_path,
        [
            f"[openclaw] execution_id={execution_id}",
            f"[openclaw] actor={execution_actor}",
            f"[openclaw] target={target_id}",
            "[openclaw] mode=controlled_executor_only",
        ],
    )
    try:
        proc = subprocess.run(
            ["cmd", "/c", "echo", f"FORGE OpenClaw controlled execution {execution_id} target={target_id}"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_path or None,
            check=False,
        )
    except Exception as e:
        _append_log(log_path, [f"[openclaw][error] startup={e}"])
        return build_executor_response_v1(
            status="error",
            result_status="failed",
            exit_code=None,
            stderr_summary=str(e),
            log_ref=str(log_path or ""),
            artifacts_written_count=1 if log_path else 0,
            failure_class="runtime_start_failure",
            runtime_artifact={
                "artifact_type": "execution_log",
                "execution_id": execution_id,
                "log_ref": str(log_path or ""),
                "runtime_target_id": target_id,
            } if log_path else {},
            adapter_status=ADAPTER_STATUS,
            backend_id=BACKEND_ID,
        )

    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()
    _append_log(
        log_path,
        [
            f"[openclaw][result] exit_code={proc.returncode}",
            f"[openclaw][stdout] {stdout_text}",
            f"[openclaw][stderr] {stderr_text}",
        ],
    )
    failure_class = "" if proc.returncode == 0 else "runtime_execution_failure"
    return build_executor_response_v1(
        status="ok" if proc.returncode == 0 else "error",
        result_status="succeeded" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode,
        stdout_summary=stdout_text,
        stderr_summary=stderr_text,
        log_ref=str(log_path or ""),
        files_touched_count=0,
        artifacts_written_count=1 if log_path else 0,
        failure_class=failure_class,
        runtime_artifact={
            "artifact_type": "execution_log",
            "execution_id": execution_id,
            "log_ref": str(log_path or ""),
            "runtime_target_id": target_id,
        } if log_path else {},
        adapter_status=ADAPTER_STATUS,
        backend_id=BACKEND_ID,
    )
