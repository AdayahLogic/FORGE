"""
Mission packet contracts for supervised autonomy.

This module is policy and data-shaping only. It does not execute work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MISSION_STATUSES = {
    "proposed",
    "awaiting_initial_approval",
    "approved_for_execution",
    "executing",
    "awaiting_final_review",
    "completed",
    "failed",
    "rejected",
    "paused",
}

MISSION_TYPES = {
    "forge_self_build",
    "revenue_business_ops",
    "project_delivery",
    "research_ops",
}

MISSION_RISK_LEVELS = {"low", "medium", "high", "critical"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _mission_type_from_task(task: dict[str, Any] | None) -> str:
    t = task or {}
    task_type = str(t.get("type") or "").strip().lower()
    payload = t.get("payload") if isinstance(t.get("payload"), dict) else {}
    hint = str(payload.get("domain") or payload.get("task_domain") or "").strip().lower()
    if hint in MISSION_TYPES:
        return hint
    if "revenue" in task_type:
        return "revenue_business_ops"
    if "research" in task_type:
        return "research_ops"
    if "self" in task_type:
        return "forge_self_build"
    return "project_delivery"


def _objective_from_task(task: dict[str, Any] | None) -> str:
    t = task or {}
    payload = t.get("payload") if isinstance(t.get("payload"), dict) else {}
    return str(
        t.get("task")
        or payload.get("description")
        or payload.get("summary")
        or t.get("id")
        or "Execute bounded project objective."
    ).strip()


def build_mission_packet(
    *,
    mission_id: str,
    task: dict[str, Any] | None,
    objective: str | None = None,
    mission_type: str | None = None,
    risk_level: str = "medium",
    requires_initial_approval: bool = True,
    requires_final_approval: bool = True,
    allowed_executors: list[str] | None = None,
    allowed_actions: list[str] | None = None,
    forbidden_actions: list[str] | None = None,
) -> dict[str, Any]:
    resolved_type = str(mission_type or _mission_type_from_task(task)).strip().lower()
    if resolved_type not in MISSION_TYPES:
        resolved_type = "project_delivery"
    resolved_risk = str(risk_level or "medium").strip().lower()
    if resolved_risk not in MISSION_RISK_LEVELS:
        resolved_risk = "medium"
    mission_objective = str(objective or _objective_from_task(task) or "Execute bounded objective.").strip()
    packet = {
        "mission_id": str(mission_id or "").strip(),
        "mission_type": resolved_type,
        "mission_title": mission_objective[:140],
        "mission_objective": mission_objective,
        "mission_scope_boundary": {
            "scope_type": "bounded_task_packet",
            "change_scope": "project_scoped",
            "requires_new_approval_for_scope_expansion": True,
        },
        "mission_allowed_actions": _as_list(
            allowed_actions
            or [
                "decision",
                "eligibility",
                "release",
                "handoff",
                "execute",
                "evaluate",
                "local_analysis",
            ]
        ),
        "mission_forbidden_actions": _as_list(
            forbidden_actions
            or [
                "unbounded_loop",
                "policy_self_modification",
                "mode_self_escalation",
                "auto_merge",
                "auto_deploy",
            ]
        ),
        "mission_allowed_executors": _as_list(allowed_executors or ["forge_internal", "codex", "openclaw", "operator_only"]),
        "mission_risk_level": resolved_risk,
        "mission_success_criteria": {
            "required_outcomes": ["bounded_execution_completed", "governance_safe", "auditable_trace_present"],
            "final_acceptance_required": True,
        },
        "mission_stop_conditions": [
            "scope_expansion_required",
            "governance_hard_block",
            "credentials_required_unexpectedly",
            "executor_critical_failure",
            "risky_external_action_out_of_scope",
            "repo_safety_cannot_be_maintained",
        ],
        "mission_status": "proposed",
        "mission_created_at": _now_iso(),
        "mission_started_at": "",
        "mission_completed_at": "",
        "mission_failed_at": "",
        "mission_requires_initial_approval": bool(requires_initial_approval),
        "mission_requires_final_approval": bool(requires_final_approval),
        "mission_stop_condition_hit": False,
        "mission_stop_condition_reason": "",
        "mission_escalation_required": False,
    }
    return packet


def normalize_mission_packet(packet: dict[str, Any] | None) -> dict[str, Any]:
    p = packet or {}
    status = str(p.get("mission_status") or "proposed").strip().lower()
    if status not in MISSION_STATUSES:
        status = "proposed"
    mission_type = str(p.get("mission_type") or "project_delivery").strip().lower()
    if mission_type not in MISSION_TYPES:
        mission_type = "project_delivery"
    risk = str(p.get("mission_risk_level") or "medium").strip().lower()
    if risk not in MISSION_RISK_LEVELS:
        risk = "medium"
    return {
        "mission_id": str(p.get("mission_id") or "").strip(),
        "mission_type": mission_type,
        "mission_title": str(p.get("mission_title") or ""),
        "mission_objective": str(p.get("mission_objective") or ""),
        "mission_scope_boundary": dict(p.get("mission_scope_boundary") or {}),
        "mission_allowed_actions": _as_list(p.get("mission_allowed_actions")),
        "mission_forbidden_actions": _as_list(p.get("mission_forbidden_actions")),
        "mission_allowed_executors": _as_list(p.get("mission_allowed_executors")),
        "mission_risk_level": risk,
        "mission_success_criteria": dict(p.get("mission_success_criteria") or {}),
        "mission_stop_conditions": _as_list(p.get("mission_stop_conditions")),
        "mission_status": status,
        "mission_created_at": str(p.get("mission_created_at") or ""),
        "mission_started_at": str(p.get("mission_started_at") or ""),
        "mission_completed_at": str(p.get("mission_completed_at") or ""),
        "mission_failed_at": str(p.get("mission_failed_at") or ""),
        "mission_requires_initial_approval": bool(p.get("mission_requires_initial_approval", True)),
        "mission_requires_final_approval": bool(p.get("mission_requires_final_approval", True)),
        "mission_stop_condition_hit": bool(p.get("mission_stop_condition_hit")),
        "mission_stop_condition_reason": str(p.get("mission_stop_condition_reason") or ""),
        "mission_escalation_required": bool(p.get("mission_escalation_required")),
    }


def evaluate_mission_stop_conditions(context: dict[str, Any] | None) -> dict[str, Any]:
    c = context or {}
    checks = [
        ("scope_expansion_required", bool(c.get("scope_expansion_required"))),
        ("governance_hard_block", bool(c.get("governance_hard_block"))),
        ("credentials_required_unexpectedly", bool(c.get("credentials_required_unexpectedly"))),
        ("executor_critical_failure", bool(c.get("executor_critical_failure"))),
        ("risky_external_action_out_of_scope", bool(c.get("risky_external_action_out_of_scope"))),
        ("repo_safety_cannot_be_maintained", bool(c.get("repo_safety_cannot_be_maintained"))),
    ]
    hit = [name for name, active in checks if active]
    reason = hit[0] if hit else ""
    return {
        "mission_stop_condition_hit": bool(hit),
        "mission_stop_condition_reason": reason,
        "mission_escalation_required": bool(hit),
        "mission_stop_condition_hits": hit,
    }
