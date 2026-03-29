"""
Revenue follow-up scheduler and stall detection.

Read/derive layer used by command surface and operator views.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from NEXUS.execution_package_registry import list_execution_package_journal_entries


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status(value: Any) -> str:
    return _text(value).lower()


def _followup_reason(package: dict[str, Any], *, stale_hours: float) -> str:
    if stale_hours >= 72:
        return "Follow-up overdue >72h; re-engagement needed."
    if stale_hours >= 24:
        return "Follow-up overdue >24h."
    if _status(package.get("post_delivery_status")) in {"active", "pending"} and _status(package.get("delivery_status")) == "delivered":
        return "Post-delivery retention follow-up opportunity."
    if bool(package.get("upsell_opportunity_detected")):
        return "Upsell opportunity follow-up."
    return _text(package.get("approval_queue_reason") or package.get("highest_value_next_action_reason") or "Follow-up required.")


def _compute_followup_record(package: dict[str, Any], *, now_dt: datetime) -> dict[str, Any]:
    package_id = _text(package.get("package_id"))
    followup_required = bool(package.get("follow_up_required"))
    followup_status = _status(package.get("follow_up_status") or "not_required")
    next_dt = _parse_dt(package.get("follow_up_next_at"))
    if not next_dt:
        next_dt = _parse_dt(package.get("conversation_last_updated_at")) or _parse_dt(package.get("created_at"))
    stale_hours = 0.0
    if next_dt:
        stale_hours = max(0.0, round((now_dt - next_dt).total_seconds() / 3600.0, 2))
    stale = bool(next_dt and now_dt > next_dt and followup_status in {"pending", "scheduled", "awaiting_approval"})
    retry_count = max(0, int(package.get("follow_up_attempt_count") or 0))
    retry_limit = 3
    blocked = followup_status in {"escalated", "closed"}
    awaiting_approval = bool(package.get("email_requires_approval")) or followup_status == "awaiting_approval"
    ready = followup_required and not blocked and not awaiting_approval
    reengagement = stale or bool(package.get("upsell_opportunity_detected")) or (
        _status(package.get("delivery_status")) == "delivered" and _status(package.get("post_delivery_status")) in {"active", "pending"}
    )
    priority = _status(package.get("follow_up_priority") or "medium")
    if stale_hours >= 72 or bool(package.get("mission_stop_condition_hit")):
        priority = "high"
    elif stale_hours >= 24 and priority == "low":
        priority = "medium"
    return {
        "execution_package_id": package_id,
        "lead_id": _text(package.get("lead_id")),
        "deal_status": _status(package.get("deal_status") or "open"),
        "pipeline_stage": _status(package.get("pipeline_stage") or "intake"),
        "follow_up_required": followup_required,
        "follow_up_status": followup_status,
        "follow_up_next_at": next_dt.isoformat().replace("+00:00", "Z") if next_dt else "",
        "stale_follow_up": stale,
        "stale_hours": stale_hours,
        "retry_count": retry_count,
        "retry_limit": retry_limit,
        "follow_up_priority": priority or "medium",
        "follow_up_reason": _followup_reason(package, stale_hours=stale_hours),
        "blocked": blocked,
        "awaiting_approval": awaiting_approval,
        "ready": ready,
        "reengagement_opportunity": reengagement,
    }


def build_follow_up_status_summary(
    *,
    project_path: str | None,
    n: int = 200,
) -> dict[str, Any]:
    rows = list_execution_package_journal_entries(project_path=project_path, n=max(1, min(int(n or 200), 500)))
    now_dt = _now_utc()
    records = [_compute_followup_record(dict(row or {}), now_dt=now_dt) for row in rows if isinstance(row, dict)]
    records = [r for r in records if r.get("follow_up_required") or r.get("reengagement_opportunity")]
    records.sort(
        key=lambda r: (
            0 if bool(r.get("stale_follow_up")) else 1,
            0 if _status(r.get("follow_up_priority")) == "high" else 1 if _status(r.get("follow_up_priority")) == "medium" else 2,
            -float(r.get("stale_hours") or 0.0),
        )
    )
    return {
        "follow_up_status": "ok",
        "follow_up_count": len(records),
        "stale_follow_up_count": sum(1 for r in records if bool(r.get("stale_follow_up"))),
        "awaiting_approval_count": sum(1 for r in records if bool(r.get("awaiting_approval"))),
        "reengagement_count": sum(1 for r in records if bool(r.get("reengagement_opportunity"))),
        "follow_ups": records[:100],
    }


def build_stalled_deals_summary(
    *,
    project_path: str | None,
    n: int = 200,
    stall_hours: int = 72,
) -> dict[str, Any]:
    rows = list_execution_package_journal_entries(project_path=project_path, n=max(1, min(int(n or 200), 500)))
    now_dt = _now_utc()
    stalled: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        deal_status = _status(row.get("deal_status") or "open")
        if deal_status not in {"open", "negotiating"}:
            continue
        last_touch = _parse_dt(row.get("conversation_last_updated_at")) or _parse_dt(row.get("follow_up_next_at")) or _parse_dt(row.get("created_at"))
        if not last_touch:
            continue
        age_hours = max(0.0, round((now_dt - last_touch).total_seconds() / 3600.0, 2))
        if age_hours < float(stall_hours):
            continue
        stalled.append(
            {
                "execution_package_id": _text(row.get("package_id")),
                "lead_id": _text(row.get("lead_id")),
                "deal_status": deal_status,
                "pipeline_stage": _status(row.get("pipeline_stage") or "intake"),
                "last_touch_at": last_touch.isoformat().replace("+00:00", "Z"),
                "stalled_hours": age_hours,
                "missing_response": _status(row.get("email_status")) in {"approval_required", "queued_for_approval", "received", ""},
                "overdue_follow_up": bool(_status(row.get("follow_up_status")) in {"pending", "scheduled", "awaiting_approval"}),
                "post_delivery_retention_opportunity": bool(
                    _status(row.get("delivery_status")) == "delivered"
                    and _status(row.get("post_delivery_status")) in {"active", "pending"}
                ),
                "upsell_opportunity": bool(row.get("upsell_opportunity_detected")),
            }
        )
    stalled.sort(key=lambda item: float(item.get("stalled_hours") or 0.0), reverse=True)
    return {
        "stalled_deals_status": "ok",
        "stalled_deals_count": len(stalled),
        "stalled_deals": stalled[:100],
    }


def build_reengagement_queue_summary(
    *,
    project_path: str | None,
    n: int = 200,
) -> dict[str, Any]:
    followups = build_follow_up_status_summary(project_path=project_path, n=n)
    stalled = build_stalled_deals_summary(project_path=project_path, n=n)
    queue: list[dict[str, Any]] = []
    for row in list(followups.get("follow_ups") or []):
        if not bool(row.get("reengagement_opportunity")):
            continue
        queue.append(
            {
                "execution_package_id": row.get("execution_package_id"),
                "lead_id": row.get("lead_id"),
                "priority": row.get("follow_up_priority"),
                "reason": row.get("follow_up_reason"),
                "stale_hours": row.get("stale_hours"),
                "queue_type": "follow_up_reengagement",
            }
        )
    for row in list(stalled.get("stalled_deals") or []):
        queue.append(
            {
                "execution_package_id": row.get("execution_package_id"),
                "lead_id": row.get("lead_id"),
                "priority": "high" if float(row.get("stalled_hours") or 0.0) >= 120 else "medium",
                "reason": "Stalled deal requires re-engagement planning.",
                "stale_hours": row.get("stalled_hours"),
                "queue_type": "stalled_deal_reengagement",
            }
        )
    queue.sort(key=lambda item: (0 if _status(item.get("priority")) == "high" else 1, -float(item.get("stale_hours") or 0.0)))
    return {
        "reengagement_queue_status": "ok",
        "reengagement_count": len(queue),
        "reengagement_queue": queue[:150],
    }

