from __future__ import annotations

from datetime import datetime
from typing import Any


ACTION_TYPES = {
    "mission_task",
    "execution_package",
    "revenue_follow_up",
    "deal_recovery",
    "opportunity_activation",
    "operator_escalation",
    "pause_and_replan",
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clamp(value: Any, *, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = fallback
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_task_queue(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _pending_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    queue = _normalize_task_queue(state.get("task_queue_snapshot") or state.get("task_queue"))
    return [
        item
        for item in queue
        if _text(item.get("status")).lower() in ("", "pending", "queued", "ready")
    ]


def _outcome_history_score(
    *,
    learning_records: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> float:
    records = [row for row in (learning_records or []) if isinstance(row, dict)]
    if not records:
        summary = (state or {}).get("learning_summary")
        if isinstance(summary, dict):
            total = max(1, int(summary.get("total_records") or 0))
            success = max(0, int(summary.get("recent_success_count") or 0))
            failure = max(0, int(summary.get("recent_failure_count") or 0))
            warning = max(0, int(summary.get("recent_warning_count") or 0))
            raw = (success - (failure * 0.8) - (warning * 0.4)) / float(total)
            return _clamp((raw + 1.0) / 2.0, fallback=0.5)
        return 0.5

    window = records[-20:]
    success = 0
    failed = 0
    warning = 0
    for row in window:
        outcome = _text(row.get("actual_outcome")).lower()
        if outcome == "success":
            success += 1
        elif outcome in ("failed", "blocked"):
            failed += 1
        elif outcome == "warning":
            warning += 1
    total = max(1, len(window))
    raw = (success - (failed * 0.8) - (warning * 0.4)) / float(total)
    return _clamp((raw + 1.0) / 2.0, fallback=0.5)


def score_priority(
    *,
    expected_value: Any,
    urgency: Any,
    probability_of_success: Any,
    risk: Any,
    effort: Any,
    dependency_readiness: Any,
    outcome_history: Any,
    blocked: bool = False,
) -> float:
    ev = _clamp(expected_value, fallback=0.0)
    urg = _clamp(urgency, fallback=0.0)
    prob = _clamp(probability_of_success, fallback=0.0)
    rsk = _clamp(risk, fallback=0.0)
    efr = _clamp(effort, fallback=0.0)
    dep = _clamp(dependency_readiness, fallback=0.0)
    hist = _clamp(outcome_history, fallback=0.5)
    score = (
        (ev * 0.28)
        + (urg * 0.2)
        + (prob * 0.18)
        + (dep * 0.12)
        + (hist * 0.12)
        + ((1.0 - rsk) * 0.06)
        + ((1.0 - efr) * 0.04)
    )
    if blocked:
        score *= 0.15
    return round(max(0.0, min(100.0, score * 100.0)), 2)


def _task_priority_to_urgency(task: dict[str, Any]) -> float:
    try:
        priority = int(task.get("priority") or 0)
    except Exception:
        priority = 0
    if priority <= 0:
        return 0.95
    if priority == 1:
        return 0.85
    if priority <= 3:
        return 0.7
    return 0.5


def _task_expected_value(task: dict[str, Any]) -> float:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    explicit = payload.get("expected_value")
    if explicit is not None:
        return _clamp(explicit, fallback=0.5)
    text = _text(task.get("task") or payload.get("description")).lower()
    if any(token in text for token in ("revenue", "client", "deal", "lead", "offer", "conversion")):
        return 0.82
    if any(token in text for token in ("block", "critical", "failure", "incident", "repair")):
        return 0.8
    return 0.62


def build_actionable_items(
    *,
    state: dict[str, Any],
    learning_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    outcome_hist = _outcome_history_score(learning_records=learning_records, state=state)
    items: list[dict[str, Any]] = []

    for task in _pending_tasks(state):
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        action_id = _text(task.get("id")) or _text(payload.get("id")) or f"task-{len(items) + 1}"
        expected_value = _task_expected_value(task)
        urgency = _task_priority_to_urgency(task)
        probability = _clamp(payload.get("probability_of_success"), fallback=0.68)
        risk = _clamp(payload.get("risk"), fallback=0.32)
        effort = _clamp(payload.get("effort"), fallback=0.45)
        dependency = _clamp(payload.get("dependency_readiness"), fallback=0.7)
        priority_score = score_priority(
            expected_value=expected_value,
            urgency=urgency,
            probability_of_success=probability,
            risk=risk,
            effort=effort,
            dependency_readiness=dependency,
            outcome_history=outcome_hist,
        )
        items.append(
            {
                "item_id": action_id,
                "action_type": "mission_task",
                "target_entity": "task_queue",
                "target_ref": action_id,
                "label": _text(task.get("task") or payload.get("description") or action_id),
                "signals": {
                    "expected_value": expected_value,
                    "urgency": urgency,
                    "probability_of_success": probability,
                    "risk": risk,
                    "effort": effort,
                    "dependency_readiness": dependency,
                    "outcome_history": outcome_hist,
                },
                "priority_score": priority_score,
                "reasoning": "Pending mission task scored from value, urgency, readiness, and outcome history.",
            }
        )

    package_id = _text(state.get("execution_package_id") or state.get("autopilot_last_package_id"))
    if package_id:
        risk_band = _text(((state.get("project_routing_result") or {}).get("routing_inputs") or {}).get("failure_risk_band")).lower()
        blocked = _text(state.get("autopilot_status")).lower() in {"blocked", "escalated", "paused"}
        package_risk = 0.72 if risk_band in {"high", "critical"} else 0.45
        priority_score = score_priority(
            expected_value=0.74,
            urgency=0.82 if blocked else 0.6,
            probability_of_success=0.58 if blocked else 0.7,
            risk=package_risk,
            effort=0.42,
            dependency_readiness=0.86,
            outcome_history=outcome_hist,
            blocked=blocked and risk_band in {"high", "critical"},
        )
        items.append(
            {
                "item_id": f"package-{package_id}",
                "action_type": "execution_package",
                "target_entity": "execution_package",
                "target_ref": package_id,
                "label": f"Advance execution package {package_id}",
                "signals": {
                    "expected_value": 0.74,
                    "urgency": 0.82 if blocked else 0.6,
                    "probability_of_success": 0.58 if blocked else 0.7,
                    "risk": package_risk,
                    "effort": 0.42,
                    "dependency_readiness": 0.86,
                    "outcome_history": outcome_hist,
                },
                "priority_score": priority_score,
                "reasoning": "Active execution package receives progression priority under governed workflow.",
            }
        )

    revenue_status = _text(state.get("revenue_activation_status") or state.get("revenue_workflow_status")).lower()
    revenue_next = _text(state.get("highest_value_next_action"))
    if revenue_status or revenue_next:
        blocked = revenue_status in {"blocked_for_revenue_action", "needs_operator_review"}
        priority_score = score_priority(
            expected_value=_clamp(state.get("roi_estimate"), fallback=0.55),
            urgency=_clamp(state.get("time_sensitivity"), fallback=0.5),
            probability_of_success=_clamp(state.get("conversion_probability"), fallback=0.5),
            risk=0.64 if blocked else 0.38,
            effort=0.44,
            dependency_readiness=0.78 if not blocked else 0.45,
            outcome_history=outcome_hist,
            blocked=blocked and revenue_status == "blocked_for_revenue_action",
        )
        items.append(
            {
                "item_id": "revenue-next-action",
                "action_type": "opportunity_activation",
                "target_entity": "revenue_pipeline",
                "target_ref": _text(state.get("opportunity_id") or state.get("lead_id") or "active"),
                "label": revenue_next or "Advance revenue opportunity",
                "signals": {
                    "expected_value": _clamp(state.get("roi_estimate"), fallback=0.55),
                    "urgency": _clamp(state.get("time_sensitivity"), fallback=0.5),
                    "probability_of_success": _clamp(state.get("conversion_probability"), fallback=0.5),
                    "risk": 0.64 if blocked else 0.38,
                    "effort": 0.44,
                    "dependency_readiness": 0.78 if not blocked else 0.45,
                    "outcome_history": outcome_hist,
                },
                "priority_score": priority_score,
                "reasoning": "Revenue opportunity ranked from ROI, conversion, urgency, and governance posture.",
            }
        )

    return items


def rank_actionable_items(items: list[dict[str, Any]], *, top_n: int = 12) -> list[dict[str, Any]]:
    normalized = [dict(item) for item in items if isinstance(item, dict)]
    normalized.sort(
        key=lambda item: (
            -float(item.get("priority_score") or 0.0),
            str(item.get("action_type") or ""),
            str(item.get("item_id") or ""),
        )
    )
    ranked: list[dict[str, Any]] = []
    for index, item in enumerate(normalized[: max(1, int(top_n))], start=1):
        ranked.append(
            {
                **item,
                "rank": index,
                "explanation": _text(item.get("reasoning")) or "Ranked from strategic weighted priority score.",
            }
        )
    return ranked


def _risk_level_from_score(score: float) -> str:
    if score < 35:
        return "high"
    if score < 60:
        return "guarded"
    return "managed"


def select_next_best_action(
    *,
    state: dict[str, Any],
    learning_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ranked = rank_actionable_items(build_actionable_items(state=state, learning_records=learning_records))
    if not ranked:
        return {
            "best_next_action": "pause_and_replan",
            "action_type": "pause_and_replan",
            "target_entity": "project",
            "target_ref": "",
            "reasoning": "No actionable mission, package, or opportunity was found.",
            "confidence": 0.52,
            "risk_level": "guarded",
            "priority_score": 0.0,
            "priority_queue": [],
            "recorded_at": _now_iso(),
        }
    top = ranked[0]
    confidence = _clamp((float(top.get("priority_score") or 0.0) / 100.0) * 0.92 + 0.08, fallback=0.5)
    return {
        "best_next_action": _text(top.get("label") or top.get("action_type") or top.get("item_id")),
        "action_type": _text(top.get("action_type")).lower() if _text(top.get("action_type")).lower() in ACTION_TYPES else "mission_task",
        "target_entity": _text(top.get("target_entity") or "task_queue"),
        "target_ref": _text(top.get("target_ref") or top.get("item_id")),
        "reasoning": _text(top.get("explanation")),
        "confidence": round(confidence, 4),
        "risk_level": _risk_level_from_score(float(top.get("priority_score") or 0.0)),
        "priority_score": float(top.get("priority_score") or 0.0),
        "priority_queue": ranked,
        "recorded_at": _now_iso(),
    }


def mission_priority_score(
    *,
    project_id: str,
    state: dict[str, Any],
    learning_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pending_count = len(_pending_tasks(state))
    outcome_hist = _outcome_history_score(learning_records=learning_records, state=state)
    has_package = bool(_text(state.get("execution_package_id") or state.get("autopilot_last_package_id")))
    autopilot_status = _text(state.get("autopilot_status")).lower()
    blocked = autopilot_status in {"blocked", "escalated", "paused"} or _text(state.get("enforcement_status")).lower() in {
        "blocked",
        "approval_required",
    }
    score = score_priority(
        expected_value=0.85 if has_package else (0.7 if pending_count > 0 else 0.25),
        urgency=0.92 if blocked else (0.68 if pending_count > 0 else 0.2),
        probability_of_success=0.52 if blocked else 0.75,
        risk=0.7 if blocked else 0.36,
        effort=0.42,
        dependency_readiness=0.9 if has_package else (0.68 if pending_count > 0 else 0.2),
        outcome_history=outcome_hist,
        blocked=blocked and not has_package,
    )
    return {
        "project_id": project_id,
        "mission_priority_score": score,
        "blocked": blocked,
        "pending_task_count": pending_count,
        "has_active_package": has_package,
        "autopilot_status": autopilot_status or "idle",
        "reasoning": "Mission priority score balances package momentum, queue urgency, blockers, and outcome history.",
    }


def detect_mission_conflicts(priorities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    ordered = sorted(
        [row for row in priorities if isinstance(row, dict)],
        key=lambda row: -float(row.get("mission_priority_score") or 0.0),
    )
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            left = ordered[i]
            right = ordered[j]
            delta = abs(float(left.get("mission_priority_score") or 0.0) - float(right.get("mission_priority_score") or 0.0))
            if delta <= 6.0 and (left.get("blocked") or right.get("blocked")):
                conflicts.append(
                    {
                        "projects": [left.get("project_id"), right.get("project_id")],
                        "conflict_type": "priority_contention_with_blocker",
                        "delta": round(delta, 2),
                        "resolution_hint": "Prioritize unblocked project or escalate blocked mission for operator decision.",
                    }
                )
    return conflicts


def build_mission_priorities(
    *,
    states_by_project: dict[str, dict[str, Any]],
    learning_by_project: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    priorities = [
        mission_priority_score(
            project_id=project_id,
            state=state if isinstance(state, dict) else {},
            learning_records=(learning_by_project or {}).get(project_id),
        )
        for project_id, state in sorted(states_by_project.items())
    ]
    priorities.sort(
        key=lambda row: (
            -float(row.get("mission_priority_score") or 0.0),
            str(row.get("project_id") or ""),
        )
    )
    conflicts = detect_mission_conflicts(priorities)
    selected = priorities[0].get("project_id") if priorities else ""
    strategy = (
        "highest_mission_priority_score_with_conflict_and_blocker_awareness"
        if priorities
        else "no_active_missions"
    )
    return {
        "mission_priorities": priorities,
        "mission_conflicts": conflicts,
        "mission_selection_strategy": strategy,
        "selected_project_id": selected,
        "recorded_at": _now_iso(),
    }

