"""
Delivery readiness and verification backbone.

Provides additive delivery truth contracts without changing execution behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _artifact_refs(package: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    runtime_artifacts = [dict(x) for x in list(package.get("runtime_artifacts") or []) if isinstance(x, dict)]
    for artifact in runtime_artifacts[:50]:
        refs.append(
            {
                "artifact_type": _text(artifact.get("artifact_type")) or "runtime_artifact",
                "artifact_ref": _text(artifact.get("artifact_ref") or artifact.get("log_ref") or artifact.get("path")),
                "source": "runtime_artifacts",
            }
        )
    email_message_id = _text(package.get("email_message_id"))
    if email_message_id:
        refs.append({"artifact_type": "delivery_email_message", "artifact_ref": email_message_id, "source": "revenue_delivery"})
    execution_receipt = dict(package.get("execution_receipt") or {})
    log_ref = _text(execution_receipt.get("log_ref"))
    if log_ref:
        refs.append({"artifact_type": "execution_log", "artifact_ref": log_ref, "source": "execution_receipt"})
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        key = f"{ref.get('artifact_type')}::{ref.get('artifact_ref')}::{ref.get('source')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique[:50]


def build_delivery_backbone_contract(
    *,
    package: dict[str, Any] | None,
    receipt: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = dict(package or {})
    r = dict(receipt or {})
    v = dict(verification or {})

    delivery_status = _text(p.get("delivery_status")).lower() or "pending"
    post_delivery_status = _text(p.get("post_delivery_status")).lower() or "pending"
    delivery_requires_approval = bool(p.get("delivery_requires_approval", True))
    verification_status = _text(v.get("verification_status") or p.get("verification_status")).lower() or "pending"
    execution_status = _text(r.get("execution_status") or p.get("execution_status")).lower()
    refs = _artifact_refs(p)
    evidence_present = bool(refs)
    delivery_verification_status = "pending"
    if verification_status in {"verified", "unverified", "failed"}:
        delivery_verification_status = verification_status
    elif evidence_present:
        delivery_verification_status = "evidence_present_unverified"

    if not _text(p.get("project_id")):
        readiness_state = "not_ready"
    elif delivery_status in {"failed"}:
        readiness_state = "failed"
    elif delivery_status in {"ready"} and delivery_requires_approval:
        readiness_state = "ready_for_delivery_approval"
    elif delivery_status in {"ready"}:
        readiness_state = "ready_for_handoff"
    elif delivery_status in {"delivered"}:
        readiness_state = "delivered_evidence_pending" if not evidence_present else "delivered_evidence_recorded"
    elif execution_status in {"succeeded", "completed"} and evidence_present:
        readiness_state = "ready_for_internal_review"
    else:
        readiness_state = "in_progress"

    delivery_completed_truth = bool(delivery_status == "delivered" and evidence_present)
    post_delivery_handoff_ready = bool(
        delivery_completed_truth
        and post_delivery_status in {"active", "completed"}
    )

    return {
        "delivery_readiness_state": readiness_state,
        "delivery_artifact_refs": refs,
        "delivery_evidence_present": evidence_present,
        "delivery_verification_status": delivery_verification_status,
        "delivery_approval_required_status": "required" if delivery_requires_approval else "not_required",
        "delivery_completed_truth": delivery_completed_truth,
        "post_delivery_handoff_ready": post_delivery_handoff_ready,
        "delivery_evidence_summary": (
            "Delivery evidence captured."
            if evidence_present
            else "No delivery evidence captured yet."
        ),
        "delivery_backbone_recorded_at": _now_iso(),
    }

