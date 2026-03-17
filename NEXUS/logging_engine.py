"""
NEXUS unified operational logging engine.

Append-only JSONL operational logging with a stable schema. Fail-safe: logging
never raises to callers. No external dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_RELATIVE_PATH = Path("logs") / "forge_operations.jsonl"


def _repo_root() -> Path:
    # NEXUS/ is at repo_root/NEXUS
    return Path(__file__).resolve().parent.parent


def _safe_now_iso() -> str:
    try:
        return datetime.now().isoformat()
    except Exception:
        return ""


def _scrub_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """
    Best-effort scrub of likely-secret keys. Keeps the logger deterministic and safe.
    Does not attempt deep inspection of arbitrary objects.
    """
    md = metadata or {}
    if not isinstance(md, dict):
        return {}
    scrubbed: dict[str, Any] = {}
    for k, v in md.items():
        key = str(k).lower()
        if any(s in key for s in ("api_key", "apikey", "authorization", "bearer", "token", "secret", "password", "openai_api_key")):
            scrubbed[k] = "[REDACTED]"
            continue
        # Keep only JSON-serializable primitives where possible
        if isinstance(v, (str, int, float, bool)) or v is None:
            scrubbed[k] = v
        elif isinstance(v, (list, dict)):
            # Avoid deep recursion; store shallow summary
            scrubbed[k] = {"type": type(v).__name__, "size": len(v)}
        else:
            scrubbed[k] = {"type": type(v).__name__}
    return scrubbed


def build_log_record(
    *,
    project: str | None = None,
    subsystem: str = "nexus",
    action: str = "",
    status: str = "ok",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Build a stable log record dict.

    Shape:
    {
      timestamp, project, subsystem, action, status, reason, metadata
    }
    """
    return {
        "timestamp": timestamp or _safe_now_iso(),
        "project": project or "",
        "subsystem": subsystem or "nexus",
        "action": action or "",
        "status": status or "ok",
        "reason": reason or "",
        "metadata": _scrub_metadata(metadata),
    }


def append_log_record(record: dict[str, Any], log_path: str | None = None) -> bool:
    """
    Append record as JSONL. Returns True if appended, False otherwise.
    Never raises.
    """
    try:
        lp = Path(log_path) if log_path else (_repo_root() / DEFAULT_LOG_RELATIVE_PATH)
        lp.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        lp.open("a", encoding="utf-8").write(line + "\n")
        return True
    except Exception:
        return False


def log_system_event(
    *,
    project: str | None = None,
    subsystem: str = "nexus",
    action: str = "",
    status: str = "ok",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    log_path: str | None = None,
) -> bool:
    """
    Convenience: build and append a log record. Returns True if appended.
    Never raises.
    """
    try:
        rec = build_log_record(
            project=project,
            subsystem=subsystem,
            action=action,
            status=status,
            reason=reason,
            metadata=metadata,
        )
        return append_log_record(rec, log_path=log_path)
    except Exception:
        return False

