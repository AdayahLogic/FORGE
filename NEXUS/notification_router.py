"""
Unified notification router for Forge.

Responsibilities:
- normalize notification events
- apply priority/event-type routing rules
- deliver through bounded channel bridges
- persist lightweight recent activity history
- tolerate partial channel failures without crashing callers
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from NEXUS.logging_engine import log_system_event


ALLOWED_PRIORITIES = {"info", "normal", "high", "critical"}
DEFAULT_HISTORY_LIMIT = 200
DEDUPE_SCAN_LIMIT = 120

PRIORITY_CHANNEL_RULES: dict[str, list[str]] = {
    "info": ["telegram"],
    "normal": ["telegram"],
    "high": ["telegram", "pushover"],
    "critical": ["telegram", "pushover"],
}

EVENT_CHANNEL_OVERRIDES: dict[str, list[str]] = {
    "approval_required": ["telegram", "pushover"],
    "new_lead": ["telegram"],
    "deal_closed": ["telegram", "pushover"],
    "delivery_ready": ["telegram", "pushover"],
    "mission_failed": ["telegram", "pushover"],
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_priority(value: Any) -> str:
    parsed = _to_text(value).lower()
    return parsed if parsed in ALLOWED_PRIORITIES else "normal"


def _normalize_event_type(value: Any) -> str:
    event_type = _to_text(value).lower()
    return event_type if event_type else "operator_alert"


def _event_title_from_type(event_type: str) -> str:
    return event_type.replace("_", " ").strip().title() or "Operator Alert"


def _normalize_payload(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _history_path(project_path: str | None) -> Path:
    if _to_text(project_path):
        try:
            state_dir = Path(_to_text(project_path)).resolve() / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            return state_dir / "notification_history.jsonl"
        except Exception:
            pass
    ops_dir = _repo_root() / "ops"
    ops_dir.mkdir(parents=True, exist_ok=True)
    return ops_dir / "notification_history.jsonl"


def _read_history(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    source = lines if limit is None else lines[-max(1, int(limit)) :]
    for line in source:
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except Exception:
            continue
    return out


def _write_history(path: Path, events: list[dict[str, Any]]) -> bool:
    try:
        serialized = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
        if serialized:
            serialized += "\n"
        path.write_text(serialized, encoding="utf-8")
        return True
    except Exception:
        return False


def _append_history(project_path: str | None, event: dict[str, Any], max_items: int = DEFAULT_HISTORY_LIMIT) -> bool:
    path = _history_path(project_path)
    events = _read_history(path, limit=max_items - 1 if max_items > 1 else 1)
    events.append(event)
    return _write_history(path, events[-max(1, int(max_items)) :])


def _event_fingerprint(event_type: str, message: str, priority: str, source: str, dedupe_key: str = "") -> str:
    base = dedupe_key or "|".join([event_type, message, priority, source])
    return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _parse_iso(value: Any) -> datetime | None:
    text = _to_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def resolve_notification_channels(event_type: str, priority: str) -> list[str]:
    evt = _normalize_event_type(event_type)
    pri = _normalize_priority(priority)
    channels = EVENT_CHANNEL_OVERRIDES.get(evt) or PRIORITY_CHANNEL_RULES.get(pri) or ["telegram"]
    out: list[str] = []
    for channel in channels:
        name = _to_text(channel).lower()
        if name and name not in out:
            out.append(name)
    return out


def normalize_notification_event(
    *,
    event_type: str,
    message: str,
    priority: str = "normal",
    payload: dict[str, Any] | None = None,
    event_title: str | None = None,
    event_source: str = "forge",
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    evt_type = _normalize_event_type(event_type)
    evt_priority = _normalize_priority(priority)
    evt_message = _to_text(message)
    evt_source = _to_text(event_source) or "forge"
    evt_payload = _normalize_payload(payload)
    evt_dedupe = _to_text(dedupe_key) or _to_text(evt_payload.get("dedupe_key"))
    fingerprint = _event_fingerprint(evt_type, evt_message, evt_priority, evt_source, evt_dedupe)
    return {
        "event_id": uuid.uuid4().hex[:16],
        "event_type": evt_type,
        "event_title": _to_text(event_title) or _event_title_from_type(evt_type),
        "event_message": evt_message,
        "event_priority": evt_priority,
        "event_source": evt_source,
        "event_timestamp": _now_iso(),
        "event_payload": evt_payload,
        "event_channels_sent": [],
        "event_delivery_status": {},
        "event_fingerprint": fingerprint,
    }


def _is_duplicate_event(
    *,
    project_path: str | None,
    fingerprint: str,
    event_timestamp: str,
    dedupe_window_seconds: int,
) -> bool:
    history = _read_history(_history_path(project_path), limit=DEDUPE_SCAN_LIMIT)
    now_dt = _parse_iso(event_timestamp)
    if not now_dt:
        return False
    for item in reversed(history):
        if _to_text(item.get("event_fingerprint")) != fingerprint:
            continue
        prior_dt = _parse_iso(item.get("event_timestamp"))
        if not prior_dt:
            continue
        if abs((now_dt - prior_dt).total_seconds()) > max(0, int(dedupe_window_seconds)):
            continue
        return True
    return False


def _overall_delivery_status(channel_results: dict[str, dict[str, Any]], target_channels: list[str]) -> str:
    if not target_channels:
        return "no_channels"
    statuses = [_to_text((channel_results.get(ch) or {}).get("status")).lower() for ch in target_channels]
    sent_like = {"sent", "ok"}
    if any(s in sent_like for s in statuses) and all(s in sent_like.union({"skipped_unconfigured", "skipped_duplicate"}) for s in statuses):
        return "sent" if all(s in sent_like for s in statuses) else "partial"
    if all(s == "skipped_unconfigured" for s in statuses):
        return "unconfigured"
    if any(s == "failed" for s in statuses) and any(s in sent_like for s in statuses):
        return "partial"
    if any(s == "failed" for s in statuses):
        return "failed"
    if all(not s for s in statuses):
        return "unknown"
    return "partial"


def notify_operator(
    event_type: str,
    message: str,
    priority: str = "normal",
    payload: dict[str, Any] | None = None,
    *,
    event_title: str | None = None,
    event_source: str = "forge",
    project_path: str | None = None,
    channels_override: list[str] | None = None,
    dedupe_key: str | None = None,
    dedupe_window_seconds: int = 300,
) -> dict[str, Any]:
    """
    Main unified notification interface.
    """
    event = normalize_notification_event(
        event_type=event_type,
        message=message,
        priority=priority,
        payload=payload,
        event_title=event_title,
        event_source=event_source,
        dedupe_key=dedupe_key,
    )
    requested_channels = (
        [c for c in [(_to_text(x).lower()) for x in (channels_override or [])] if c]
        if isinstance(channels_override, list)
        else resolve_notification_channels(event["event_type"], event["event_priority"])
    )
    target_channels: list[str] = []
    for item in requested_channels:
        if item in {"telegram", "pushover"} and item not in target_channels:
            target_channels.append(item)

    duplicate = _is_duplicate_event(
        project_path=project_path,
        fingerprint=_to_text(event.get("event_fingerprint")),
        event_timestamp=_to_text(event.get("event_timestamp")),
        dedupe_window_seconds=dedupe_window_seconds,
    )
    if duplicate:
        event["event_channels_sent"] = []
        event["event_delivery_status"] = {
            "overall": "skipped_duplicate",
            "channels": {},
            "target_channels": target_channels,
        }
        _append_history(project_path, event)
        log_system_event(
            project="",
            subsystem="notification_router",
            action="notify_operator",
            status="ok",
            reason="Duplicate notification skipped.",
            metadata={"event_type": event.get("event_type"), "priority": event.get("event_priority")},
        )
        return event

    from NEXUS.notification_bridge import send_pushover_notification_safe, send_telegram_notification_safe

    channel_results: dict[str, dict[str, Any]] = {}
    sent_channels: list[str] = []
    for channel in target_channels:
        try:
            if channel == "telegram":
                result = send_telegram_notification_safe(event=event, project_path=project_path)
            elif channel == "pushover":
                result = send_pushover_notification_safe(event=event, project_path=project_path)
            else:
                result = {"channel": channel, "status": "skipped_unsupported", "reason": "Unsupported channel."}
        except Exception as exc:
            result = {"channel": channel, "status": "failed", "reason": f"Channel exception: {exc}"}
        channel_results[channel] = result
        status = _to_text(result.get("status")).lower()
        if status in {"sent", "ok"}:
            sent_channels.append(channel)

    overall = _overall_delivery_status(channel_results, target_channels)
    event["event_channels_sent"] = sent_channels
    event["event_delivery_status"] = {
        "overall": overall,
        "channels": channel_results,
        "target_channels": target_channels,
    }
    _append_history(project_path, event)
    log_system_event(
        project="",
        subsystem="notification_router",
        action="notify_operator",
        status="ok" if overall in {"sent", "partial", "unconfigured", "no_channels"} else "error",
        reason=f"Notification routed with overall={overall}.",
        metadata={
            "event_type": event.get("event_type"),
            "priority": event.get("event_priority"),
            "target_channels": target_channels,
            "sent_channels": sent_channels,
        },
    )
    return event


def notify_operator_safe(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return notify_operator(*args, **kwargs)
    except Exception as exc:
        return {
            "event_id": "",
            "event_type": _normalize_event_type(kwargs.get("event_type") if isinstance(kwargs, dict) else ""),
            "event_title": "Notification Failure",
            "event_message": "Notification routing failed.",
            "event_priority": _normalize_priority(kwargs.get("priority") if isinstance(kwargs, dict) else "normal"),
            "event_source": "notification_router",
            "event_timestamp": _now_iso(),
            "event_payload": {"error": str(exc)},
            "event_channels_sent": [],
            "event_delivery_status": {"overall": "error_fallback", "channels": {}},
        }


def get_recent_notifications(
    *,
    project_path: str | None = None,
    limit: int = 20,
    priorities: list[str] | None = None,
) -> list[dict[str, Any]]:
    path = _history_path(project_path)
    history = _read_history(path, limit=max(1, int(limit)) * 3)
    allowed_priorities = {_normalize_priority(p) for p in (priorities or []) if _to_text(p)}
    if allowed_priorities:
        history = [item for item in history if _normalize_priority(item.get("event_priority")) in allowed_priorities]
    return history[-max(1, int(limit)) :]


def get_recent_notifications_safe(**kwargs: Any) -> list[dict[str, Any]]:
    try:
        return get_recent_notifications(**kwargs)
    except Exception:
        return []


def get_notification_status_summary(*, project_path: str | None = None) -> dict[str, Any]:
    from NEXUS.notification_bridge import get_notification_channel_status_safe

    recent = get_recent_notifications_safe(project_path=project_path, limit=30)
    overall_counts: dict[str, int] = {}
    for item in recent:
        status = _to_text((item.get("event_delivery_status") or {}).get("overall")).lower() or "unknown"
        overall_counts[status] = int(overall_counts.get(status) or 0) + 1
    return {
        "channel_status": get_notification_channel_status_safe(),
        "recent_event_count": len(recent),
        "recent_delivery_breakdown": overall_counts,
    }


def get_notification_status_summary_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return get_notification_status_summary(**kwargs)
    except Exception:
        return {
            "channel_status": {"telegram_configured": False, "pushover_configured": False},
            "recent_event_count": 0,
            "recent_delivery_breakdown": {"error": 1},
        }
