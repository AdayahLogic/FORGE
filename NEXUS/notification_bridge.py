"""
Bounded notification channel bridge for Forge.

This module provides safe channel adapters for Telegram and Pushover.
It never raises to callers and returns normalized status payloads.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, parse, request


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _priority_for_pushover(value: str) -> str:
    p = _to_text(value).lower()
    if p == "critical":
        return "critical"
    if p == "high":
        return "high"
    return "normal"


def _clip(value: Any, max_len: int = 1024) -> str:
    text = _to_text(value)
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)].rstrip() + "..."


def send_pushover_notification_safe(
    *,
    event: dict[str, Any],
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Deliver via existing revenue communication Pushover path.
    """
    try:
        from NEXUS.revenue_communication_loop import notify_operator_safe

        payload = dict(event.get("event_payload") or {})
        package_id = _to_text(payload.get("package_id")) or None
        dedupe_key = _to_text(payload.get("dedupe_key")) or _to_text(event.get("event_fingerprint"))
        result = notify_operator_safe(
            project_path=project_path,
            notification_type=_to_text(event.get("event_type")) or "operator_alert",
            notification_message=_clip(event.get("event_message"), max_len=1024),
            notification_priority=_priority_for_pushover(_to_text(event.get("event_priority"))),
            package_id=package_id,
            dedupe_key=dedupe_key or None,
        )
        out = {
            "channel": "pushover",
            "status": _to_text(result.get("status")) or "unknown",
            "reason": _to_text(result.get("reason")),
        }
        if _to_text(result.get("pushover_request")):
            out["request_id"] = _to_text(result.get("pushover_request"))
        return out
    except Exception as exc:
        return {
            "channel": "pushover",
            "status": "failed",
            "reason": f"Pushover bridge failure: {exc}",
        }


def _format_telegram_message(event: dict[str, Any]) -> str:
    title = _to_text(event.get("event_title")) or _to_text(event.get("event_type")) or "Notification"
    message = _clip(event.get("event_message"), max_len=700)
    priority = (_to_text(event.get("event_priority")) or "normal").upper()
    source = _to_text(event.get("event_source")) or "forge"
    timestamp = _to_text(event.get("event_timestamp"))
    return (
        f"[{priority}] {title}\n"
        f"{message}\n"
        f"source: {source}\n"
        f"time: {timestamp}"
    )


def send_telegram_notification_safe(
    *,
    event: dict[str, Any],
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Deliver one event to Telegram chat in operator-readable format.
    """
    del project_path  # Reserved for future per-project channel routing.
    token = _to_text(os.environ.get("TELEGRAM_BOT_TOKEN"))
    chat_id = _to_text(os.environ.get("TELEGRAM_CHAT_ID"))
    if not token or not chat_id:
        return {
            "channel": "telegram",
            "status": "skipped_unconfigured",
            "reason": "Telegram credentials are not configured.",
        }

    message_text = _format_telegram_message(event)
    body = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message_text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=6) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw) if raw.strip() else {}
        if bool(parsed.get("ok")):
            return {
                "channel": "telegram",
                "status": "sent",
                "reason": "Telegram message sent.",
            }
        return {
            "channel": "telegram",
            "status": "failed",
            "reason": _clip(parsed.get("description") or "Telegram API returned non-ok response.", max_len=300),
        }
    except Exception as exc:
        detail = str(exc)
        if isinstance(exc, error.HTTPError):
            try:
                detail = exc.read().decode("utf-8", errors="ignore") or detail
            except Exception:
                pass
        return {
            "channel": "telegram",
            "status": "failed",
            "reason": _clip(detail, max_len=300),
        }


def get_notification_channel_status_safe() -> dict[str, Any]:
    """
    Return configured/not-configured state for channels.
    """
    return {
        "telegram_configured": bool(_to_text(os.environ.get("TELEGRAM_BOT_TOKEN")) and _to_text(os.environ.get("TELEGRAM_CHAT_ID"))),
        "pushover_configured": bool(_to_text(os.environ.get("PUSHOVER_API_TOKEN")) and _to_text(os.environ.get("PUSHOVER_USER_KEY"))),
    }
