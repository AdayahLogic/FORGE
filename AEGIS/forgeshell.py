"""
AEGIS ForgeShell: secure shell wrapper for allowlisted command families only.

- Structured command requests only; no unrestricted shell.
- MVP families: shell_test, shell_lint, shell_build, git_status.
- Validates arguments, enforces timeouts, scoped cwd, blocks dangerous patterns.
- Logs execution via NEXUS/AEGIS logging.
"""

from __future__ import annotations

import json
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


_FORGESHELL_SECURITY_LEVEL = "allowlisted_wrapper"
_FORGESHELL_POSTURE_REASON = "ForgeShell is an allowlisted wrapper, not a full sandbox (no adversarial filesystem isolation guarantees)."


def _cache_file() -> Path:
    # Per-project cached status is handled by keying on resolved project_path.
    return Path(__file__).resolve().parent / "forgeshell_cache.json"


def _cache_key(project_path: str | None) -> str:
    if not project_path:
        return "global"
    try:
        return str(Path(project_path).resolve())
    except Exception:
        return str(project_path)


def _safe_read_json(p: Path) -> dict[str, Any]:
    try:
        if not p.exists():
            return {}
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_write_json(p: Path, payload: dict[str, Any]) -> None:
    try:
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Never break execution due to cache writes.
        pass


def _cache_write(project_path: str | None, result: dict[str, Any]) -> None:
    try:
        key = _cache_key(project_path)
        cache = _safe_read_json(_cache_file())
        if not isinstance(cache.get("projects"), dict):
            cache["projects"] = {}
        cache["projects"][key] = {"result": result}
        _safe_write_json(_cache_file(), cache)
    except Exception:
        pass


def _cache_read(project_path: str | None) -> dict[str, Any] | None:
    try:
        key = _cache_key(project_path)
        cache = _safe_read_json(_cache_file())
        projects = cache.get("projects")
        if not isinstance(projects, dict):
            return None
        entry = projects.get(key)
        if not isinstance(entry, dict):
            return None
        res = entry.get("result")
        if not isinstance(res, dict):
            return None
        return res
    except Exception:
        return None


def get_forgeshell_status_cached(*, project_path: str | None = None) -> dict[str, Any]:
    """
    Return cached ForgeShell result if available.
    Does NOT execute ForgeShell.
    """
    cached = _cache_read(project_path)
    if isinstance(cached, dict) and cached:
        out = dict(cached)
        out.setdefault("forgeshell_security_level", _FORGESHELL_SECURITY_LEVEL)
        out.setdefault("summary_reason", "Cached last ForgeShell result.")
        out.setdefault("forgeshell_posture_reason", _FORGESHELL_POSTURE_REASON)
        return out

    if project_path:
        return {
            "forgeshell_status": "not_run_yet",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": None,
            "summary_reason": "ForgeShell has not been executed for this project yet.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }

    return {
        "forgeshell_status": "idle",
        "stdout": "",
        "stderr": "",
        "exit_code": -1,
        "timeout_hit": False,
        "blocked_reason": None,
        "summary_reason": "ForgeShell idle (no project scope provided).",
        "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
        "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
    }


def get_forgeshell_status_cached_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return get_forgeshell_status_cached(**kwargs)
    except Exception:
        return {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": None,
            "summary_reason": "ForgeShell status cache read failed.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }


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

    Result shape (ForgeShell allowlisted wrapper; not a full sandbox):
    {
      "forgeshell_status": "executed" | "blocked" | "error_fallback" | "idle" | "not_run_yet",
      "stdout": "...",
      "stderr": "...",
      "exit_code": 0,
      "timeout_hit": false,
      "blocked_reason": null,
      "summary_reason": "...",
      "forgeshell_security_level": "allowlisted_wrapper",
      "forgeshell_posture_reason": "..."
    }
    """
    req = request or {}
    family = str(command_family or req.get("command_family") or "").strip().lower()
    if not family or family not in _FAMILIES:
        out = {
            "forgeshell_status": "blocked",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": f"Unsupported or missing command_family: {family!r}.",
            "summary_reason": "ForgeShell request blocked (not an allowlisted wrapper family).",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }
        _cache_write(project_path, out)
        return out
    reason = _blocked_reason(req)
    if reason:
        out = {
            "forgeshell_status": "blocked",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": reason,
            "summary_reason": "ForgeShell request blocked by dangerous pattern/policy checks. Not a full sandbox.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }
        _cache_write(project_path, out)
        return out
    cwd: Path | None = None
    if project_path:
        try:
            cwd = Path(project_path).resolve()
            if not cwd.is_dir():
                out = {
                    "forgeshell_status": "error_fallback",
                    "stdout": "",
                    "stderr": str(project_path),
                    "exit_code": -1,
                    "timeout_hit": False,
                    "blocked_reason": "project_path is not a directory.",
                    "summary_reason": "ForgeShell failed due to invalid project_path. Not a full sandbox.",
                    "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
                    "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
                }
                _cache_write(project_path, out)
                return out
        except Exception as e:
            out = {
                "forgeshell_status": "error_fallback",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "timeout_hit": False,
                "blocked_reason": None,
                "summary_reason": "ForgeShell failed to validate project_path. Not a full sandbox.",
                "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
                "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
            }
            _cache_write(project_path, out)
            return out
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
        out["summary_reason"] = "ForgeShell executed via allowlisted wrapper (not a full sandbox)."
        out["forgeshell_security_level"] = _FORGESHELL_SECURITY_LEVEL
        out["forgeshell_posture_reason"] = _FORGESHELL_POSTURE_REASON
        _cache_write(project_path, out)
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
        out = {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": "Command timed out.",
            "exit_code": -1,
            "timeout_hit": True,
            "blocked_reason": None,
            "summary_reason": "ForgeShell execution timed out; allowlisted wrapper did not complete. Not a full sandbox.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }
        _cache_write(project_path, out)
        return out
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
        out = {
            "forgeshell_status": "error_fallback",
            "stdout": "",
            "stderr": str(e)[: 2048],
            "exit_code": -1,
            "timeout_hit": False,
            "blocked_reason": None,
            "summary_reason": "ForgeShell execution failed; allowlisted wrapper not a full sandbox.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }
        _cache_write(project_path, out)
        return out


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
            "summary_reason": "ForgeShell failed unexpectedly; allowlisted wrapper not a full sandbox.",
            "forgeshell_security_level": _FORGESHELL_SECURITY_LEVEL,
            "forgeshell_posture_reason": _FORGESHELL_POSTURE_REASON,
        }
