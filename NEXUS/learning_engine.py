from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.learning_models import normalize_learning_record


def _safe_get(d: Any, key: str, default: Any = None) -> Any:
    """
    Safe attribute/dict getter for both dict-like payloads and StudioState-like objects.

    Deterministic and intentionally simple:
    - dict => d.get(key, default)
    - otherwise => getattr(d, key, default)
    """
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    try:
        if hasattr(d, key):
            return getattr(d, key)
    except Exception:
        return default
    return default


def _safe_as_dict(v: Any) -> dict[str, Any]:
    """
    Convert values that are commonly dict-like (dict, Pydantic BaseModel) into a dict.

    If conversion fails or value isn't convertible, return {}.
    """
    if isinstance(v, dict):
        return v

    # Pydantic v1: .dict(); Pydantic v2: .model_dump()
    try:
        d_fn = getattr(v, "dict", None)
        if callable(d_fn):
            res = d_fn()
            if isinstance(res, dict):
                return res
    except Exception:
        pass

    try:
        dump_fn = getattr(v, "model_dump", None)
        if callable(dump_fn):
            res = dump_fn()
            if isinstance(res, dict):
                return res
    except Exception:
        pass

    return {}


def _derive_predicted_from_enforcement(enforcement_status: str | None) -> str:
    es = (enforcement_status or "").strip().lower()
    if es == "continue":
        return "proceed"
    if es == "approval_required":
        return "await_approval"
    if es == "manual_review_required":
        return "manual_review"
    if es == "blocked":
        return "blocked"
    if es == "hold":
        return "hold"
    if es == "error_fallback":
        return "error_fallback"
    return "unknown"


def _derive_actual_outcome(system_health_summary: dict[str, Any] | None, workflow_route_status: str | None) -> tuple[str, str]:
    sh = system_health_summary or {}
    overall = str(sh.get("overall_status") or "").strip().lower()
    if workflow_route_status in ("manual_review_hold", "approval_hold", "hold_state"):
        return ("manual_review_required", "gated")
    if workflow_route_status in ("blocked_stop",):
        return ("blocked", "blocked")
    if overall == "healthy":
        return ("success", "success")
    if overall == "warning":
        return ("warning", "warning")
    if overall == "critical":
        return ("failed", "failed")
    return ("unknown", overall or "unknown")


def _extract_error_summary(state: Any) -> str:
    dispatch_result = _safe_as_dict(_safe_get(state, "dispatch_result", {}) or {})
    if dispatch_result:
        # prefer explicit errors reasons
        errors = dispatch_result.get("errors") or []
        if isinstance(errors, list) and errors:
            for err in errors:
                if isinstance(err, dict) and err.get("reason"):
                    return str(err.get("reason"))
        msg = dispatch_result.get("message") or dispatch_result.get("reason")
        if msg:
            return str(msg)
    return str(_safe_get(state, "workflow_route_reason") or _safe_get(state, "notes") or "")


def _derive_predicted_confidence(state: Any) -> float:
    """
    Lightweight, honest confidence heuristic (not a calibrated predictor).

    We intentionally start low and only increase confidence when concrete
    enforcement/governance/health signals are present in the workflow state.
    """
    enforcement_status = _safe_get(state, "enforcement_status")
    governance_status = _safe_get(state, "governance_status")
    workflow_route_status = _safe_get(state, "workflow_route_status")

    dispatch_result = _safe_as_dict(_safe_get(state, "dispatch_result"))
    governance_result = _safe_as_dict(_safe_get(state, "governance_result"))
    enforcement_result = _safe_as_dict(_safe_get(state, "enforcement_result"))
    system_health_summary = _safe_as_dict(_safe_get(state, "system_health_summary"))

    has_enforcement = isinstance(enforcement_status, str) and bool(enforcement_status.strip())
    has_governance = isinstance(governance_status, str) and bool(governance_status.strip())
    has_route = isinstance(workflow_route_status, str) and bool(workflow_route_status.strip())
    has_dispatch = bool(dispatch_result)
    has_governance_result = bool(governance_result)
    has_enforcement_result = bool(enforcement_result)
    has_health = bool(system_health_summary)

    # Start conservative at early-stage hooks.
    confidence = 0.08

    if has_dispatch:
        confidence += 0.10
    if has_governance_result:
        confidence += 0.10
    if has_enforcement_result:
        confidence += 0.10
    if has_health:
        confidence += 0.20

    if has_governance:
        confidence += 0.08
    if has_enforcement:
        confidence += 0.18
    if has_route:
        confidence += 0.08

    # If we have effectively no signals, keep it low.
    if not any(
        [
            has_dispatch,
            has_governance_result,
            has_enforcement_result,
            has_health,
            has_governance,
            has_enforcement,
            has_route,
        ]
    ):
        return 0.05

    # Clamp to [0,1]
    if confidence < 0:
        confidence = 0.0
    if confidence > 1:
        confidence = 1.0
    return confidence


