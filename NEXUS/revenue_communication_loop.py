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
QUALIFICATION_STATUSES = {"unqualified", "qualified", "high_intent", "low_intent"}
URGENCY_LEVELS = {"low", "medium", "high"}
OBJECTION_TYPES = {"price", "trust", "timing", "unclear", "other"}
CLOSING_SIGNAL_TYPES = {"interest", "readiness", "confirmation", "none"}
CONVERSATION_STAGES = {"lead", "qualified", "negotiating", "closing", "closed", "lost"}


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


def _bounded_ratio(value: Any, *, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = fallback
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return round(parsed, 4)


def _normalize_urgency_level(value: Any) -> str:
    urgency = _to_text(value).lower()
    return urgency if urgency in URGENCY_LEVELS else "low"


def _clip_text(value: Any, *, max_len: int = 400) -> str:
    text = _to_text(value)
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)].rstrip() + "..."


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for item in keywords if item in lowered)


def _compute_qualification_fields(*, package: dict[str, Any], subject: str, body: str, now_iso: str) -> dict[str, Any]:
    lead_intent = _to_text(package.get("lead_intent"))
    lead_business_type = _to_text(package.get("lead_business_type"))
    follow_up_attempts = max(0, int(package.get("follow_up_attempt_count") or 0))
    status_hint = _to_text(package.get("lead_status")).lower()
    text = f"{subject} {body}".strip().lower()

    intent_hits = _count_keyword_hits(
        text,
        ["pricing", "quote", "proposal", "scope", "budget", "automation", "rebuild", "migration", "integration"],
    )
    urgency_hits = _count_keyword_hits(text, ["urgent", "asap", "today", "this week", "deadline", "soon"])
    readiness_hits = _count_keyword_hits(text, ["ready", "move forward", "next step", "approved", "timeline"])
    low_intent_hits = _count_keyword_hits(text, ["just browsing", "no rush", "maybe later", "not now", "someday"])

    score = 0.2
    score += min(0.35, intent_hits * 0.06)
    score += min(0.2, urgency_hits * 0.08)
    score += min(0.2, readiness_hits * 0.07)
    score -= min(0.25, low_intent_hits * 0.09)
    if status_hint in {"qualified", "contacted", "nurturing", "converted"}:
        score += 0.1
    if follow_up_attempts >= 3 and not readiness_hits:
        score -= 0.08
    score = _bounded_ratio(score, fallback=0.0)

    if score >= 0.78:
        q_status = "high_intent"
    elif score >= 0.55:
        q_status = "qualified"
    elif score < 0.30:
        q_status = "low_intent"
    else:
        q_status = "unqualified"

    urgency_level = "high" if urgency_hits >= 1 else "medium" if "week" in text else "low"
    urgency_level = _normalize_urgency_level(urgency_level)

    base_value = {
        "delivery_request": 12000.0,
        "automation_request": 9000.0,
        "pricing_request": 7000.0,
        "support_request": 3000.0,
        "general_inquiry": 2500.0,
    }.get(lead_intent, 3500.0)
    business_multiplier = {
        "finance": 1.35,
        "healthcare": 1.25,
        "ecommerce": 1.15,
        "agency_services": 1.1,
    }.get(lead_business_type, 1.0)
    qualification_multiplier = {
        "high_intent": 1.3,
        "qualified": 1.1,
        "unqualified": 0.85,
        "low_intent": 0.65,
    }.get(q_status, 1.0)
    value_estimate = round(base_value * business_multiplier * qualification_multiplier, 2)

    reason = (
        f"score={score:.2f} derived from intent_hits={intent_hits}, urgency_hits={urgency_hits}, "
        f"readiness_hits={readiness_hits}, low_intent_hits={low_intent_hits}, follow_up_attempts={follow_up_attempts}."
    )
    return {
        "qualification_status": q_status if q_status in QUALIFICATION_STATUSES else "unqualified",
        "qualification_score": score,
        "qualification_reason": reason,
        "lead_value_estimate": value_estimate,
        "urgency_level": urgency_level,
        "qualification_updated_at": now_iso,
    }


def _compute_offer_fields(*, package: dict[str, Any], qualification: dict[str, Any]) -> dict[str, Any]:
    lead_intent = _to_text(package.get("lead_intent")).lower()
    business_type = _to_text(package.get("lead_business_type")).lower()
    q_status = _to_text(qualification.get("qualification_status")).lower()
    q_score = _bounded_ratio(qualification.get("qualification_score"), fallback=0.0)
    value_estimate = float(qualification.get("lead_value_estimate") or 0.0)

    offer_type = {
        "automation_request": "automation_implementation_estimate",
        "delivery_request": "delivery_rebuild_estimate",
        "support_request": "support_retainer_estimate",
        "pricing_request": "scoped_project_estimate",
    }.get(lead_intent, "discovery_call_estimate")
    low_estimate = max(500.0, round(value_estimate * 0.65, -2))
    high_estimate = max(low_estimate + 500.0, round(value_estimate * 1.2, -2))
    offer_price_estimate = f"${int(low_estimate):,} - ${int(high_estimate):,} estimate"
    value_proposition = (
        "Reduce delivery risk with a bounded scope, explicit milestones, and approval-gated communication."
    )
    offer_summary = (
        f"Propose {offer_type.replace('_', ' ')} tailored to {business_type or 'business'} context "
        f"with urgency={qualification.get('urgency_level') or 'low'}."
    )
    offer_confidence = _bounded_ratio((q_score * 0.75) + (0.15 if q_status in {"qualified", "high_intent"} else 0.0))
    offer_reason = (
        f"Offer selected from lead_intent={lead_intent or 'general_inquiry'} and "
        f"qualification_status={q_status or 'unqualified'}."
    )
    return {
        "offer_type": offer_type,
        "offer_summary": offer_summary,
        "offer_price_estimate": offer_price_estimate,
        "offer_value_proposition": value_proposition,
        "offer_confidence": offer_confidence,
        "offer_customization_reason": offer_reason,
    }


