"""
NEXUS patch proposal registry (Phase 23).

Governed patch proposal storage. Proposals are first-class artifacts;
application is approval-gated and uses existing diff_patch infrastructure.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

PATCH_PROPOSAL_JOURNAL_FILENAME = "patch_proposal_journal.jsonl"

# Allowed source values
PATCH_SOURCES = ("helix_builder", "surgeon", "manual", "architect", "unknown")
# Allowed status values
PATCH_STATUSES = (
    "proposed",
    "approval_required",
    "approved_pending_apply",
    "rejected",
    "blocked",
    "applied",
    "error_fallback",
)
# Allowed change_type values
CHANGE_TYPES = ("diff_patch", "safe_patch", "advisory_only")


def get_patch_proposal_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for patch proposal journal."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_patch_proposal_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped patch proposal journal."""
    state_dir = get_patch_proposal_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PATCH_PROPOSAL_JOURNAL_FILENAME)


def normalize_patch_proposal(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize patch proposal to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    source = str(r.get("source") or "unknown").strip().lower()
    if source not in PATCH_SOURCES:
        source = "unknown"
    status = str(r.get("status") or "proposed").strip().lower()
    if status not in PATCH_STATUSES:
        status = "proposed"
    change_type = str(r.get("change_type") or "diff_patch").strip().lower()
    if change_type not in CHANGE_TYPES:
        change_type = "diff_patch"

    now = datetime.now().isoformat()
    patch_payload = r.get("patch_payload")
    if not isinstance(patch_payload, dict):
        patch_payload = {}

    return {
        "patch_id": str(r.get("patch_id") or uuid.uuid4().hex[:16]),
        "project_name": str(r.get("project_name") or ""),
        "run_id": str(r.get("run_id") or ""),
        "source": source,
        "status": status,
        "summary": str(r.get("summary") or "")[:500],
        "target_files": list(r.get("target_files") or [])[:20],
        "change_type": change_type,
        "risk_level": str(r.get("risk_level") or "medium").strip().lower()[:20],
        "requires_approval": bool(r.get("requires_approval", True)),
        "approval_id_refs": list(r.get("approval_id_refs") or []),
        "product_id_refs": list(r.get("product_id_refs") or []),
        "autonomy_id_refs": list(r.get("autonomy_id_refs") or []),
        "helix_id_refs": list(r.get("helix_id_refs") or []),
        "rationale": str(r.get("rationale") or "")[:1000],
        "patch_payload": patch_payload,
        "created_at": str(r.get("created_at") or now),
        "updated_at": str(r.get("updated_at") or now),
    }


def append_patch_proposal(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized patch proposal to the project's journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_patch_proposal_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_patch_proposal(record)
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_patch_proposal_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_patch_proposal(project_path=project_path, record=record)
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


def read_patch_proposal_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n patch proposal journal lines. Corruption-tolerant."""
    path = get_patch_proposal_journal_path(project_path)
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


def get_patch_proposal_by_id(
    project_path: str | None,
    patch_id: str,
    n: int = 200,
) -> dict[str, Any] | None:
    """Return patch proposal by id, or None if not found."""
    if not patch_id:
        return None
    tail = read_patch_proposal_journal_tail(project_path=project_path, n=n)
    for r in reversed(tail):
        if r.get("patch_id") == patch_id:
            return r
    return None
