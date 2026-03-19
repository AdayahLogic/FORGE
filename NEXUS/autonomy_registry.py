"""
NEXUS autonomy registry (Phase 20).

Defines autonomy run contract and append-only journal for traceability.
Bounded multi-step orchestration; no uncontrolled autonomy.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

AUTONOMY_JOURNAL_FILENAME = "autonomy_journal.jsonl"


def get_autonomy_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for autonomy journal; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_autonomy_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped autonomy journal."""
    state_dir = get_autonomy_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / AUTONOMY_JOURNAL_FILENAME)


def normalize_autonomy_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize autonomy run record to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    return {
        "autonomy_id": str(r.get("autonomy_id") or uuid.uuid4().hex[:16]),
        "run_id": str(r.get("run_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "autonomy_status": str(r.get("autonomy_status") or "idle").strip().lower(),
        "autonomy_mode": str(r.get("autonomy_mode") or "bounded_multi_step"),
        "max_steps": int(r.get("max_steps") or 1),
        "steps_attempted": int(r.get("steps_attempted") or 0),
        "steps_completed": int(r.get("steps_completed") or 0),
        "stop_reason": str(r.get("stop_reason") or ""),
        "approval_blocked": bool(r.get("approval_blocked", False)),
        "safety_blocked": bool(r.get("safety_blocked", False)),
        "reached_limit": bool(r.get("reached_limit", False)),
        "step_results": list(r.get("step_results") or []),
        "started_at": str(r.get("started_at") or ""),
        "finished_at": str(r.get("finished_at") or ""),
    }


def append_autonomy_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized autonomy record to the project's append-only journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_autonomy_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_autonomy_record(record)
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_autonomy_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_autonomy_record(project_path=project_path, record=record)
    except Exception:
        return None


def _truncate_for_json(v: Any, max_str_len: int = 2000) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        if isinstance(v, str) and len(v) > max_str_len:
            return v[:max_str_len]
        return v
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, val in list(v.items())[:50]:
            out[str(k)] = _truncate_for_json(val, max_str_len=max_str_len)
        return out
    if isinstance(v, list):
        return [_truncate_for_json(x, max_str_len=max_str_len) for x in v[:50]]
    return str(v)[:max_str_len]


def read_autonomy_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n autonomy journal lines and parse JSONL."""
    path = get_autonomy_journal_path(project_path)
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out
