"""
Durable outcome verifier and performance summary.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTCOME_VERIFICATION_JOURNAL_FILENAME = "outcome_verification_journal.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status(value: Any) -> str:
    return _text(value).lower()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        path = Path(project_path).resolve() / "state"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def get_outcome_verification_journal_path(project_path: str | None) -> str | None:
    state = _state_dir(project_path)
    if not state:
        return None
    return str(state / OUTCOME_VERIFICATION_JOURNAL_FILENAME)


def normalize_outcome_verification_record(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record if isinstance(record, dict) else {}
    evidence = [dict(item) for item in list(r.get("evidence_source") or []) if isinstance(item, dict)]
    confidence = float(r.get("confidence") or 0.0)
    confidence = max(0.0, min(confidence, 1.0))
    expected_revenue = float(r.get("expected_revenue") or 0.0)
    actual_revenue = float(r.get("actual_revenue") or 0.0)
    expected_conversion = float(r.get("expected_conversion") or 0.0)
    actual_conversion = float(r.get("actual_conversion") or 0.0)
    revenue_delta = round(actual_revenue - expected_revenue, 4)
    conversion_delta = round(actual_conversion - expected_conversion, 4)
    performance_delta = round(float(r.get("performance_delta") or (revenue_delta + conversion_delta)), 4)
    classification = _status(r.get("success_classification") or "partial")
    if classification not in {"success", "partial", "failure"}:
        classification = "partial"
    return {
        "outcome_verification_id": _text(r.get("outcome_verification_id") or f"outcome-{uuid.uuid4().hex[:16]}"),
        "project_name": _text(r.get("project_name")),
        "run_id": _text(r.get("run_id")),
        "mission_id": _text(r.get("mission_id")),
        "execution_package_id": _text(r.get("execution_package_id")),
        "deal_id": _text(r.get("deal_id")),
        "expected_outcome": _text(r.get("expected_outcome")),
        "actual_outcome": _text(r.get("actual_outcome")),
        "expected_revenue": expected_revenue,
        "actual_revenue": actual_revenue,
        "expected_conversion": expected_conversion,
        "actual_conversion": actual_conversion,
        "revenue_delta": revenue_delta,
        "conversion_delta": conversion_delta,
        "performance_delta": performance_delta,
        "success_classification": classification,
        "evidence_source": evidence[:30],
        "confidence": round(confidence, 4),
        "operator_confirmed": bool(r.get("operator_confirmed")),
        "system_inferred": bool(r.get("system_inferred", True)),
        "verification_status": _status(r.get("verification_status") or "pending"),
        "verification_reason": _text(r.get("verification_reason")),
        "recorded_at": _text(r.get("recorded_at") or _now_iso()),
    }


def build_outcome_verification_from_package(
    *,
    package: dict[str, Any] | None,
    operator_confirmed: bool = False,
) -> dict[str, Any]:
    p = dict(package or {})
    expected_outcome = _text(p.get("expected_outcome"))
    actual_outcome = _text(p.get("actual_outcome"))
    expected_revenue = float(p.get("expected_revenue") or 0.0)
    actual_revenue = float(p.get("actual_revenue") or 0.0)
    expected_conversion = float(p.get("expected_conversion") or 0.0)
    actual_conversion = float(p.get("actual_conversion") or 0.0)
    outcome_status = _status(p.get("outcome_status") or "pending")
    classification = "partial"
    if outcome_status in {"success"}:
        classification = "success"
    elif outcome_status in {"failure"}:
        classification = "failure"
    verification_status = "pending"
    reason = "Outcome verification pending evidence."
    evidence: list[dict[str, Any]] = []
    if _text(p.get("email_message_id")):
        evidence.append({"evidence_type": "communication_receipt", "receipt_ref": _text(p.get("email_message_id"))})
    if _text(p.get("execution_receipt_id")):
        evidence.append({"evidence_type": "execution_receipt", "receipt_ref": _text(p.get("execution_receipt_id"))})
    if _text(p.get("verification_id")):
        evidence.append({"evidence_type": "execution_verification", "receipt_ref": _text(p.get("verification_id"))})
    if actual_outcome or abs(actual_revenue) > 0 or abs(actual_conversion) > 0:
        verification_status = "verified" if (operator_confirmed or len(evidence) > 0) else "unverified"
        reason = "Outcome verified with evidence." if verification_status == "verified" else "Outcome inferred without sufficient evidence."
    confidence = 0.25
    if len(evidence) > 0:
        confidence += 0.35
    if operator_confirmed:
        confidence += 0.35
    if classification == "success":
        confidence += 0.05
    confidence = max(0.0, min(confidence, 1.0))
    return normalize_outcome_verification_record(
        {
            "project_name": p.get("project_name"),
            "run_id": p.get("run_id"),
            "mission_id": p.get("mission_id"),
            "execution_package_id": p.get("package_id"),
            "deal_id": p.get("lead_id"),
            "expected_outcome": expected_outcome,
            "actual_outcome": actual_outcome,
            "expected_revenue": expected_revenue,
            "actual_revenue": actual_revenue,
            "expected_conversion": expected_conversion,
            "actual_conversion": actual_conversion,
            "success_classification": classification,
            "evidence_source": evidence,
            "confidence": confidence,
            "operator_confirmed": operator_confirmed,
            "system_inferred": not operator_confirmed,
            "verification_status": verification_status,
            "verification_reason": reason,
        }
    )


def append_outcome_verification(
    *,
    project_path: str | None,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    journal_path = get_outcome_verification_journal_path(project_path)
    if not journal_path:
        return {"status": "degraded", "reason": "Outcome verification journal unavailable.", "outcome": None}
    normalized = normalize_outcome_verification_record(record)
    try:
        with open(journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Outcome verification appended.", "outcome": normalized}
    except Exception as exc:
        return {"status": "degraded", "reason": f"Failed to append outcome verification: {exc}", "outcome": normalized}


def append_outcome_verification_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return append_outcome_verification(**kwargs)
    except Exception as exc:
        return {"status": "degraded", "reason": f"Outcome verification write failed: {exc}", "outcome": None}


def read_outcome_verification_journal_tail(
    *,
    project_path: str | None,
    n: int = 100,
) -> list[dict[str, Any]]:
    journal_path = get_outcome_verification_journal_path(project_path)
    if not journal_path:
        return []
    file_path = Path(journal_path)
    if not file_path.exists():
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    limit = max(1, min(int(n or 100), 1000))
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(normalize_outcome_verification_record(parsed))
    return out


def get_latest_outcome_verification(
    *,
    project_path: str | None,
    execution_package_id: str | None = None,
) -> dict[str, Any] | None:
    package_id = _text(execution_package_id)
    rows = read_outcome_verification_journal_tail(project_path=project_path, n=500)
    for row in reversed(rows):
        if package_id and _text(row.get("execution_package_id")) != package_id:
            continue
        return row
    return None


def build_performance_summary(*, project_path: str | None, n: int = 200) -> dict[str, Any]:
    rows = read_outcome_verification_journal_tail(project_path=project_path, n=n)
    if not rows:
        return {
            "performance_summary_status": "ok",
            "count": 0,
            "high_performing_count": 0,
            "failing_count": 0,
            "adjustments_required_count": 0,
            "avg_performance_delta": 0.0,
            "recommendations": [],
        }
    high = [r for r in rows if _status(r.get("success_classification")) == "success" and float(r.get("performance_delta") or 0.0) >= 0.0]
    failing = [r for r in rows if _status(r.get("success_classification")) == "failure" or float(r.get("performance_delta") or 0.0) < 0.0]
    avg_delta = round(sum(float(r.get("performance_delta") or 0.0) for r in rows) / float(len(rows)), 4)
    recommendations: list[dict[str, Any]] = []
    if failing:
        recommendations.append(
            {
                "recommendation": "Adjust low-performing strategy cohort and increase operator review.",
                "reason": f"{len(failing)} outcome(s) classified as failure or negative delta.",
                "confidence_update": -0.1,
            }
        )
    if high:
        recommendations.append(
            {
                "recommendation": "Promote high-performing strategy patterns in next cycle planning.",
                "reason": f"{len(high)} outcome(s) show positive verified performance.",
                "confidence_update": 0.08,
            }
        )
    return {
        "performance_summary_status": "ok",
        "count": len(rows),
        "high_performing_count": len(high),
        "failing_count": len(failing),
        "adjustments_required_count": len(failing),
        "avg_performance_delta": avg_delta,
        "recommendations": recommendations,
    }

