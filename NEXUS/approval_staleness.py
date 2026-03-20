"""
NEXUS approval staleness evaluation (Phase 25).

Derived staleness: timestamp-based, read-only.
No auto-delete; no mutation. Mark stale in summaries only.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

# Default: approval/resolution older than 24h is considered stale
APPROVAL_STALENESS_HOURS = 24.0


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
