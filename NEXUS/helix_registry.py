"""
NEXUS HELIX registry (Phase 21).

Defines HELIX pipeline contracts and append-only journal for traceability.
Governed engineering pipeline; no arbitrary execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

HELIX_JOURNAL_FILENAME = "helix_journal.jsonl"

# Stage names (deterministic ordering)
HELIX_STAGES = ("architect", "builder", "inspector", "critic", "optimizer", "surgeon")


def get_helix_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for HELIX journal; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_helix_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped HELIX journal."""
    state_dir = get_helix_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / HELIX_JOURNAL_FILENAME)


def normalize_helix_stage_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize stage result to contract shape."""
    r = result or {}
    return {
        "stage": str(r.get("stage") or ""),
        "stage_status": str(r.get("stage_status") or "skipped").strip().lower(),
        "output_summary": str(r.get("output_summary") or ""),
        "approaches": list(r.get("approaches") or []),
        "tradeoffs": list(r.get("tradeoffs") or []),
        "implementation_plan": r.get("implementation_plan"),
        "validation_result": r.get("validation_result"),
        "critique": str(r.get("critique") or ""),
        "critique_evaluation": r.get("critique_evaluation") if isinstance(r.get("critique_evaluation"), dict) else {},
        "optimizations": list(r.get("optimizations") or []),
        "optimization_suggestions": r.get("optimization_suggestions") if isinstance(r.get("optimization_suggestions"), dict) else {},
        "repair_recommended": bool(r.get("repair_recommended", False)),
        "repair_reason": str(r.get("repair_reason") or ""),
        "repair_patch_proposal": r.get("repair_patch_proposal") if isinstance(r.get("repair_patch_proposal"), dict) else None,
    }


def normalize_helix_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize HELIX pipeline record to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    return {
        "helix_id": str(r.get("helix_id") or uuid.uuid4().hex[:16]),
        "run_id": str(r.get("run_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "pipeline_status": str(r.get("pipeline_status") or "planned").strip().lower(),
        "requested_outcome": str(r.get("requested_outcome") or ""),
        "stages": list(r.get("stages") or list(HELIX_STAGES)),
        "current_stage": str(r.get("current_stage") or ""),
        "stage_results": list(r.get("stage_results") or []),
        "approval_blocked": bool(r.get("approval_blocked", False)),
        "safety_blocked": bool(r.get("safety_blocked", False)),
        "requires_surgeon": bool(r.get("requires_surgeon", False)),
        "stop_reason": str(r.get("stop_reason") or ""),
        "started_at": str(r.get("started_at") or ""),
        "finished_at": str(r.get("finished_at") or ""),
        "approval_id_refs": list(r.get("approval_id_refs") or []),
        "autonomy_id_refs": list(r.get("autonomy_id_refs") or []),
        "product_id_refs": list(r.get("product_id_refs") or []),
    }


def append_helix_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized HELIX record to the project's append-only journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_helix_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_helix_record(record)
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_helix_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_helix_record(project_path=project_path, record=record)
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


def read_helix_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n HELIX journal lines and parse JSONL."""
    path = get_helix_journal_path(project_path)
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
