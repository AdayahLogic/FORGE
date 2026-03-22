"""
NEXUS review-only execution package registry.

Stores sealed execution envelopes for review without performing execution.
Packages are append-only in the journal and persisted as individual JSON files
under the project state directory.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXECUTION_PACKAGE_JOURNAL_FILENAME = "execution_package_journal.jsonl"
EXECUTION_PACKAGE_DIRNAME = "execution_packages"
MAX_EXECUTION_PACKAGE_LIST_LIMIT = 50


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_execution_package_journal_record(normalized: dict[str, Any], package_path: str | None) -> dict[str, Any]:
    return {
        "package_id": normalized.get("package_id"),
        "project_name": normalized.get("project_name"),
        "run_id": normalized.get("run_id"),
        "created_at": normalized.get("created_at"),
        "package_status": normalized.get("package_status"),
        "review_status": normalized.get("review_status"),
        "runtime_target_id": normalized.get("runtime_target_id"),
        "requires_human_approval": normalized.get("requires_human_approval"),
        "approval_id_refs": normalized.get("approval_id_refs"),
        "sealed": normalized.get("sealed"),
        "reason": normalized.get("reason"),
        "package_file": package_path,
        "decision_status": normalized.get("decision_status"),
        "decision_timestamp": normalized.get("decision_timestamp"),
        "decision_actor": normalized.get("decision_actor"),
        "decision_id": normalized.get("decision_id"),
    }


def get_execution_package_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for execution packages; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_execution_package_dir(project_path: str | None) -> Path | None:
    """Return per-project execution package directory."""
    state_dir = get_execution_package_state_dir(project_path)
    if not state_dir:
        return None
    try:
        package_dir = state_dir / EXECUTION_PACKAGE_DIRNAME
        package_dir.mkdir(parents=True, exist_ok=True)
        return package_dir
    except Exception:
        return None


def get_execution_package_journal_path(project_path: str | None) -> str | None:
    """Return append-only execution package journal path."""
    state_dir = get_execution_package_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / EXECUTION_PACKAGE_JOURNAL_FILENAME)


def get_execution_package_file_path(project_path: str | None, package_id: str | None) -> str | None:
    """Return full JSON package path for package_id."""
    package_dir = get_execution_package_dir(project_path)
    if not package_dir or not package_id:
        return None
    return str(package_dir / f"{str(package_id).strip()}.json")


def normalize_execution_package(package: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize execution package to stable review-only contract shape.
    """
    p = package or {}
    package_id = str(p.get("package_id") or uuid.uuid4().hex[:16])
    approval_id_refs = [str(x) for x in (p.get("approval_id_refs") or []) if str(x).strip()][:20]
    runtime_artifacts = p.get("runtime_artifacts") or []
    if not isinstance(runtime_artifacts, list):
        runtime_artifacts = []
    review_checklist = p.get("review_checklist") or []
    if not isinstance(review_checklist, list):
        review_checklist = []

    return {
        "package_id": package_id,
        "package_version": str(p.get("package_version") or "1.0"),
        "package_kind": str(p.get("package_kind") or "review_only_execution_envelope"),
        "project_name": str(p.get("project_name") or ""),
        "project_path": str(p.get("project_path") or ""),
        "run_id": str(p.get("run_id") or ""),
        "created_at": str(p.get("created_at") or datetime.now().isoformat()),
        "package_status": str(p.get("package_status") or "review_pending").strip().lower(),
        "review_status": str(p.get("review_status") or "pending").strip().lower(),
        "sealed": bool(p.get("sealed", True)),
        "seal_reason": str(p.get("seal_reason") or "Review-only package; execution disabled in this phase."),
        "runtime_target_id": str(p.get("runtime_target_id") or "local"),
        "runtime_target_name": str(p.get("runtime_target_name") or p.get("runtime_target_id") or "local"),
        "execution_mode": str(p.get("execution_mode") or "manual_only"),
        "requested_action": str(p.get("requested_action") or "adapter_dispatch_call"),
        "requested_by": str(p.get("requested_by") or "workflow"),
        "requires_human_approval": bool(p.get("requires_human_approval", True)),
        "approval_id_refs": approval_id_refs,
        "aegis_decision": str(p.get("aegis_decision") or ""),
        "aegis_scope": str(p.get("aegis_scope") or ""),
        "reason": str(p.get("reason") or ""),
        "dispatch_plan_summary": dict(p.get("dispatch_plan_summary") or {}),
        "routing_summary": dict(p.get("routing_summary") or {}),
        "execution_summary": dict(p.get("execution_summary") or {}),
        "command_request": dict(p.get("command_request") or {}),
        "candidate_paths": [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50],
        "expected_outputs": [str(x) for x in (p.get("expected_outputs") or []) if str(x).strip()][:50],
        "review_checklist": [str(x) for x in review_checklist[:20]],
        "rollback_notes": [str(x) for x in (p.get("rollback_notes") or []) if str(x).strip()][:20],
        "runtime_artifacts": [x for x in runtime_artifacts[:20] if isinstance(x, dict)],
        "metadata": dict(p.get("metadata") or {}),
        "decision_status": str(p.get("decision_status") or "pending").strip().lower(),
        "decision_timestamp": str(p.get("decision_timestamp") or ""),
        "decision_actor": str(p.get("decision_actor") or ""),
        "decision_notes": str(p.get("decision_notes") or ""),
        "decision_id": str(p.get("decision_id") or ""),
    }


