"""
Approval triage and batching model.

This layer prioritizes operator attention without bypassing approval controls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from NEXUS.approval_registry import read_approval_journal_tail


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status(value: Any) -> str:
    return _text(value).lower()


def _hours_since(timestamp: Any) -> float:
    raw = _text(timestamp)
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        return max(0.0, round(delta.total_seconds() / 3600.0, 2))
    except Exception:
        return 0.0


def _risk_group(record: dict[str, Any]) -> str:
    approval_type = _status(record.get("approval_type"))
    risk_level = _status(record.get("risk_level"))
    sensitivity = _status(record.get("sensitivity"))
    if approval_type in {"aegis_policy", "billing", "outreach", "communication", "external_action"}:
        return "risky_external"
    if risk_level in {"high", "critical"} or sensitivity in {"high", "critical"}:
        return "risky_external"
    if approval_type in {"dispatch_plan", "execution_gate", "tool_sensitivity"}:
        return "internal_controlled"
    return "internal_low_risk"


def _triage_priority(record: dict[str, Any]) -> str:
    risk_group = _risk_group(record)
    stale_hours = _hours_since(record.get("timestamp"))
    if risk_group == "risky_external":
        return "high"
    if stale_hours >= 24.0:
        return "high"
    if risk_group == "internal_controlled":
        return "medium"
    return "low"


def _batch_key(record: dict[str, Any]) -> str:
    context = record.get("context") if isinstance(record.get("context"), dict) else {}
    runtime_target_id = _text(context.get("runtime_target_id") or "unknown").lower()
    approval_type = _status(record.get("approval_type") or "unknown")
    risk_group = _risk_group(record)
    return f"{risk_group}:{approval_type}:{runtime_target_id}"


def enrich_approval_for_triage(record: dict[str, Any] | None) -> dict[str, Any]:
    r = dict(record or {})
    stale_hours = _hours_since(r.get("timestamp"))
    risk_group = _risk_group(r)
    priority = _triage_priority(r)
    batchable = risk_group == "internal_low_risk" and priority in {"low", "medium"}
    return {
        **r,
        "triage_category": risk_group,
        "triage_priority": priority,
        "triage_stale_hours": stale_hours,
        "triage_batchable": batchable,
        "triage_batch_key": _batch_key(r) if batchable else "",
        "triage_operator_focus_score": (
            100
            if priority == "high"
            else 70
            if priority == "medium"
            else 40
        )
        + min(40, int(stale_hours)),
    }


def build_approval_triage_summary(
    *,
    project_path: str | None,
    n: int = 200,
) -> dict[str, Any]:
    records = read_approval_journal_tail(project_path=project_path, n=max(10, min(int(n or 200), 500)))
    pending = [r for r in records if _status(r.get("status")) == "pending"]
    enriched = [enrich_approval_for_triage(r) for r in pending]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in enriched:
        key = _text(item.get("triage_batch_key"))
        if not key:
            continue
        grouped.setdefault(key, []).append(item)

    batch_groups = []
    for key, items in grouped.items():
        if len(items) < 2:
            continue
        batch_groups.append(
            {
                "batch_key": key,
                "approval_count": len(items),
                "priority": max((_text(i.get("triage_priority")) for i in items), default="low"),
                "approval_ids": [_text(i.get("approval_id")) for i in items if _text(i.get("approval_id"))][:30],
            }
        )

    enriched.sort(key=lambda item: float(item.get("triage_operator_focus_score") or 0.0), reverse=True)
    high = [row for row in enriched if _text(row.get("triage_priority")) == "high"]
    stale = [row for row in enriched if float(row.get("triage_stale_hours") or 0.0) >= 24.0]
    risky = [row for row in enriched if _text(row.get("triage_category")) == "risky_external"]

    return {
        "triage_status": "ok",
        "pending_count": len(enriched),
        "high_priority_count": len(high),
        "stale_pending_count": len(stale),
        "risky_external_count": len(risky),
        "batch_groups": sorted(batch_groups, key=lambda row: row.get("approval_count", 0), reverse=True)[:20],
        "ranked_approvals": enriched[:100],
    }


def build_approval_triage_summary_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_approval_triage_summary(**kwargs)
    except Exception as exc:
        return {
            "triage_status": "error_fallback",
            "pending_count": 0,
            "high_priority_count": 0,
            "stale_pending_count": 0,
            "risky_external_count": 0,
            "batch_groups": [],
            "ranked_approvals": [],
            "reason": f"Approval triage failed: {exc}",
        }
