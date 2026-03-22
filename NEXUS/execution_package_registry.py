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
        "eligibility_status": normalized.get("eligibility_status"),
        "eligibility_timestamp": normalized.get("eligibility_timestamp"),
        "eligibility_reason": normalized.get("eligibility_reason"),
        "eligibility_checked_by": normalized.get("eligibility_checked_by"),
        "eligibility_check_id": normalized.get("eligibility_check_id"),
        "release_status": normalized.get("release_status"),
        "release_timestamp": normalized.get("release_timestamp"),
        "release_actor": normalized.get("release_actor"),
        "release_id": normalized.get("release_id"),
        "release_reason": normalized.get("release_reason"),
        "release_version": normalized.get("release_version"),
        "handoff_status": normalized.get("handoff_status"),
        "handoff_timestamp": normalized.get("handoff_timestamp"),
        "handoff_actor": normalized.get("handoff_actor"),
        "handoff_id": normalized.get("handoff_id"),
        "handoff_reason": normalized.get("handoff_reason"),
        "handoff_version": normalized.get("handoff_version"),
        "handoff_executor_target_id": normalized.get("handoff_executor_target_id"),
        "handoff_executor_target_name": normalized.get("handoff_executor_target_name"),
        "execution_status": normalized.get("execution_status"),
        "execution_timestamp": normalized.get("execution_timestamp"),
        "execution_actor": normalized.get("execution_actor"),
        "execution_id": normalized.get("execution_id"),
        "execution_reason": normalized.get("execution_reason"),
        "execution_version": normalized.get("execution_version"),
        "execution_executor_target_id": normalized.get("execution_executor_target_id"),
        "execution_executor_target_name": normalized.get("execution_executor_target_name"),
        "rollback_status": normalized.get("rollback_status"),
        "rollback_timestamp": normalized.get("rollback_timestamp"),
        "rollback_reason": normalized.get("rollback_reason"),
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


def _normalize_eligibility_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_release_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_handoff_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_handoff_aegis_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        from AEGIS.aegis_contract import normalize_aegis_result

        return normalize_aegis_result(value)
    except Exception:
        return {}


def _normalize_execution_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_rollback_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


VALID_EXECUTION_FAILURE_CLASSES = (
    "preflight_block",
    "aegis_block",
    "runtime_start_failure",
    "runtime_execution_failure",
    "rollback_failure",
)


def _normalize_failure_class(value: Any) -> str:
    s = str(value or "").strip().lower()
    return s if s in VALID_EXECUTION_FAILURE_CLASSES else ""


def _normalize_execution_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    exit_code = value.get("exit_code")
    if not isinstance(exit_code, int):
        try:
            exit_code = int(exit_code) if exit_code not in (None, "") else None
        except Exception:
            exit_code = None
    return {
        "result_status": str(value.get("result_status") or ""),
        "exit_code": exit_code,
        "log_ref": str(value.get("log_ref") or ""),
        "files_touched_count": max(0, int(value.get("files_touched_count") or 0)),
        "artifacts_written_count": max(0, int(value.get("artifacts_written_count") or 0)),
        "failure_class": _normalize_failure_class(value.get("failure_class")),
        "stdout_summary": str(value.get("stdout_summary") or ""),
        "stderr_summary": str(value.get("stderr_summary") or ""),
        "rollback_summary": dict(value.get("rollback_summary") or {}),
    }