def _derive_performance_impact(state: Any) -> int:
    """
    Lightweight, deterministic performance impact heuristic.

    This is not a calibrated performance model; it simply maps system health
    overall status to a small integer impact score:
    - healthy => +2
    - warning => -3
    - critical => -8
    """
    sh = _safe_as_dict(_safe_get(state, "system_health_summary")) or {}
    overall = str(sh.get("overall_status") or "").strip().lower()
    if overall == "healthy":
        return 2
    if overall == "warning":
        return -3
    if overall == "critical":
        return -8
    return 0


def build_outcome_learning_record(
    *,
    state: Any,
    workflow_stage: str | None = None,
    decision_source: str | None = None,
    decision_type: str | None = None,
    decision_summary: str | None = None,
) -> dict[str, Any]:
    """
    Build one deterministic outcome-learning record from the current workflow state.
    """
    run_id = _safe_get(state, "run_id")
    project_name = _safe_get(state, "active_project")
    project_name = project_name or _safe_get(state, "project_name") or ""

    enforcement_status = _safe_get(state, "enforcement_status")
    governance_status = _safe_get(state, "governance_status")
    workflow_route_status = _safe_get(state, "workflow_route_status")

    predicted_outcome = _derive_predicted_from_enforcement(enforcement_status)
    predicted_confidence = _derive_predicted_confidence(state)

    system_health_summary = _safe_as_dict(_safe_get(state, "system_health_summary")) or {}
    actual_outcome, actual_status = _derive_actual_outcome(system_health_summary, workflow_route_status)

    error_summary = _extract_error_summary(state)
    performance_impact = _derive_performance_impact(state)

    review_queue_entry = _safe_as_dict(_safe_get(state, "review_queue_entry") or {})
    human_review_required = False
    if review_queue_entry:
        human_review_required = bool(review_queue_entry.get("requires_human_action", False))

    tags: list[str] = []
    system_overall = ""
    if isinstance(system_health_summary, dict):
        system_overall = str(system_health_summary.get("overall_status") or "").strip().lower()
    for t in [
        str(enforcement_status or "").strip().lower(),
        str(governance_status or "").strip().lower(),
        str(workflow_route_status or "").strip().lower(),
        system_overall,
    ]:
        if t:
            tags.append(t)

    derived_decision_type = decision_type or "enforcement_status"
    derived_decision_summary = decision_summary or str(enforcement_status or workflow_route_status or "")

    dispatch_result_map = _safe_as_dict(_safe_get(state, "dispatch_result"))
    file_mod_summary_map = _safe_as_dict(_safe_get(state, "file_modification_summary"))

    record = {
        "learning_contract_version": "1.0",
        "record_type": "outcome_record",
        "run_id": run_id,
        "project_name": project_name,
        "timestamp": datetime.now().isoformat(),
        "workflow_stage": workflow_stage or str(workflow_route_status or "workflow_completed"),
        "decision_source": decision_source or "nexus",
        "decision_type": derived_decision_type,
        "decision_summary": derived_decision_summary,
        "predicted_outcome": predicted_outcome,
        "predicted_confidence": predicted_confidence,
        "actual_outcome": actual_outcome,
        "actual_status": actual_status,
        "error_summary": error_summary[: 2000] if isinstance(error_summary, str) else "",
        "performance_impact": performance_impact,
        "human_review_required": human_review_required,
        "human_override": None,
        "downstream_effects": {
            "dispatch_status": dispatch_result_map.get("status"),
            "execution_status": dispatch_result_map.get("execution_status"),
            "files_updated": bool(file_mod_summary_map),
            "file_modification_summary_present": bool(file_mod_summary_map),
        },
        "tags": tags,
    }

    return normalize_learning_record(record)


