"""Unified notification routing for operator integrations."""

from __future__ import annotations

from typing import Any

from NEXUS.revenue_communication_loop import notify_operator_safe


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def route_operator_notification_safe(*, project_path: str | None, event_type: str, event_message: str, priority: str = "info", payload: dict[str, Any] | None = None, dedupe_key: str | None = None) -> dict[str, Any]:
    normalized_priority = _to_text(priority).lower() or "info"
    if normalized_priority not in {"info", "normal", "high", "critical"}:
        normalized_priority = "normal"

    telegram_delivery = {"status": "skipped"}
    try:
        from NEXUS.telegram_bridge import send_operator_message_safe

        telegram_delivery = send_operator_message_safe(
            message=(f"[{normalized_priority.upper()}] {event_type}: {event_message}" if _to_text(event_type) else event_message)
        )
    except Exception as exc:
        telegram_delivery = {"status": "failed", "reason": str(exc)}

    pushover_delivery = {"status": "not_required"}
    if normalized_priority in {"high", "critical"}:
        pushover_delivery = notify_operator_safe(
            project_path=project_path,
            notification_type=_to_text(event_type) or "operator_alert",
            notification_message=_to_text(event_message),
            notification_priority=normalized_priority,
            package_id=_to_text((payload or {}).get("package_id")),
            dedupe_key=_to_text(dedupe_key),
        )

    statuses = {_to_text(telegram_delivery.get("status")), _to_text(pushover_delivery.get("status"))}
    if "failed" in statuses:
        overall = "degraded"
    elif "sent" in statuses or "ok" in statuses:
        overall = "ok"
    elif "skipped_unconfigured" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "priority": normalized_priority,
        "delivery": {"telegram": telegram_delivery, "pushover": pushover_delivery},
        "routing_policy": {"info": "telegram", "high": "telegram+pushover", "critical": "telegram+pushover"},
    }
