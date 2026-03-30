"""
Governed revenue communication registry.

Provides one live channel (SMTP email) with explicit approval gating,
receipt-backed send attempts, response event journaling, and outcome evidence.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

SEND_RECEIPTS_FILENAME = "revenue_send_receipts.jsonl"
RESPONSE_EVENTS_FILENAME = "revenue_response_events.jsonl"
OUTCOMES_FILENAME = "revenue_outcomes.jsonl"

LIVE_CHANNEL_ID = "smtp_email"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def _journal_path(project_path: str | None, filename: str) -> str | None:
    state_dir = _state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / filename)


def get_send_receipts_path(project_path: str | None) -> str | None:
    return _journal_path(project_path, SEND_RECEIPTS_FILENAME)


def get_response_events_path(project_path: str | None) -> str | None:
    return _journal_path(project_path, RESPONSE_EVENTS_FILENAME)


def get_outcomes_path(project_path: str | None) -> str | None:
    return _journal_path(project_path, OUTCOMES_FILENAME)


def smtp_channel_readiness() -> dict[str, Any]:
    host = str(os.getenv("FORGE_SMTP_HOST") or "").strip()
    port_raw = str(os.getenv("FORGE_SMTP_PORT") or "").strip()
    username = str(os.getenv("FORGE_SMTP_USERNAME") or "").strip()
    password = str(os.getenv("FORGE_SMTP_PASSWORD") or "").strip()
    sender = str(os.getenv("FORGE_SMTP_FROM") or "").strip()
    use_starttls = str(os.getenv("FORGE_SMTP_USE_STARTTLS") or "1").strip().lower() not in {"0", "false", "no"}
    missing: list[str] = []
    if not host:
        missing.append("FORGE_SMTP_HOST")
    if not port_raw:
        missing.append("FORGE_SMTP_PORT")
    if not sender:
        missing.append("FORGE_SMTP_FROM")
    if not username:
        missing.append("FORGE_SMTP_USERNAME")
    if not password:
        missing.append("FORGE_SMTP_PASSWORD")
    try:
        port = int(port_raw)
    except Exception:
        port = 0
    if port <= 0:
        missing.append("FORGE_SMTP_PORT(valid_int)")
    return {
        "channel_id": LIVE_CHANNEL_ID,
        "channel_type": "email",
        "ready": len(missing) == 0,
        "missing_requirements": missing,
        "config": {
            "host": host,
            "port": port,
            "from": sender,
            "username": username,
            "use_starttls": use_starttls,
        },
        "safety_posture": "explicit_approval_required",
    }


def _append_jsonl(path: str | None, record: dict[str, Any]) -> bool:
    if not path:
        return False
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _read_jsonl_tail(path: str | None, n: int = 50) -> list[dict[str, Any]]:
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
    for line in lines[-max(1, int(n or 50)):]:
        row = str(line).strip()
        if not row:
            continue
        try:
            parsed = json.loads(row)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def normalize_send_receipt(record: dict[str, Any] | None) -> dict[str, Any]:
    r = dict(record or {})
    return {
        "receipt_id": str(r.get("receipt_id") or uuid.uuid4().hex[:16]),
        "attempted_at": str(r.get("attempted_at") or _utc_now_iso()),
        "project_name": str(r.get("project_name") or ""),
        "package_id": str(r.get("package_id") or ""),
        "channel_id": str(r.get("channel_id") or LIVE_CHANNEL_ID),
        "status": str(r.get("status") or "failed").strip().lower(),
        "approved": bool(r.get("approved")),
        "approval_id": str(r.get("approval_id") or ""),
        "operator_id": str(r.get("operator_id") or ""),
        "to": str(r.get("to") or ""),
        "subject": str(r.get("subject") or ""),
        "body_ref": str(r.get("body_ref") or ""),
        "provider_message_id": str(r.get("provider_message_id") or ""),
        "failure_class": str(r.get("failure_class") or ""),
        "error": str(r.get("error") or ""),
        "follow_up_due_at": str(r.get("follow_up_due_at") or ""),
    }


def append_send_receipt(project_path: str | None, record: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_send_receipt(record)
    written = _append_jsonl(get_send_receipts_path(project_path), normalized)
    return {"status": "ok" if written else "error", "receipt": normalized}


def read_send_receipts_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl_tail(get_send_receipts_path(project_path), n=n)
    return [normalize_send_receipt(row) for row in rows]


def normalize_response_event(record: dict[str, Any] | None) -> dict[str, Any]:
    r = dict(record or {})
    return {
        "event_id": str(r.get("event_id") or uuid.uuid4().hex[:16]),
        "event_at": str(r.get("event_at") or _utc_now_iso()),
        "project_name": str(r.get("project_name") or ""),
        "package_id": str(r.get("package_id") or ""),
        "receipt_id": str(r.get("receipt_id") or ""),
        "event_type": str(r.get("event_type") or "response_received").strip().lower(),
        "event_summary": str(r.get("event_summary") or ""),
        "evidence_ref": str(r.get("evidence_ref") or ""),
        "operator_confirmed": bool(r.get("operator_confirmed", True)),
    }


def append_response_event(project_path: str | None, record: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_response_event(record)
    written = _append_jsonl(get_response_events_path(project_path), normalized)
    return {"status": "ok" if written else "error", "event": normalized}


def read_response_events_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl_tail(get_response_events_path(project_path), n=n)
    return [normalize_response_event(row) for row in rows]


def normalize_revenue_outcome(record: dict[str, Any] | None) -> dict[str, Any]:
    r = dict(record or {})
    status = str(r.get("outcome_status") or "pending").strip().lower()
    if status not in {"pending", "closed_won", "closed_lost"}:
        status = "pending"
    return {
        "outcome_id": str(r.get("outcome_id") or uuid.uuid4().hex[:16]),
        "recorded_at": str(r.get("recorded_at") or _utc_now_iso()),
        "project_name": str(r.get("project_name") or ""),
        "package_id": str(r.get("package_id") or ""),
        "receipt_id": str(r.get("receipt_id") or ""),
        "outcome_status": status,
        "outcome_summary": str(r.get("outcome_summary") or ""),
        "evidence_ref": str(r.get("evidence_ref") or ""),
        "operator_confirmed": bool(r.get("operator_confirmed", True)),
    }


def append_revenue_outcome(project_path: str | None, record: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_revenue_outcome(record)
    written = _append_jsonl(get_outcomes_path(project_path), normalized)
    return {"status": "ok" if written else "error", "outcome": normalized}


def read_revenue_outcomes_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl_tail(get_outcomes_path(project_path), n=n)
    return [normalize_revenue_outcome(row) for row in rows]


def send_governed_email(
    *,
    to_email: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    readiness = smtp_channel_readiness()
    if not readiness.get("ready"):
        return {
            "status": "failed",
            "failure_class": "channel_not_ready",
            "error": "SMTP channel is not configured for live send.",
            "provider_message_id": "",
            "channel_readiness": readiness,
        }

    config = dict(readiness.get("config") or {})
    host = str(config.get("host") or "")
    port = int(config.get("port") or 0)
    sender = str(config.get("from") or "")
    username = str(config.get("username") or "")
    password = str(os.getenv("FORGE_SMTP_PASSWORD") or "")
    use_starttls = bool(config.get("use_starttls"))

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body or "")

    message_id = msg.get("Message-ID")
    if not message_id:
        message_id = f"<forge-{uuid.uuid4().hex}@{host or 'smtp'}>"
        msg["Message-ID"] = message_id

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host=host, port=port, timeout=30) as client:
            client.ehlo()
            if use_starttls:
                client.starttls(context=context)
                client.ehlo()
            if username:
                client.login(username, password)
            client.send_message(msg)
        return {
            "status": "sent",
            "failure_class": "",
            "error": "",
            "provider_message_id": str(message_id),
            "channel_readiness": readiness,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "failure_class": "smtp_send_failed",
            "error": str(exc),
            "provider_message_id": str(message_id),
            "channel_readiness": readiness,
        }


def send_governed_email_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return send_governed_email(**kwargs)
    except Exception as exc:
        return {
            "status": "failed",
            "failure_class": "unexpected_send_failure",
            "error": str(exc),
            "provider_message_id": "",
            "channel_readiness": smtp_channel_readiness(),
        }
