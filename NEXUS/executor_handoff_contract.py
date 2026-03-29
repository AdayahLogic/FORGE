"""
Executor handoff truth contract builder.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_executor_handoff_contract(
    *,
    package: dict[str, Any] | None,
    backend_status: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = dict(package or {})
    backend = dict((backend_status or {}).get("backend") or backend_status or {})
    r = dict(receipt or {})
    v = dict(verification or {})

    package_id = _text(p.get("package_id"))
    mission_id = _text(p.get("mission_id") or p.get("project_name"))
    target_id = _text(p.get("handoff_executor_target_id") or p.get("execution_executor_target_id") or p.get("runtime_target_id")).lower()
    backend_id = _text(p.get("execution_executor_backend_id") or backend.get("backend_id") or target_id).lower()
    handoff_status = _text(p.get("handoff_status")).lower() or "pending"
    execution_status = _text(p.get("execution_status") or r.get("execution_status")).lower() or "pending"
    verification_status = _text(v.get("verification_status") or p.get("verification_status")).lower() or "pending"
    receipt_id = _text(r.get("receipt_id") or p.get("execution_receipt_id"))
    verification_id = _text(v.get("verification_id") or p.get("verification_id"))

    accepted_handoff = handoff_status in {"authorized", "accepted"}
    executed = execution_status in {"succeeded", "failed", "blocked", "rolled_back"}
    return {
        "contract_version": "v1",
        "mission_created_package": bool(mission_id and package_id),
        "mission_id": mission_id,
        "execution_package_id": package_id,
        "targeted_backend_id": backend_id,
        "targeted_executor_target_id": target_id,
        "backend_acceptance_status": handoff_status,
        "backend_accepted_handoff": accepted_handoff,
        "backend_execution_status": execution_status,
        "backend_executed": executed,
        "execution_receipt_exists": bool(receipt_id),
        "execution_receipt_id": receipt_id,
        "verification_exists": bool(verification_id),
        "verification_id": verification_id,
        "verification_status": verification_status,
        "contract_status": (
            "executed_with_verification"
            if executed and verification_status in {"verified", "unverified", "failed"}
            else "executed_pending_verification"
            if executed
            else "handoff_accepted_not_executed"
            if accepted_handoff
            else "handoff_pending_or_blocked"
        ),
        "recorded_at": _now_iso(),
    }

