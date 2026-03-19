from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.learning_engine import build_learning_summary_from_records
from NEXUS.learning_models import normalize_learning_record


LEARNING_JOURNAL_FILENAME = "learning_journal.jsonl"
LEARNING_SUMMARY_FILENAME = "learning_summary.json"


def get_learning_state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_learning_journal_path(project_path: str | None) -> str | None:
    state_dir = get_learning_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / LEARNING_JOURNAL_FILENAME)


def get_learning_summary_path(project_path: str | None) -> str | None:
    state_dir = get_learning_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / LEARNING_SUMMARY_FILENAME)


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


def append_learning_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized learning record to the project's append-only journal.
    Returns written path, or None if skipped/failed.
    """
    path = get_learning_journal_path(project_path)
    if not path:
        return None

    try:
        normalized = normalize_learning_record(record)
        # Enforce timestamp: stable and always present.
        if not normalized.get("timestamp"):
            normalized["timestamp"] = datetime.now().isoformat()

        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_learning_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_learning_record(project_path=project_path, record=record)
    except Exception:
        return None


def read_learning_journal_tail(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """Read last n learning journal lines and parse JSONL."""
    path = get_learning_journal_path(project_path)
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


def write_learning_summary(
    project_path: str | None,
    *,
    last_n: int = 50,
) -> str | None:
    """
    Compute deterministic summary from the tail of the append-only journal.

    Honesty note:
    In the current workflow integration, this summary write is best-effort and
    typically occurs at/near the final save stage. Early failures may leave
    journal entries without a freshly updated `learning_summary.json`.
    """
    summary_path = get_learning_summary_path(project_path)
    if not summary_path:
        return None

    try:
        records = read_learning_journal_tail(project_path=project_path, n=last_n)
        summary = build_learning_summary_from_records(records, last_n=min(last_n, len(records)))
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return summary_path
    except Exception:
        return None


def write_learning_summary_safe(
    project_path: str | None,
    *,
    last_n: int = 50,
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return write_learning_summary(project_path=project_path, last_n=last_n)
    except Exception:
        return None

