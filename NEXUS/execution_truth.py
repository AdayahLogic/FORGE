"""
Execution truth taxonomy registry.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRUTH_REGISTRY_DIR = "state"
TRUTH_REGISTRY_FILE = "execution_truth.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_execution_truth_path() -> Path:
    state_dir = _repo_root() / TRUTH_REGISTRY_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / TRUTH_REGISTRY_FILE


def _normalize_truth_store(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    rows = raw.get("records")
    if not isinstance(rows, dict):
        rows = {}
    return {
        "schema_version": "1.0",
        "updated_at": str(raw.get("updated_at") or ""),
        "records": dict(rows),
    }


def load_execution_truth_store() -> dict[str, Any]:
    path = get_execution_truth_path()
    if not path.exists():
        return _normalize_truth_store(None)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _normalize_truth_store(None)
    return _normalize_truth_store(payload)


def _derive_truth_state(*, execution_status: str, verification_status: str, receipt_result_status: str) -> str:
    e = str(execution_status or "").strip().lower()
    v = str(verification_status or "").strip().lower()
    r = str(receipt_result_status or "").strip().lower()
    if e == "succeeded" and v == "verified" and r == "succeeded":
        return "executed_verified"
    if e in ("failed", "rolled_back", "blocked") or r in ("failed", "blocked") or v == "failed":
        return "executed_not_verified"
    if e in ("pending", "not_started", ""):
        return "not_executed"
    return "execution_unverified"


def update_execution_truth(
    *,
    project_name: str,
    package_id: str,
    execution_id: str,
    runtime_target_id: str,
    execution_status: str,
    receipt_record: dict[str, Any],
    verification_record: dict[str, Any],
    outcome_linkage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = load_execution_truth_store()
    receipt = dict(receipt_record or {})
    verification = dict(verification_record or {})
    receipt_result = str(((receipt.get("execution_receipt") or {}).get("result_status")) or "")
    verification_status = str(verification.get("verification_status") or "")
    truth_state = _derive_truth_state(
        execution_status=execution_status,
        verification_status=verification_status,
        receipt_result_status=receipt_result,
    )
    record = {
        "truth_record_id": uuid.uuid4().hex,
        "updated_at": _utc_now_iso(),
        "project_name": str(project_name or ""),
        "package_id": str(package_id or ""),
        "execution_id": str(execution_id or ""),
        "runtime_target_id": str(runtime_target_id or ""),
        "execution_status": str(execution_status or ""),
        "verification_status": verification_status,
        "receipt_result_status": receipt_result,
        "truth_state": truth_state,
        "receipt_record_id": str(receipt.get("receipt_record_id") or ""),
        "verification_record_id": str(verification.get("verification_record_id") or ""),
        "outcome_linkage": dict(outcome_linkage or {}),
    }
    key = str(package_id or execution_id or uuid.uuid4().hex)
    store["records"][key] = record
    store["updated_at"] = record["updated_at"]
    path = get_execution_truth_path()
    path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def read_execution_truth(*, package_id: str) -> dict[str, Any]:
    key = str(package_id or "").strip()
    if not key:
        return {}
    store = load_execution_truth_store()
    rows = dict(store.get("records") or {})
    return dict(rows.get(key) or {})
