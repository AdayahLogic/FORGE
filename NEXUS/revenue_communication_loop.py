"""
Phase 107-110 governed revenue communication loop.

Capabilities:
- outbound email wrapper with mandatory approval gating
- inbound email intake normalization and lead conversion
- lead intake journaling (email/manual/future openclaw-compatible source tags)
- follow-up planning and escalation (no auto-send)
- operator push notifications via Pushover (retry-safe, non-blocking)

This module is intentionally side-effect conservative:
- never auto-sends external communication without explicit approval
- always records auditable journal events
- returns structured status payloads for operator workflows
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, parse, request
import os

from NEXUS.approval_registry import append_approval_record_safe
from NEXUS.console_attachment_registry import preview_intake_request_safe
from NEXUS.execution_package_registry import read_execution_package, record_execution_package_revenue_loop_safe
from NEXUS.logging_engine import log_system_event


RESEND_API_URL = "https://api.resend.com/emails"
PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
EMAIL_AUDIT_FILE = "email_communications.jsonl"
LEAD_AUDIT_FILE = "lead_intake.jsonl"
FOLLOW_UP_AUDIT_FILE = "follow_up_journal.jsonl"
NOTIFICATION_AUDIT_FILE = "operator_notifications.jsonl"

LEAD_PRIORITIES = {"low", "medium", "high", "critical"}
LEAD_STATUSES = {"new", "qualified", "contacted", "nurturing", "converted", "closed_lost"}
LEAD_TEMPERATURES = {"hot", "warm", "cold"}
FOLLOW_UP_STATUSES = {"not_required", "pending", "scheduled", "awaiting_approval", "sent", "escalated", "closed"}
EMAIL_DIRECTIONS = {"inbound", "outbound"}
EMAIL_STATUSES = {"received", "queued_for_approval", "sent", "failed", "approval_required", "skipped"}
NOTIFICATION_PRIORITIES = {"low", "normal", "high", "critical"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        state_dir = Path(project_path).resolve() / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def _append_jsonl(project_path: str | None, file_name: str, payload: dict[str, Any]) -> bool:
    state_dir = _state_dir(project_path)
    if not state_dir:
        return False
    try:
        target = state_dir / file_name
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_email_direction(value: Any) -> str:
    direction = _to_text(value).lower()
    return direction if direction in EMAIL_DIRECTIONS else "inbound"


def _normalize_email_status(value: Any) -> str:
    status = _to_text(value).lower()
    return status if status in EMAIL_STATUSES else "received"


def _normalize_lead_priority(value: Any) -> str:
    priority = _to_text(value).lower()
    return priority if priority in LEAD_PRIORITIES else "medium"


def _normalize_lead_status(value: Any) -> str:
    status = _to_text(value).lower()
    return status if status in LEAD_STATUSES else "new"


def _normalize_notification_priority(value: Any) -> str:
    priority = _to_text(value).lower()
    return priority if priority in NOTIFICATION_PRIORITIES else "normal"


def _normalize_follow_up_status(value: Any) -> str:
    status = _to_text(value).lower()
    return status if status in FOLLOW_UP_STATUSES else "pending"


def _infer_business_type(lead_contact_info: dict[str, Any], lead_intent: str) -> str:
    company = _to_text(lead_contact_info.get("company_name")).lower()
    email_addr = _to_text(lead_contact_info.get("contact_email")).lower()
    intent = _to_text(lead_intent).lower()
    if any(term in company for term in ("agency", "studio", "consult", "labs")):
        return "agency_services"
    if any(term in company for term in ("clinic", "hospital", "health")) or ".health" in email_addr:
        return "healthcare"
    if any(term in company for term in ("bank", "capital", "fintech")):
        return "finance"
    if any(term in intent for term in ("ecommerce", "store", "checkout")):
        return "ecommerce"
    return "general_business"


def _infer_lead_intent(subject: str, body: str) -> str:
    text = f"{subject} {body}".strip().lower()
    if any(term in text for term in ("quote", "pricing", "proposal", "cost")):
        return "pricing_request"
    if any(term in text for term in ("migration", "rebuild", "overhaul")):
        return "delivery_request"
    if any(term in text for term in ("automate", "workflow", "integration")):
        return "automation_request"
    if any(term in text for term in ("support", "help", "issue", "fix")):
        return "support_request"
    return "general_inquiry"


def _classify_temperature(*, intent: str, urgency_hint: str = "", subject: str = "") -> str:
    combined = f"{intent} {urgency_hint} {subject}".lower()
    if any(term in combined for term in ("urgent", "asap", "today", "critical", "pricing_request")):
        return "hot"
    if any(term in combined for term in ("delivery_request", "automation_request", "this week")):
        return "warm"
    return "cold"


def normalize_inbound_email(payload: dict[str, Any] | None) -> dict[str, Any]:
    p = payload or {}
    return {
        "sender": _to_text(p.get("sender") or p.get("from")),
        "subject": _to_text(p.get("subject")),
        "body": _to_text(p.get("body") or p.get("text") or p.get("content")),
        "timestamp": _to_text(p.get("timestamp")) or _now_iso(),
        "thread_id": _to_text(p.get("thread_id") or p.get("conversation_id") or p.get("email_thread_id")),
        "message_id": _to_text(p.get("message_id") or p.get("email_message_id")),
        "direction": "inbound",
        "status": "received",
        "requires_approval": False,
    }


def _lead_from_email(normalized_email: dict[str, Any], *, source: str) -> dict[str, Any]:
    sender = _to_text(normalized_email.get("sender"))
    subject = _to_text(normalized_email.get("subject"))
    body = _to_text(normalized_email.get("body"))
    timestamp = _to_text(normalized_email.get("timestamp")) or _now_iso()
    intent = _infer_lead_intent(subject, body)
    lead_contact_info = {
        "contact_name": "",
        "contact_email": sender,
        "company_name": "",
        "contact_channel": "email",
    }
    business_type = _infer_business_type(lead_contact_info, intent)
    temperature = _classify_temperature(intent=intent, subject=subject)
    priority = "high" if temperature == "hot" else "medium" if temperature == "warm" else "low"
    return {
        "lead_id": f"lead-{uuid.uuid4().hex[:12]}",
        "lead_source": source,
        "lead_contact_info": lead_contact_info,
        "lead_intent": intent,
        "lead_status": "new",
        "lead_priority": priority,
        "lead_created_at": timestamp,
        "lead_temperature": temperature,
        "lead_inferred_intent": intent,
        "lead_business_type": business_type,
        "email_thread_id": _to_text(normalized_email.get("thread_id")),
        "email_message_id": _to_text(normalized_email.get("message_id")),
        "email_direction": "inbound",
        "email_status": "received",
        "email_requires_approval": False,
    }


def ingest_email_lead_safe(
    *,
    project_path: str | None,
    inbound_email: dict[str, Any],
    package_id: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    try:
        normalized = normalize_inbound_email(inbound_email)
        lead = _lead_from_email(normalized, source="inbound_email")
        audit_record = {
            "record_type": "email_lead_ingest",
            "recorded_at": _now_iso(),
            "package_id": _to_text(package_id),
            "mission_id": _to_text(mission_id),
            "email": normalized,
            "lead": lead,
        }
        _append_jsonl(project_path, LEAD_AUDIT_FILE, audit_record)
        _append_jsonl(project_path, EMAIL_AUDIT_FILE, audit_record)
        log_system_event(
            project="",
            subsystem="revenue_communication_loop",
            action="ingest_email_lead",
            status="ok",
            reason="Inbound email normalized into lead.",
            metadata={"package_id": package_id or "", "lead_id": lead.get("lead_id"), "lead_source": "inbound_email"},
        )
        if package_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=package_id,
                updates={
                    **lead,
                    "email_threads": [
                        {
                            "email_thread_id": lead.get("email_thread_id") or "",
                            "email_message_id": lead.get("email_message_id") or "",
                            "email_direction": "inbound",
                            "email_status": "received",
                            "sender": normalized.get("sender") or "",
                            "subject": normalized.get("subject") or "",
                            "timestamp": normalized.get("timestamp") or _now_iso(),
                        }
                    ],
                },
            )
        return {"status": "ok", "reason": "Inbound email lead ingested.", "lead": lead, "email": normalized}
    except Exception as exc:
        return {"status": "error", "reason": f"Failed to ingest inbound email lead: {exc}", "lead": {}, "email": {}}


def inject_manual_lead_safe(
    *,
    project_path: str | None,
    lead_payload: dict[str, Any],
    package_id: str | None = None,
) -> dict[str, Any]:
    try:
        payload = lead_payload if isinstance(lead_payload, dict) else {}
        contact_info = dict(payload.get("lead_contact_info") or {})
        lead_intent = _to_text(payload.get("lead_intent")) or "general_inquiry"
        lead = {
            "lead_id": _to_text(payload.get("lead_id")) or f"lead-{uuid.uuid4().hex[:12]}",
            "lead_source": _to_text(payload.get("lead_source")) or "manual_injection",
            "lead_contact_info": {
                "contact_name": _to_text(contact_info.get("contact_name")),
                "contact_email": _to_text(contact_info.get("contact_email")),
                "company_name": _to_text(contact_info.get("company_name")),
                "contact_channel": _to_text(contact_info.get("contact_channel")) or "manual",
            },
            "lead_intent": lead_intent,
            "lead_status": _normalize_lead_status(payload.get("lead_status")),
            "lead_priority": _normalize_lead_priority(payload.get("lead_priority")),
            "lead_created_at": _to_text(payload.get("lead_created_at")) or _now_iso(),
            "lead_temperature": (
                _to_text(payload.get("lead_temperature")).lower()
                if _to_text(payload.get("lead_temperature")).lower() in LEAD_TEMPERATURES
                else _classify_temperature(intent=lead_intent)
            ),
            "lead_inferred_intent": _to_text(payload.get("lead_inferred_intent")) or lead_intent,
            "lead_business_type": _to_text(payload.get("lead_business_type"))
            or _infer_business_type(contact_info, lead_intent),
        }
        _append_jsonl(
            project_path,
            LEAD_AUDIT_FILE,
            {
                "record_type": "manual_lead_injection",
                "recorded_at": _now_iso(),
                "package_id": _to_text(package_id),
                "lead": lead,
            },
        )
        if package_id:
            record_execution_package_revenue_loop_safe(project_path=project_path, package_id=package_id, updates=lead)
        return {"status": "ok", "reason": "Manual lead injected.", "lead": lead}
    except Exception as exc:
        return {"status": "error", "reason": f"Manual lead injection failed: {exc}", "lead": {}}


def _build_email_approval_record(
    *,
    package_id: str,
    subject: str,
    to_email: str,
    thread_id: str,
    requested_by: str,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "approval_id": uuid.uuid4().hex[:16],
        "run_id": "",
        "project_name": "",
        "timestamp": _now_iso(),
        "status": "pending",
        "approval_type": "email_outbound_send",
        "reason": "Outbound email requires explicit operator approval before external delivery.",
        "requested_by": requested_by or "revenue_communication_loop",
        "requires_human": True,
        "risk_level": risk_level or "medium",
        "sensitivity": "high",
        "context": {
            "package_id": package_id,
            "to_email": to_email,
            "subject": subject,
            "email_thread_id": thread_id,
            "email_requires_approval": True,
        },
        "decision": None,
        "decision_timestamp": None,
    }


def send_email_safe(
    *,
    project_path: str | None,
    package_id: str | None,
    to_email: str,
    subject: str,
    body_text: str,
    from_email: str | None = None,
    thread_id: str | None = None,
    approval_granted: bool = False,
    approval_actor: str | None = None,
    risk_level: str = "high",
) -> dict[str, Any]:
    """
    Governed outbound email path.

    Without approval_granted=True this method never sends and writes an approval
    record instead.
    """
    pkg_id = _to_text(package_id)
    normalized_thread_id = _to_text(thread_id)
    now = _now_iso()
    email_record = {
        "record_type": "outbound_email",
        "recorded_at": now,
        "package_id": pkg_id,
        "to_email": _to_text(to_email),
        "subject": _to_text(subject),
        "thread_id": normalized_thread_id,
        "email_direction": "outbound",
        "email_requires_approval": True,
    }
    if not approval_granted:
        approval = _build_email_approval_record(
            package_id=pkg_id,
            subject=subject,
            to_email=to_email,
            thread_id=normalized_thread_id,
            requested_by=_to_text(approval_actor) or "revenue_communication_loop",
            risk_level=risk_level,
        )
        append_approval_record_safe(project_path=project_path, record=approval)
        email_record.update(
            {
                "status": "approval_required",
                "message": "Outbound email blocked until approval is granted.",
                "approval_id": approval.get("approval_id"),
            }
        )
        _append_jsonl(project_path, EMAIL_AUDIT_FILE, email_record)
        log_system_event(
            project="",
            subsystem="revenue_communication_loop",
            action="send_email_safe",
            status="blocked",
            reason="Approval required for outbound email.",
            metadata={"package_id": pkg_id, "approval_id": approval.get("approval_id"), "to_email": _to_text(to_email)},
        )
        if pkg_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=pkg_id,
                updates={
                    "email_thread_id": normalized_thread_id,
                    "email_message_id": "",
                    "email_direction": "outbound",
                    "email_status": "approval_required",
                    "email_requires_approval": True,
                    "approval_queue_item_type": "email_send_approval",
                    "approval_queue_risk_class": risk_level,
                    "approval_queue_reason": "Outbound email requires approval before send.",
                },
            )
        return {"status": "approval_required", "reason": "Approval required before outbound email send.", "approval_id": approval.get("approval_id")}

    resend_api_key = _to_text(os.environ.get("RESEND_API_KEY"))
    configured_from = _to_text(from_email) or _to_text(os.environ.get("RESEND_FROM_EMAIL"))
    if not resend_api_key or not configured_from:
        reason = "Resend configuration missing (RESEND_API_KEY or from email)."
        email_record.update({"status": "failed", "message": reason})
        _append_jsonl(project_path, EMAIL_AUDIT_FILE, email_record)
        if pkg_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=pkg_id,
                updates={
                    "email_thread_id": normalized_thread_id,
                    "email_message_id": "",
                    "email_direction": "outbound",
                    "email_status": "failed",
                    "email_requires_approval": True,
                },
            )
        return {"status": "error", "reason": reason, "email_message_id": ""}

    payload = {
        "from": configured_from,
        "to": [_to_text(to_email)],
        "subject": _to_text(subject),
        "text": _to_text(body_text),
    }
    if normalized_thread_id:
        payload["headers"] = {"X-Forge-Thread-ID": normalized_thread_id}
    req = request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw) if raw.strip() else {}
        message_id = _to_text(parsed.get("id") or parsed.get("message_id")) or f"resend-{uuid.uuid4().hex[:12]}"
        email_record.update({"status": "sent", "message_id": message_id})
        _append_jsonl(project_path, EMAIL_AUDIT_FILE, email_record)
        if pkg_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=pkg_id,
                updates={
                    "email_thread_id": normalized_thread_id,
                    "email_message_id": message_id,
                    "email_direction": "outbound",
                    "email_status": "sent",
                    "email_requires_approval": True,
                },
            )
        return {"status": "ok", "reason": "Outbound email sent.", "email_message_id": message_id}
    except Exception as exc:
        detail = str(exc)
        if isinstance(exc, error.HTTPError):
            try:
                detail = exc.read().decode("utf-8", errors="ignore") or detail
            except Exception:
                pass
        email_record.update({"status": "failed", "message": detail[:500]})
        _append_jsonl(project_path, EMAIL_AUDIT_FILE, email_record)
        if pkg_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=pkg_id,
                updates={
                    "email_thread_id": normalized_thread_id,
                    "email_message_id": "",
                    "email_direction": "outbound",
                    "email_status": "failed",
                    "email_requires_approval": True,
                },
            )
        return {"status": "error", "reason": f"Resend send failed: {detail[:500]}", "email_message_id": ""}


def schedule_follow_up_safe(
    *,
    project_path: str | None,
    package_id: str | None,
    no_response_hours: int = 48,
    max_attempts: int = 3,
    follow_up_strategy: str = "email_response_nudge",
    follow_up_priority: str = "medium",
    now_iso: str | None = None,
) -> dict[str, Any]:
    try:
        pkg_id = _to_text(package_id)
        package = read_execution_package(project_path=project_path, package_id=pkg_id) if pkg_id else {}
        package = package or {}
        now = datetime.fromisoformat((now_iso or _now_iso()).replace("Z", "+00:00"))
        attempt_count = max(0, int(package.get("follow_up_attempt_count") or 0))
        inbound_at = _to_text((package.get("metadata") or {}).get("last_inbound_email_at"))
        outbound_at = _to_text((package.get("metadata") or {}).get("last_outbound_email_at")) or _to_text(package.get("created_at"))
        latest_touch = inbound_at or outbound_at
        if latest_touch:
            try:
                last_dt = datetime.fromisoformat(latest_touch.replace("Z", "+00:00"))
            except Exception:
                last_dt = now
        else:
            last_dt = now
        elapsed = now - last_dt
        should_follow_up = elapsed >= timedelta(hours=max(1, int(no_response_hours)))
        escalated = attempt_count >= max(1, int(max_attempts))
        follow_up_status = "escalated" if escalated else "scheduled" if should_follow_up else "pending"
        next_at = (
            now.isoformat()
            if should_follow_up and not escalated
            else (last_dt + timedelta(hours=max(1, int(no_response_hours)))).isoformat()
        )

        lead_contact_info = dict(package.get("lead_contact_info") or {})
        qualification = dict((package.get("metadata") or {}).get("lead_qualification") or {})
        preview = preview_intake_request_safe(
            request_kind="lead_intake",
            project_key="",
            project_path=project_path or "",
            objective="Generate governed follow-up response draft.",
            project_context="Revenue follow-up planning.",
            constraints={
                "scope_boundaries": ["No automatic outbound send without approval."],
                "output_expectations": ["Generate follow-up response draft."],
                "review_expectations": ["Operator approval required before send."],
            },
            requested_artifacts={"selected": ["summary_report"], "custom": []},
            linked_attachment_ids=[],
            autonomy_mode="supervised_build",
            lead_intake_profile={
                "contact_name": _to_text(lead_contact_info.get("contact_name")),
                "contact_email": _to_text(lead_contact_info.get("contact_email")),
                "company_name": _to_text(lead_contact_info.get("company_name")),
                "contact_channel": _to_text(lead_contact_info.get("contact_channel")) or "email",
                "lead_source": _to_text(package.get("lead_source")) or "inbound_email",
                "problem_summary": _to_text(package.get("lead_intent")) or "Follow-up requested",
                "requested_outcome": "Progress response thread toward scoped proposal.",
                "budget_context": "",
                "urgency_context": "",
            },
            qualification=qualification,
        )
        response_summary = dict(preview.get("response_summary") or {})

        updates = {
            "follow_up_required": bool(should_follow_up),
            "follow_up_status": _normalize_follow_up_status(follow_up_status),
            "follow_up_next_at": _to_text(next_at),
            "follow_up_attempt_count": attempt_count,
            "follow_up_strategy": _to_text(follow_up_strategy) or "email_response_nudge",
            "follow_up_priority": _normalize_lead_priority(follow_up_priority),
        }
        if pkg_id:
            record_execution_package_revenue_loop_safe(project_path=project_path, package_id=pkg_id, updates=updates)
        _append_jsonl(
            project_path,
            FOLLOW_UP_AUDIT_FILE,
            {
                "record_type": "follow_up_schedule",
                "recorded_at": _now_iso(),
                "package_id": pkg_id,
                "follow_up": updates,
                "elapsed_hours_since_last_touch": round(elapsed.total_seconds() / 3600.0, 2),
                "response_summary": {
                    "response_status": _to_text(response_summary.get("response_status")),
                    "response_message": _to_text(response_summary.get("response_message")),
                },
            },
        )
        return {
            "status": "ok",
            "reason": "Follow-up evaluation completed.",
            "follow_up": updates,
            "response_summary": response_summary,
            "requires_send_approval": True,
            "escalated": escalated,
        }
    except Exception as exc:
        return {"status": "error", "reason": f"Follow-up scheduling failed: {exc}", "follow_up": {}}


def _notification_already_sent(project_path: str | None, dedupe_key: str) -> bool:
    if not dedupe_key:
        return False
    state_dir = _state_dir(project_path)
    if not state_dir:
        return False
    path = state_dir / NOTIFICATION_AUDIT_FILE
    if not path.exists():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for line in reversed(lines[-200:]):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if _to_text(rec.get("dedupe_key")) == dedupe_key and _to_text(rec.get("status")) in {"sent", "skipped_duplicate"}:
            return True
    return False


def notify_operator_safe(
    *,
    project_path: str | None,
    notification_type: str,
    notification_message: str,
    notification_priority: str = "normal",
    package_id: str | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    now = _now_iso()
    notif_type = _to_text(notification_type) or "operator_alert"
    priority = _normalize_notification_priority(notification_priority)
    dedupe = _to_text(dedupe_key)
    if dedupe and _notification_already_sent(project_path, dedupe):
        payload = {
            "status": "skipped_duplicate",
            "notification_type": notif_type,
            "notification_priority": priority,
            "notification_message": _to_text(notification_message),
            "notification_timestamp": now,
            "package_id": _to_text(package_id),
            "dedupe_key": dedupe,
        }
        _append_jsonl(project_path, NOTIFICATION_AUDIT_FILE, payload)
        return payload

    token = _to_text(os.environ.get("PUSHOVER_API_TOKEN"))
    user_key = _to_text(os.environ.get("PUSHOVER_USER_KEY"))
    payload = {
        "status": "queued",
        "notification_type": notif_type,
        "notification_priority": priority,
        "notification_message": _to_text(notification_message),
        "notification_timestamp": now,
        "package_id": _to_text(package_id),
        "dedupe_key": dedupe,
    }
    if not token or not user_key:
        payload["status"] = "skipped_unconfigured"
        payload["reason"] = "Pushover credentials are not configured."
        _append_jsonl(project_path, NOTIFICATION_AUDIT_FILE, payload)
        if package_id:
            record_execution_package_revenue_loop_safe(project_path=project_path, package_id=package_id, updates=payload)
        return payload

    pushover_priority = 0
    if priority == "high":
        pushover_priority = 1
    if priority == "critical":
        pushover_priority = 2

    body = parse.urlencode(
        {
            "token": token,
            "user": user_key,
            "title": f"Forge: {notif_type}",
            "message": _to_text(notification_message)[:1024],
            "priority": str(pushover_priority),
        }
    ).encode("utf-8")
    req = request.Request(PUSHOVER_API_URL, data=body, method="POST")
    attempts = max(1, int(max_attempts))
    last_error = ""
    for _ in range(attempts):
        try:
            with request.urlopen(req, timeout=4) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw) if raw.strip() else {}
            if int(parsed.get("status") or 0) == 1:
                payload["status"] = "sent"
                payload["pushover_request"] = _to_text(parsed.get("request"))
                _append_jsonl(project_path, NOTIFICATION_AUDIT_FILE, payload)
                if package_id:
                    record_execution_package_revenue_loop_safe(project_path=project_path, package_id=package_id, updates=payload)
                return payload
            last_error = raw[:500]
        except Exception as exc:
            last_error = str(exc)[:500]
    payload["status"] = "failed"
    payload["reason"] = f"Pushover delivery failed: {last_error}"
    _append_jsonl(project_path, NOTIFICATION_AUDIT_FILE, payload)
    if package_id:
        record_execution_package_revenue_loop_safe(project_path=project_path, package_id=package_id, updates=payload)
    return payload
