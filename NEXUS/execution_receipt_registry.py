"""
Global execution receipt registry.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
