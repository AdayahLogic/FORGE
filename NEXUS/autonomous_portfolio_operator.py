"""
NEXUS autonomous portfolio operator (Phase 10).

Implements a bounded, observable, interruptible autonomy loop that can:
- generate missions from portfolio/project signals,
- enforce portfolio resource allocation as real behavior,
- execute bounded missions in parallel,
- resolve conflicts and collisions,
- escalate only when required,
- apply autonomy limits and emergency kill-switch controls.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import sleep
from typing import Any
import uuid

from NEXUS.project_state import load_project_state, update_project_state_fields
from NEXUS.registry import PROJECTS
from NEXUS.studio_coordinator import build_studio_coordination_summary_safe
from NEXUS.studio_driver import build_studio_driver_result_safe
from portfolio_manager import build_portfolio_summary_safe


_KILL_SWITCH_STATE: dict[str, Any] = {
    "enabled": False,
    "reason": "",
    "source": "default",
    "updated_at": "",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_project_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_int(value: Any, default: int, minimum: int = 0, maximum: int = 10_000) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(minimum, min(parsed, maximum))


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "enabled"):
        return True
    if text in ("0", "false", "no", "off", "disabled"):
        return False
    return default


def _pending_task_count(state: dict[str, Any]) -> int:
    queue = state.get("task_queue_snapshot") or state.get("task_queue") or []
    if not isinstance(queue, list):
        return 0
    count = 0
    for row in queue:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in ("", "pending", "queued", "ready"):
            count += 1
    return count


def _build_states_by_project(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    if isinstance(states_by_project, dict) and states_by_project:
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in states_by_project.items()}
    out: dict[str, dict[str, Any]] = {}
    for key, meta in PROJECTS.items():
        path = meta.get("path")
        if not path:
            continue
        out[key] = load_project_state(path)
    return out


def get_portfolio_kill_switch_status() -> dict[str, Any]:
    return {
        "enabled": bool(_KILL_SWITCH_STATE.get("enabled", False)),
        "reason": str(_KILL_SWITCH_STATE.get("reason") or ""),
        "source": str(_KILL_SWITCH_STATE.get("source") or "default"),
        "updated_at": str(_KILL_SWITCH_STATE.get("updated_at") or ""),
    }


def set_portfolio_kill_switch(*, enabled: bool, reason: str = "", source: str = "operator") -> dict[str, Any]:
    _KILL_SWITCH_STATE["enabled"] = bool(enabled)
    _KILL_SWITCH_STATE["reason"] = str(reason or "").strip()
    _KILL_SWITCH_STATE["source"] = str(source or "operator")
    _KILL_SWITCH_STATE["updated_at"] = _now_iso()
    return get_portfolio_kill_switch_status()


def set_portfolio_kill_switch_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return set_portfolio_kill_switch(
            enabled=_safe_bool(kwargs.get("enabled"), default=False),
            reason=str(kwargs.get("reason") or ""),
            source=str(kwargs.get("source") or "operator"),
        )
    except Exception:
        return {
            "enabled": True,
            "reason": "kill_switch_update_failed",
            "source": "error_fallback",
            "updated_at": _now_iso(),
        }


def _effective_kill_switch(operator_controls: dict[str, Any] | None = None) -> dict[str, Any]:
    status = get_portfolio_kill_switch_status()
    controls = operator_controls or {}
    if "kill_switch_enabled" in controls:
        status["enabled"] = _safe_bool(controls.get("kill_switch_enabled"), default=status["enabled"])
        status["source"] = "operator_controls"
    if controls.get("kill_switch_reason"):
        status["reason"] = str(controls.get("kill_switch_reason"))
    return status


def generate_autonomous_missions(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    portfolio_summary: dict[str, Any] | None = None,
    intelligence_signals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    states = _build_states_by_project(states_by_project=states_by_project)
    signals = intelligence_signals or {}
    portfolio = portfolio_summary or {}
    high_value = {_normalize_project_id(v) for v in (signals.get("high_value_projects") or [])}
    low_value = {_normalize_project_id(v) for v in (signals.get("low_value_projects") or [])}
    stalled = {_normalize_project_id(v) for v in (signals.get("stalled_deals") or [])}

    missions: list[dict[str, Any]] = []
    for project_id, state in states.items():
        s = state if isinstance(state, dict) else {}
        autopilot_status = str(s.get("autopilot_status") or "").strip().lower()
        governance_status = str(s.get("governance_status") or "").strip().lower()
        pending = _pending_task_count(s)
        blocked = governance_status in ("blocked", "approval_required", "review_required")
        score = 0.25
        reasons: list[str] = []

        if project_id in high_value:
            score += 0.45
            reasons.append("high_value_signal")
        if project_id in stalled or autopilot_status in ("paused", "escalated", "blocked"):
            score += 0.35
            reasons.append("stalled_or_blocked_progress")
        if pending > 0:
            score += min(0.25, pending * 0.05)
            reasons.append("pending_tasks_present")
        if blocked:
            score -= 0.30
            reasons.append("governance_blocked")
        if project_id in low_value:
            score -= 0.20
            reasons.append("low_value_signal")

        mission_type = "execution_push"
        action = "start_or_resume_autopilot"
        if blocked:
            mission_type = "operator_resolution"
            action = "hold_for_operator"
        elif autopilot_status in ("paused", "escalated", "blocked"):
            mission_type = "unstall_cycle"
            action = "resume_autopilot"

        missions.append(
            {
                "mission_id": f"mission-{uuid.uuid4().hex[:10]}",
                "project_id": project_id,
                "mission_type": mission_type,
                "action": action,
                "priority_score": round(max(0.0, min(1.0, score)), 4),
                "priority_band": "high" if score >= 0.65 else ("medium" if score >= 0.4 else "low"),
                "reasons": reasons,
                "bounded": True,
                "safety_class": "governed",
                "strategy_group": "portfolio_throughput",
            }
        )

    portfolio_status = str(portfolio.get("portfolio_status") or "").strip().lower()
    priority_project = _normalize_project_id(portfolio.get("priority_project"))
    if portfolio_status in ("idle", "waiting") and priority_project:
        missions.append(
            {
                "mission_id": f"mission-{uuid.uuid4().hex[:10]}",
                "project_id": priority_project,
                "mission_type": "opportunity_generation",
                "action": "genesis_rank",
                "priority_score": 0.58,
                "priority_band": "medium",
                "reasons": [f"portfolio_status_{portfolio_status}"],
                "bounded": True,
                "safety_class": "evaluation_only",
                "strategy_group": "opportunity_generation",
            }
        )

    missions.sort(
        key=lambda m: (
            -float(m.get("priority_score") or 0.0),
            str(m.get("project_id") or ""),
            str(m.get("mission_type") or ""),
        )
    )
    return missions


def generate_autonomous_missions_safe(**kwargs: Any) -> list[dict[str, Any]]:
    try:
        return generate_autonomous_missions(**kwargs)
    except Exception:
        return []


def allocate_portfolio_resources(
    *,
    missions: list[dict[str, Any]] | None = None,
    parallel_capacity: int = 2,
) -> dict[str, Any]:
    capacity = _safe_int(parallel_capacity, default=2, minimum=1, maximum=25)
    rows = [m for m in (missions or []) if isinstance(m, dict)]
    per_project_best: dict[str, float] = {}
    for mission in rows:
        project_id = _normalize_project_id(mission.get("project_id"))
        if not project_id:
            continue
        score = float(mission.get("priority_score") or 0.0)
        if project_id not in per_project_best or score > per_project_best[project_id]:
            per_project_best[project_id] = score

    ranked = sorted(per_project_best.items(), key=lambda x: (-x[1], x[0]))
    allocated_projects = {project_id for project_id, _ in ranked[:capacity]}
    allocations: dict[str, int] = {}
    for project_id, _ in ranked:
        allocations[project_id] = 1 if project_id in allocated_projects else 0

    return {
        "parallel_capacity": capacity,
        "allocation_mode": "enforced_slots",
        "allocations_by_project": allocations,
        "allocated_projects": sorted(allocated_projects),
        "deferred_projects": sorted([project_id for project_id, slots in allocations.items() if slots <= 0]),
    }


def allocate_portfolio_resources_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return allocate_portfolio_resources(**kwargs)
    except Exception:
        return {
            "parallel_capacity": 1,
            "allocation_mode": "error_fallback",
            "allocations_by_project": {},
            "allocated_projects": [],
            "deferred_projects": [],
        }


def resolve_mission_conflicts(
    *,
    missions: list[dict[str, Any]] | None = None,
    allocation_result: dict[str, Any] | None = None,
    parallel_capacity: int = 2,
) -> dict[str, Any]:
    rows = [m for m in (missions or []) if isinstance(m, dict)]
    allocations = (allocation_result or {}).get("allocations_by_project") or {}
    capacity = _safe_int(parallel_capacity, default=2, minimum=1, maximum=25)
    selected_by_project: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []

    for mission in rows:
        project_id = _normalize_project_id(mission.get("project_id"))
        if not project_id:
            continue
        existing = selected_by_project.get(project_id)
        if not existing:
            selected_by_project[project_id] = mission
            continue
        existing_strategy = str(existing.get("strategy_group") or "")
        new_strategy = str(mission.get("strategy_group") or "")
        if existing_strategy and new_strategy and existing_strategy != new_strategy:
            conflicts.append(
                {
                    "conflict_type": "strategy_collision",
                    "project_id": project_id,
                    "existing_mission_id": existing.get("mission_id"),
                    "new_mission_id": mission.get("mission_id"),
                    "resolution": "highest_priority_wins",
                }
            )
        existing_score = float(existing.get("priority_score") or 0.0)
        new_score = float(mission.get("priority_score") or 0.0)
        if new_score > existing_score:
            selected_by_project[project_id] = mission

    executable: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for project_id, mission in selected_by_project.items():
        slots = _safe_int((allocations or {}).get(project_id), default=0, minimum=0, maximum=10)
        if slots <= 0:
            deferred.append({**mission, "defer_reason": "no_allocated_slot"})
        else:
            executable.append(mission)

    executable.sort(key=lambda m: (-float(m.get("priority_score") or 0.0), str(m.get("project_id") or "")))
    if len(executable) > capacity:
        over = executable[capacity:]
        executable = executable[:capacity]
        for row in over:
            deferred.append({**row, "defer_reason": "parallel_capacity_limit"})

    return {
        "conflict_status": "ok" if not conflicts else "resolved_with_conflicts",
        "conflicts": conflicts,
        "executable_missions": executable,
        "deferred_missions": deferred,
        "parallel_capacity": capacity,
    }


def resolve_mission_conflicts_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return resolve_mission_conflicts(**kwargs)
    except Exception:
        return {
            "conflict_status": "error_fallback",
            "conflicts": [],
            "executable_missions": [],
            "deferred_missions": [],
            "parallel_capacity": 1,
        }


def enforce_portfolio_allocations(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    allocation_result: dict[str, Any] | None = None,
    execute_actions: bool = True,
) -> dict[str, Any]:
    states = _build_states_by_project(states_by_project=states_by_project)
    allocations = (allocation_result or {}).get("allocations_by_project") or {}
    changes: list[dict[str, Any]] = []
    if not execute_actions:
        return {
            "enforcement_status": "simulated",
            "changes": changes,
        }

    from NEXUS.project_autopilot import get_project_autopilot_status, pause_project_autopilot

    for project_id, state in states.items():
        slots = _safe_int(allocations.get(project_id), default=0, minimum=0, maximum=10)
        autopilot_status = str((state or {}).get("autopilot_status") or "").strip().lower()
        if slots > 0:
            continue
        if autopilot_status not in ("ready", "running"):
            continue
        project_path = (PROJECTS.get(project_id) or {}).get("path")
        if not project_path:
            continue
        session = get_project_autopilot_status(project_path=project_path, project_name=project_id)
        if session.get("status") != "ok":
            continue
        paused = pause_project_autopilot(project_path=project_path, project_name=project_id)
        changes.append(
            {
                "project_id": project_id,
                "action": "pause_autopilot",
                "status": paused.get("status"),
                "reason": "resource_allocation_enforced",
            }
        )
    return {
        "enforcement_status": "enforced",
        "changes": changes,
    }


def enforce_portfolio_allocations_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return enforce_portfolio_allocations(**kwargs)
    except Exception:
        return {
            "enforcement_status": "error_fallback",
            "changes": [],
        }


def _execute_single_mission(mission: dict[str, Any]) -> dict[str, Any]:
    project_id = _normalize_project_id(mission.get("project_id"))
    action = str(mission.get("action") or "").strip().lower()
    project_path = (PROJECTS.get(project_id) or {}).get("path")
    if not project_id:
        return {"mission_id": mission.get("mission_id"), "status": "error", "reason": "project_id_missing"}

    if action in ("hold_for_operator",):
        return {
            "mission_id": mission.get("mission_id"),
            "project_id": project_id,
            "status": "escalated",
            "reason": "operator_action_required",
            "action": action,
        }

    if action == "genesis_rank":
        from studio_loop_executor import execute_selected_path_safe

        result = execute_selected_path_safe(
            selected_path="genesis_generation",
            selected_project=project_id,
            dashboard_summary={},
            helios_summary={},
            studio_driver_summary={},
            portfolio_summary={},
        )
        return {
            "mission_id": mission.get("mission_id"),
            "project_id": project_id,
            "status": "ok",
            "action": action,
            "execution_started": bool(result.get("execution_started", False)),
            "result": result.get("executed_result_summary") or {},
        }

    if action in ("resume_autopilot", "start_or_resume_autopilot"):
        from NEXUS.project_autopilot import (
            get_project_autopilot_status,
            resume_project_autopilot,
            start_project_autopilot,
        )

        if not project_path:
            return {
                "mission_id": mission.get("mission_id"),
                "project_id": project_id,
                "status": "error",
                "action": action,
                "reason": "project_path_missing",
            }
        status = get_project_autopilot_status(project_path=project_path, project_name=project_id)
        session = (status.get("session") or {}) if isinstance(status.get("session"), dict) else {}
        autopilot_status = str(session.get("autopilot_status") or "").strip().lower()
        if autopilot_status in ("paused", "ready"):
            result = resume_project_autopilot(project_path=project_path, project_name=project_id)
        else:
            result = start_project_autopilot(project_path=project_path, project_name=project_id)
        return {
            "mission_id": mission.get("mission_id"),
            "project_id": project_id,
            "status": "ok" if result.get("status") == "ok" else "error",
            "action": action,
            "reason": result.get("reason"),
            "autopilot_status": ((result.get("session") or {}).get("autopilot_status")),
        }

    return {
        "mission_id": mission.get("mission_id"),
        "project_id": project_id,
        "status": "deferred",
        "action": action,
        "reason": "unsupported_action",
    }


def execute_parallel_missions(
    *,
    executable_missions: list[dict[str, Any]] | None = None,
    parallel_capacity: int = 2,
    execute_actions: bool = True,
) -> dict[str, Any]:
    missions = [m for m in (executable_missions or []) if isinstance(m, dict)]
    capacity = _safe_int(parallel_capacity, default=2, minimum=1, maximum=25)
    if not execute_actions:
        return {
            "execution_status": "simulated",
            "parallel_capacity": capacity,
            "results": [
                {"mission_id": m.get("mission_id"), "project_id": m.get("project_id"), "status": "simulated"} for m in missions[:capacity]
            ],
        }

    results: list[dict[str, Any]] = []
    run_rows = missions[:capacity]
    with ThreadPoolExecutor(max_workers=capacity) as pool:
        future_map = {pool.submit(_execute_single_mission, mission): mission for mission in run_rows}
        for future in as_completed(future_map):
            mission = future_map[future]
            try:
                res = future.result()
            except Exception as exc:
                res = {
                    "mission_id": mission.get("mission_id"),
                    "project_id": mission.get("project_id"),
                    "status": "error",
                    "reason": str(exc),
                }
            results.append(res)
    results.sort(key=lambda row: str(row.get("project_id") or ""))
    return {
        "execution_status": "ok",
        "parallel_capacity": capacity,
        "results": results,
    }


def execute_parallel_missions_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return execute_parallel_missions(**kwargs)
    except Exception:
        return {
            "execution_status": "error_fallback",
            "parallel_capacity": 1,
            "results": [],
        }


def build_operator_escalations(
    *,
    conflict_result: dict[str, Any] | None = None,
    execution_result: dict[str, Any] | None = None,
    kill_switch_status: dict[str, Any] | None = None,
    safety_stop_reason: str = "",
) -> list[dict[str, Any]]:
    escalations: list[dict[str, Any]] = []
    conflict = conflict_result or {}
    execution = execution_result or {}
    kill = kill_switch_status or {}

    if kill.get("enabled"):
        escalations.append(
            {
                "severity": "critical",
                "what_happened": "Emergency kill switch is enabled.",
                "action_needed": "Confirm disable conditions before resuming autonomous operations.",
                "why_it_matters": "All autonomous activity remains paused until the kill switch is cleared.",
                "source": "kill_switch",
            }
        )

    conflicts = conflict.get("conflicts") or []
    if isinstance(conflicts, list) and conflicts:
        escalations.append(
            {
                "severity": "high",
                "what_happened": f"{len(conflicts)} mission conflict(s) were resolved by policy arbitration.",
                "action_needed": "Review conflict outcomes if strategic intent should override current priority policy.",
                "why_it_matters": "Repeated collisions can suppress valid opportunities or delay critical fixes.",
                "source": "conflict_resolution",
            }
        )

    results = execution.get("results") or []
    if isinstance(results, list):
        errors = [r for r in results if str(r.get("status") or "").strip().lower() in ("error", "escalated")]
        if errors:
            escalations.append(
                {
                    "severity": "high",
                    "what_happened": f"{len(errors)} mission(s) require operator intervention.",
                    "action_needed": "Resolve blocked approvals/governance issues and rerun bounded autonomy.",
                    "why_it_matters": "Unresolved mission failures can stall throughput and mask portfolio risk.",
                    "source": "mission_execution",
                }
            )

    if safety_stop_reason:
        escalations.append(
            {
                "severity": "medium",
                "what_happened": f"Autonomy loop stopped due to safety limit: {safety_stop_reason}.",
                "action_needed": "Inspect limits and confirm whether another bounded loop should be started.",
                "why_it_matters": "Safety stops prevent unbounded operation and protect system stability.",
                "source": "safety_limits",
            }
        )
    return escalations


def build_operator_escalations_safe(**kwargs: Any) -> list[dict[str, Any]]:
    try:
        return build_operator_escalations(**kwargs)
    except Exception:
        return []


def _persist_portfolio_operator_trace(
    *,
    states_by_project: dict[str, dict[str, Any]],
    trace: dict[str, Any],
) -> None:
    for project_id in states_by_project.keys():
        path = (PROJECTS.get(project_id) or {}).get("path")
        if not path:
            continue
        try:
            update_project_state_fields(
                path,
                portfolio_operator_summary=trace,
                portfolio_operator_last_tick_at=str(trace.get("tick_finished_at") or _now_iso()),
            )
        except Exception:
            continue


def run_autonomous_portfolio_tick(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    intelligence_signals: dict[str, Any] | None = None,
    operator_controls: dict[str, Any] | None = None,
    parallel_capacity: int = 2,
    execute_actions: bool = True,
    persist_trace: bool = False,
    trigger: str = "scheduled_tick",
) -> dict[str, Any]:
    tick_id = f"tick-{uuid.uuid4().hex[:12]}"
    started_at = _now_iso()
    states = _build_states_by_project(states_by_project=states_by_project)
    kill_switch = _effective_kill_switch(operator_controls)
    capacity = _safe_int(parallel_capacity, default=2, minimum=1, maximum=25)

    if kill_switch.get("enabled"):
        return {
            "tick_id": tick_id,
            "trigger": str(trigger),
            "tick_status": "stopped",
            "stop_reason": "kill_switch_enabled",
            "bounded": True,
            "interruptible": True,
            "observable": True,
            "tick_started_at": started_at,
            "tick_finished_at": _now_iso(),
            "project_count": len(states),
            "missions_generated": [],
            "allocation_result": allocate_portfolio_resources_safe(missions=[], parallel_capacity=capacity),
            "conflict_result": resolve_mission_conflicts_safe(missions=[], allocation_result={}, parallel_capacity=capacity),
            "execution_result": execute_parallel_missions_safe(executable_missions=[], parallel_capacity=capacity, execute_actions=False),
            "escalations": build_operator_escalations_safe(kill_switch_status=kill_switch, safety_stop_reason="kill_switch_enabled"),
            "kill_switch_status": kill_switch,
        }

    coordination = build_studio_coordination_summary_safe(states_by_project=states)
    driver = build_studio_driver_result_safe(
        studio_coordination_summary=coordination,
        states_by_project=states,
    )
    portfolio = build_portfolio_summary_safe(
        states_by_project=states,
        studio_coordination_summary=coordination,
        studio_driver_summary=driver,
    )
    missions = generate_autonomous_missions_safe(
        states_by_project=states,
        portfolio_summary=portfolio,
        intelligence_signals=intelligence_signals,
    )
    allocation = allocate_portfolio_resources_safe(missions=missions, parallel_capacity=capacity)
    enforcement = enforce_portfolio_allocations_safe(
        states_by_project=states,
        allocation_result=allocation,
        execute_actions=execute_actions,
    )
    conflict = resolve_mission_conflicts_safe(
        missions=missions,
        allocation_result=allocation,
        parallel_capacity=capacity,
    )
    execution = execute_parallel_missions_safe(
        executable_missions=conflict.get("executable_missions") or [],
        parallel_capacity=capacity,
        execute_actions=execute_actions,
    )
    escalations = build_operator_escalations_safe(
        conflict_result=conflict,
        execution_result=execution,
        kill_switch_status=kill_switch,
    )

    summary = {
        "tick_id": tick_id,
        "trigger": str(trigger),
        "tick_status": "ok",
        "stop_reason": "",
        "bounded": True,
        "interruptible": True,
        "observable": True,
        "tick_started_at": started_at,
        "tick_finished_at": _now_iso(),
        "project_count": len(states),
        "parallel_capacity": capacity,
        "studio_coordination_summary": coordination,
        "studio_driver_summary": driver,
        "portfolio_summary": portfolio,
        "missions_generated": missions,
        "allocation_result": allocation,
        "allocation_enforcement_result": enforcement,
        "conflict_result": conflict,
        "execution_result": execution,
        "escalations": escalations,
        "kill_switch_status": kill_switch,
    }
    if persist_trace:
        _persist_portfolio_operator_trace(states_by_project=states, trace=summary)
    return summary


def run_autonomous_portfolio_tick_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return run_autonomous_portfolio_tick(**kwargs)
    except Exception as exc:
        return {
            "tick_id": f"tick-{uuid.uuid4().hex[:12]}",
            "trigger": str(kwargs.get("trigger") or "scheduled_tick"),
            "tick_status": "error_fallback",
            "stop_reason": str(exc),
            "bounded": True,
            "interruptible": True,
            "observable": True,
            "tick_started_at": _now_iso(),
            "tick_finished_at": _now_iso(),
            "project_count": 0,
            "missions_generated": [],
            "allocation_result": allocate_portfolio_resources_safe(missions=[], parallel_capacity=1),
            "conflict_result": resolve_mission_conflicts_safe(missions=[], allocation_result={}, parallel_capacity=1),
            "execution_result": execute_parallel_missions_safe(executable_missions=[], parallel_capacity=1, execute_actions=False),
            "escalations": [
                {
                    "severity": "high",
                    "what_happened": "Autonomous portfolio tick failed.",
                    "action_needed": "Review error details and rerun a bounded tick.",
                    "why_it_matters": "Failure prevents autonomous portfolio progression.",
                    "source": "error_fallback",
                }
            ],
            "kill_switch_status": get_portfolio_kill_switch_status(),
        }


def run_autonomous_portfolio_loop(
    *,
    max_ticks: int = 3,
    max_runtime_seconds: int = 60,
    max_operations: int = 50,
    wake_interval_seconds: float = 0.0,
    parallel_capacity: int = 2,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    intelligence_signals: dict[str, Any] | None = None,
    operator_controls: dict[str, Any] | None = None,
    execute_actions: bool = True,
    persist_trace: bool = False,
    stop_on_escalation: bool = False,
    trigger: str = "continuous_loop",
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    ticks_limit = _safe_int(max_ticks, default=3, minimum=1, maximum=500)
    runtime_limit = _safe_int(max_runtime_seconds, default=60, minimum=1, maximum=86_400)
    operation_limit = _safe_int(max_operations, default=50, minimum=1, maximum=50_000)
    capacity = _safe_int(parallel_capacity, default=2, minimum=1, maximum=25)

    tick_results: list[dict[str, Any]] = []
    operations_used = 0
    stop_reason = ""
    loop_status = "completed"

    for index in range(ticks_limit):
        elapsed = int((datetime.now(timezone.utc) - started_at).total_seconds())
        if elapsed >= runtime_limit:
            loop_status = "stopped"
            stop_reason = "runtime_limit_reached"
            break
        if operations_used >= operation_limit:
            loop_status = "stopped"
            stop_reason = "operation_limit_reached"
            break
        if _effective_kill_switch(operator_controls).get("enabled"):
            loop_status = "stopped"
            stop_reason = "kill_switch_enabled"
            break

        tick = run_autonomous_portfolio_tick_safe(
            states_by_project=states_by_project,
            intelligence_signals=intelligence_signals,
            operator_controls=operator_controls,
            parallel_capacity=capacity,
            execute_actions=execute_actions,
            persist_trace=persist_trace,
            trigger=f"{trigger}:{index + 1}",
        )
        tick_results.append(tick)
        operations_used += len((tick.get("execution_result") or {}).get("results") or [])

        if tick.get("tick_status") in ("stopped", "error_fallback"):
            loop_status = "stopped"
            stop_reason = str(tick.get("stop_reason") or tick.get("tick_status"))
            break
        if stop_on_escalation and (tick.get("escalations") or []):
            loop_status = "stopped"
            stop_reason = "escalation_detected"
            break
        if index < ticks_limit - 1 and wake_interval_seconds > 0:
            sleep(max(0.0, float(wake_interval_seconds)))

    if not stop_reason and tick_results:
        final_tick = tick_results[-1]
        final_status = str(final_tick.get("tick_status") or "").strip().lower()
        if final_status in ("error_fallback", "stopped"):
            loop_status = "stopped"
            stop_reason = str(final_tick.get("stop_reason") or final_status)

    if not stop_reason and loop_status == "completed":
        stop_reason = "max_ticks_completed"

    escalations = build_operator_escalations_safe(
        conflict_result=tick_results[-1].get("conflict_result") if tick_results else {},
        execution_result=tick_results[-1].get("execution_result") if tick_results else {},
        kill_switch_status=_effective_kill_switch(operator_controls),
        safety_stop_reason=stop_reason if stop_reason in ("runtime_limit_reached", "operation_limit_reached", "kill_switch_enabled") else "",
    )

    return {
        "loop_status": loop_status,
        "stop_reason": stop_reason,
        "bounded": True,
        "interruptible": True,
        "observable": True,
        "max_ticks": ticks_limit,
        "ticks_run": len(tick_results),
        "max_runtime_seconds": runtime_limit,
        "runtime_seconds": int((datetime.now(timezone.utc) - started_at).total_seconds()),
        "max_operations": operation_limit,
        "operations_used": operations_used,
        "parallel_capacity": capacity,
        "started_at": started_at.isoformat(),
        "finished_at": _now_iso(),
        "tick_results": tick_results,
        "kill_switch_status": _effective_kill_switch(operator_controls),
        "escalations": escalations,
    }


def run_autonomous_portfolio_loop_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return run_autonomous_portfolio_loop(**kwargs)
    except Exception as exc:
        return {
            "loop_status": "error_fallback",
            "stop_reason": str(exc),
            "bounded": True,
            "interruptible": True,
            "observable": True,
            "max_ticks": 0,
            "ticks_run": 0,
            "max_runtime_seconds": 0,
            "runtime_seconds": 0,
            "max_operations": 0,
            "operations_used": 0,
            "parallel_capacity": 1,
            "started_at": _now_iso(),
            "finished_at": _now_iso(),
            "tick_results": [],
            "kill_switch_status": get_portfolio_kill_switch_status(),
            "escalations": [
                {
                    "severity": "high",
                    "what_happened": "Autonomous portfolio loop failed.",
                    "action_needed": "Investigate loop failure and run a bounded retry.",
                    "why_it_matters": "Continuous autonomous operation is suspended.",
                    "source": "error_fallback",
                }
            ],
        }