def normalize_execution_package_journal_record(record: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize journal record to stable summary-only contract shape."""
    r = record or {}
    return {
        "package_id": str(r.get("package_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "run_id": str(r.get("run_id") or ""),
        "created_at": str(r.get("created_at") or ""),
        "package_status": str(r.get("package_status") or "review_pending").strip().lower(),
        "review_status": str(r.get("review_status") or "pending").strip().lower(),
        "runtime_target_id": str(r.get("runtime_target_id") or "local"),
        "requires_human_approval": bool(r.get("requires_human_approval", True)),
        "approval_id_refs": [str(x) for x in (r.get("approval_id_refs") or []) if str(x).strip()][:20],
        "sealed": bool(r.get("sealed", True)),
        "reason": str(r.get("reason") or ""),
        "package_file": str(r.get("package_file") or ""),
        "decision_status": str(r.get("decision_status") or "pending").strip().lower(),
        "decision_timestamp": str(r.get("decision_timestamp") or ""),
        "decision_actor": str(r.get("decision_actor") or ""),
        "decision_id": str(r.get("decision_id") or ""),
    }


def _is_review_pending_package(record: dict[str, Any] | None) -> bool:
    r = normalize_execution_package_journal_record(record)
    review_status = r.get("review_status") or ""
    package_status = r.get("package_status") or ""
    return review_status in ("pending", "review_pending") or package_status in ("pending", "review_pending")


def write_execution_package(project_path: str | None, package: dict[str, Any]) -> str | None:
    """
    Write a normalized package JSON file and append a journal entry.
    Returns package file path, or None on failure.
    """
    package_path = None
    journal_path = get_execution_package_journal_path(project_path)
    try:
        normalized = normalize_execution_package(package)
        package_path = get_execution_package_file_path(project_path, normalized.get("package_id"))
        if not package_path or not journal_path:
            return None

        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return package_path
    except Exception:
        return None


def write_execution_package_safe(project_path: str | None, package: dict[str, Any]) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return write_execution_package(project_path=project_path, package=package)
    except Exception:
        return None


def read_execution_package(project_path: str | None, package_id: str | None) -> dict[str, Any] | None:
    """Read a single persisted execution package by id."""
    path = get_execution_package_file_path(project_path, package_id)
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_execution_package(data)
    except Exception:
        return None
    return None


def read_execution_package_journal_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    """Read last n journal lines and parse JSONL."""
    path = get_execution_package_journal_path(project_path)
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
                out.append(normalize_execution_package_journal_record(parsed))
        except json.JSONDecodeError:
            continue
    return out


def list_execution_package_journal_entries(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """List recent execution package journal entries sorted by created_at DESC."""
    limit = max(1, min(int(n or 20), MAX_EXECUTION_PACKAGE_LIST_LIMIT))
    rows = read_execution_package_journal_tail(project_path=project_path, n=MAX_EXECUTION_PACKAGE_LIST_LIMIT)
    rows = [normalize_execution_package_journal_record(r) for r in rows if isinstance(r, dict)]
    latest_by_package: dict[str, dict[str, Any]] = {}
    for row in reversed(rows):
        package_id = str(row.get("package_id") or "").strip()
        if not package_id or package_id in latest_by_package:
            continue
        latest_by_package[package_id] = row
    deduped = list(latest_by_package.values())
    deduped.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return deduped[:limit]


def list_reviewable_execution_packages(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """List recent pending/reviewable execution package summaries sorted by created_at DESC."""
    limit = max(1, min(int(n or 20), MAX_EXECUTION_PACKAGE_LIST_LIMIT))
    rows = read_execution_package_journal_tail(project_path=project_path, n=MAX_EXECUTION_PACKAGE_LIST_LIMIT)
    reviewable = [normalize_execution_package_journal_record(r) for r in rows if _is_review_pending_package(r)]
    reviewable.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return reviewable[:limit]


def record_execution_package_decision(
    *,
    project_path: str | None,
    package_id: str | None,
    decision_status: str,
    decision_actor: str,
    decision_notes: str = "",
) -> dict[str, Any]:
    """Persist an immutable human decision onto a sealed package and append a summary journal record."""
    normalized_status = str(decision_status or "").strip().lower()
    if normalized_status not in ("approved", "rejected"):
        return {"status": "error", "reason": "decision_status must be approved or rejected.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    if not bool(package.get("sealed")):
        return {"status": "error", "reason": "Only sealed execution packages may be decided.", "package": package}
    if str(package.get("decision_status") or "pending").strip().lower() != "pending":
        return {"status": "error", "reason": "Execution package decision is immutable once set.", "package": package}
    package["decision_status"] = normalized_status
    package["decision_timestamp"] = _utc_now_iso()
    package["decision_actor"] = str(decision_actor or "").strip()
    package["decision_notes"] = str(decision_notes or "")
    package["decision_id"] = str(uuid.uuid4())
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id)
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution package decision recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package decision.", "package": None}


def record_execution_package_decision_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_decision(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package decision.", "package": None}
