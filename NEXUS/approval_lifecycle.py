"""
NEXUS approval lifecycle evaluation (Phase 39).

Explicit expiry metadata, lifecycle states, re-approval readiness.
Read-only; no auto-approval or auto-retry.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from NEXUS.approval_staleness import (
    APPROVAL_STALENESS_HOURS,
    get_staleness_hours,
    evaluate_approval_staleness,
    evaluate_proposal_approval_staleness,
    compute_expiry_metadata,
)

VALID_EXPIRY_STATUS = ("active", "stale", "expired", "unknown")
VALID_LIFECYCLE_STATUS = ("active", "stale", "expired", "reapproval_required", "retry_ready", "unknown")


def evaluate_approval_lifecycle(
    approval_record: dict[str, Any] | None,
    *,
    resolution_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Phase 39: Evaluate approval lifecycle from approval record or resolution.
    Returns lifecycle_status, reapproval_required, retry_after_expiry_ready,
    lifecycle_reason, lifecycle_next_step, expiry_metadata.
    """
    out: dict[str, Any] = {
        "approval_lifecycle_status": "unknown",
        "reapproval_required": False,
        "retry_after_expiry_ready": False,
        "lifecycle_reason": "",
        "lifecycle_next_step": "Unknown lifecycle state.",
        "expiry_status": "unknown",
        "expiry_timestamp": "",
        "stale_after_hours": 0.0,
        "hours_since_approval": 0.0,
    }
    rec = approval_record or resolution_record
    if not rec or not isinstance(rec, dict):
        return out

    if resolution_record:
        expiry_meta = compute_expiry_metadata(resolution_record, record_type="resolution")
        staleness_h = expiry_meta.get("stale_after_hours", APPROVAL_STALENESS_HOURS)
        is_stale, hours = evaluate_proposal_approval_staleness(resolution_record, staleness_hours=staleness_h)
    else:
        expiry_meta = compute_expiry_metadata(approval_record, record_type="approval")
        staleness_h = expiry_meta.get("stale_after_hours", APPROVAL_STALENESS_HOURS)
        is_stale, hours = evaluate_approval_staleness(approval_record, staleness_hours=staleness_h)

    out["expiry_status"] = expiry_meta.get("expiry_status", "unknown")
    out["expiry_timestamp"] = expiry_meta.get("expiry_timestamp", "")
    out["stale_after_hours"] = expiry_meta.get("stale_after_hours", APPROVAL_STALENESS_HOURS)
    out["hours_since_approval"] = hours

    if is_stale:
        out["approval_lifecycle_status"] = "stale"
        out["reapproval_required"] = True
        out["retry_after_expiry_ready"] = True
        out["lifecycle_reason"] = f"Approval stale; {hours:.1f}h since approval. Re-approval required."
        out["lifecycle_next_step"] = "Re-approve via approve_patch_proposal before apply."
    else:
        out["approval_lifecycle_status"] = "active"
        out["reapproval_required"] = False
        out["retry_after_expiry_ready"] = False
        out["lifecycle_reason"] = f"Approval active; {hours:.1f}h since approval."
        out["lifecycle_next_step"] = "Proceed to apply when ready."

    return out


def evaluate_resolution_lifecycle(
    resolution_record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Convenience: evaluate lifecycle for patch resolution record."""
    return evaluate_approval_lifecycle(None, resolution_record=resolution_record)


def get_reapproval_required_count(
    project_path: str | None = None,
    *,
    resolution_tail: list[dict[str, Any]] | None = None,
) -> int:
    """
    Count resolutions (approved_pending_apply) that are stale and require re-approval.
    Pass resolution_tail to avoid re-reading; else reads from project.
    """
    count = 0
    if resolution_tail is not None:
        for r in resolution_tail:
            if str(r.get("new_status") or "").strip().lower() != "approved_pending_apply":
                continue
            lc = evaluate_resolution_lifecycle(r)
            if lc.get("reapproval_required"):
                count += 1
        return count
    if not project_path:
        return 0
    try:
        from NEXUS.patch_proposal_registry import read_patch_proposal_resolution_tail
        tail = read_patch_proposal_resolution_tail(project_path=project_path, n=100)
        return get_reapproval_required_count(resolution_tail=tail)
    except Exception:
        return 0
