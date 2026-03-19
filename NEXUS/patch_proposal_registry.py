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
PATCH_PROPOSAL_RESOLUTION_FILENAME = "patch_proposal_resolution.jsonl"

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


def find_proposal_and_project(patch_id: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Search all projects for patch_id. Return (proposal, project_path, project_key) or (None, None, None)."""
    if not patch_id:
        return None, None, None
    try:
        from NEXUS.registry import PROJECTS
        for proj_key in PROJECTS:
            path = PROJECTS.get(proj_key, {}).get("path")
            if path:
                p = get_patch_proposal_by_id(project_path=path, patch_id=patch_id)
                if p:
                    return p, path, proj_key
    except Exception:
        pass
    return None, None, None


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


def get_patch_proposal_resolution_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped patch proposal resolution journal."""
    state_dir = get_patch_proposal_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PATCH_PROPOSAL_RESOLUTION_FILENAME)


def read_patch_proposal_resolution_tail(
    project_path: str | None,
    n: int = 100,
) -> list[dict[str, Any]]:
    """Read last n resolution records. Corruption-tolerant."""
    path = get_patch_proposal_resolution_journal_path(project_path)
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
            if isinstance(parsed, dict) and parsed.get("patch_id"):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def get_latest_resolution_for_patch(
    project_path: str | None,
    patch_id: str,
    n: int = 100,
) -> dict[str, Any] | None:
    """Return latest resolution record for patch_id, or None."""
    if not patch_id:
        return None
    tail = read_patch_proposal_resolution_tail(project_path=project_path, n=n)
    for r in reversed(tail):
        if r.get("patch_id") == patch_id:
            return r
    return None


def get_proposal_effective_status(
    project_path: str | None,
    patch_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """
    Return (effective_status, latest_resolution).
    Effective status = resolution.new_status if resolution exists else proposal.status.
    """
    proposal = get_patch_proposal_by_id(project_path=project_path, patch_id=patch_id)
    base_status = str(proposal.get("status") or "proposed").strip().lower() if proposal else "proposed"
    resolution = get_latest_resolution_for_patch(project_path=project_path, patch_id=patch_id)
    if resolution:
        new_status = str(resolution.get("new_status") or base_status).strip().lower()
        if new_status in PATCH_STATUSES:
            return new_status, resolution
    return base_status, resolution


def append_patch_proposal_resolution(
    project_path: str | None,
    patch_id: str,
    decision: str,
    new_status: str,
    approval_id: str,
    *,
    project_name: str = "",
    reason: str = "",
) -> str | None:
    """
    Append resolution record. Never raises.
    decision: approve | reject
    new_status: approved_pending_apply | rejected
    """
    path = get_patch_proposal_resolution_journal_path(project_path)
    if not path:
        return None
    if decision not in ("approve", "reject", "apply"):
        return None
    if new_status not in PATCH_STATUSES:
        return None
    now = datetime.now().isoformat()
    record = {
        "patch_id": patch_id,
        "decision": decision,
        "new_status": new_status,
        "approval_id": approval_id,
        "project_name": project_name,
        "reason": reason[:500],
        "timestamp": now,
    }
    try:
        safe = _truncate_for_json(record)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def resolve_patch_proposal(
    project_path: str | None,
    patch_id: str,
    decision: str,
    *,
    project_name: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """
    Approve or reject a patch proposal.
    Validates proposal exists and is in proposed/approval_required.
    Appends resolution + approval record.
    Returns result dict; never raises.
    """
    result: dict[str, Any] = {
        "resolved": False,
        "patch_id": patch_id,
        "decision": decision,
        "effective_status": "",
        "approval_id": "",
        "reason": "",
        "error": "",
    }
    if not project_path or not patch_id:
        result["error"] = "project_path and patch_id required."
        return result
    proposal = get_patch_proposal_by_id(project_path=project_path, patch_id=patch_id)
    if not proposal:
        result["error"] = "Patch proposal not found."
        return result
    current_status, _ = get_proposal_effective_status(project_path=project_path, patch_id=patch_id)
    if current_status not in ("proposed", "approval_required"):
        result["error"] = f"Proposal not resolvable; current status={current_status}."
        result["effective_status"] = current_status
        return result
    if decision == "approve":
        new_status = "approved_pending_apply"
    elif decision == "reject":
        new_status = "rejected"
    else:
        result["error"] = f"Invalid decision: {decision}."
        return result
    approval_id = uuid.uuid4().hex[:16]
    written = append_patch_proposal_resolution(
        project_path=project_path,
        patch_id=patch_id,
        decision=decision,
        new_status=new_status,
        approval_id=approval_id,
        project_name=project_name or proposal.get("project_name", ""),
        reason=reason,
    )
    if not written:
        result["error"] = "Failed to write resolution."
        return result
    try:
        from NEXUS.approval_registry import append_approval_record_safe
        approval_record = {
            "approval_id": approval_id,
            "project_name": project_name or proposal.get("project_name", ""),
            "status": "approved" if decision == "approve" else "rejected",
            "approval_type": "patch_proposal_resolution",
            "reason": reason or f"{decision} patch proposal {patch_id}",
            "context": {"patch_id": patch_id, "decision": decision, "new_status": new_status},
            "decision": decision,
            "decision_timestamp": datetime.now().isoformat(),
        }
        append_approval_record_safe(project_path=project_path, record=approval_record)
    except Exception:
        pass
    result["resolved"] = True
    result["effective_status"] = new_status
    result["approval_id"] = approval_id
    result["reason"] = reason or f"Patch proposal {decision}d."
    return result