def _compute_objection_fields(*, body: str) -> dict[str, Any]:
    lowered = body.lower()
    objection_type = "other"
    objection_reason = ""
    if any(term in lowered for term in ("too expensive", "cost too high", "budget is tight", "expensive")):
        objection_type = "price"
        objection_reason = "Lead expressed pricing pressure."
    elif any(term in lowered for term in ("proof", "reference", "case study", "trust", "credibility")):
        objection_type = "trust"
        objection_reason = "Lead asked for proof or trust signals."
    elif any(term in lowered for term in ("later", "next quarter", "timing", "not now", "busy")):
        objection_type = "timing"
        objection_reason = "Lead signaled timing hesitation."
    elif any(term in lowered for term in ("not sure", "unclear", "confused", "don't understand")):
        objection_type = "unclear"
        objection_reason = "Lead indicated unclear scope or understanding."

    detected = bool(objection_reason)
    if not detected:
        return {
            "objection_detected": False,
            "objection_type": "other",
            "objection_reason": "",
            "objection_response_strategy": "",
            "objection_response_draft": "",
        }
    strategy = {
        "price": "Acknowledge budget constraints, offer phased scope, and keep estimates transparent.",
        "trust": "Provide concise proof points, prior outcomes, and clear delivery safeguards.",
        "timing": "Offer a low-pressure next step with flexible scheduling.",
        "unclear": "Clarify scope in plain language and confirm goals before proposing commitment.",
    }.get(objection_type, "Acknowledge concern and ask a clarifying question.")
    draft = {
        "price": "Thanks for sharing the budget concern. We can scope a phased option so you can start small and expand only after results.",
        "trust": "Completely fair question. I can share a concise proof summary and outline exactly how we de-risk delivery before we proceed.",
        "timing": "Understood on timing. A practical next step is a brief planning pass now so you can activate when the window opens.",
        "unclear": "Thanks for calling that out. I can simplify the scope into clear milestones and confirm priorities before any commitment.",
    }.get(objection_type, "Thanks for the feedback. I can adjust the plan to match your constraints.")
    return {
        "objection_detected": True,
        "objection_type": objection_type if objection_type in OBJECTION_TYPES else "other",
        "objection_reason": objection_reason,
        "objection_response_strategy": strategy,
        "objection_response_draft": _clip_text(draft, max_len=500),
    }


def _compute_closing_fields(*, body: str, qualification: dict[str, Any]) -> dict[str, Any]:
    lowered = body.lower()
    signal_type = "none"
    confidence = 0.0
    if any(term in lowered for term in ("approved", "send contract", "let's proceed", "we are in", "ready to sign")):
        signal_type = "confirmation"
        confidence = 0.9
    elif any(term in lowered for term in ("ready", "next steps", "move forward", "can we start")):
        signal_type = "readiness"
        confidence = 0.78
    elif any(term in lowered for term in ("interested", "sounds good", "this works", "looks good")):
        signal_type = "interest"
        confidence = 0.62
    q_score = _bounded_ratio(qualification.get("qualification_score"), fallback=0.0)
    confidence = _bounded_ratio(confidence + (q_score * 0.15))
    detected = signal_type != "none"
    action = {
        "confirmation": "ask for confirmation",
        "readiness": "propose next step",
        "interest": "schedule follow-up",
        "none": "suggest onboarding",
    }.get(signal_type, "schedule follow-up")
    draft = {
        "confirmation": "Great to hear. If you confirm, I will prepare the onboarding checklist and kickoff timeline for approval.",
        "readiness": "Happy to move this forward. Would you like me to send the proposed next-step plan and kickoff options?",
        "interest": "Thanks for the signal. A useful next step is a short alignment call to finalize scope and timeline.",
        "none": "If helpful, I can share a concise onboarding outline so you can evaluate fit before committing.",
    }.get(signal_type, "If useful, I can suggest the next step.")
    return {
        "closing_signal_detected": detected,
        "closing_signal_type": signal_type if signal_type in CLOSING_SIGNAL_TYPES else "none",
        "closing_confidence": confidence,
        "recommended_closing_action": action,
        "closing_message_draft": _clip_text(draft, max_len=500),
    }


