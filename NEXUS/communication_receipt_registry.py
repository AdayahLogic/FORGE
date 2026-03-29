"""
Durable communication send-receipt registry.

Records governed communication transitions so send truth is explicit:
draft -> approval -> requested -> attempted -> receipt -> response/failed/blocked.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMMUNICATION_RECEIPT_JOURNAL_FILENAME = "communication_receipt_journal.jsonl"

VALID_SEND_STATUSES = {
    "draft_exists",
    "approval_required",
    "approval_granted",
    "send_requested",
    "send_attempted",
    "send_receipt_exists",
    "response_received",
    "send_blocked",
    "send_failed",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        path = Path(project_path).resolve() / "state"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def get_communication_receipt_journal_path(project_path: str | None) -> str | None:
    state = _state_dir(project_path)
    if not state:
        return None
    return str(state / COMMUNICATION_RECEIPT_JOURNAL_FILENAME)


def _normalize_send_status(value: Any) -> str:
    status = _text(value).lower()
    if status in VALID_SEND_STATUSES:
        return status
    return "draft_exists"


def normalize_communication_receipt_record(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record if isinstance(record, dict) else {}
    evidence = [dict(item) for item in list(r.get("evidence") or []) if isinstance(item, dict)]
    return {
        "communication_receipt_id": _text(r.get("communication_receipt_id") or f"commrcpt-{uuid.uuid4().hex[:16]}"),
        "project_name": _text(r.get("project_name")),
        "run_id": _text(r.get("run_id")),
        "mission_id": _text(r.get("mission_id")),
        "execution_package_id": _text(r.get("execution_package_id")),
        "deal_id": _text(r.get("deal_id")),
        "lead_id": _text(r.get("lead_id")),
        "email_thread_id": _text(r.get("email_thread_id")),
        "email_message_id": _text(r.get("email_message_id")),
        "channel": _text(r.get("channel") or "email").lower(),
        "direction": _text(r.get("direction") or "outbound").lower(),
        "send_status": _normalize_send_status(r.get("send_status")),
        "approval_id": _text(r.get("approval_id")),
        "approval_required": bool(r.get("approval_required")),
        "send_requested_at": _text(r.get("send_requested_at")),
        "send_attempted_at": _text(r.get("send_attempted_at")),
        "send_receipt_at": _text(r.get("send_receipt_at")),
        "response_received_at": _text(r.get("response_received_at")),
        "blocked_reason": _text(r.get("blocked_reason")),
        "failure_reason": _text(r.get("failure_reason")),
        "operator_actor": _text(r.get("operator_actor")),
        "system_inferred": bool(r.get("system_inferred", True)),
        "evidence": evidence[:30],
        "recorded_at": _text(r.get("recorded_at") or _now_iso()),
    }


def append_communication_receipt(
    *,
    project_path: str | None,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    journal_path = get_communication_receipt_journal_path(project_path)
    if not journal_path:
        return {"status": "degraded", "reason": "Communication receipt journal unavailable.", "receipt": None}
    normalized = normalize_communication_receipt_record(record)
    try:
        with open(journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Communication receipt appended.", "receipt": normalized}
    except Exception as exc:
        return {"status": "degraded", "reason": f"Failed to append communication receipt: {exc}", "receipt": normalized}


def append_communication_receipt_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return append_communication_receipt(**kwargs)
    except Exception as exc:
        return {"status": "degraded", "reason": f"Communication receipt write failed: {exc}", "receipt": None}


def read_communication_receipt_journal_tail(
    *,
    project_path: str | None,
    n: int = 100,
) -> list[dict[str, Any]]:
    journal_path = get_communication_receipt_journal_path(project_path)
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
    limit = max(1, min(int(n or 100), 1000))
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(normalize_communication_receipt_record(parsed))
    return out


def get_latest_communication_receipt(
    *,
    project_path: str | None,
    execution_package_id: str | None = None,
    email_thread_id: str | None = None,
) -> dict[str, Any] | None:
    package_id = _text(execution_package_id)
    thread_id = _text(email_thread_id)
    rows = read_communication_receipt_journal_tail(project_path=project_path, n=500)
    for row in reversed(rows):
        if package_id and _text(row.get("execution_package_id")) != package_id:
            continue
        if thread_id and _text(row.get("email_thread_id")) != thread_id:
            continue
        return row
    return None

