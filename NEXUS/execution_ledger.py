"""
NEXUS execution ledger.

Append-only JSONL ledger of execution events (agent routing, tool decisions,
file modifications, terminal runs, workflow summaries). Stored per project
under state/execution_ledger.jsonl. No database, no async; best-effort append.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


LEDGER_FILENAME = "execution_ledger.jsonl"


def get_ledger_path(project_path: str | None) -> str | None:
    """Return path to project-scoped execution ledger, or None if no project_path."""
    if not project_path:
        return None
    base = Path(project_path).resolve()
    state_dir = base / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / LEDGER_FILENAME)


def append_entry(
    project_path: str | None,
    event_type: str,
    status: str,
    summary: str,
    *,
    project_name: str | None = None,
    agent_name: str | None = None,
    tool_name: str | None = None,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> str | None:
    """
    Append one JSONL record to the project's execution ledger.

    Fields: timestamp (ISO), event_type, project_name, agent_name, tool_name,
    status, summary, payload (optional), run_id (optional). Returns ledger path
    if written, None if skipped or failed.
    """
    path = get_ledger_path(project_path)
    if not path:
        return None

    record: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "project_name": project_name,
        "agent_name": agent_name,
        "tool_name": tool_name,
        "status": status,
        "summary": summary,
    }
    if run_id:
        record["run_id"] = run_id
    if payload is not None:
        # Keep payload small: truncate long values, omit huge structures
        safe_payload: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                safe_payload[k] = v
            elif isinstance(v, dict):
                safe_payload[k] = {str(a): str(b)[:200] for a, b in list(v.items())[:20]}
            elif isinstance(v, list):
                safe_payload[k] = [str(x)[:200] for x in v[:20]]
            else:
                safe_payload[k] = str(v)[:200]
        record["payload"] = safe_payload

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def read_ledger_tail(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """
    Read the last n lines from the project execution ledger and parse as JSONL.
    Returns a list of record dicts (newest last). Missing or unreadable file returns [].
    """
    if not project_path:
        return []
    path = get_ledger_path(project_path)
    if not path or not Path(path).exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    records: list[dict[str, Any]] = []
    for line in lines[-n:] if len(lines) > n else lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
