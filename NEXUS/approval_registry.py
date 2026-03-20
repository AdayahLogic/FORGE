"""
NEXUS approval registry (Phase 18).

Defines the approval record contract and append-only storage.
Approval sits between AEGIS policy allow and execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

APPROVAL_JOURNAL_FILENAME = "approval_journal.jsonl"


def get_approval_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for approval journal; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_approval_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped approval journal."""
    state_dir = get_approval_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / APPROVAL_JOURNAL_FILENAME)


def normalize_approval_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize approval record to contract shape.
    Ensures required fields exist with safe defaults.
    Phase 28: capture patch_id_refs from context when available (forward-link).
    """
    r = record or {}
    context = dict(r.get("context") or {})
    patch_id_refs: list[str] = list(r.get("patch_id_refs") or [])
    pid = context.get("patch_id")
    if pid and isinstance(pid, str) and pid.strip() and pid not in patch_id_refs:
        patch_id_refs = [pid] + [x for x in patch_id_refs if x != pid][:19]
    return {
        "approval_id": str(r.get("approval_id") or uuid.uuid4().hex[:16]),
        "run_id": str(r.get("run_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "timestamp": str(r.get("timestamp") or datetime.now().isoformat()),
        "status": str(r.get("status") or "pending").strip().lower(),
        "approval_type": str(r.get("approval_type") or "unknown"),
        "reason": str(r.get("reason") or ""),
        "requested_by": str(r.get("requested_by") or ""),
        "requires_human": bool(r.get("requires_human", True)),
        "risk_level": str(r.get("risk_level") or "unknown"),
        "sensitivity": str(r.get("sensitivity") or "unknown"),
        "context": context,
        "decision": r.get("decision"),
        "decision_timestamp": r.get("decision_timestamp"),
        "patch_id_refs": patch_id_refs[:20],
    }


def append_approval_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized approval record to the project's append-only journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_approval_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_approval_record(record)
        if normalized.get("status") not in ("pending", "approved", "rejected", "expired"):
            normalized["status"] = "pending"
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_approval_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_approval_record(project_path=project_path, record=record)
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


def read_approval_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n approval journal lines and parse JSONL."""
    path = get_approval_journal_path(project_path)
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


def count_pending_approvals(project_path: str | None, n: int = 200) -> int:
    """Count pending approvals in last n journal entries."""
    records = read_approval_journal_tail(project_path=project_path, n=n)
    return sum(1 for r in records if str(r.get("status") or "").strip().lower() == "pending")


def get_pending_approvals(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Return pending approvals from last n journal entries."""
    records = read_approval_journal_tail(project_path=project_path, n=n)
    return [r for r in records if str(r.get("status") or "").strip().lower() == "pending"]
