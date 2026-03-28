"""
Unified integration routing layer for Forge.

This module centralizes integration readiness checks, integration event journaling,
and safe execution wrappers. All risky actions remain approval-gated.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from NEXUS.project_state import update_project_state_fields
from NEXUS.registry import PROJECTS
from NEXUS.revenue_communication_loop import inject_manual_lead_safe

INTEGRATION_EVENT_FILE = "integration_events.jsonl"
ALLOWED_INTEGRATION_STATUSES = {"ready", "not_configured", "degraded", "failed"}

_ENV_BOOTSTRAPPED = False
_ENV_SEARCHED_PATHS: list[str] = []
_INTEGRATION_ENV_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "PUSHOVER_API_TOKEN",
    "PUSHOVER_USER_KEY",
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "STRIPE_SECRET_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_DEFAULT_VOICE_ID",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_text(value: Any) -> str:
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


def _append_jsonl(project_path: str | None, file_name: str, payload: dict[str, Any]) -> bool:
    state = _state_dir(project_path)
    if not state:
        return False
    try:
        target = state / file_name
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _parse_env_assignment(line: str) -> tuple[str, str] | None:
    raw = _to_text(line)
    if not raw or raw.startswith("#") or "=" not in raw:
        return None
    key, value = raw.split("=", 1)
    env_key = _to_text(key)
    if not env_key:
        return None
    env_val = value.strip()
    if env_val and len(env_val) >= 2 and env_val[0] == env_val[-1] and env_val[0] in {"'", '"'}:
        env_val = env_val[1:-1]
    return env_key, env_val


def _load_selected_env(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for line in lines:
        parsed = _parse_env_assignment(line)
        if not parsed:
            continue
        key, value = parsed
        if key not in _INTEGRATION_ENV_KEYS:
            continue
        if _to_text(os.environ.get(key)):
            continue
        os.environ[key] = value


def bootstrap_integration_env() -> dict[str, Any]:
    global _ENV_BOOTSTRAPPED, _ENV_SEARCHED_PATHS
    if _ENV_BOOTSTRAPPED:
        return {
            "status": "ok",
            "searched_paths": list(_ENV_SEARCHED_PATHS),
            "bootstrapped": True,
            "tavily_detected": bool(_to_text(os.environ.get("TAVILY_API_KEY"))),
        }
    _ENV_BOOTSTRAPPED = True
    seen: set[str] = set()
    candidates: list[Path] = []
    cwd_env = (Path.cwd().expanduser() / ".env")
    repo_env = (Path(__file__).resolve().parents[1].expanduser() / ".env")
    for candidate in (cwd_env, repo_env):
        try:
            resolved = candidate.resolve(strict=False)
        except Exception:
            continue
        marker = str(resolved)
        if marker in seen:
            continue
        seen.add(marker)
        candidates.append(resolved)
    _ENV_SEARCHED_PATHS = [str(path) for path in candidates]
    for candidate in candidates:
        _load_selected_env(candidate)
    return {
        "status": "ok",
        "searched_paths": list(_ENV_SEARCHED_PATHS),
        "bootstrapped": True,
        "tavily_detected": bool(_to_text(os.environ.get("TAVILY_API_KEY"))),
    }


def _integration_status(name: str, *, configured: bool, reason: str = "") -> dict[str, Any]:
    if configured:
        status = "ready"
        detail = reason or f"{name} credentials detected."
    else:
        status = "not_configured"
        detail = reason or f"{name} credentials missing."
    return {
        "integration": name,
        "status": status if status in ALLOWED_INTEGRATION_STATUSES else "failed",
        "reason": detail,
    }


def _project_for_lead_storage(project_key: str | None = None) -> tuple[str, str] | None:
    if project_key:
        key = _to_text(project_key).lower()
        project = PROJECTS.get(key) or {}
        path = _to_text(project.get("path"))
        if path:
            return key, path
    for key in sorted(PROJECTS.keys()):
        path = _to_text((PROJECTS.get(key) or {}).get("path"))
        if path:
            return key, path
    return None


def append_integration_event_safe(*, event_type: str, integration: str, status: str, project_path: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_status = _to_text(status).lower()
    if normalized_status not in ALLOWED_INTEGRATION_STATUSES | {"ok", "approval_required", "sent", "error"}:
        normalized_status = "failed"
    event = {
        "record_type": "integration_event",
        "recorded_at": _now_iso(),
        "event_type": _to_text(event_type) or "integration_event",
        "integration": _to_text(integration) or "unknown",
        "status": normalized_status,
        "payload": dict(payload or {}),
    }
    wrote = _append_jsonl(project_path, INTEGRATION_EVENT_FILE, event)
    if project_path:
        try:
            update_project_state_fields(project_path, last_integration_event={"event_type": event["event_type"], "integration": event["integration"], "status": event["status"], "recorded_at": event["recorded_at"]})
        except Exception:
            pass
    return {"status": "ok" if wrote else "failed", "event": event}


def get_recent_integration_events_safe(project_path: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    state = _state_dir(project_path)
    if not state:
        return []
    path = state / INTEGRATION_EVENT_FILE
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)) :]:
        raw = _to_text(line)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def integration_status_safe(project_path: str | None = None) -> dict[str, Any]:
    env_meta = bootstrap_integration_env()
    statuses = {
        "telegram": _integration_status("telegram", configured=bool(_to_text(os.environ.get("TELEGRAM_BOT_TOKEN"))), reason="Telegram bot token present." if _to_text(os.environ.get("TELEGRAM_BOT_TOKEN")) else "TELEGRAM_BOT_TOKEN missing."),
        "pushover": _integration_status("pushover", configured=bool(_to_text(os.environ.get("PUSHOVER_API_TOKEN")) and _to_text(os.environ.get("PUSHOVER_USER_KEY"))), reason=("Pushover token and user key present." if _to_text(os.environ.get("PUSHOVER_API_TOKEN")) and _to_text(os.environ.get("PUSHOVER_USER_KEY")) else "PUSHOVER_API_TOKEN and/or PUSHOVER_USER_KEY missing.")),
        "tavily": _integration_status("tavily", configured=bool(_to_text(os.environ.get("TAVILY_API_KEY"))), reason="Tavily API key present." if _to_text(os.environ.get("TAVILY_API_KEY")) else "TAVILY_API_KEY missing."),
        "firecrawl": _integration_status("firecrawl", configured=bool(_to_text(os.environ.get("FIRECRAWL_API_KEY"))), reason="Firecrawl API key present." if _to_text(os.environ.get("FIRECRAWL_API_KEY")) else "FIRECRAWL_API_KEY missing."),
        "stripe": _integration_status("stripe", configured=bool(_to_text(os.environ.get("STRIPE_SECRET_KEY"))), reason="Stripe secret key present." if _to_text(os.environ.get("STRIPE_SECRET_KEY")) else "STRIPE_SECRET_KEY missing."),
        "elevenlabs": _integration_status("elevenlabs", configured=bool(_to_text(os.environ.get("ELEVENLABS_API_KEY"))), reason="ElevenLabs API key present." if _to_text(os.environ.get("ELEVENLABS_API_KEY")) else "ELEVENLABS_API_KEY missing."),
        "twilio": _integration_status("twilio", configured=bool(_to_text(os.environ.get("TWILIO_ACCOUNT_SID")) and _to_text(os.environ.get("TWILIO_AUTH_TOKEN")) and _to_text(os.environ.get("TWILIO_FROM_NUMBER"))), reason=("Twilio account SID/auth token/from number present." if _to_text(os.environ.get("TWILIO_ACCOUNT_SID")) and _to_text(os.environ.get("TWILIO_AUTH_TOKEN")) and _to_text(os.environ.get("TWILIO_FROM_NUMBER")) else "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and/or TWILIO_FROM_NUMBER missing.")),
    }
    append_integration_event_safe(event_type="integration_status_checked", integration="integration_router", status="ok", project_path=project_path, payload={"statuses": statuses})
    return {"status": "ok", "env_bootstrap": env_meta, "integrations": statuses, "allowed_statuses": sorted(ALLOWED_INTEGRATION_STATUSES), "safety": {"auto_outreach": False, "auto_billing": False, "auto_calling": False}}


def discover_leads_safe(*, query: str | None, project_key: str | None = None, max_results: int = 5) -> dict[str, Any]:
    bootstrap_integration_env()
    search_query = _to_text(query) or "cleaning businesses in Baltimore"
    project = _project_for_lead_storage(project_key=project_key)
    if not project:
        return {"status": "failed", "query": search_query, "reason": "No writable project available for lead storage.", "lead_count": 0, "leads": []}
    resolved_project_key, resolved_project_path = project

    from NEXUS.tavily_bridge import discover_leads_safe as _tavily_discover
    from NEXUS.firecrawl_bridge import enrich_leads_safe as _firecrawl_enrich

    discovery = _tavily_discover(query=search_query, max_results=max_results)
    if _to_text(discovery.get("status")) == "not_configured":
        append_integration_event_safe(event_type="lead_discovery", integration="tavily", status="not_configured", project_path=resolved_project_path, payload={"query": search_query})
        return {"status": "not_configured", "query": search_query, "reason": "Tavily not configured", "lead_count": 0, "leads": [], "enrichment_occurred": False, "stored_count": 0, "project_key": resolved_project_key, "outreach_enabled": False, "approval_required_for_outreach": True}

    leads = [dict(item) for item in list(discovery.get("leads") or []) if isinstance(item, dict)]
    enriched = _firecrawl_enrich(leads=leads)
    final_leads = [dict(item) for item in list(enriched.get("leads") or leads) if isinstance(item, dict)]

    stored_ids: list[str] = []
    for lead in final_leads:
        payload = {
            "lead_source": "integration_router_tavily",
            "lead_contact_info": {
                "contact_name": "",
                "contact_email": _to_text(lead.get("contact_email")),
                "company_name": _to_text(lead.get("name")) or _to_text(lead.get("company_name")),
                "contact_channel": "web_discovery",
            },
            "lead_intent": "general_inquiry",
            "lead_status": "new",
            "lead_priority": "medium",
            "lead_business_type": "service_business",
            "lead_temperature": "warm",
            "lead_notes": {"query": search_query, "website": _to_text(lead.get("website")), "snippet": _to_text(lead.get("snippet")), "services": list(lead.get("services") or [])},
        }
        result = inject_manual_lead_safe(project_path=resolved_project_path, lead_payload=payload, package_id=None)
        if _to_text(result.get("status")) == "ok":
            lead_obj = dict(result.get("lead") or {})
            lead_id = _to_text(lead_obj.get("lead_id"))
            if lead_id:
                stored_ids.append(lead_id)

    top_names = [(_to_text(item.get("name")) or _to_text(item.get("company_name"))) for item in final_leads if _to_text(item.get("name")) or _to_text(item.get("company_name"))][:5]

    response = {"status": "ok", "query": search_query, "lead_count": len(final_leads), "top_lead_names": top_names, "leads": final_leads, "enrichment_occurred": bool(enriched.get("enrichment_occurred")), "enrichment_status": _to_text(enriched.get("status")) or "unknown", "stored_count": len(stored_ids), "stored_lead_ids": stored_ids, "project_key": resolved_project_key, "outreach_enabled": False, "approval_required_for_outreach": True}
    append_integration_event_safe(event_type="lead_discovery", integration="integration_router", status="ok", project_path=resolved_project_path, payload={"query": search_query, "lead_count": response["lead_count"], "stored_count": response["stored_count"], "enrichment_occurred": response["enrichment_occurred"]})
    return response


def route_notification_safe(*, project_path: str | None, event_type: str, message: str, priority: str = "info", payload: dict[str, Any] | None = None, dedupe_key: str | None = None) -> dict[str, Any]:
    from NEXUS.notification_router import route_operator_notification_safe

    result = route_operator_notification_safe(project_path=project_path, event_type=event_type, event_message=message, priority=priority, payload=payload or {}, dedupe_key=dedupe_key)
    append_integration_event_safe(event_type="notification_delivery", integration="notification_router", status="ok" if _to_text(result.get("status")) in {"ok", "degraded"} else "failed", project_path=project_path, payload=result)
    return result


def create_payment_link_safe(*, amount_cents: int, currency: str, description: str, approval_granted: bool = False, project_path: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    bootstrap_integration_env()
    if not approval_granted:
        result = {"status": "approval_required", "reason": "Payment link creation requires explicit approval.", "payment_link_url": "", "one_time_only": True, "auto_billing_enabled": False}
        append_integration_event_safe(event_type="stripe_payment_link", integration="stripe", status="degraded", project_path=project_path, payload=result)
        return result

    from NEXUS.stripe_bridge import create_one_time_payment_link_safe

    result = create_one_time_payment_link_safe(amount_cents=amount_cents, currency=currency, description=description, metadata=metadata or {})
    append_integration_event_safe(event_type="stripe_payment_link", integration="stripe", status="ok" if _to_text(result.get("status")) == "ok" else "failed", project_path=project_path, payload=result)
    return result


def generate_voice_artifact_safe(*, text: str, voice_id: str | None = None, output_path: str | None = None, project_path: str | None = None) -> dict[str, Any]:
    bootstrap_integration_env()
    from NEXUS.elevenlabs_bridge import generate_voice_safe

    result = generate_voice_safe(text=text, voice_id=voice_id, output_path=output_path)
    append_integration_event_safe(event_type="voice_generation", integration="elevenlabs", status="ok" if _to_text(result.get("status")) == "ok" else "failed", project_path=project_path, payload=result)
    return result


def send_twilio_sms_safe(*, to_number: str, message: str, approval_granted: bool = False, project_path: str | None = None) -> dict[str, Any]:
    bootstrap_integration_env()
    if not approval_granted:
        result = {"status": "approval_required", "reason": "Twilio SMS send requires explicit approval.", "auto_calling_enabled": False, "auto_send_enabled": False}
        append_integration_event_safe(event_type="twilio_sms", integration="twilio", status="degraded", project_path=project_path, payload=result)
        return result

    from NEXUS.twilio_bridge import send_sms_safe

    result = send_sms_safe(to_number=to_number, message=message)
    append_integration_event_safe(event_type="twilio_sms", integration="twilio", status="ok" if _to_text(result.get("status")) == "ok" else "failed", project_path=project_path, payload=result)
    return result
