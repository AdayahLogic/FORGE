"""
HELIX outcome ingestion inputs from canonical records.
"""

from __future__ import annotations

from typing import Any

from NEXUS.communication_receipt_registry import read_communication_receipt_journal_tail
from NEXUS.outcome_verifier_registry import read_outcome_verification_journal_tail
from NEXUS.revenue_followup_scheduler import (
    build_follow_up_status_summary,
    build_stalled_deals_summary,
)


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _classification_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"success": 0, "partial": 0, "failure": 0}
    for row in rows:
        key = _status((row or {}).get("success_classification"))
        if key in counts:
            counts[key] += 1
    return counts


def build_helix_outcome_inputs(
    *,
    project_path: str | None,
    n: int = 200,
) -> dict[str, Any]:
    outcomes = read_outcome_verification_journal_tail(project_path=project_path, n=n)
    comms = read_communication_receipt_journal_tail(project_path=project_path, n=n)
    follow_up = build_follow_up_status_summary(project_path=project_path, n=n)
    stalled = build_stalled_deals_summary(project_path=project_path, n=n)
    classification = _classification_counts(outcomes)
    verified_outcomes = [r for r in outcomes if _status((r or {}).get("verification_status")) == "verified"]
    failed_sends = [r for r in comms if _status((r or {}).get("send_status")) in {"send_failed", "send_blocked"}]
    response_received = [r for r in comms if _status((r or {}).get("send_status")) == "response_received"]
    avg_delta = 0.0
    if outcomes:
        avg_delta = round(sum(float((r or {}).get("performance_delta") or 0.0) for r in outcomes) / float(len(outcomes)), 4)
    return {
        "helix_outcome_inputs_status": "ok",
        "verified_outcome_count": len(verified_outcomes),
        "outcome_classification_counts": classification,
        "avg_performance_delta": avg_delta,
        "stalled_deal_count": int(stalled.get("stalled_deals_count") or 0),
        "stale_follow_up_count": int(follow_up.get("stale_follow_up_count") or 0),
        "follow_up_effectiveness": {
            "response_received_count": len(response_received),
            "failed_or_blocked_send_count": len(failed_sends),
            "follow_up_count": int(follow_up.get("follow_up_count") or 0),
        },
        "delivery_success_signals": {
            "success_count": int(classification.get("success") or 0),
            "failure_count": int(classification.get("failure") or 0),
        },
        "recent_outcome_refs": [str((r or {}).get("outcome_verification_id") or "") for r in outcomes[-20:]],
    }

