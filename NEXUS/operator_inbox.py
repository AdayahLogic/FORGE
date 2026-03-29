"""
Operator inbox prioritization.

Builds a focused operator queue from review, approval, verification, and
execution truth signals.
"""

from __future__ import annotations

from typing import Any

from NEXUS.approval_triage import build_approval_triage_summary_safe
from NEXUS.execution_truth import build_execution_truth_snapshot
from NEXUS.execution_receipt_registry import read_execution_receipt_journal_tail
from NEXUS.execution_verification_registry import read_execution_verification_journal_tail


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status(value: Any) -> str:
    return _text(value).lower()


def build_operator_inbox(
    *,
    project_name: str | None,
    project_path: str | None,
    project_state: dict[str, Any] | None,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = dict(project_state or {})
    pkg = dict(package or {})
    triage = build_approval_triage_summary_safe(project_path=project_path, n=200)
    receipts = read_execution_receipt_journal_tail(project_path=project_path, n=30)
    verifications = read_execution_verification_journal_tail(project_path=project_path, n=30)
    latest_receipt = receipts[-1] if receipts else {}
    latest_verification = verifications[-1] if verifications else {}
    truth = build_execution_truth_snapshot(
        project_state=state,
        package=pkg,
        receipt=latest_receipt,
        verification=latest_verification,
    )

    items: list[dict[str, Any]] = []
    review_queue = dict(state.get("review_queue_entry") or {})
    queue_status = _status(review_queue.get("queue_status"))
    queue_type = _status(review_queue.get("queue_type"))
    if queue_status == "queued":
        score = 95 if queue_type in {"blocked", "approval"} else 70
        items.append(
            {
                "inbox_item_type": "review_queue",
                "priority_score": score,
                "priority": "high" if score >= 90 else "medium",
                "title": f"Review queue: {queue_type or 'pending'}",
                "reason": _text(review_queue.get("queue_reason") or "Queued for operator review."),
                "batchable": False,
            }
        )

    for approval in list((triage.get("ranked_approvals") or []))[:20]:
        priority = _status(approval.get("triage_priority"))
        items.append(
            {
                "inbox_item_type": "approval",
                "priority_score": int(approval.get("triage_operator_focus_score") or 0),
                "priority": priority or "low",
                "title": f"Approval {_text(approval.get('approval_id'))}",
                "reason": _text(approval.get("reason") or "Approval pending."),
                "batchable": bool(approval.get("triage_batchable")),
                "batch_key": _text(approval.get("triage_batch_key")),
                "approval_id": _text(approval.get("approval_id")),
            }
        )

    for batch in list((triage.get("batch_groups") or []))[:10]:
        items.append(
            {
                "inbox_item_type": "approval_batch",
                "priority_score": 80 if _status(batch.get("priority")) == "high" else 60,
                "priority": _status(batch.get("priority")) or "medium",
                "title": f"Batchable approvals ({int(batch.get('approval_count') or 0)})",
                "reason": f"Batch key: {_text(batch.get('batch_key'))}",
                "batchable": True,
                "batch_key": _text(batch.get("batch_key")),
                "approval_ids": list(batch.get("approval_ids") or [])[:30],
            }
        )

    if _status(truth.get("execution_truth_status")) in {"blocked", "failed", "rolled_back"}:
        items.append(
            {
                "inbox_item_type": "execution_escalation",
                "priority_score": 100,
                "priority": "high",
                "title": "Execution requires escalation",
                "reason": f"Truth status={_text(truth.get('execution_truth_status'))}.",
                "batchable": False,
            }
        )
    elif _status(truth.get("execution_truth_status")) == "executed_unverified":
        items.append(
            {
                "inbox_item_type": "verification_pending",
                "priority_score": 85,
                "priority": "high",
                "title": "Execution verification pending",
                "reason": _text(latest_verification.get("verification_summary") or "Execution completed but verification is pending."),
                "batchable": False,
                "receipt_id": _text(latest_receipt.get("receipt_id")),
            }
        )

    # Mission stop-condition escalation signal.
    stop_reason = _text(state.get("autopilot_stop_reason") or state.get("autopilot_escalation_reason"))
    if stop_reason:
        items.append(
            {
                "inbox_item_type": "mission_stop_condition",
                "priority_score": 88,
                "priority": "high",
                "title": "Mission stop-condition escalation",
                "reason": stop_reason,
                "batchable": False,
            }
        )

    items.sort(key=lambda row: int(row.get("priority_score") or 0), reverse=True)
    return {
        "operator_inbox_status": "ok",
        "project_name": project_name or state.get("active_project") or "",
        "execution_truth_status": truth.get("execution_truth_status"),
        "verification_status": truth.get("verification_status"),
        "inbox_count": len(items),
        "inbox_items": items[:50],
        "triage_summary": {
            "pending_count": triage.get("pending_count", 0),
            "high_priority_count": triage.get("high_priority_count", 0),
            "stale_pending_count": triage.get("stale_pending_count", 0),
            "risky_external_count": triage.get("risky_external_count", 0),
        },
    }


def build_operator_inbox_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_operator_inbox(**kwargs)
    except Exception as exc:
        return {
            "operator_inbox_status": "error_fallback",
            "project_name": _text(kwargs.get("project_name")),
            "execution_truth_status": "simulated",
            "verification_status": "pending",
            "inbox_count": 0,
            "inbox_items": [],
            "triage_summary": {},
            "reason": f"Operator inbox build failed: {exc}",
        }
