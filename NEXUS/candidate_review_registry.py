"""
NEXUS candidate review registry (Phase 37).

Project-scoped review record storage. Append-safe; never breaks workflow.
Behaves like patch_proposal_registry and other governed artifact journals.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.patch_proposal_registry import get_patch_proposal_state_dir

CANDIDATE_REVIEW_JOURNAL_FILENAME = "candidate_review_journal.jsonl"


def get_candidate_review_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped candidate review journal."""
    state_dir = get_patch_proposal_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / CANDIDATE_REVIEW_JOURNAL_FILENAME)


def normalize_review_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize review record to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    now = datetime.now().isoformat()
    review_status = str(r.get("review_status") or "ready_for_review").strip().lower()
    if review_status not in ("not_ready_for_review", "ready_for_review", "reviewed", "changes_requested", "approved_for_approval", "error_fallback"):
        review_status = "ready_for_review"
    review_readiness = str(r.get("review_readiness") or "medium").strip().lower()
    if review_readiness not in ("low", "medium", "high"):
        review_readiness = "medium"
    return {
        "review_id": str(r.get("review_id") or uuid.uuid4().hex[:16]),
        "patch_id": str(r.get("patch_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "review_status": review_status,
        "review_reason": str(r.get("review_reason") or "")[:300],
        "review_readiness": review_readiness,
        "review_requirements_met": list(r.get("review_requirements_met") or [])[:10],
        "review_requirements_missing": list(r.get("review_requirements_missing") or [])[:10],
        "reviewer_notes": str(r.get("reviewer_notes") or "")[:1000],
        "review_outcome": str(r.get("review_outcome") or "")[:300],
        "followup_actions": list(r.get("followup_actions") or [])[:10],
        "human_review_required": bool(r.get("human_review_required", True)),
        "approval_progression_ready": bool(r.get("approval_progression_ready", False)),
        "created_at": str(r.get("created_at") or now),
        "updated_at": str(r.get("updated_at") or now),
    }


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


def append_candidate_review_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized review record to the project's journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_candidate_review_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_review_record(record)
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_candidate_review_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_candidate_review_record(project_path=project_path, record=record)
    except Exception:
        return None


def read_candidate_review_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n review journal lines. Corruption-tolerant."""
    path = get_candidate_review_journal_path(project_path)
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


def get_latest_review_for_patch(
    project_path: str | None,
    patch_id: str,
    n: int = 100,
) -> dict[str, Any] | None:
    """Return latest review record for patch_id, or None."""
    if not patch_id:
        return None
    tail = read_candidate_review_journal_tail(project_path=project_path, n=n)
    for r in reversed(tail):
        if r.get("patch_id") == patch_id:
            return r
    return None
