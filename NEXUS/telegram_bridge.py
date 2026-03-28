"""
Telegram activity feed utilities for Forge notifications.

This module provides safe command handling for activity visibility:
- activity / recent events
- alerts
- notifications status
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.notification_router import (
    get_notification_status_summary_safe,
    get_recent_notifications_safe,
)


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _short_time(value: Any) -> str:
    raw = _to_text(value)
    if not raw:
        return "unknown"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw


def _priority_tag(priority: Any) -> str:
    p = _to_text(priority).lower()
    if p == "critical":
        return "CRITICAL"
    if p == "high":
        return "HIGH"
    if p == "info":
        return "INFO"
    return "NORMAL"


def format_event_summary(event: dict[str, Any]) -> str:
    event_type = _to_text(event.get("event_type")) or "operator_alert"
    title = _to_text(event.get("event_title")) or event_type.replace("_", " ")
    message = _to_text(event.get("event_message"))
    status = _to_text((event.get("event_delivery_status") or {}).get("overall")) or "unknown"
    when = _short_time(event.get("event_timestamp"))
    return (
        f"- [{_priority_tag(event.get('event_priority'))}] {title} ({event_type})\n"
        f"  {message}\n"
        f"  status={status}; time={when}"
    )


def format_activity_feed(events: list[dict[str, Any]], *, title: str = "Forge Activity Feed") -> str:
    if not events:
        return f"{title}\nNo recent events."
    lines = [title]
    for event in events:
        lines.append(format_event_summary(event))
    return "\n".join(lines)


def _help_text() -> str:
    return (
        "Supported commands:\n"
        "- activity\n"
        "- recent events\n"
        "- alerts\n"
        "- notifications status"
    )


def handle_telegram_command_safe(
    *,
    command: str,
    project_path: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    cmd = " ".join(_to_text(command).lower().split())
    if cmd in {"activity", "recent events", "recent", "events"}:
        events = get_recent_notifications_safe(project_path=project_path, limit=max(1, int(limit)))
        return {
            "status": "ok",
            "command": "activity",
            "response_text": format_activity_feed(events, title="Forge Activity Feed"),
            "events": events,
        }
    if cmd in {"alerts", "recent alerts"}:
        events = get_recent_notifications_safe(
            project_path=project_path,
            limit=max(1, int(limit)),
            priorities=["high", "critical"],
        )
        return {
            "status": "ok",
            "command": "alerts",
            "response_text": format_activity_feed(events, title="Forge Alerts"),
            "events": events,
        }
    if cmd in {"notifications status", "notification status", "alerts status"}:
        status = get_notification_status_summary_safe(project_path=project_path)
        channel = dict(status.get("channel_status") or {})
        breakdown = dict(status.get("recent_delivery_breakdown") or {})
        text = (
            "Notification Status\n"
            f"telegram: {'configured' if bool(channel.get('telegram_configured')) else 'not_configured'}\n"
            f"pushover: {'configured' if bool(channel.get('pushover_configured')) else 'not_configured'}\n"
            f"recent_events: {int(status.get('recent_event_count') or 0)}\n"
            f"delivery_breakdown: {breakdown}"
        )
        return {
            "status": "ok",
            "command": "notifications_status",
            "response_text": text,
            "details": status,
        }
    return {
        "status": "ok",
        "command": "help",
        "response_text": _help_text(),
        "events": [],
    }
