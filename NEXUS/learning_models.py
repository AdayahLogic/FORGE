from __future__ import annotations

from datetime import datetime
from typing import Any


LEARNING_CONTRACT_VERSION = "1.0"


def _normalize_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    try:
        s = str(v).strip()
        return s if s else default
    except Exception:
        return default


def _normalize_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalize_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return bool(v)


def normalize_learning_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize any outcome-learning record to a stable, explicit contract shape.

    Important honesty note:
    This is *not* strict runtime type validation (e.g., full Pydantic model enforcement).
    It provides deterministic, safe defaults and coercions so learning writes are
    robust and inspectable without risking workflow failures.
    """
    rec = record if isinstance(record, dict) else {}

    predicted_confidence = _normalize_float(rec.get("predicted_confidence"), default=0.0)
    if predicted_confidence < 0:
        predicted_confidence = 0.0
    if predicted_confidence > 1:
        predicted_confidence = 1.0

    performance_impact = rec.get("performance_impact")
    if isinstance(performance_impact, (int, float)):
        # Keep it deterministic and explainable (int impact score).
        performance_impact_out: int = int(round(float(performance_impact)))
    else:
        performance_impact_out = 0

    timestamp = rec.get("timestamp")
    if not timestamp:
        timestamp = datetime.now().isoformat()

    return {
        "learning_contract_version": LEARNING_CONTRACT_VERSION,
        "record_type": _normalize_str(rec.get("record_type"), default="outcome_record"),
        "run_id": rec.get("run_id"),
        "project_name": _normalize_str(rec.get("project_name"), default=""),
        "timestamp": timestamp,
        "workflow_stage": _normalize_str(rec.get("workflow_stage"), default=""),
        "decision_source": _normalize_str(rec.get("decision_source"), default=""),
        "decision_type": _normalize_str(rec.get("decision_type"), default="unknown"),
        "decision_summary": _normalize_str(rec.get("decision_summary"), default=""),
        "predicted_outcome": _normalize_str(rec.get("predicted_outcome"), default="unknown"),
        "predicted_confidence": predicted_confidence,
        "actual_outcome": _normalize_str(rec.get("actual_outcome"), default="unknown"),
        "actual_status": _normalize_str(rec.get("actual_status"), default="unknown"),
        "error_summary": _normalize_str(rec.get("error_summary"), default=""),
        "performance_impact": performance_impact_out,
        "human_review_required": _normalize_bool(rec.get("human_review_required"), default=False),
        "human_override": rec.get("human_override"),
        "downstream_effects": rec.get("downstream_effects") if isinstance(rec.get("downstream_effects"), dict) else {},
        "tags": rec.get("tags") if isinstance(rec.get("tags"), list) else [],
    }