def _empty_execution_receipt(*, result_status: str = "", failure_class: str = "", log_ref: str = "", exit_code: int | None = None) -> dict[str, Any]:
    return _normalize_execution_receipt(
        {
            "result_status": result_status,
            "exit_code": exit_code,
            "log_ref": log_ref,
            "files_touched_count": 0,
            "artifacts_written_count": 0,
            "failure_class": failure_class,
        }
    )


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
        "eligibility_status": str(p.get("eligibility_status") or "pending").strip().lower(),
        "eligibility_timestamp": str(p.get("eligibility_timestamp") or ""),
        "eligibility_reason": _normalize_eligibility_reason(p.get("eligibility_reason")),
        "eligibility_checked_by": str(p.get("eligibility_checked_by") or ""),
        "eligibility_check_id": str(p.get("eligibility_check_id") or ""),
        "release_status": str(p.get("release_status") or "pending").strip().lower(),
        "release_timestamp": str(p.get("release_timestamp") or ""),
        "release_actor": str(p.get("release_actor") or ""),
        "release_notes": str(p.get("release_notes") or ""),
        "release_id": str(p.get("release_id") or ""),
        "release_reason": _normalize_release_reason(p.get("release_reason")),
        "release_version": str(p.get("release_version") or "v1"),
        "handoff_status": str(p.get("handoff_status") or "pending").strip().lower(),
        "handoff_timestamp": str(p.get("handoff_timestamp") or ""),
        "handoff_actor": str(p.get("handoff_actor") or ""),
        "handoff_notes": str(p.get("handoff_notes") or ""),
        "handoff_id": str(p.get("handoff_id") or ""),
        "handoff_reason": _normalize_handoff_reason(p.get("handoff_reason")),
        "handoff_version": str(p.get("handoff_version") or "v1"),
        "handoff_executor_target_id": str(p.get("handoff_executor_target_id") or ""),
        "handoff_executor_target_name": str(p.get("handoff_executor_target_name") or ""),
        "handoff_aegis_result": _normalize_handoff_aegis_result(p.get("handoff_aegis_result")),
        "execution_status": str(p.get("execution_status") or "pending").strip().lower(),
        "execution_timestamp": str(p.get("execution_timestamp") or ""),
        "execution_actor": str(p.get("execution_actor") or ""),
        "execution_id": str(p.get("execution_id") or ""),
        "execution_reason": _normalize_execution_reason(p.get("execution_reason")),
        "execution_receipt": _normalize_execution_receipt(p.get("execution_receipt")),
        "execution_version": str(p.get("execution_version") or "v1"),
        "execution_executor_target_id": str(p.get("execution_executor_target_id") or ""),
        "execution_executor_target_name": str(p.get("execution_executor_target_name") or ""),
        "execution_aegis_result": _normalize_handoff_aegis_result(p.get("execution_aegis_result")),
        "execution_started_at": str(p.get("execution_started_at") or ""),
        "execution_finished_at": str(p.get("execution_finished_at") or ""),
        "rollback_status": str(p.get("rollback_status") or "not_needed").strip().lower(),
        "rollback_timestamp": str(p.get("rollback_timestamp") or ""),
        "rollback_reason": _normalize_rollback_reason(p.get("rollback_reason")),
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
        "eligibility_status": str(r.get("eligibility_status") or "pending").strip().lower(),
        "eligibility_timestamp": str(r.get("eligibility_timestamp") or ""),
        "eligibility_reason": _normalize_eligibility_reason(r.get("eligibility_reason")),
        "eligibility_checked_by": str(r.get("eligibility_checked_by") or ""),
        "eligibility_check_id": str(r.get("eligibility_check_id") or ""),
        "release_status": str(r.get("release_status") or "pending").strip().lower(),
        "release_timestamp": str(r.get("release_timestamp") or ""),
        "release_actor": str(r.get("release_actor") or ""),
        "release_id": str(r.get("release_id") or ""),
        "release_reason": _normalize_release_reason(r.get("release_reason")),
        "release_version": str(r.get("release_version") or "v1"),
        "handoff_status": str(r.get("handoff_status") or "pending").strip().lower(),
        "handoff_timestamp": str(r.get("handoff_timestamp") or ""),
        "handoff_actor": str(r.get("handoff_actor") or ""),
        "handoff_id": str(r.get("handoff_id") or ""),
        "handoff_reason": _normalize_handoff_reason(r.get("handoff_reason")),
        "handoff_version": str(r.get("handoff_version") or "v1"),
        "handoff_executor_target_id": str(r.get("handoff_executor_target_id") or ""),
        "handoff_executor_target_name": str(r.get("handoff_executor_target_name") or ""),
        "execution_status": str(r.get("execution_status") or "pending").strip().lower(),
        "execution_timestamp": str(r.get("execution_timestamp") or ""),
        "execution_actor": str(r.get("execution_actor") or ""),
        "execution_id": str(r.get("execution_id") or ""),
        "execution_reason": _normalize_execution_reason(r.get("execution_reason")),
        "execution_version": str(r.get("execution_version") or "v1"),
        "execution_executor_target_id": str(r.get("execution_executor_target_id") or ""),
        "execution_executor_target_name": str(r.get("execution_executor_target_name") or ""),
        "execution_receipt": _normalize_execution_receipt(r.get("execution_receipt")),
        "rollback_status": str(r.get("rollback_status") or "not_needed").strip().lower(),
        "rollback_timestamp": str(r.get("rollback_timestamp") or ""),
        "rollback_reason": _normalize_rollback_reason(r.get("rollback_reason")),
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


