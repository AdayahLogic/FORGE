"""
Outcome tracking, performance evaluation, strategy adaptation, and autonomy scaling.

This module is deterministic policy logic only. It computes bounded fields without
triggering side effects or executing external actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


OUTCOME_STATUSES = {"pending", "success", "partial", "failure"}
PERFORMANCE_CATEGORIES = {"excellent", "good", "average", "poor"}
ADJUSTMENT_TYPES = {"pricing", "messaging", "targeting", "follow_up", "other"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "None"):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_slug(value: Any, *, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip().lower()
    if text in allowed:
        return text
    return fallback


def _derive_outcome_status(
    *,
    expected_outcome: str,
    actual_outcome: str,
    revenue_delta: float,
    conversion_delta: float,
    performance_score: float,
    recorded: bool,
) -> str:
    if not recorded:
        return "pending"
    if performance_score >= 0.8 and (revenue_delta >= 0.0 or conversion_delta >= 0.0):
        return "success"
    if performance_score >= 0.45:
        return "partial"
    return "failure"


def _performance_category(performance_score: float) -> str:
    if performance_score >= 0.85:
        return "excellent"
    if performance_score >= 0.65:
        return "good"
    if performance_score >= 0.40:
        return "average"
    return "poor"


def _strategy_adjustment_type(
    *,
    outcome_status: str,
    revenue_delta: float,
    conversion_delta: float,
    follow_up_status: str,
) -> str:
    if revenue_delta < 0.0:
        return "pricing"
    if conversion_delta < 0.0:
        return "messaging"
    if outcome_status == "failure":
        return "targeting"
    if follow_up_status in {"pending", "scheduled", "escalated"}:
        return "follow_up"
    return "other"


def evaluate_outcome_adaptation_fields(
    *,
    package: dict[str, Any] | None,
    updates: dict[str, Any] | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """
    Compute deterministic, bounded fields for phases 121-125.

    Returns only the phase-specific fields so callers can merge safely.
    """
    base = dict(package or {})
    patch = dict(updates or {})
    merged = {**base, **patch}

    expected_outcome = _normalize_text(merged.get("expected_outcome"))
    actual_outcome = _normalize_text(merged.get("actual_outcome"))
    expected_revenue = _as_float(merged.get("expected_revenue"), 0.0)
    expected_conversion = _as_float(merged.get("expected_conversion"), 0.0)
    actual_revenue = _as_float(merged.get("actual_revenue"), 0.0)
    actual_conversion = _as_float(merged.get("actual_conversion"), 0.0)

    numeric_actual_update = ("actual_revenue" in patch) or ("actual_conversion" in patch)
    outcome_recorded_at = _normalize_text(merged.get("outcome_recorded_at"))
    recorded = bool(actual_outcome) or bool(outcome_recorded_at) or bool(numeric_actual_update)
    if recorded and not outcome_recorded_at:
        outcome_recorded_at = str(now_iso or _now_iso())

    revenue_delta = actual_revenue - expected_revenue
    conversion_delta = actual_conversion - expected_conversion
    revenue_ratio = _clamp(revenue_delta / max(abs(expected_revenue), 1.0), -1.0, 1.0)
    conversion_ratio = _clamp(conversion_delta / max(abs(expected_conversion), 0.01), -1.0, 1.0)

    expected_lower = expected_outcome.lower()
    actual_lower = actual_outcome.lower()
    if expected_lower and actual_lower:
        if expected_lower == actual_lower:
            textual_signal = 1.0
        elif expected_lower in actual_lower or actual_lower in expected_lower:
            textual_signal = 0.4
        else:
            textual_signal = -0.4
    else:
        textual_signal = 0.0

    outcome_delta_score = _clamp((revenue_ratio * 0.45) + (conversion_ratio * 0.35) + (textual_signal * 0.20), -1.0, 1.0)
    performance_score = _clamp((outcome_delta_score + 1.0) / 2.0, 0.0, 1.0)
    performance_category = _performance_category(performance_score)
    outcome_status = _derive_outcome_status(
        expected_outcome=expected_outcome,
        actual_outcome=actual_outcome,
        revenue_delta=revenue_delta,
        conversion_delta=conversion_delta,
        performance_score=performance_score,
        recorded=recorded,
    )
    performance_reason = (
        f"Revenue delta={revenue_delta:.4f}, conversion delta={conversion_delta:.4f}, "
        f"combined score={outcome_delta_score:.4f}."
    )

    follow_up_status = _normalize_text(merged.get("follow_up_status")).lower()
    strategy_adjustment_required = (
        recorded
        and (
            performance_category in {"average", "poor"}
            or revenue_delta < 0.0
            or conversion_delta < 0.0
            or outcome_status in {"partial", "failure"}
        )
    )
    strategy_adjustment_type = _strategy_adjustment_type(
        outcome_status=outcome_status,
        revenue_delta=revenue_delta,
        conversion_delta=conversion_delta,
        follow_up_status=follow_up_status,
    )
    if not strategy_adjustment_required:
        strategy_adjustment_type = "other"
    strategy_adjustment_reason = (
        "Performance signals indicate adaptation is needed."
        if strategy_adjustment_required
        else "Performance is stable; no strategy adjustment required."
    )
    recommendation_map = {
        "pricing": "Test revised pricing bands and value framing before changing live offers.",
        "messaging": "Run messaging variant experiments with controlled approval review.",
        "targeting": "Refine ICP targeting segments and route high-risk shifts to review.",
        "follow_up": "Adjust follow-up cadence and escalation templates under approval gates.",
        "other": "Maintain current strategy and continue monitoring outcomes.",
    }
    strategy_new_recommendation = recommendation_map[strategy_adjustment_type]
    baseline_confidence = _clamp(_as_float(merged.get("strategy_variant_confidence"), 0.5), 0.0, 1.0)
    if performance_category == "excellent":
        confidence_delta = 0.12
    elif performance_category == "good":
        confidence_delta = 0.05
    elif performance_category == "average":
        confidence_delta = -0.08
    else:
        confidence_delta = -0.15
    strategy_confidence_update = _clamp(baseline_confidence + confidence_delta, 0.0, 1.0)

    mission_risk = _normalize_text(merged.get("mission_risk_level")).lower() or "medium"
    approval_risk = _normalize_text(merged.get("approval_queue_risk_class")).lower() or mission_risk
    high_risk = mission_risk in {"high", "critical"} or approval_risk in {"high", "critical"}
    external_comm = bool(merged.get("email_requires_approval")) or _normalize_text(merged.get("email_direction")).lower() == "outbound"
    delivery_action = bool(_normalize_text(merged.get("project_id"))) and _normalize_text(merged.get("delivery_status")).lower() in {
        "pending",
        "ready",
        "delivered",
    }
    safe_pattern_count = _as_int((merged.get("metadata") or {}).get("safe_pattern_count"), 0)

    auto_approval_allowed = bool(
        not high_risk
        and not external_comm
        and not delivery_action
        and safe_pattern_count >= 3
        and outcome_status in {"success", "partial"}
    )
    current_autonomy_level = _as_int(merged.get("autonomy_level"), 0)
    if auto_approval_allowed:
        autonomy_level = _clamp(float(current_autonomy_level + 1), 0.0, 5.0)
    else:
        autonomy_level = _clamp(float(min(current_autonomy_level, 2)), 0.0, 5.0)
    auto_approval_scope = (
        "low_risk_internal_repeated_actions"
        if auto_approval_allowed
        else "manual_review_only"
    )
    auto_approval_risk_threshold = 0.35 if auto_approval_allowed else 0.0
    if high_risk:
        auto_approval_reason = "High-risk context remains approval-gated."
    elif external_comm:
        auto_approval_reason = "External communication is never auto-approved."
    elif delivery_action:
        auto_approval_reason = "Delivery actions remain operator approval-gated."
    elif not auto_approval_allowed:
        auto_approval_reason = "Insufficient repeated safe patterns for autonomy scaling."
    else:
        auto_approval_reason = "Low-risk repeated internal pattern qualifies for bounded auto-approval."

    mission_priority_base = {
        "critical": 1.0,
        "high": 0.8,
        "medium": 0.55,
        "low": 0.35,
    }.get(mission_risk, 0.5)
    lead_priority = _normalize_text(merged.get("lead_priority")).lower()
    lead_boost = {"high": 0.15, "medium": 0.08, "low": 0.02}.get(lead_priority, 0.0)
    mission_priority_score = _clamp(mission_priority_base + lead_boost, 0.0, 1.0)

    capacity = _as_int(merged.get("autopilot_parallel_capacity"), 1)
    capacity = int(_clamp(float(capacity), 1.0, 10.0))
    active_missions = merged.get("active_missions")
    if not isinstance(active_missions, list):
        active_missions = []
    normalized_missions: list[dict[str, Any]] = []
    for mission in active_missions:
        if not isinstance(mission, dict):
            continue
        normalized_missions.append(
            {
                "mission_id": _normalize_text(mission.get("mission_id")),
                "file_targets": [
                    _normalize_text(item)
                    for item in list(mission.get("file_targets") or [])
                    if _normalize_text(item)
                ][:40],
            }
        )
    active_mission_count = _as_int(merged.get("active_mission_count"), len(normalized_missions))
    if normalized_missions:
        active_mission_count = len(normalized_missions)

    file_to_mission: dict[str, str] = {}
    conflict_detected = False
    for mission in normalized_missions:
        mission_id = mission.get("mission_id") or "unknown"
        for file_target in mission.get("file_targets") or []:
            previous = file_to_mission.get(file_target)
            if previous and previous != mission_id:
                conflict_detected = True
            else:
                file_to_mission[file_target] = mission_id
    if active_mission_count > capacity:
        conflict_detected = True
    if conflict_detected and active_mission_count > capacity:
        conflict_resolution = "capacity_throttle_and_serialize"
    elif conflict_detected:
        conflict_resolution = "serialize_conflicting_file_targets"
    else:
        conflict_resolution = "parallel_safe_execution"

    return {
        "expected_outcome": expected_outcome,
        "expected_revenue": expected_revenue,
        "expected_conversion": expected_conversion,
        "actual_outcome": actual_outcome,
        "actual_revenue": actual_revenue,
        "actual_conversion": actual_conversion,
        "outcome_status": _normalize_slug(
            merged.get("outcome_status") if not recorded else outcome_status,
            allowed=OUTCOME_STATUSES,
            fallback="pending" if not recorded else outcome_status,
        ),
        "outcome_recorded_at": outcome_recorded_at,
        "outcome_delta_score": outcome_delta_score,
        "revenue_delta": revenue_delta,
        "conversion_delta": conversion_delta,
        "performance_score": performance_score,
        "performance_category": _normalize_slug(
            merged.get("performance_category") if not recorded else performance_category,
            allowed=PERFORMANCE_CATEGORIES,
            fallback=performance_category,
        ),
        "performance_reason": performance_reason,
        "strategy_adjustment_required": bool(strategy_adjustment_required),
        "strategy_adjustment_type": _normalize_slug(
            strategy_adjustment_type, allowed=ADJUSTMENT_TYPES, fallback="other"
        ),
        "strategy_adjustment_reason": strategy_adjustment_reason,
        "strategy_new_recommendation": strategy_new_recommendation,
        "strategy_confidence_update": strategy_confidence_update,
        "autonomy_level": int(autonomy_level),
        "auto_approval_allowed": bool(auto_approval_allowed),
        "auto_approval_scope": auto_approval_scope,
        "auto_approval_risk_threshold": _clamp(auto_approval_risk_threshold, 0.0, 1.0),
        "auto_approval_reason": auto_approval_reason,
        "autopilot_parallel_capacity": capacity,
        "active_mission_count": max(0, active_mission_count),
        "mission_priority_score": mission_priority_score,
        "mission_conflict_detected": bool(conflict_detected),
        "mission_conflict_resolution_strategy": conflict_resolution,
    }
