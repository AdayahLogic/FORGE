"""
AEGIS ForgeShell: secure shell wrapper for allowlisted command families only.

- Structured command requests only; no unrestricted shell.
- MVP families: shell_test, shell_lint, shell_build, git_status.
- Validates arguments, enforces timeouts, scoped cwd, blocks dangerous patterns.
- Logs execution via NEXUS/AEGIS logging.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

# Allowlisted command families and their safe MVP argv (no user-controlled args in MVP).
_FAMILIES: dict[str, list[list[str]]] = {
    "shell_test": [
        ["python", "-m", "pytest", "--collect-only", "-q"],
        ["python", "-c", "print('test_probe_ok')"],
    ],
    "shell_lint": [
        ["python", "-m", "ruff", "check", "--help"],
        ["python", "-c", "print('lint_probe_ok')"],
    ],
    "shell_build": [
        ["python", "-c", "print('build_probe_ok')"],
    ],
    "git_status": [
        ["git", "status", "--porcelain"],
        ["git", "rev-parse", "--is-inside-work-tree"],
    ],
}

# Dangerous substrings that must not appear in any request (block even if family matches).
_DANGEROUS_PATTERNS = (
    "&&", "||", ";", "|", "&", "`", "$(", "${", "sudo", "su ", "chmod", "chown",
    "rm ", "rm -", "mkfs", "dd ", ">", "<", "eval", "exec(", "subprocess.Popen",
    "os.system", "__import__", "compile(", "breakpoint",
)


def _blocked_reason(request: dict[str, Any]) -> str | None:
    """Return reason string if request is dangerous or invalid; else None."""
    raw = str(request.get("raw_command") or "").strip()
    if raw:
        lower = raw.lower()
        for p in _DANGEROUS_PATTERNS:
            if p in lower or p in raw:
                return f"Blocked: dangerous pattern '{p}'."
    cmd_family = str(request.get("command_family") or "").strip().lower()
    if cmd_family and cmd_family not in _FAMILIES:
        return f"Blocked: unsupported command_family '{cmd_family}'."
    return None


def execute_forgeshell_command(
    *,
    command_family: str,
    project_path: str | None = None,
    timeout_seconds: float = 30.0,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute an allowlisted ForgeShell command in a scoped workspace.

    Result shape:
    {
      "forgeshell_status": "executed" | "blocked" | "error_fallback",
      "stdout": "...",
      "stderr": "...",
      "exit_code": 0,
      "timeout_hit": false,
      "blocked_reason": null
    }
    """
    req = request or {}
    family = str(command_family or req.get("command_family") or "").strip().lower()
    if not family or family not in _FAMILIES:
        return {
            "forgeshell_status": "blocked",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": f"Unsupported or missing command_family: {family!r}.",
        }
    reason = _blocked_reason(req)
    if reason:
        return {
            "forgeshell_status": "blocked",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": reason,
        }
    cwd: Path | None = None
    if project_path:
        try:
            cwd = Path(project_path).resolve()
            if not cwd.is_dir():
                return {
                    "forgeshell_status": "error_fallback",
                    "stdout": "",
                    "stderr": str(project_path),
                    "exit_code": -1,
                    "timeout_hit": False,
                    "blocked_reason": "project_path is not a directory.",
                }
        except Exception as e:
            return {
                "forgeshell_status": "error_fallback",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "timeout_hit": False,
                "blocked_reason": None,
            }
    # Use first allowed argv for this family (MVP: no user-supplied args).
    argv_list = _FAMILIES[family]
    argv = list(argv_list[0]) if argv_list else ["python", "-c", "print('ok')"]
    timeout_sec = max(1.0, min(300.0, float(timeout_seconds)))

    try:
        from NEXUS.logging_engine import log_system_event
        log_system_event(
            project=None,
            subsystem="forgeshell",
            action="execute",
            status="start",
            reason=f"family={family}",
            metadata={"command_family": family, "cwd": str(cwd) if cwd else None},
        )
    except Exception:
        pass

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=cwd,
            shell=False,
        )
        out = {
            "forgeshell_status": "executed",
            "stdout": (result.stdout or "")[: 32 * 1024],
            "stderr": (result.stderr or "")[: 8 * 1024],
            "exit_code": result.returncode,
            "timeout_hit": False,
            "blocked_reason": None,
        }
        try:
            from NEXUS.logging_engine import log_system_event
            log_system_event(
                project=None,
                subsystem="forgeshell",
                action="execute",
                status="ok",
                reason=f"family={family} exit_code={result.returncode}",
                metadata={"command_family": family, "exit_code": result.returncode},
            )
        except Exception:
            pass
        return out
    except subprocess.TimeoutExpired:
        try:
            from NEXUS.logging_engine import log_system_event
            log_system_event(
                project=None,
                subsystem="forgeshell",
                action="execute",
                status="timeout",
                reason=f"family={family}",
                metadata={"command_family": family},
            )
        except Exception:
            pass
        return {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": "Command timed out.",
            "exit_code": -1,
            "timeout_hit": True,
            "blocked_reason": None,
        }
    except Exception as e:
        try:
            from NEXUS.logging_engine import log_system_event
            log_system_event(
                project=None,
                subsystem="forgeshell",
                action="execute",
                status="error",
                reason=str(e),
                metadata={"command_family": family},
            )
        except Exception:
            pass
        return {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": str(e)[: 2048],
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": None,
        }


def execute_forgeshell_command_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return execute_forgeshell_command(**kwargs)
    except Exception as e:
        return {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": str(e)[: 2048],
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": None,
        }