def _derive_conversation_stage(*, package: dict[str, Any], qualification: dict[str, Any], objection: dict[str, Any], closing: dict[str, Any]) -> str:
    lead_status = _to_text(package.get("lead_status")).lower()
    if lead_status == "converted":
        return "closed"
    if lead_status == "closed_lost":
        return "lost"
    if bool(closing.get("closing_signal_detected")):
        return "closing"
    if bool(objection.get("objection_detected")):
        return "negotiating"
    if _to_text(qualification.get("qualification_status")).lower() in {"qualified", "high_intent"}:
        return "qualified"
    return "lead"


def evaluate_sales_brain_safe(
    *,
    project_path: str | None,
    package_id: str | None,
    inbound_email: dict[str, Any] | None = None,
    outbound_message: str | None = None,
) -> dict[str, Any]:
    """
    Compute phase 111-115 sales intelligence and persist bounded fields.
    This function is deterministic and storage-only.
    """
    try:
        pkg_id = _to_text(package_id)
        package = read_execution_package(project_path=project_path, package_id=pkg_id) if pkg_id else {}
        package = package or {}
        inbound = inbound_email if isinstance(inbound_email, dict) else {}
        subject = _to_text(inbound.get("subject")) or _to_text((package.get("email_threads") or [{}])[-1].get("subject"))
        body = _to_text(inbound.get("body")) or _to_text(inbound.get("text")) or _to_text(inbound.get("content"))
        if not body:
            body = _to_text((package.get("email_threads") or [{}])[-1].get("body"))
        now_iso = _now_iso()
        qualification = _compute_qualification_fields(package=package, subject=subject, body=body, now_iso=now_iso)
        offer = _compute_offer_fields(package=package, qualification=qualification)
        objection = _compute_objection_fields(body=body)
        closing = _compute_closing_fields(body=body, qualification=qualification)

        prior_history = [dict(item) for item in list(package.get("conversation_history") or []) if isinstance(item, dict)]
        conversation_event: dict[str, Any] | None = None
        if body:
            conversation_event = {
                "direction": "inbound",
                "message": _clip_text(body, max_len=1000),
                "subject": _clip_text(subject, max_len=240),
                "at": now_iso,
            }
        elif _to_text(outbound_message):
            conversation_event = {
                "direction": "outbound_draft",
                "message": _clip_text(outbound_message, max_len=1000),
                "subject": _clip_text(subject, max_len=240),
                "at": now_iso,
            }
        if conversation_event:
            prior_history.append(conversation_event)
        conversation_history = prior_history[-30:]
        conversation_id = (
            _to_text(package.get("conversation_id"))
            or _to_text(inbound.get("thread_id"))
            or _to_text(package.get("email_thread_id"))
            or (f"conv-{pkg_id}" if pkg_id else f"conv-{uuid.uuid4().hex[:12]}")
        )
        conversation = {
            "conversation_id": conversation_id,
            "conversation_history": conversation_history,
            "last_user_message": _clip_text(body, max_len=1000) if body else _to_text(package.get("last_user_message")),
            "last_forge_message": (
                _clip_text(outbound_message, max_len=1000)
                if _to_text(outbound_message)
                else _to_text(package.get("last_forge_message"))
            ),
            "conversation_stage": _derive_conversation_stage(
                package=package,
                qualification=qualification,
                objection=objection,
                closing=closing,
            ),
            "conversation_last_updated_at": now_iso,
        }
        if conversation["conversation_stage"] not in CONVERSATION_STAGES:
            conversation["conversation_stage"] = "lead"

        updates = {
            **qualification,
            **offer,
            **objection,
            **closing,
            **conversation,
        }
        if closing.get("closing_signal_type") == "confirmation":
            updates["deal_status"] = "closed_won"
        elif _to_text(package.get("lead_status")).lower() == "closed_lost":
            updates["deal_status"] = "closed_lost"
        else:
            updates["deal_status"] = _to_text(package.get("deal_status")).lower() or "open"
        if pkg_id:
            record_execution_package_revenue_loop_safe(
                project_path=project_path,
                package_id=pkg_id,
                updates=updates,
            )
        return {"status": "ok", "reason": "Sales brain evaluated.", "sales_brain": updates}
    except Exception as exc:
        return {"status": "error", "reason": f"Sales brain evaluation failed: {exc}", "sales_brain": {}}


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
        sales_brain = evaluate_sales_brain_safe(
            project_path=project_path,
            package_id=package_id,
            inbound_email=normalized,
        )
        return {
            "status": "ok",
            "reason": "Inbound email lead ingested.",
            "lead": lead,
            "email": normalized,
            "sales_brain": sales_brain.get("sales_brain") or {},
        }
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
            evaluate_sales_brain_safe(
                project_path=project_path,
                package_id=pkg_id,
                outbound_message=body_text,
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
            evaluate_sales_brain_safe(
                project_path=project_path,
                package_id=pkg_id,
                outbound_message=body_text,
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
            evaluate_sales_brain_safe(
                project_path=project_path,
                package_id=pkg_id,
                inbound_email={},
            )
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
