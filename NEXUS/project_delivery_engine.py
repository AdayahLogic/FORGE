"""
Phase 116-120 project conversion + build + delivery field derivation.

This module is storage and policy shaping only. It does not execute build,
setup, delivery, or follow-up actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from NEXUS.executor_router import route_executor
from NEXUS.mission_system import build_mission_packet


DEAL_STATUSES = {"open", "negotiating", "closed_won", "closed_lost"}
PROJECT_STATUSES = {"initialized", "building", "ready", "delivered", "failed"}
BUILD_STATUSES = {"pending", "in_progress", "completed", "failed"}
SETUP_STATUSES = {"pending", "ready", "completed", "failed"}
SETUP_EXECUTORS = {"openclaw", "operator"}
DELIVERY_STATUSES = {"pending", "ready", "delivered", "failed"}
DELIVERY_TYPES = {"email", "link", "system_setup", "other"}
POST_DELIVERY_STATUSES = {"pending", "active", "completed"}
SATISFACTION_STATUSES = {"unknown", "satisfied", "unsatisfied"}
PROJECT_PRIORITIES = {"low", "medium", "high", "critical"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _pick(value: Any, *, allowed: set[str], fallback: str) -> str:
    normalized = _text(value).lower()
    if normalized in allowed:
        return normalized
    return fallback


def _derive_deal_status(package: dict[str, Any]) -> str:
    explicit = _pick(package.get("deal_status"), allowed=DEAL_STATUSES, fallback="")
    if explicit:
        return explicit
    lead_status = _text(package.get("lead_status")).lower()
    if lead_status == "converted":
        return "closed_won"
    if lead_status == "closed_lost":
        return "closed_lost"
    conversation_stage = _text(package.get("conversation_stage")).lower()
    if conversation_stage in {"qualified", "negotiating", "closing"}:
        return "negotiating"
    return "open"


def _derive_project_priority(package: dict[str, Any]) -> str:
    explicit = _pick(package.get("project_priority"), allowed=PROJECT_PRIORITIES, fallback="")
    if explicit:
        return explicit
    urgency = _text(package.get("urgency_level")).lower()
    lead_priority = _text(package.get("lead_priority")).lower()
    if urgency == "high" or lead_priority == "critical":
        return "high"
    if lead_priority == "high":
        return "high"
    if lead_priority == "low":
        return "low"
    return "medium"


def _derive_project_scope(package: dict[str, Any]) -> str:
    return (
        _text(package.get("project_scope"))
        or _text(package.get("offer_summary"))
        or _text(package.get("lead_intent"))
        or "Deliver scoped implementation for confirmed client deal."
    )


def _derive_requirements_summary(package: dict[str, Any]) -> str:
    return (
        _text(package.get("project_requirements_summary"))
        or _text(package.get("qualification_reason"))
        or _text(package.get("highest_value_next_action_reason"))
        or "Requirements derived from closed-won opportunity context."
    )


def _derive_build_scope_summary(package: dict[str, Any], project_scope: str) -> str:
    return (
        _text(package.get("build_scope_summary"))
        or _text(package.get("highest_value_next_action"))
        or project_scope
        or "Implement project scope in bounded codex mission."
    )


def _derive_expected_files(package: dict[str, Any]) -> list[str]:
    existing = package.get("build_files_expected")
    if isinstance(existing, list) and existing:
        return [str(item).strip() for item in existing if str(item).strip()][:50]
    expected_outputs = [str(item).strip() for item in list(package.get("expected_outputs") or []) if str(item).strip()]
    if expected_outputs:
        return expected_outputs[:50]
    return ["implementation_changes", "tests", "delivery_notes"]


def _derive_validation_requirements(package: dict[str, Any]) -> list[str]:
    existing = package.get("build_validation_requirements")
    if isinstance(existing, list) and existing:
        return [str(item).strip() for item in existing if str(item).strip()][:30]
    return [
        "all_changed_tests_pass",
        "no_auto_merge",
        "approval_required_for_delivery",
        "audit_trail_updated",
    ]


def derive_project_delivery_fields(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    package_id = _text(p.get("package_id")) or "pkg"
    deal_status = _derive_deal_status(p)

    project_id = _text(p.get("project_id"))
    project_created_at = _text(p.get("project_created_at"))
    if deal_status == "closed_won" and not project_id:
        project_id = f"proj-{package_id}"
        project_created_at = project_created_at or _now_iso()

    project_exists = bool(project_id)
    project_scope = _derive_project_scope(p)
    requirements_summary = _derive_requirements_summary(p)
    project_priority = _derive_project_priority(p)

    project_status = _pick(
        p.get("project_status"),
        allowed=PROJECT_STATUSES,
        fallback="initialized" if project_exists else "initialized",
    )

    build_required = bool(p.get("build_required")) or project_exists
    build_status = _pick(
        p.get("build_status"),
        allowed=BUILD_STATUSES,
        fallback="pending" if build_required else "pending",
    )
    build_scope_summary = _derive_build_scope_summary(p, project_scope)
    build_files_expected = _derive_expected_files(p)
    build_validation_requirements = _derive_validation_requirements(p)

    build_mission_id = _text(p.get("build_mission_id"))
    if project_exists and not build_mission_id:
        build_mission_id = f"msn-build-{project_id}"
    build_executor = "codex"

    mission_packet = dict(p.get("mission_packet") or {})
    if project_exists:
        mission_packet = build_mission_packet(
            mission_id=build_mission_id or f"msn-build-{project_id}",
            task={
                "task": build_scope_summary,
                "type": "implementation_step",
                "payload": {
                    "description": build_scope_summary,
                    "project_id": project_id,
                    "domain": "project_delivery",
                },
            },
            objective=build_scope_summary,
            mission_type="project_delivery",
            risk_level="medium",
            requires_initial_approval=True,
            requires_final_approval=True,
            allowed_executors=["codex", "forge_internal", "operator_only"],
            forbidden_actions=["auto_merge", "auto_deploy", "unbounded_loop", "policy_self_modification"],
        )
        # Keep routing metadata auditable while enforcing codex build route.
        route_executor(
            task_summary=build_scope_summary,
            task_type_hint="coding_repo_implementation",
            allowed_executors=["codex", "forge_internal", "operator_only"],
        )

    setup_required = bool(p.get("setup_required")) or project_exists
    setup_status = _pick(
        p.get("setup_status"),
        allowed=SETUP_STATUSES,
        fallback="pending" if setup_required else "pending",
    )
    if build_status == "completed" and setup_status == "pending":
        setup_status = "ready"
    setup_executor = _pick(p.get("setup_executor"), allowed=SETUP_EXECUTORS, fallback="openclaw")
    setup_steps_summary = _text(p.get("setup_steps_summary")) or "Structured setup packet prepared for operator/OpenClaw execution."
    setup_environment_requirements = (
        _text(p.get("setup_environment_requirements")) or "Environment prerequisites and credentials reviewed before setup."
    )

    delivery_requires_approval = bool(p.get("delivery_requires_approval", True))
    delivery_status = _pick(p.get("delivery_status"), allowed=DELIVERY_STATUSES, fallback="pending")
    if delivery_status == "pending" and build_status == "completed" and (not setup_required or setup_status == "completed"):
        delivery_status = "ready"
    delivery_type = _pick(p.get("delivery_type"), allowed=DELIVERY_TYPES, fallback="other")
    delivery_payload_summary = (
        _text(p.get("delivery_payload_summary"))
        or _text(p.get("offer_summary"))
        or "Delivery payload prepared from validated build/setup outcomes."
    )

    post_delivery_status = _pick(p.get("post_delivery_status"), allowed=POST_DELIVERY_STATUSES, fallback="pending")
    if delivery_status == "delivered" and post_delivery_status == "pending":
        post_delivery_status = "active"
    satisfaction_check_required = bool(p.get("satisfaction_check_required", True))
    satisfaction_status = _pick(p.get("satisfaction_status"), allowed=SATISFACTION_STATUSES, fallback="unknown")
    upsell_opportunity_detected = bool(p.get("upsell_opportunity_detected"))
    retention_follow_up_required = bool(p.get("retention_follow_up_required", True))

    return {
        "deal_status": deal_status,
        "project_id": project_id,
        "project_created_at": project_created_at,
        "project_status": project_status,
        "project_requirements_summary": requirements_summary,
        "project_scope": project_scope,
        "project_priority": project_priority,
        "build_required": build_required,
        "build_status": build_status,
        "build_mission_id": build_mission_id,
        "build_executor": build_executor,
        "build_scope_summary": build_scope_summary,
        "build_files_expected": build_files_expected,
        "build_validation_requirements": build_validation_requirements,
        "setup_required": setup_required,
        "setup_status": setup_status,
        "setup_executor": setup_executor,
        "setup_steps_summary": setup_steps_summary,
        "setup_environment_requirements": setup_environment_requirements,
        "delivery_status": delivery_status,
        "delivery_type": delivery_type,
        "delivery_payload_summary": delivery_payload_summary,
        "delivery_requires_approval": delivery_requires_approval,
        "post_delivery_status": post_delivery_status,
        "satisfaction_check_required": satisfaction_check_required,
        "satisfaction_status": satisfaction_status,
        "upsell_opportunity_detected": upsell_opportunity_detected,
        "retention_follow_up_required": retention_follow_up_required,
        "mission_packet": mission_packet,
        "mission_id": _text(mission_packet.get("mission_id")) or _text(p.get("mission_id")),
        "mission_type": _text(mission_packet.get("mission_type")) or _text(p.get("mission_type")) or "project_delivery",
        "mission_title": _text(mission_packet.get("mission_title")) or _text(p.get("mission_title")),
        "mission_objective": _text(mission_packet.get("mission_objective")) or _text(p.get("mission_objective")),
        "mission_scope_boundary": dict(mission_packet.get("mission_scope_boundary") or p.get("mission_scope_boundary") or {}),
        "mission_allowed_actions": list(mission_packet.get("mission_allowed_actions") or p.get("mission_allowed_actions") or []),
        "mission_forbidden_actions": list(mission_packet.get("mission_forbidden_actions") or p.get("mission_forbidden_actions") or []),
        "mission_allowed_executors": list(mission_packet.get("mission_allowed_executors") or p.get("mission_allowed_executors") or []),
        "mission_risk_level": _text(mission_packet.get("mission_risk_level") or p.get("mission_risk_level") or "medium"),
        "mission_success_criteria": dict(mission_packet.get("mission_success_criteria") or p.get("mission_success_criteria") or {}),
        "mission_stop_conditions": list(mission_packet.get("mission_stop_conditions") or p.get("mission_stop_conditions") or []),
        "mission_status": _text(mission_packet.get("mission_status") or p.get("mission_status") or "proposed"),
        "mission_created_at": _text(mission_packet.get("mission_created_at") or p.get("mission_created_at")),
        "mission_started_at": _text(p.get("mission_started_at")),
        "mission_completed_at": _text(p.get("mission_completed_at")),
        "mission_failed_at": _text(p.get("mission_failed_at")),
        "mission_requires_initial_approval": bool(mission_packet.get("mission_requires_initial_approval", p.get("mission_requires_initial_approval", True))),
        "mission_requires_final_approval": bool(mission_packet.get("mission_requires_final_approval", p.get("mission_requires_final_approval", True))),
        "mission_stop_condition_hit": bool(p.get("mission_stop_condition_hit")),
        "mission_stop_condition_reason": _text(p.get("mission_stop_condition_reason")),
        "mission_escalation_required": bool(p.get("mission_escalation_required")),
        "executor_route": "codex" if project_exists else _text(p.get("executor_route")),
        "executor_route_reason": (
            "Build missions are routed through Codex for phase 117."
            if project_exists
            else _text(p.get("executor_route_reason"))
        ),
        "executor_route_confidence": 0.9 if project_exists else float(p.get("executor_route_confidence") or 0.0),
        "executor_route_status": "routed" if project_exists else _text(p.get("executor_route_status")),
        "executor_task_type": (
            "coding_repo_implementation"
            if project_exists
            else _text(p.get("executor_task_type"))
        ),
        "executor_task_packet": {
            "build_scope_summary": build_scope_summary,
            "build_files_expected": build_files_expected,
            "build_validation_requirements": build_validation_requirements,
            "project_id": project_id,
            "project_status": project_status,
            "delivery_requires_approval": delivery_requires_approval,
        }
        if project_exists
        else dict(p.get("executor_task_packet") or {}),
        "executor_fallback_route": "forge_internal" if project_exists else _text(p.get("executor_fallback_route")),
    }
