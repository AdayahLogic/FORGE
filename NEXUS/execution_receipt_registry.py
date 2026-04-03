"""
Durable execution receipt registry.

Receipts are append-only records of execution attempts and remain the canonical
source for "attempted/completed" evidence.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECEIPT_JOURNAL_FILENAME = "execution_receipt_journal.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        state = Path(project_path).resolve() / "state"
        state.mkdir(parents=True, exist_ok=True)
        return state
    except Exception:
        return None


def get_execution_receipt_journal_path(project_path: str | None) -> str | None:
    state = _state_dir(project_path)
    if not state:
        return None
    return str(state / RECEIPT_JOURNAL_FILENAME)


def normalize_execution_receipt_record(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record if isinstance(record, dict) else {}
    claims = [str(item).strip() for item in (r.get("world_change_claims") or []) if str(item).strip()]
    changed_artifacts = [dict(item) for item in (r.get("changed_artifacts") or []) if isinstance(item, dict)]
    evidence = [dict(item) for item in (r.get("verification_evidence") or []) if isinstance(item, dict)]
    errors = [dict(item) for item in (r.get("errors") or []) if isinstance(item, dict)]
    return {
        "receipt_id": _text(r.get("receipt_id") or f"receipt-{uuid.uuid4().hex[:16]}"),
        "mission_id": _text(r.get("mission_id")),
        "run_id": _text(r.get("run_id")),
        "project_name": _text(r.get("project_name")),
        "execution_package_id": _text(r.get("execution_package_id")),
        "executor_target_id": _text(r.get("executor_target_id")),
        "executor_backend_id": _text(r.get("executor_backend_id")).lower(),
        "execution_actor": _text(r.get("execution_actor") or "workflow"),
        "execution_started_at": _text(r.get("execution_started_at") or _now_iso()),
        "execution_finished_at": _text(r.get("execution_finished_at")),
        "execution_status": _text(r.get("execution_status") or "unknown").lower(),
        "verification_status": _text(r.get("verification_status") or "pending").lower(),
        "rollback_status": _text(r.get("rollback_status") or "not_needed").lower(),
        "changed_artifacts": changed_artifacts[:50],
        "receipt_summary": _text(r.get("receipt_summary")),
        "world_change_claims": claims[:20],
        "verification_evidence": evidence[:30],
        "errors": errors[:30],
        "followup_required": bool(r.get("followup_required")),
        "recorded_at": _text(r.get("recorded_at") or _now_iso()),
    }


def build_execution_receipt_from_package(
    *,
    package: dict[str, Any] | None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    p = package if isinstance(package, dict) else {}
    execution_receipt = dict(p.get("execution_receipt") or {})
    execution_status = _text(p.get("execution_status") or execution_receipt.get("result_status") or "unknown").lower()
    changed_artifacts = [dict(item) for item in (p.get("runtime_artifacts") or []) if isinstance(item, dict)]
    failure_summary = dict(p.get("failure_summary") or {})
    errors: list[dict[str, Any]] = []
    if _text(failure_summary.get("failure_class")):
        errors.append(
            {
                "failure_class": _text(failure_summary.get("failure_class")),
                "failure_stage": _text(failure_summary.get("failure_stage")),
            }
        )
    return normalize_execution_receipt_record(
        {
            "mission_id": mission_id,
            "run_id": p.get("run_id"),
            "project_name": p.get("project_name"),
            "execution_package_id": p.get("package_id"),
            "executor_target_id": p.get("execution_executor_target_id") or p.get("handoff_executor_target_id"),
            "executor_backend_id": p.get("execution_executor_backend_id"),
            "execution_actor": p.get("execution_actor"),
            "execution_started_at": p.get("execution_started_at"),
            "execution_finished_at": p.get("execution_finished_at") or p.get("execution_timestamp"),
            "execution_status": execution_status,
            "verification_status": p.get("verification_status") or "pending",
            "rollback_status": p.get("rollback_status"),
            "changed_artifacts": changed_artifacts,
            "receipt_summary": p.get("execution_reason", {}).get("message"),
            "world_change_claims": [
                "runtime_artifacts_updated"
                if changed_artifacts
                else "no_world_change_claimed"
            ],
            "verification_evidence": [
                {
                    "evidence_type": "execution_receipt",
                    "result_status": _text(execution_receipt.get("result_status")).lower(),
                    "exit_code": execution_receipt.get("exit_code"),
                    "log_ref": _text(execution_receipt.get("log_ref")),
                }
            ],
            "errors": errors,
            "followup_required": execution_status in {"failed", "blocked", "rolled_back"},
        }
    )


def append_execution_receipt(
    *,
    project_path: str | None,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    journal_path = get_execution_receipt_journal_path(project_path)
    if not journal_path:
        return {"status": "degraded", "reason": "Execution receipt journal unavailable.", "receipt": None}
    normalized = normalize_execution_receipt_record(record)
    try:
        with open(journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution receipt recorded.", "receipt": normalized}
    except Exception as exc:
        return {"status": "degraded", "reason": f"Failed to persist execution receipt: {exc}", "receipt": normalized}


def append_execution_receipt_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return append_execution_receipt(**kwargs)
    except Exception as exc:
        return {"status": "degraded", "reason": f"Execution receipt write failed: {exc}", "receipt": None}


def read_execution_receipt_journal_tail(
    *,
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    journal_path = get_execution_receipt_journal_path(project_path)
    if not journal_path:
        return []
    file_path = Path(journal_path)
    if not file_path.exists():
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, min(int(n or 50), 500)) :]:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(normalize_execution_receipt_record(parsed))
    return out


def get_execution_receipt(
    *,
    project_path: str | None,
    receipt_id: str | None,
) -> dict[str, Any] | None:
    target_id = _text(receipt_id)
    if not target_id:
        return None
    rows = read_execution_receipt_journal_tail(project_path=project_path, n=500)
    for row in reversed(rows):
        if _text(row.get("receipt_id")) == target_id:
            return row
    return None


# ---------------------------------------------------------------------------
# Global execution receipt registry (phase-12)
# ---------------------------------------------------------------------------

RECEIPT_REGISTRY_DIR = "state"
RECEIPT_REGISTRY_FILE = "execution_receipts.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_execution_receipt_registry_path() -> Path:
    state_dir = _repo_root() / RECEIPT_REGISTRY_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / RECEIPT_REGISTRY_FILE


def record_execution_receipt(
    *,
    project_name: str,
    package_id: str,
    execution_id: str,
    runtime_target_id: str,
    execution_status: str,
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    receipt_record = {
        "receipt_record_id": uuid.uuid4().hex,
        "recorded_at": _utc_now_iso(),
        "project_name": str(project_name or ""),
        "package_id": str(package_id or ""),
        "execution_id": str(execution_id or ""),
        "runtime_target_id": str(runtime_target_id or ""),
        "execution_status": str(execution_status or ""),
        "execution_receipt": dict(execution_receipt or {}),
    }
    path = get_execution_receipt_registry_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(receipt_record, ensure_ascii=False) + "\n")
    return receipt_record


def read_latest_execution_receipt(*, package_id: str) -> dict[str, Any]:
    target = str(package_id or "").strip()
    if not target:
        return {}
    path = get_execution_receipt_registry_path()
    if not path.exists():
        return {}
    latest: dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if str(row.get("package_id") or "") == target:
                    latest = row
    except Exception:
        return {}
    return latest
