"""
Integration readiness registry.

Tracks configuration/auth/readiness posture for external integrations without
enabling unsafe live behavior.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


INTEGRATION_REGISTRY: dict[str, dict[str, Any]] = {
    "tavily": {
        "integration_name": "tavily",
        "configuration_env": ["TAVILY_API_KEY"],
        "authentication_env": ["TAVILY_API_KEY"],
        "capabilities": ["search_api"],
        "blocked_actions": ["live_unreviewed_search"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "firecrawl": {
        "integration_name": "firecrawl",
        "configuration_env": ["FIRECRAWL_API_KEY"],
        "authentication_env": ["FIRECRAWL_API_KEY"],
        "capabilities": ["crawl_api", "extract_content"],
        "blocked_actions": ["live_unreviewed_crawl"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "stripe": {
        "integration_name": "stripe",
        "configuration_env": ["STRIPE_API_KEY"],
        "authentication_env": ["STRIPE_API_KEY"],
        "capabilities": ["billing", "payment_intents", "invoice_operations"],
        "blocked_actions": ["charge_customer_without_review", "live_payout_without_review"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "twilio": {
        "integration_name": "twilio",
        "configuration_env": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
        "authentication_env": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
        "capabilities": ["sms_send", "voice_send"],
        "blocked_actions": ["outbound_live_messaging_without_review"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "pushover": {
        "integration_name": "pushover",
        "configuration_env": ["PUSHOVER_API_TOKEN", "PUSHOVER_USER_KEY"],
        "authentication_env": ["PUSHOVER_API_TOKEN", "PUSHOVER_USER_KEY"],
        "capabilities": ["operator_notifications"],
        "blocked_actions": [],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": False,
        "implemented": True,
    },
    "elevenlabs": {
        "integration_name": "elevenlabs",
        "configuration_env": ["ELEVENLABS_API_KEY"],
        "authentication_env": ["ELEVENLABS_API_KEY"],
        "capabilities": ["voice_generation"],
        "blocked_actions": ["live_voice_outreach_without_review"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "telegram": {
        "integration_name": "telegram",
        "configuration_env": ["TELEGRAM_BOT_TOKEN"],
        "authentication_env": ["TELEGRAM_BOT_TOKEN"],
        "capabilities": ["bot_messaging"],
        "blocked_actions": ["outbound_live_messaging_without_review"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": False,
    },
    "resend": {
        "integration_name": "resend",
        "configuration_env": ["RESEND_API_KEY", "RESEND_FROM_EMAIL"],
        "authentication_env": ["RESEND_API_KEY"],
        "capabilities": ["email_send"],
        "blocked_actions": ["outbound_email_without_approval"],
        "governed_only": True,
        "dry_run_available": True,
        "operator_review_required": True,
        "implemented": True,
    },
}


def _state_file(project_path: str | None, file_name: str) -> Path | None:
    if not project_path:
        return None
    try:
        path = Path(project_path).resolve() / "state" / file_name
        return path
    except Exception:
        return None


def _latest_audit_status(path: Path | None, *, success_statuses: set[str], failure_statuses: set[str]) -> tuple[str, str]:
    if not path or not path.exists():
        return ("", "")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ("", "")
    last_success_at = ""
    last_failure = ""
    for raw in reversed(lines[-300:]):
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        status = _text(row.get("status")).lower()
        at = _text(row.get("recorded_at") or row.get("notification_timestamp") or row.get("timestamp"))
        if not last_success_at and status in success_statuses:
            last_success_at = at
        if not last_failure and status in failure_statuses:
            detail = _text(row.get("reason") or row.get("message") or status)
            last_failure = f"{at}|{detail}" if at else detail
        if last_success_at and last_failure:
            break
    return (last_success_at, last_failure)


def _env_present(keys: list[str]) -> bool:
    if not keys:
        return False
    return all(bool(_text(os.environ.get(key))) for key in keys)


def build_integration_readiness_entry(
    *,
    integration_name: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    name = _text(integration_name).lower()
    config = INTEGRATION_REGISTRY.get(name)
    if not config:
        return {
            "integration_name": name,
            "configured": False,
            "authenticated": False,
            "safe_to_use": False,
            "governed_only": True,
            "last_success_at": "",
            "last_failure_at": "",
            "last_failure_reason": "unknown_integration",
            "capabilities": [],
            "blocked_actions": ["all_actions"],
            "dry_run_available": True,
            "live_action_allowed": False,
            "operator_review_required": True,
            "readiness_status": "unknown",
            "recorded_at": _now_iso(),
        }

    configured = _env_present(list(config.get("configuration_env") or []))
    authenticated = _env_present(list(config.get("authentication_env") or []))
    implemented = bool(config.get("implemented"))
    governed_only = bool(config.get("governed_only", True))
    operator_review_required = bool(config.get("operator_review_required", True))
    live_flag = _text(os.environ.get(f"{name.upper()}_LIVE_ENABLED")).lower()
    live_requested = live_flag in {"1", "true", "yes", "on"}
    live_action_allowed = bool(implemented and configured and authenticated and live_requested and not governed_only and not operator_review_required)
    safe_to_use = bool(implemented and configured and authenticated)

    last_success_at = ""
    last_failure_at = ""
    last_failure_reason = ""
    if name == "resend":
        success_at, failure = _latest_audit_status(
            _state_file(project_path, "email_communications.jsonl"),
            success_statuses={"sent", "ok"},
            failure_statuses={"failed", "error"},
        )
        last_success_at = success_at
        if failure:
            parts = failure.split("|", 1)
            if len(parts) == 2:
                last_failure_at, last_failure_reason = parts[0], parts[1]
            else:
                last_failure_reason = failure
    elif name == "pushover":
        success_at, failure = _latest_audit_status(
            _state_file(project_path, "operator_notifications.jsonl"),
            success_statuses={"sent"},
            failure_statuses={"failed"},
        )
        last_success_at = success_at
        if failure:
            parts = failure.split("|", 1)
            if len(parts) == 2:
                last_failure_at, last_failure_reason = parts[0], parts[1]
            else:
                last_failure_reason = failure

    readiness_status = "not_configured"
    if implemented and configured and authenticated:
        readiness_status = "ready_governed" if governed_only else "ready"
    elif not implemented:
        readiness_status = "adapter_missing"
        if not last_failure_reason:
            last_failure_reason = "integration_adapter_not_implemented"
    elif configured and not authenticated:
        readiness_status = "auth_missing"

    return {
        "integration_name": name,
        "configured": configured,
        "authenticated": authenticated,
        "safe_to_use": safe_to_use,
        "governed_only": governed_only,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "last_failure_reason": last_failure_reason,
        "capabilities": [str(x) for x in list(config.get("capabilities") or []) if str(x).strip()],
        "blocked_actions": [str(x) for x in list(config.get("blocked_actions") or []) if str(x).strip()],
        "dry_run_available": bool(config.get("dry_run_available", True)),
        "live_action_allowed": live_action_allowed,
        "operator_review_required": operator_review_required,
        "readiness_status": readiness_status,
        "recorded_at": _now_iso(),
    }


def build_integration_readiness_summary(*, project_path: str | None = None) -> dict[str, Any]:
    names = sorted(INTEGRATION_REGISTRY.keys())
    integrations = [
        build_integration_readiness_entry(integration_name=name, project_path=project_path)
        for name in names
    ]
    ready_count = sum(1 for row in integrations if bool(row.get("safe_to_use")))
    governed_only_count = sum(1 for row in integrations if bool(row.get("governed_only")))
    live_allowed_count = sum(1 for row in integrations if bool(row.get("live_action_allowed")))
    degraded_count = sum(1 for row in integrations if _text(row.get("readiness_status")) not in {"ready", "ready_governed"})
    return {
        "integration_readiness_status": "ok",
        "integration_count": len(integrations),
        "ready_count": ready_count,
        "governed_only_count": governed_only_count,
        "live_allowed_count": live_allowed_count,
        "degraded_count": degraded_count,
        "integrations": integrations,
    }

