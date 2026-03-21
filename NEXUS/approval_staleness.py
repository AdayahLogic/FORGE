"""
NEXUS approval staleness evaluation (Phase 25).

Derived staleness: timestamp-based, read-only.
No auto-delete; no mutation. Mark stale in summaries only.
Phase 39: configurable staleness by type; explicit expiry metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

# Default: approval/resolution older than 24h is considered stale
APPROVAL_STALENESS_HOURS = 24.0

# Phase 39: optional per-approval-type staleness (hours). Empty = use default.
APPROVAL_STALENESS_BY_TYPE: dict[str, float] = {
    "patch_proposal_resolution": 24.0,
}


def get_staleness_hours(approval_type: str | None = None) -> float:
    """Phase 39: Return staleness hours for approval type, or default."""
    if approval_type and str(approval_type).strip():
        key = str(approval_type).strip()
        if key in APPROVAL_STALENESS_BY_TYPE:
            return APPROVAL_STALENESS_BY_TYPE[key]
    return APPROVAL_STALENESS_HOURS


def compute_expiry_metadata(
    record: dict[str, Any] | None,
    *,
    record_type: str = "approval",
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Phase 39: Compute explicit expiry metadata from approval or resolution record.
    Returns expiry_timestamp, expiry_status, stale_after_hours, requires_reapproval.
    For old records without persisted expiry, derives from timestamp.
    """
    out: dict[str, Any] = {
        "expiry_timestamp": "",
        "expiry_status": "unknown",
        "stale_after_hours": APPROVAL_STALENESS_HOURS,
        "requires_reapproval": False,
        "approval_type": "",
        "approval_policy_source": "derived",
    }
    if not record or not isinstance(record, dict):
        return out

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    ts = record.get("expiry_timestamp") or record.get("decision_timestamp") or record.get("timestamp")
    dt = _parse_iso(ts)
    approval_type = str(record.get("approval_type") or "unknown").strip()
    stale_hours = get_staleness_hours(approval_type)
    out["stale_after_hours"] = stale_hours
    out["approval_type"] = approval_type

    if record_type == "resolution":
        if str(record.get("new_status") or "").strip().lower() != "approved_pending_apply":
            out["expiry_status"] = "unknown"
            return out
        ts = record.get("timestamp")
        dt = _parse_iso(ts)
        approval_type = "patch_proposal_resolution"
        stale_hours = get_staleness_hours(approval_type)
        out["stale_after_hours"] = stale_hours

    if not dt:
        return out
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    expiry_dt = dt + timedelta(hours=stale_hours)
    out["expiry_timestamp"] = expiry_dt.isoformat()
    delta = now - dt
    hours = delta.total_seconds() / 3600.0

    if hours > stale_hours:
        out["expiry_status"] = "stale"
        out["requires_reapproval"] = True
    else:
        out["expiry_status"] = "active"
        out["requires_reapproval"] = False

    return out


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse ISO timestamp; return None if invalid."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        s = ts.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def evaluate_approval_staleness(
    approval_record: dict[str, Any],
    *,
    now: datetime | None = None,
    staleness_hours: float = APPROVAL_STALENESS_HOURS,
) -> tuple[bool, float]:
    """
    Return (is_stale, hours_since_relevant).
    Relevant timestamp: decision_timestamp if approved/rejected, else timestamp.
    """
    if not approval_record or not isinstance(approval_record, dict):
        return False, 0.0
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    status = str(approval_record.get("status") or "").strip().lower()
    ts = approval_record.get("decision_timestamp") or approval_record.get("timestamp")
    dt = _parse_iso(ts)
    if not dt:
        return False, 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600.0
    is_stale = hours > staleness_hours
    return is_stale, hours


def evaluate_proposal_approval_staleness(
    resolution_record: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    staleness_hours: float = APPROVAL_STALENESS_HOURS,
) -> tuple[bool, float]:
    """
    For patch proposal: use resolution timestamp (when approved).
    Return (is_stale, hours_since_approval).
    """
    if not resolution_record or not isinstance(resolution_record, dict):
        return False, 0.0
    new_status = str(resolution_record.get("new_status") or "").strip().lower()
    if new_status != "approved_pending_apply":
        return False, 0.0
    ts = resolution_record.get("timestamp")
    dt = _parse_iso(ts)
    if not dt:
        return False, 0.0
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600.0
    is_stale = hours > staleness_hours
    return is_stale, hours


def is_proposal_approval_stale(
    project_path: str | None,
    patch_id: str,
    *,
    staleness_hours: float = APPROVAL_STALENESS_HOURS,
) -> tuple[bool, float, dict[str, Any] | None]:
    """
    Return (is_stale, hours_since_approval, resolution_record).
    Only meaningful when effective_status is approved_pending_apply.
    """
    try:
        from NEXUS.patch_proposal_registry import get_proposal_effective_status, get_latest_resolution_for_patch
        effective_status, resolution = get_proposal_effective_status(project_path=project_path, patch_id=patch_id)
        if effective_status != "approved_pending_apply":
            return False, 0.0, resolution
        is_stale, hours = evaluate_proposal_approval_staleness(resolution, staleness_hours=staleness_hours)
        return is_stale, hours, resolution
    except Exception:
        return False, 0.0, None