def build_outcome_learning_record_safe(
    *,
    state: Any,
    workflow_stage: str | None = None,
    decision_source: str | None = None,
    decision_type: str | None = None,
    decision_summary: str | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_outcome_learning_record(
            state=state,
            workflow_stage=workflow_stage,
            decision_source=decision_source,
            decision_type=decision_type,
            decision_summary=decision_summary,
        )
    except Exception:
        fallback = {
            "learning_contract_version": "1.0",
            "record_type": "outcome_record",
            "run_id": _safe_get(state, "run_id"),
            "project_name": _safe_get(state, "active_project") or "",
            "timestamp": datetime.now().isoformat(),
            "workflow_stage": workflow_stage or "workflow_completed",
            "decision_source": decision_source or "nexus",
            "decision_type": decision_type or "enforcement_status",
            "decision_summary": decision_summary or "",
            "predicted_outcome": "error_fallback",
            "predicted_confidence": 0.0,
            "actual_outcome": "unknown",
            "actual_status": "error_fallback",
            "error_summary": "learning_record_build_failed",
            "performance_impact": 0,
            "human_review_required": True,
            "human_override": None,
            "downstream_effects": {},
            "tags": ["learning_build_failed"],
        }
        return normalize_learning_record(fallback)


def build_learning_summary_from_records(records: list[dict[str, Any]], *, last_n: int = 20) -> dict[str, Any]:
    """
    Lightweight aggregation over a list of learning records.
    Deterministic and explainable; intended for future calibration hooks.
    """
    window = records[-last_n:] if isinstance(records, list) else []

    total = len(window)
    if total == 0:
        return {
            "learning_summary_status": "idle",
            "total_records": 0,
            "recent_success_count": 0,
            "recent_failure_count": 0,
            "recent_warning_count": 0,
            "prediction_accuracy": None,
            "recommended_caution_level": "low",
            "top_error_signatures": [],
        }

    success = 0
    failure = 0
    warning = 0
    correct_predictions = 0

    def map_actual_to_pred_domain(actual_outcome: str) -> str:
        ao = (actual_outcome or "").strip().lower()
        if ao == "success":
            return "proceed"
        return ao

    # repeated failure patterns: naive deterministic signature extraction
    sig_counts: dict[str, int] = {}
    for rec in window:
        ao = (rec.get("actual_outcome") or "").strip().lower()
        if ao == "success":
            success += 1
        elif ao == "failed" or ao == "blocked":
            failure += 1
        else:
            if ao == "warning":
                warning += 1

        po = (rec.get("predicted_outcome") or "").strip().lower()
        mapped = map_actual_to_pred_domain(ao)
        if po and mapped and po == mapped:
            correct_predictions += 1

        err = str(rec.get("error_summary") or "")
        signature = ""
        if err:
            # Signature: first 3 alnum tokens
            tokens = [t for t in err.replace(":", " ").replace(",", " ").split() if t.strip()]
            signature = "-".join(tokens[:3]).lower()
        if signature:
            sig_counts[signature] = sig_counts.get(signature, 0) + 1

    prediction_accuracy = correct_predictions / float(total) if total else None

    # Recommended caution: conservative thresholding
    failure_rate = failure / float(total)
    warning_rate = warning / float(total)

    if failure_rate >= 0.3:
        caution = "high"
    elif failure_rate >= 0.15 or warning_rate >= 0.3:
        caution = "medium"
    else:
        caution = "low"

    top_sigs = sorted(sig_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_error_signatures = [{"signature": k, "count": v} for k, v in top_sigs]

    return {
        "learning_summary_status": "ok",
        "total_records": total,
        "recent_success_count": success,
        "recent_failure_count": failure,
        "recent_warning_count": warning,
        "prediction_accuracy": prediction_accuracy,
        "recommended_caution_level": caution,
        "top_error_signatures": top_error_signatures,
    }