def evaluate_execution_package_eligibility(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a package is eligible for future execution without executing anything."""
    p = normalize_execution_package(package)
    if str(p.get("decision_status") or "").strip().lower() == "pending":
        return {
            "eligibility_status": "pending",
            "eligibility_reason": {
                "code": "decision_pending",
                "message": "Eligibility check requires a non-pending decision.",
            },
        }
    if not bool(p.get("sealed")):
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "not_sealed",
                "message": "Package must remain sealed to be eligible.",
            },
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "decision_not_approved",
                "message": "Package decision must be approved.",
            },
        }
    if not (p.get("approval_id_refs") or []):
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "approval_refs_missing",
                "message": "Approval references are required.",
            },
        }
    runtime_target_id = str(p.get("runtime_target_id") or "").strip().lower()
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(runtime_target_id) or {}
    except Exception:
        runtime_target = {}
    if not runtime_target or str(runtime_target.get("active_or_planned") or "").strip().lower() != "active":
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "runtime_target_invalid",
                "message": "Runtime target must be known and active.",
            },
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "execution_detected",
                "message": "Package indicates execution has already occurred.",
            },
        }
    return {
        "eligibility_status": "eligible",
        "eligibility_reason": {
            "code": "eligible",
            "message": "Package is eligible for future execution review.",
        },
    }


def evaluate_execution_package_release(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a package can be released for future execution without executing it."""
    p = normalize_execution_package(package)
    if not bool(p.get("sealed")):
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "not_sealed",
                "message": "Package must remain sealed to be released.",
            },
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "decision_not_approved",
                "message": "Package decision must be approved.",
            },
        }
    if str(p.get("eligibility_status") or "").strip().lower() != "eligible":
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "eligibility_not_eligible",
                "message": "Package eligibility must be eligible before release.",
            },
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "execution_detected",
                "message": "Package indicates execution has already occurred.",
            },
        }
    return {
        "release_status": "released",
        "release_reason": {
            "code": "released",
            "message": "Package is released for future execution handling.",
        },
    }


def evaluate_execution_package_handoff(
    package: dict[str, Any] | None,
    *,
    executor_target_id: str | None,
) -> dict[str, Any]:
    """Evaluate whether a released package can be handed to a future executor without executing it."""
    p = normalize_execution_package(package)
    target_id = str(executor_target_id or "").strip().lower()
    empty = {
        "handoff_executor_target_id": target_id,
        "handoff_executor_target_name": "",
        "handoff_aegis_result": {},
    }

    if not bool(p.get("sealed")):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "not_sealed", "message": "Package must remain sealed to be handed off."},
            **empty,
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "decision_not_approved", "message": "Package decision must be approved before handoff."},
            **empty,
        }
    eligibility_status = str(p.get("eligibility_status") or "").strip().lower()
    if eligibility_status == "pending":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "eligibility_pending", "message": "Package eligibility must not be pending before handoff."},
            **empty,
        }
    if eligibility_status != "eligible":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "eligibility_not_eligible", "message": "Package eligibility must be eligible before handoff."},
            **empty,
        }
    if str(p.get("release_status") or "").strip().lower() != "released":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "release_not_released", "message": "Package release status must be released before handoff."},
            **empty,
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "execution_detected", "message": "Package indicates execution has already occurred."},
            **empty,
        }

    runtime_target = {}
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(target_id) or {}
    except Exception:
        runtime_target = {}
    capabilities = [str(x).strip().lower() for x in (runtime_target.get("capabilities") or []) if str(x).strip()]
    target_name = str(runtime_target.get("display_name") or runtime_target.get("canonical_name") or "")
    if (
        not runtime_target
        or str(runtime_target.get("active_or_planned") or "").strip().lower() not in ("active", "planned")
        or "execute" not in capabilities
        or target_id == "windows_review_package"
    ):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {
                "code": "executor_target_invalid",
                "message": "Executor target must exist, be active or planned, support execute, and not be windows_review_package.",
            },
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name,
            "handoff_aegis_result": {},
        }

    try:
        from AEGIS.aegis_contract import normalize_aegis_result
        from AEGIS.aegis_core import evaluate_action_safe

        candidate_paths = [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50]
        routing = p.get("routing_summary") or {}
        tool_name = str(routing.get("tool_name") or "").strip().lower()
        aegis_request = {
            "project_name": p.get("project_name"),
            "project_path": p.get("project_path"),
            "runtime_target_id": target_id,
            "action": p.get("requested_action") or "adapter_dispatch_call",
            "action_mode": "execution",
            "requires_human_approval": bool(p.get("requires_human_approval")),
            "candidate_paths": candidate_paths,
            "requested_reads": candidate_paths,
        }
        if tool_name:
            aegis_request["tool_family"] = "file_write" if ("write" in tool_name or "patch" in tool_name) else "file_read"
        aegis_result = normalize_aegis_result(evaluate_action_safe(request=aegis_request))
    except Exception:
        aegis_result = _normalize_handoff_aegis_result(None)

    aegis_decision = str(aegis_result.get("aegis_decision") or "").strip().lower()
    workspace_valid = aegis_result.get("workspace_valid")
    file_guard_status = str(aegis_result.get("file_guard_status") or "").strip().lower()
    if aegis_decision in ("deny", "error_fallback"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "aegis_blocked", "message": "AEGIS denied or failed handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if workspace_valid is False:
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "workspace_invalid", "message": "AEGIS workspace validation failed during handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if file_guard_status in ("deny", "error_fallback"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "file_guard_blocked", "message": "AEGIS file guard blocked handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if aegis_decision not in ("allow", "approval_required"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "aegis_blocked", "message": "AEGIS did not return an allowed handoff decision."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    return {
        "handoff_status": "authorized",
        "handoff_reason": {"code": "authorized", "message": "Package is authorized for future executor handoff."},
        "handoff_executor_target_id": target_id,
        "handoff_executor_target_name": target_name or target_id,
        "handoff_aegis_result": aegis_result,
    }


def evaluate_execution_package_execution(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a handed-off package may execute through the controlled runtime boundary."""
    p = normalize_execution_package(package)
    target_id = str(p.get("handoff_executor_target_id") or p.get("runtime_target_id") or "").strip().lower()
    target_name = str(p.get("handoff_executor_target_name") or p.get("runtime_target_name") or target_id)

    def _blocked(code: str, message: str, *, failure_class: str = "preflight_block", aegis_result: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "execution_status": "blocked",
            "execution_reason": {"code": code, "message": message},
            "execution_executor_target_id": target_id,
            "execution_executor_target_name": target_name,
            "execution_aegis_result": aegis_result or {},
            "execution_receipt": _empty_execution_receipt(result_status="blocked", failure_class=failure_class),
            "rollback_status": "not_needed",
            "rollback_reason": {"code": "", "message": ""},
        }

    if not bool(p.get("sealed")):
        return _blocked("not_sealed", "Package must remain sealed to execute.")
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return _blocked("decision_not_approved", "Package decision must be approved before execution.")
    if str(p.get("eligibility_status") or "").strip().lower() != "eligible":
        return _blocked("eligibility_not_eligible", "Package eligibility must be eligible before execution.")
    if str(p.get("release_status") or "").strip().lower() != "released":
        return _blocked("release_not_released", "Package release status must be released before execution.")
    if str(p.get("handoff_status") or "").strip().lower() != "authorized":
        return _blocked("handoff_not_authorized", "Package handoff must be authorized before execution.")
    if str(p.get("execution_status") or "").strip().lower() == "succeeded":
        return _blocked("already_succeeded", "Package execution_status must not already be succeeded.")

    runtime_target = {}
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(target_id) or {}
    except Exception:
        runtime_target = {}
    capabilities = [str(x).strip().lower() for x in (runtime_target.get("capabilities") or []) if str(x).strip()]
    target_name = str(runtime_target.get("display_name") or runtime_target.get("canonical_name") or target_name)
    if (
        not runtime_target
        or str(runtime_target.get("active_or_planned") or "").strip().lower() != "active"
        or "execute" not in capabilities
        or target_id == "windows_review_package"
    ):
        return _blocked(
            "executor_target_invalid",
            "Executor target must be active, support execute, and not be windows_review_package.",
        )

    try:
        from AEGIS.aegis_contract import normalize_aegis_result
        from AEGIS.aegis_core import evaluate_action_safe

        candidate_paths = [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50]
        routing = p.get("routing_summary") or {}
        tool_name = str(routing.get("tool_name") or "").strip().lower()
        aegis_request = {
            "project_name": p.get("project_name"),
            "project_path": p.get("project_path"),
            "runtime_target_id": target_id,
            "action": p.get("requested_action") or "adapter_dispatch_call",
            "action_mode": "execution",
            "requires_human_approval": bool(p.get("requires_human_approval")),
            "candidate_paths": candidate_paths,
            "requested_reads": candidate_paths,
        }
        if tool_name:
            aegis_request["tool_family"] = "file_write" if ("write" in tool_name or "patch" in tool_name) else "file_read"
        aegis_result = normalize_aegis_result(evaluate_action_safe(request=aegis_request))
    except Exception:
        aegis_result = _normalize_handoff_aegis_result(None)

    aegis_decision = str(aegis_result.get("aegis_decision") or "").strip().lower()
    workspace_valid = aegis_result.get("workspace_valid")
    file_guard_status = str(aegis_result.get("file_guard_status") or "").strip().lower()
    if aegis_decision in ("deny", "error_fallback"):
        return _blocked("aegis_blocked", "AEGIS denied or failed execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if workspace_valid is False:
        return _blocked("workspace_invalid", "AEGIS workspace validation failed during execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if file_guard_status in ("deny", "error_fallback"):
        return _blocked("file_guard_blocked", "AEGIS file guard blocked execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if aegis_decision not in ("allow", "approval_required"):
        return _blocked("aegis_blocked", "AEGIS did not return an allowed execution decision.", failure_class="aegis_block", aegis_result=aegis_result)

    return {
        "execution_status": "ready",
        "execution_reason": {"code": "ready", "message": "Package is ready for controlled runtime execution."},
        "execution_executor_target_id": target_id,
        "execution_executor_target_name": target_name or target_id,
        "execution_aegis_result": aegis_result,
        "execution_receipt": _empty_execution_receipt(result_status="ready"),
        "rollback_status": "not_needed",
        "rollback_reason": {"code": "", "message": ""},
    }


def record_execution_package_eligibility(
    *,
    project_path: str | None,
    package_id: str | None,
    eligibility_checked_by: str,
) -> dict[str, Any]:
    """Evaluate and persist package eligibility using package-local facts only."""
    checked_by = str(eligibility_checked_by or "").strip()
    if not checked_by:
        return {"status": "error", "reason": "eligibility_checked_by required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_eligibility(package)
    if evaluation.get("eligibility_status") == "pending":
        return {
            "status": "error",
            "reason": str((evaluation.get("eligibility_reason") or {}).get("message") or "Eligibility check requires a non-pending decision."),
            "package": package,
        }
    package["eligibility_status"] = evaluation.get("eligibility_status") or "pending"
    package["eligibility_timestamp"] = _utc_now_iso()
    package["eligibility_reason"] = _normalize_eligibility_reason(evaluation.get("eligibility_reason"))
    package["eligibility_checked_by"] = checked_by
    package["eligibility_check_id"] = str(uuid.uuid4())
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
        return {"status": "ok", "reason": "Execution package eligibility recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package eligibility.", "package": None}


def record_execution_package_eligibility_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_eligibility(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package eligibility.", "package": None}


def record_execution_package_release(
    *,
    project_path: str | None,
    package_id: str | None,
    release_actor: str,
    release_notes: str = "",
) -> dict[str, Any]:
    """Evaluate and persist package release state using package-local facts only."""
    actor = str(release_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "release_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_release(package)
    package["release_status"] = evaluation.get("release_status") or "pending"
    package["release_timestamp"] = _utc_now_iso()
    package["release_actor"] = actor
    package["release_notes"] = str(release_notes or "")
    package["release_id"] = str(uuid.uuid4())
    package["release_reason"] = _normalize_release_reason(evaluation.get("release_reason"))
    package["release_version"] = "v1"
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
        return {"status": "ok", "reason": "Execution package release recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package release.", "package": None}


def record_execution_package_release_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_release(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package release.", "package": None}


def record_execution_package_handoff(
    *,
    project_path: str | None,
    package_id: str | None,
    handoff_actor: str,
    executor_target_id: str,
    handoff_notes: str = "",
) -> dict[str, Any]:
    """Evaluate and persist package handoff status using package JSON as the source of truth."""
    actor = str(handoff_actor or "").strip()
    target_id = str(executor_target_id or "").strip().lower()
    if not actor:
        return {"status": "error", "reason": "handoff_actor required.", "package": None}
    if not target_id:
        return {"status": "error", "reason": "executor_target_id required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_handoff(package, executor_target_id=target_id)
    package["handoff_status"] = evaluation.get("handoff_status") or "pending"
    package["handoff_timestamp"] = _utc_now_iso()
    package["handoff_actor"] = actor
    package["handoff_notes"] = str(handoff_notes or "")
    package["handoff_id"] = str(uuid.uuid4())
    package["handoff_reason"] = _normalize_handoff_reason(evaluation.get("handoff_reason"))
    package["handoff_version"] = "v1"
    package["handoff_executor_target_id"] = str(evaluation.get("handoff_executor_target_id") or target_id)
    package["handoff_executor_target_name"] = str(evaluation.get("handoff_executor_target_name") or target_id)
    package["handoff_aegis_result"] = _normalize_handoff_aegis_result(evaluation.get("handoff_aegis_result"))
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
        return {"status": "ok", "reason": "Execution package handoff recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package handoff.", "package": None}


def record_execution_package_handoff_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_handoff(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package handoff.", "package": None}


def record_execution_package_execution(
    *,
    project_path: str | None,
    package_id: str | None,
    execution_actor: str,
) -> dict[str, Any]:
    """Evaluate and persist controlled runtime execution state for an authorized package."""
    actor = str(execution_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "execution_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    execution_id = str(uuid.uuid4())
    started_at = _utc_now_iso()
    evaluation = evaluate_execution_package_execution(package)
    package["execution_actor"] = actor
    package["execution_id"] = execution_id
    package["execution_version"] = "v1"
    package["execution_timestamp"] = started_at
    package["execution_started_at"] = started_at
    package["execution_executor_target_id"] = str(evaluation.get("execution_executor_target_id") or "")
    package["execution_executor_target_name"] = str(evaluation.get("execution_executor_target_name") or "")
    package["execution_aegis_result"] = _normalize_handoff_aegis_result(evaluation.get("execution_aegis_result"))

    if evaluation.get("execution_status") == "blocked":
        package["execution_status"] = "blocked"
        package["execution_reason"] = _normalize_execution_reason(evaluation.get("execution_reason"))
        package["execution_receipt"] = _normalize_execution_receipt(evaluation.get("execution_receipt"))
        package["execution_finished_at"] = _utc_now_iso()
        package["rollback_status"] = "not_needed"
        package["rollback_timestamp"] = ""
        package["rollback_reason"] = _normalize_rollback_reason(evaluation.get("rollback_reason"))
    else:
        try:
            from NEXUS.execution_package_executor import execute_execution_package_safe

            exec_result = execute_execution_package_safe(
                project_path=project_path,
                package=package,
                execution_id=execution_id,
                execution_actor=actor,
            )
        except Exception:
            exec_result = {
                "execution_status": "failed",
                "execution_reason": {"code": "runtime_start_failed", "message": "Runtime execution bridge unavailable."},
                "execution_receipt": _empty_execution_receipt(result_status="failed", failure_class="runtime_start_failure"),
                "rollback_status": "not_needed",
                "rollback_timestamp": "",
                "rollback_reason": {"code": "", "message": ""},
                "runtime_artifact": {},
                "execution_finished_at": _utc_now_iso(),
            }
        package["execution_status"] = str(exec_result.get("execution_status") or "failed")
        package["execution_reason"] = _normalize_execution_reason(exec_result.get("execution_reason"))
        package["execution_receipt"] = _normalize_execution_receipt(exec_result.get("execution_receipt"))
        package["execution_finished_at"] = str(exec_result.get("execution_finished_at") or _utc_now_iso())
        package["execution_timestamp"] = package["execution_finished_at"]
        package["rollback_status"] = str(exec_result.get("rollback_status") or "not_needed")
        package["rollback_timestamp"] = str(exec_result.get("rollback_timestamp") or "")
        package["rollback_reason"] = _normalize_rollback_reason(exec_result.get("rollback_reason"))
        runtime_artifact = exec_result.get("runtime_artifact")
        if isinstance(runtime_artifact, dict) and runtime_artifact:
            artifacts = list(package.get("runtime_artifacts") or [])
            artifacts.append(runtime_artifact)
            package["runtime_artifacts"] = [x for x in artifacts[:20] if isinstance(x, dict)]

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
        return {"status": "ok", "reason": "Execution package execution recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package execution.", "package": None}


def record_execution_package_execution_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_execution(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package execution.", "package": None}
