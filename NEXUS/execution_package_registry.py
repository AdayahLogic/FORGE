"""
NEXUS review-only execution package registry.

Stores sealed execution envelopes for review without performing execution.
Packages are append-only in the journal and persisted as individual JSON files
under the project state directory.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.authority_model import enforce_component_authority_safe, infer_component_name
from NEXUS.budget_controls import (
    evaluate_budget_controls,
    normalize_budget_control,
    resolve_budget_caps,
    summarize_journal_estimated_costs,
)
from NEXUS.execution_package_hardening import (
    VALID_EXECUTION_FAILURE_CLASSES,
    build_default_hardening_fields,
    derive_idempotency_key,
    evaluate_recovery_summary,
    normalize_failure_summary,
    normalize_idempotency,
    normalize_integrity_verification,
    normalize_recovery_summary,
    normalize_retry_policy,
    normalize_rollback_repair,
    summarize_failure,
    utc_now_iso,
    verify_terminal_execution_integrity,
)
from NEXUS.execution_package_evaluation import (
    evaluate_execution_package_safe,
    normalize_evaluation_basis,
    normalize_evaluation_reason,
    normalize_evaluation_summary,
)
from NEXUS.execution_package_local_analysis import (
    analyze_execution_package_locally_safe,
    normalize_local_analysis_basis,
    normalize_local_analysis_reason,
    normalize_local_analysis_summary,
)
from NEXUS.memory_layer import write_governed_memory_safe
from NEXUS.runtimes.cursor_runtime import (
    build_cursor_bridge_result,
    normalize_cursor_artifact_return,
    normalize_cursor_bridge_handoff,
    validate_cursor_artifact_return,
)
from NEXUS.self_evolution_governance import build_self_change_audit_record
from NEXUS.project_state import load_project_state


EXECUTION_PACKAGE_JOURNAL_FILENAME = "execution_package_journal.jsonl"
EXECUTION_PACKAGE_DIRNAME = "execution_packages"
MAX_EXECUTION_PACKAGE_LIST_LIMIT = 50
SELF_CHANGE_AUDIT_FILENAME = "self_change_audit.jsonl"
REVENUE_PIPELINE_STAGES = {
    "intake",
    "qualified",
    "proposal_pending",
    "follow_up",
    "negotiation",
    "onboarding",
    "delivery",
    "closed_won",
    "closed_lost",
}
REVENUE_WORKFLOW_STATUSES = {
    "ready_for_revenue_action",
    "blocked_for_revenue_action",
    "needs_operator_review",
    "needs_revision",
    "low_value_deferred",
}
REVENUE_WORKFLOW_PRIORITIES = {"low", "medium", "high"}
OPPORTUNITY_CLASSIFICATIONS = {"hot", "warm", "cold", "strategic", "low_margin", "high_margin"}
REVENUE_CANDIDATE_STATUSES = {"ready", "blocked", "deferred", "review_required"}
OPERATOR_ACTION_QUEUE_STATUSES = {
    "ready_operator_action",
    "blocked_operator_action",
    "deferred_operator_action",
    "review_required_operator_action",
}
OPERATOR_ACTION_TYPES = {
    "review_high_value_lead",
    "approve_proposal_generation",
    "send_human_follow_up",
    "review_blocked_opportunity",
    "request_missing_onboarding_details",
    "escalate_negotiation",
    "defer_low_value_opportunity",
}
OPERATOR_ACTION_PRIORITIES = {"low", "medium", "high"}
OPERATOR_ACTION_LIFECYCLE_STATUSES = {
    "pending",
    "acknowledged",
    "in_progress",
    "completed",
    "failed",
    "ignored",
    "cancelled",
}
OPERATOR_ACTION_ATTENTION_STATUSES = {"normal", "needs_attention", "overdue", "escalated"}
OPERATOR_ACTION_REVENUE_EFFECTS = {"unknown", "positive", "negative", "neutral"}
COMMUNICATION_CHANNELS = {"none", "email"}
COMMUNICATION_INTENTS = {
    "none",
    "revenue_follow_up",
    "proposal_nudge",
    "negotiation_checkpoint",
    "onboarding_request",
    "reactivation_touchpoint",
}
COMMUNICATION_STATUSES = {
    "not_prepared",
    "draft_ready",
    "awaiting_approval",
    "approved",
    "denied",
    "sent",
}
COMMUNICATION_APPROVAL_STATUSES = {"not_required", "pending", "approved", "denied"}
COMMUNICATION_DELIVERY_STATUSES = {"not_sent", "delivery_pending", "delivered", "failed"}
FOLLOW_UP_STATUSES = {"not_ready", "follow_up_due", "follow_up_scheduled", "follow_up_not_needed"}
ACTION_SEQUENCE_STATUSES = {"not_started", "active", "waiting", "completed", "abandoned", "stalled"}
ACTION_SEQUENCE_TYPES = {"follow_up", "proposal", "negotiation", "onboarding", "general"}
FOLLOW_UP_INTELLIGENCE_STATUSES = {
    "not_applicable",
    "pending_send",
    "waiting_response",
    "action_recommended",
    "overdue_action",
    "dropoff_risk",
}
FOLLOW_UP_PRIORITIES = {"low", "medium", "high", "critical"}
FOLLOW_UP_RECOMMENDATION_TYPES = {
    "send_second_follow_up",
    "escalate_to_human_review",
    "wait_for_response",
    "prepare_offer",
    "schedule_final_attempt",
    "defer_low_value_follow_up",
}
FOLLOW_UP_WINDOW_STATUSES = {"no_window", "upcoming", "due_now", "overdue"}
FOLLOW_UP_DROPOFF_RISKS = {"low", "medium", "high"}


def _utc_now_iso() -> str:
    return utc_now_iso()


def _build_estimated_cost_tracking(
    *,
    cost_source: str,
    estimated_tokens: int,
    model: str,
) -> dict[str, Any]:
    tokens = max(0, int(estimated_tokens or 0))
    estimated_cost = round((tokens / 1000.0) * 0.004, 6)
    return {
        "cost_estimate": estimated_cost,
        "cost_unit": "usd_estimated",
        "cost_source": str(cost_source or "composed_operation"),
        "cost_breakdown": {
            "model": str(model or "forge_cost_estimator"),
            "estimated_tokens": tokens,
            "estimated_cost": estimated_cost,
        },
    }


def _normalize_cost_tracking(value: Any, *, fallback_source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _build_estimated_cost_tracking(
            cost_source=fallback_source,
            estimated_tokens=0,
            model="forge_cost_estimator",
        )
    cost_estimate = value.get("cost_estimate")
    try:
        parsed_cost_estimate = float(cost_estimate)
    except Exception:
        parsed_cost_estimate = 0.0
    breakdown = value.get("cost_breakdown")
    breakdown_dict = dict(breakdown) if isinstance(breakdown, dict) else {}
    estimated_tokens = breakdown_dict.get("estimated_tokens")
    try:
        parsed_tokens = max(0, int(estimated_tokens))
    except Exception:
        parsed_tokens = 0
    estimated_cost = breakdown_dict.get("estimated_cost")
    try:
        parsed_breakdown_cost = float(estimated_cost)
    except Exception:
        parsed_breakdown_cost = parsed_cost_estimate
    return {
        "cost_estimate": round(max(0.0, parsed_cost_estimate), 6),
        "cost_unit": str(value.get("cost_unit") or "usd_estimated"),
        "cost_source": str(value.get("cost_source") or fallback_source),
        "cost_breakdown": {
            "model": str(breakdown_dict.get("model") or "forge_cost_estimator"),
            "estimated_tokens": parsed_tokens,
            "estimated_cost": round(max(0.0, parsed_breakdown_cost), 6),
        },
    }


def _estimate_package_cost_tracking(package: dict[str, Any] | None) -> dict[str, Any]:
    p = package or {}
    receipt = _normalize_execution_receipt(p.get("execution_receipt"))
    artifacts = [x for x in list(p.get("runtime_artifacts") or []) if isinstance(x, dict)]
    expected_outputs = [x for x in list(p.get("expected_outputs") or []) if str(x).strip()]
    status = str(p.get("execution_status") or "").strip().lower()
    tokens = 140 + (len(expected_outputs) * 45) + (len(artifacts) * 70)
    tokens += max(0, int(receipt.get("files_touched_count") or 0)) * 6
    tokens += max(0, int(receipt.get("artifacts_written_count") or 0)) * 8
    if status in {"failed", "blocked", "rolled_back"}:
        tokens += 60
    source = "runtime_execution" if status not in {"", "pending", "not_started"} else "composed_operation"
    return _build_estimated_cost_tracking(
        cost_source=source,
        estimated_tokens=tokens,
        model="forge_package_cost_estimator",
    )


def _budget_fields_from_control(control: dict[str, Any]) -> dict[str, Any]:
    return {
        "budget_status": str(control.get("budget_status") or "within_budget"),
        "budget_scope": str(control.get("budget_scope") or "operation"),
        "budget_cap": float(control.get("budget_cap") or 0.0),
        "current_estimated_cost": float(control.get("current_estimated_cost") or 0.0),
        "remaining_estimated_budget": float(control.get("remaining_estimated_budget") or 0.0),
        "kill_switch_active": bool(control.get("kill_switch_active")),
        "budget_reason": str(control.get("budget_reason") or ""),
    }


def _resolve_package_budget_caps(package: dict[str, Any] | None, project_path: str | None = None) -> dict[str, Any]:
    p = package or {}
    caps = resolve_budget_caps(p)
    if any(float(caps.get(key) or 0.0) > 0.0 for key in ("operation_budget_cap", "project_budget_cap", "session_budget_cap")):
        return caps
    if not project_path:
        return caps
    project_state = load_project_state(str(project_path))
    return resolve_budget_caps(project_state)


def _build_execution_package_journal_record(normalized: dict[str, Any], package_path: str | None) -> dict[str, Any]:
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
    governance_conflict = metadata.get("governance_conflict") if isinstance(metadata.get("governance_conflict"), dict) else {}
    cursor_bridge = normalized.get("cursor_bridge_summary") if isinstance(normalized.get("cursor_bridge_summary"), dict) else {}
    return {
        "package_id": normalized.get("package_id"),
        "project_name": normalized.get("project_name"),
        "run_id": normalized.get("run_id"),
        "created_at": normalized.get("created_at"),
        "package_status": normalized.get("package_status"),
        "review_status": normalized.get("review_status"),
        "runtime_target_id": normalized.get("runtime_target_id"),
        "requires_human_approval": normalized.get("requires_human_approval"),
        "approval_id_refs": normalized.get("approval_id_refs"),
        "sealed": normalized.get("sealed"),
        "reason": normalized.get("reason"),
        "helix_contract_summary": normalized.get("helix_contract_summary"),
        "package_file": package_path,
        "decision_status": normalized.get("decision_status"),
        "decision_timestamp": normalized.get("decision_timestamp"),
        "decision_actor": normalized.get("decision_actor"),
        "decision_id": normalized.get("decision_id"),
        "eligibility_status": normalized.get("eligibility_status"),
        "eligibility_timestamp": normalized.get("eligibility_timestamp"),
        "eligibility_reason": normalized.get("eligibility_reason"),
        "eligibility_checked_by": normalized.get("eligibility_checked_by"),
        "eligibility_check_id": normalized.get("eligibility_check_id"),
        "release_status": normalized.get("release_status"),
        "release_timestamp": normalized.get("release_timestamp"),
        "release_actor": normalized.get("release_actor"),
        "release_id": normalized.get("release_id"),
        "release_reason": normalized.get("release_reason"),
        "release_version": normalized.get("release_version"),
        "handoff_status": normalized.get("handoff_status"),
        "handoff_timestamp": normalized.get("handoff_timestamp"),
        "handoff_actor": normalized.get("handoff_actor"),
        "handoff_id": normalized.get("handoff_id"),
        "handoff_reason": normalized.get("handoff_reason"),
        "handoff_version": normalized.get("handoff_version"),
        "handoff_executor_target_id": normalized.get("handoff_executor_target_id"),
        "handoff_executor_target_name": normalized.get("handoff_executor_target_name"),
        "execution_status": normalized.get("execution_status"),
        "execution_timestamp": normalized.get("execution_timestamp"),
        "execution_actor": normalized.get("execution_actor"),
        "execution_id": normalized.get("execution_id"),
        "execution_reason": normalized.get("execution_reason"),
        "execution_version": normalized.get("execution_version"),
        "execution_executor_target_id": normalized.get("execution_executor_target_id"),
        "execution_executor_target_name": normalized.get("execution_executor_target_name"),
        "execution_executor_backend_id": normalized.get("execution_executor_backend_id"),
        "rollback_status": normalized.get("rollback_status"),
        "rollback_timestamp": normalized.get("rollback_timestamp"),
        "rollback_reason": normalized.get("rollback_reason"),
        "retry_policy": normalized.get("retry_policy"),
        "idempotency": normalized.get("idempotency"),
        "failure_summary": normalized.get("failure_summary"),
        "recovery_summary": normalized.get("recovery_summary"),
        "rollback_repair": normalized.get("rollback_repair"),
        "integrity_verification": normalized.get("integrity_verification"),
        "evaluation_status": normalized.get("evaluation_status"),
        "evaluation_timestamp": normalized.get("evaluation_timestamp"),
        "evaluation_actor": normalized.get("evaluation_actor"),
        "evaluation_id": normalized.get("evaluation_id"),
        "evaluation_version": normalized.get("evaluation_version"),
        "evaluation_reason": normalized.get("evaluation_reason"),
        "evaluation_basis": normalized.get("evaluation_basis"),
        "evaluation_summary": normalized.get("evaluation_summary"),
        "local_analysis_status": normalized.get("local_analysis_status"),
        "local_analysis_timestamp": normalized.get("local_analysis_timestamp"),
        "local_analysis_actor": normalized.get("local_analysis_actor"),
        "local_analysis_id": normalized.get("local_analysis_id"),
        "local_analysis_version": normalized.get("local_analysis_version"),
        "local_analysis_reason": normalized.get("local_analysis_reason"),
        "local_analysis_basis": normalized.get("local_analysis_basis"),
        "local_analysis_summary": normalized.get("local_analysis_summary"),
        "bridge_task_id": cursor_bridge.get("bridge_task_id"),
        "cursor_bridge_status": cursor_bridge.get("bridge_status"),
        "cursor_bridge_artifact_count": cursor_bridge.get("artifact_count"),
        "cursor_bridge_latest_artifact_type": cursor_bridge.get("latest_artifact_type"),
        "cursor_bridge_latest_validation_status": cursor_bridge.get("latest_validation_status"),
        "governance_conflict_status": governance_conflict.get("status"),
        "governance_conflict_type": governance_conflict.get("conflict_type"),
        "governance_resolution_state": metadata.get("governance_resolution_state"),
        "governance_routing_outcome": metadata.get("governance_routing_outcome"),
        "lead_id": str(normalized.get("lead_id") or ""),
        "opportunity_id": str(normalized.get("opportunity_id") or ""),
        "client_id": str(normalized.get("client_id") or ""),
        "business_function": str(normalized.get("business_function") or ""),
        "pipeline_stage": str(normalized.get("pipeline_stage") or "intake"),
        "next_revenue_action": str(normalized.get("next_revenue_action") or ""),
        "revenue_action_reason": str(normalized.get("revenue_action_reason") or ""),
        "execution_score": _normalize_revenue_ratio(normalized.get("execution_score"), fallback=0.0),
        "roi_estimate": _normalize_revenue_ratio(normalized.get("roi_estimate"), fallback=0.0),
        "conversion_probability": _normalize_revenue_ratio(normalized.get("conversion_probability"), fallback=0.0),
        "time_sensitivity": _normalize_revenue_ratio(normalized.get("time_sensitivity"), fallback=0.0),
        "highest_value_next_action": str(normalized.get("highest_value_next_action") or ""),
        "highest_value_next_action_score": _normalize_revenue_ratio(normalized.get("highest_value_next_action_score"), fallback=0.0),
        "highest_value_next_action_reason": str(normalized.get("highest_value_next_action_reason") or ""),
        "revenue_activation_status": str(normalized.get("revenue_activation_status") or "needs_revision"),
        "revenue_workflow_ready": bool(normalized.get("revenue_workflow_ready")),
        "revenue_workflow_block_reason": str(normalized.get("revenue_workflow_block_reason") or ""),
        "revenue_workflow_priority": str(normalized.get("revenue_workflow_priority") or "medium"),
        "operator_revenue_review_required": bool(normalized.get("operator_revenue_review_required")),
        "revenue_candidate_status": str(normalized.get("revenue_candidate_status") or "review_required"),
        "revenue_candidate_rank": int(normalized.get("revenue_candidate_rank") or 0),
        "revenue_candidate_reason": str(normalized.get("revenue_candidate_reason") or ""),
        "operator_action_queue_status": str(normalized.get("operator_action_queue_status") or "review_required_operator_action"),
        "operator_action_queue_rank": int(normalized.get("operator_action_queue_rank") or 0),
        "operator_action_type": str(normalized.get("operator_action_type") or "send_human_follow_up"),
        "operator_action_reason": str(normalized.get("operator_action_reason") or ""),
        "operator_action_deadline": str(normalized.get("operator_action_deadline") or ""),
        "operator_action_priority": str(normalized.get("operator_action_priority") or "medium"),
        "operator_action_id": str(normalized.get("operator_action_id") or ""),
        "operator_action_status": str(normalized.get("operator_action_status") or "pending"),
        "operator_action_created_at": str(normalized.get("operator_action_created_at") or ""),
        "operator_action_acknowledged_at": str(normalized.get("operator_action_acknowledged_at") or ""),
        "operator_action_started_at": str(normalized.get("operator_action_started_at") or ""),
        "operator_action_completed_at": str(normalized.get("operator_action_completed_at") or ""),
        "operator_action_failed_at": str(normalized.get("operator_action_failed_at") or ""),
        "operator_action_ignored_at": str(normalized.get("operator_action_ignored_at") or ""),
        "operator_action_actor": str(normalized.get("operator_action_actor") or ""),
        "operator_action_notes": str(normalized.get("operator_action_notes") or ""),
        "operator_action_due_at": str(normalized.get("operator_action_due_at") or ""),
        "operator_action_attention_status": str(normalized.get("operator_action_attention_status") or "normal"),
        "operator_action_attention_reason": str(normalized.get("operator_action_attention_reason") or ""),
        "operator_action_overdue": bool(normalized.get("operator_action_overdue")),
        "operator_action_history_count": int(normalized.get("operator_action_history_count") or 0),
        "linked_execution_result": str(normalized.get("linked_execution_result") or ""),
        "linked_conversion_result": str(normalized.get("linked_conversion_result") or ""),
        "linked_revenue_realized": _normalize_revenue_ratio(normalized.get("linked_revenue_realized"), fallback=0.0),
        "linked_communication_delivery_status": str(normalized.get("linked_communication_delivery_status") or "not_sent"),
        "operator_action_effect_on_revenue": str(normalized.get("operator_action_effect_on_revenue") or "unknown"),
        "operator_action_effect_reason": str(normalized.get("operator_action_effect_reason") or ""),
        "action_success_rate": _normalize_revenue_ratio(normalized.get("action_success_rate"), fallback=0.0),
        "action_follow_through_rate": _normalize_revenue_ratio(normalized.get("action_follow_through_rate"), fallback=0.0),
        "action_to_reply_rate": _normalize_revenue_ratio(normalized.get("action_to_reply_rate"), fallback=0.0),
        "action_to_conversion_rate": _normalize_revenue_ratio(normalized.get("action_to_conversion_rate"), fallback=0.0),
        "opportunity_classification": str(normalized.get("opportunity_classification") or "cold"),
        "opportunity_classification_reason": str(normalized.get("opportunity_classification_reason") or ""),
        "communication_channel": str(normalized.get("communication_channel") or "none"),
        "communication_intent": str(normalized.get("communication_intent") or "none"),
        "communication_status": str(normalized.get("communication_status") or "not_prepared"),
        "draft_message_subject": str(normalized.get("draft_message_subject") or ""),
        "draft_message_body": str(normalized.get("draft_message_body") or ""),
        "draft_message_preview": str(normalized.get("draft_message_preview") or ""),
        "communication_requires_approval": bool(normalized.get("communication_requires_approval")),
        "communication_approval_status": str(normalized.get("communication_approval_status") or "pending"),
        "communication_approved_at": str(normalized.get("communication_approved_at") or ""),
        "communication_denied_reason": str(normalized.get("communication_denied_reason") or ""),
        "communication_sent_at": str(normalized.get("communication_sent_at") or ""),
        "communication_delivery_status": str(normalized.get("communication_delivery_status") or "not_sent"),
        "communication_send_eligible": bool(normalized.get("communication_send_eligible")),
        "communication_block_reason": str(normalized.get("communication_block_reason") or ""),
        "operator_review_required_for_send": bool(normalized.get("operator_review_required_for_send")),
        "follow_up_recommended": bool(normalized.get("follow_up_recommended")),
        "follow_up_due_at": str(normalized.get("follow_up_due_at") or ""),
        "follow_up_status": str(normalized.get("follow_up_status") or "not_ready"),
        "follow_up_reason": str(normalized.get("follow_up_reason") or ""),
        "follow_up_sequence_step": int(normalized.get("follow_up_sequence_step") or 0),
        "action_sequence_id": str(normalized.get("action_sequence_id") or ""),
        "action_sequence_type": str(normalized.get("action_sequence_type") or "general"),
        "action_sequence_step": int(normalized.get("action_sequence_step") or 0),
        "action_sequence_total_steps": int(normalized.get("action_sequence_total_steps") or 1),
        "action_sequence_status": str(normalized.get("action_sequence_status") or "not_started"),
        "action_sequence_started_at": str(normalized.get("action_sequence_started_at") or ""),
        "action_sequence_updated_at": str(normalized.get("action_sequence_updated_at") or ""),
        "action_sequence_completed_at": str(normalized.get("action_sequence_completed_at") or ""),
        "action_sequence_abandoned_at": str(normalized.get("action_sequence_abandoned_at") or ""),
        "action_sequence_next_step": str(normalized.get("action_sequence_next_step") or ""),
        "action_sequence_next_step_due_at": str(normalized.get("action_sequence_next_step_due_at") or ""),
        "action_sequence_progress_score": _normalize_revenue_ratio(normalized.get("action_sequence_progress_score"), fallback=0.0),
        "action_sequence_dropoff_detected": bool(normalized.get("action_sequence_dropoff_detected")),
        "action_sequence_dropoff_reason": str(normalized.get("action_sequence_dropoff_reason") or ""),
        "action_sequence_recovery_recommendation": str(normalized.get("action_sequence_recovery_recommendation") or ""),
        "follow_up_intelligence_status": str(normalized.get("follow_up_intelligence_status") or "not_applicable"),
        "follow_up_priority": str(normalized.get("follow_up_priority") or "medium"),
        "follow_up_recommendation": str(normalized.get("follow_up_recommendation") or "wait_for_response"),
        "follow_up_recommendation_reason": str(normalized.get("follow_up_recommendation_reason") or ""),
        "follow_up_overdue": bool(normalized.get("follow_up_overdue")),
        "follow_up_dropoff_risk": str(normalized.get("follow_up_dropoff_risk") or "low"),
        "follow_up_window_status": str(normalized.get("follow_up_window_status") or "no_window"),
        "follow_up_response_rate": _normalize_revenue_ratio(normalized.get("follow_up_response_rate"), fallback=0.0),
        "sequence_completion_rate": _normalize_revenue_ratio(normalized.get("sequence_completion_rate"), fallback=0.0),
        "second_follow_up_success_rate": _normalize_revenue_ratio(normalized.get("second_follow_up_success_rate"), fallback=0.0),
        "stalled_sequence_rate": _normalize_revenue_ratio(normalized.get("stalled_sequence_rate"), fallback=0.0),
        "cost_tracking": _normalize_cost_tracking(normalized.get("cost_tracking"), fallback_source="composed_operation"),
        "budget_caps": resolve_budget_caps(normalized.get("budget_caps") or {}),
        "budget_control": normalize_budget_control(normalized.get("budget_control") or {}),
        "budget_status": str(normalized.get("budget_status") or "within_budget"),
        "budget_scope": str(normalized.get("budget_scope") or "operation"),
        "budget_cap": float(normalized.get("budget_cap") or 0.0),
        "current_estimated_cost": float(normalized.get("current_estimated_cost") or 0.0),
        "remaining_estimated_budget": float(normalized.get("remaining_estimated_budget") or 0.0),
        "kill_switch_active": bool(normalized.get("kill_switch_active")),
        "budget_reason": str(normalized.get("budget_reason") or ""),
    }


def get_execution_package_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for execution packages; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_execution_package_dir(project_path: str | None) -> Path | None:
    """Return per-project execution package directory."""
    state_dir = get_execution_package_state_dir(project_path)
    if not state_dir:
        return None
    try:
        package_dir = state_dir / EXECUTION_PACKAGE_DIRNAME
        package_dir.mkdir(parents=True, exist_ok=True)
        return package_dir
    except Exception:
        return None


def get_execution_package_journal_path(project_path: str | None) -> str | None:
    """Return append-only execution package journal path."""
    state_dir = get_execution_package_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / EXECUTION_PACKAGE_JOURNAL_FILENAME)


def get_execution_package_file_path(project_path: str | None, package_id: str | None) -> str | None:
    """Return full JSON package path for package_id."""
    package_dir = get_execution_package_dir(project_path)
    if not package_dir or not package_id:
        return None
    return str(package_dir / f"{str(package_id).strip()}.json")


def _normalize_eligibility_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_release_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_handoff_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_handoff_aegis_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        from AEGIS.aegis_contract import normalize_aegis_result

        return normalize_aegis_result(value)
    except Exception:
        return {}


def _normalize_executor_backend_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _resolve_executor_backend_id(package: dict[str, Any] | None) -> str:
    p = package or {}
    explicit = _normalize_executor_backend_id(p.get("execution_executor_backend_id"))
    if explicit:
        return explicit
    metadata = p.get("metadata")
    if isinstance(metadata, dict):
        return _normalize_executor_backend_id(metadata.get("executor_backend_id"))
    return ""


def _normalize_execution_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_rollback_reason(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"code": "", "message": ""}
    return {
        "code": str(value.get("code") or ""),
        "message": str(value.get("message") or ""),
    }


def _normalize_evaluation_status(value: Any) -> str:
    status = str(value or "pending").strip().lower()
    if status not in ("pending", "completed", "blocked", "error_fallback"):
        status = "pending"
    return status


def _normalize_local_analysis_status(value: Any) -> str:
    status = str(value or "pending").strip().lower()
    if status not in ("pending", "completed", "blocked", "error_fallback"):
        status = "pending"
    return status


def _normalize_failure_class(value: Any) -> str:
    s = str(value or "").strip().lower()
    return s if s in VALID_EXECUTION_FAILURE_CLASSES else ""


def _normalize_execution_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    exit_code = value.get("exit_code")
    if not isinstance(exit_code, int):
        try:
            exit_code = int(exit_code) if exit_code not in (None, "") else None
        except Exception:
            exit_code = None
    return {
        "result_status": str(value.get("result_status") or ""),
        "exit_code": exit_code,
        "log_ref": str(value.get("log_ref") or ""),
        "files_touched_count": max(0, int(value.get("files_touched_count") or 0)),
        "artifacts_written_count": max(0, int(value.get("artifacts_written_count") or 0)),
        "failure_class": _normalize_failure_class(value.get("failure_class")),
        "stdout_summary": str(value.get("stdout_summary") or ""),
        "stderr_summary": str(value.get("stderr_summary") or ""),
        "rollback_summary": dict(value.get("rollback_summary") or {}),
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _with_package_authority_event(
    package: dict[str, Any] | None,
    *,
    scope: str,
    authority_trace: dict[str, Any] | None = None,
    authority_denial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = dict(package or {})
    metadata = dict(p.get("metadata") or {})
    authority_traces = dict(metadata.get("authority_traces") or {})
    authority_denials = dict(metadata.get("authority_denials") or {})
    if isinstance(authority_trace, dict) and authority_trace:
        authority_traces[str(scope)] = dict(authority_trace)
    if isinstance(authority_denial, dict) and authority_denial:
        authority_denials[str(scope)] = dict(authority_denial)
    metadata["authority_traces"] = authority_traces
    if authority_denials:
        metadata["authority_denials"] = authority_denials
    p["metadata"] = metadata
    return p


def _persist_package_update(
    *,
    project_path: str | None,
    package_id: str | None,
    package: dict[str, Any] | None,
    status: str,
    reason: str,
) -> dict[str, Any]:
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id or normalized.get("package_id"))
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": status, "reason": reason, "package": normalized}
    except Exception:
        return {"status": "error", "reason": f"Failed to persist execution package update: {reason}", "package": None}


def _empty_execution_receipt(*, result_status: str = "", failure_class: str = "", log_ref: str = "", exit_code: int | None = None) -> dict[str, Any]:
    return _normalize_execution_receipt(
        {
            "result_status": result_status,
            "exit_code": exit_code,
            "log_ref": log_ref,
            "files_touched_count": 0,
            "artifacts_written_count": 0,
            "failure_class": failure_class,
        }
    )


def _summarize_execution_receipt(value: Any) -> dict[str, Any]:
    receipt = _normalize_execution_receipt(value)
    return {
        "result_status": receipt.get("result_status") or "",
        "exit_code": receipt.get("exit_code"),
        "files_touched_count": receipt.get("files_touched_count") or 0,
        "artifacts_written_count": receipt.get("artifacts_written_count") or 0,
        "failure_class": receipt.get("failure_class") or "",
        "rollback_summary": dict(receipt.get("rollback_summary") or {}),
    }


def _normalize_cursor_bridge_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    normalized = normalize_cursor_bridge_handoff(
        value,
        authority_trace=value.get("authority_trace"),
        governance_trace=value.get("governance_trace"),
        package_id=value.get("package_id"),
        package_reference=value.get("package_reference"),
        status=str(value.get("status") or value.get("bridge_status") or "pending"),
    )
    return {
        **normalized,
        "bridge_status": str(value.get("bridge_status") or normalized.get("status") or "pending").strip().lower(),
        "bridge_phase": str(value.get("bridge_phase") or ""),
        "authority_scope": str(value.get("authority_scope") or "generation_bridge_only"),
        "execution_enabled": bool(value.get("execution_enabled", False)),
        "handoff_required": bool(value.get("handoff_required", True)),
        "artifact_count": max(0, int(value.get("artifact_count") or 0)),
        "latest_artifact_type": str(value.get("latest_artifact_type") or ""),
        "latest_validation_status": str(value.get("latest_validation_status") or ""),
        "latest_recorded_at": str(value.get("latest_recorded_at") or ""),
        "package_path": str(value.get("package_path") or ""),
    }


def _normalize_cursor_bridge_artifact_record(value: Any) -> dict[str, Any]:
    normalized = normalize_cursor_artifact_return(value if isinstance(value, dict) else {})
    return {
        **normalized,
        "package_path": str((value or {}).get("package_path") or ""),
    }


def _delivery_artifact_label(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    known = {
        "implementation_plan": "Implementation Plan",
        "implementation_summary": "Implementation Summary",
        "summary_report": "Summary Report",
        "review_package": "Review Package",
        "diff_review": "Diff Review",
        "test_report": "Test Report",
        "approved_summary": "Approved Summary",
        "code_artifacts": "Code Artifacts",
    }
    if lowered in known:
        return known[lowered]
    return text.replace("_", " ").replace("-", " ").strip().title()


def _delivery_progress_state_for_package(package: dict[str, Any]) -> str:
    review_status = str(package.get("review_status") or "").strip().lower()
    decision_status = str(package.get("decision_status") or "").strip().lower()
    release_status = str(package.get("release_status") or "").strip().lower()
    execution_status = str(package.get("execution_status") or "").strip().lower()
    runtime_artifacts = [x for x in list(package.get("runtime_artifacts") or []) if isinstance(x, dict)]
    expected_outputs = [str(x).strip() for x in list(package.get("expected_outputs") or []) if str(x).strip()]
    has_artifacts = bool(runtime_artifacts or expected_outputs)
    blocked_states = {"failed", "blocked", "error_fallback", "rejected", "denied"}
    if not has_artifacts:
        if review_status in {"pending", "review_pending"} and not decision_status:
            return "delivery_in_progress"
        if execution_status in {"pending", "not_started", ""}:
            return "no_delivery_summary"
        if execution_status in blocked_states:
            return "internal_review_required"
        return "delivery_in_progress"
    if execution_status in blocked_states or decision_status in {"rejected", "denied"}:
        return "internal_review_required"
    if decision_status == "approved" or release_status == "released" or review_status in {"reviewed", "completed"}:
        return "client_safe_packaging_ready"
    if review_status in {"pending", "review_pending"}:
        return "internal_review_required"
    return "delivery_summary_ready"


def _normalize_revenue_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_revenue_ratio(value: Any, *, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = fallback
    if parsed < 0.0:
        parsed = 0.0
    if parsed > 1.0:
        parsed = 1.0
    return round(parsed, 4)


def _normalize_pipeline_stage(value: Any) -> str:
    stage = str(value or "").strip().lower()
    if stage in REVENUE_PIPELINE_STAGES:
        return stage
    return "intake"


def _derive_pipeline_stage_from_preview(preview: dict[str, Any]) -> str:
    conversion_status = str((preview.get("conversion_summary") or {}).get("conversion_status") or "").strip().lower()
    offer_status = str((preview.get("offer_summary") or {}).get("offer_status") or "").strip().lower()
    response_status = str((preview.get("response_summary") or {}).get("response_status") or "").strip().lower()
    qualification_status = str((preview.get("qualification_summary") or {}).get("qualification_status") or "").strip().lower()
    if conversion_status in {"conversion_ready", "high_touch_conversion_required"}:
        return "proposal_pending"
    if response_status in {"response_ready", "high_touch_required"}:
        return "follow_up"
    if offer_status in {"offer_ready", "high_touch_review_recommended"}:
        return "proposal_pending"
    if qualification_status in {"qualified", "high_priority"}:
        return "qualified"
    return "intake"


def _derive_conversion_probability(*, preview: dict[str, Any], package: dict[str, Any]) -> float:
    explicit = package.get("conversion_probability")
    if explicit is not None:
        return _normalize_revenue_ratio(explicit, fallback=0.0)
    qualification_status = str((preview.get("qualification_summary") or {}).get("qualification_status") or "").strip().lower()
    offer_status = str((preview.get("offer_summary") or {}).get("offer_status") or "").strip().lower()
    response_status = str((preview.get("response_summary") or {}).get("response_status") or "").strip().lower()
    conversion_status = str((preview.get("conversion_summary") or {}).get("conversion_status") or "").strip().lower()
    base = {
        "needs_more_info": 0.22,
        "underqualified": 0.32,
        "qualified": 0.64,
        "high_priority": 0.82,
    }.get(qualification_status, 0.35)
    if offer_status == "offer_ready":
        base += 0.08
    if response_status == "response_ready":
        base += 0.07
    if conversion_status == "conversion_ready":
        base += 0.09
    if offer_status in {"offer_needs_more_info", "no_offer_yet"}:
        base -= 0.1
    if response_status in {"no_response", "needs_more_info"}:
        base -= 0.08
    return _normalize_revenue_ratio(base, fallback=0.35)


def _derive_time_sensitivity(*, preview: dict[str, Any], package: dict[str, Any], pipeline_stage: str) -> float:
    explicit = package.get("time_sensitivity")
    if explicit is not None:
        return _normalize_revenue_ratio(explicit, fallback=0.0)
    urgency = str(((preview.get("qualification_summary") or {}).get("qualification_signals") or {}).get("urgency") or "").strip().lower()
    urgency_score = {"critical": 1.0, "high": 0.82, "medium": 0.58, "low": 0.3}.get(urgency, 0.45)
    if pipeline_stage in {"proposal_pending", "negotiation"}:
        urgency_score += 0.08
    if pipeline_stage in {"closed_won", "closed_lost"}:
        urgency_score = 0.05
    return _normalize_revenue_ratio(urgency_score, fallback=0.45)


def _derive_roi_estimate(
    *,
    preview: dict[str, Any],
    package: dict[str, Any],
    conversion_probability: float,
    cost_tracking: dict[str, Any],
) -> float:
    explicit = package.get("roi_estimate")
    if explicit is not None:
        return _normalize_revenue_ratio(explicit, fallback=0.0)
    budget_band = str(((preview.get("qualification_summary") or {}).get("qualification_signals") or {}).get("budget_band") or "").strip().lower()
    offer_tier = str((preview.get("offer_summary") or {}).get("recommended_package_tier") or "").strip().lower()
    base = {
        "none": 0.18,
        "unknown": 0.22,
        "low": 0.28,
        "medium": 0.55,
        "high": 0.73,
        "enterprise": 0.82,
    }.get(budget_band, 0.45)
    if offer_tier in {"scale", "enterprise"}:
        base += 0.06
    estimated_cost = float(cost_tracking.get("cost_estimate") or 0.0)
    if estimated_cost >= 0.1:
        base -= 0.05
    elif estimated_cost <= 0.01 and estimated_cost > 0:
        base += 0.03
    # ROI should remain bounded by demand signal quality.
    roi = (base * 0.65) + (conversion_probability * 0.35)
    return _normalize_revenue_ratio(roi, fallback=0.45)


def _derive_execution_score(package: dict[str, Any]) -> float:
    explicit = package.get("execution_score")
    if explicit is not None:
        return _normalize_revenue_ratio(explicit, fallback=0.0)
    evaluation = dict(package.get("evaluation_summary") or {})
    local_analysis = dict(package.get("local_analysis_summary") or {})
    quality = _normalize_revenue_ratio((evaluation.get("execution_quality_score") or 0) / 100.0, fallback=0.0)
    confidence = _normalize_revenue_ratio((local_analysis.get("confidence_score") or 0) / 100.0, fallback=0.0)
    if quality <= 0.0 and confidence <= 0.0:
        execution_status = str(package.get("execution_status") or "").strip().lower()
        if execution_status in {"succeeded", "completed"}:
            return 0.72
        if execution_status in {"failed", "blocked", "rolled_back"}:
            return 0.2
        return 0.45
    return _normalize_revenue_ratio((quality * 0.7) + (confidence * 0.3), fallback=0.45)


def _derive_governance_enforcement_posture(package: dict[str, Any]) -> tuple[str, str, str]:
    metadata = dict(package.get("metadata") or {})
    governance_status = str(
        metadata.get("governance_status")
        or package.get("governance_status")
        or ""
    ).strip().lower()
    governance_outcome = str(
        metadata.get("governance_routing_outcome")
        or package.get("governance_routing_outcome")
        or ""
    ).strip().lower()
    enforcement_status = str(
        metadata.get("enforcement_status")
        or package.get("enforcement_status")
        or ""
    ).strip().lower()
    return governance_status, governance_outcome, enforcement_status


def _derive_opportunity_classification(
    *,
    roi_estimate: float,
    conversion_probability: float,
    time_sensitivity: float,
    pipeline_stage: str,
    governance_blocked: bool,
) -> tuple[str, str]:
    if governance_blocked:
        return ("cold", "Governance or enforcement posture blocks progression.")
    if roi_estimate >= 0.82:
        return ("high_margin", "ROI estimate indicates strong value margin.")
    if roi_estimate <= 0.3:
        return ("low_margin", "ROI estimate indicates limited value margin.")
    if pipeline_stage in {"negotiation", "proposal_pending"} and roi_estimate >= 0.7:
        return ("strategic", "Late-stage pipeline with strong ROI signal.")
    if conversion_probability >= 0.75 and time_sensitivity >= 0.65:
        return ("hot", "High conversion probability and urgency indicate immediate revenue potential.")
    if conversion_probability >= 0.5:
        return ("warm", "Moderate conversion probability suggests near-term value.")
    return ("cold", "Low conversion confidence keeps this opportunity in a cold posture.")


def _derive_highest_value_next_action(
    *,
    governance_status: str,
    governance_outcome: str,
    enforcement_status: str,
    pipeline_stage: str,
    execution_score: float,
    roi_estimate: float,
    conversion_probability: float,
    time_sensitivity: float,
    recent_outcome_adjustment: float,
) -> tuple[str, float, str]:
    if governance_status == "blocked" or governance_outcome == "stop":
        return ("escalate human review", 0.18, "Hard governance block requires operator escalation.")
    if enforcement_status in {"approval_required", "manual_review_required", "hold", "blocked"}:
        return ("escalate human review", 0.24, "Enforcement gates require explicit operator handling.")
    if conversion_probability <= 0.25 or roi_estimate <= 0.25:
        return ("delay low-value opportunity", 0.2, "Low conversion and ROI signal suggest deferral.")

    base_score = (
        (execution_score * 0.25)
        + (roi_estimate * 0.3)
        + (conversion_probability * 0.25)
        + (time_sensitivity * 0.2)
        + recent_outcome_adjustment
    )
    base_score = _normalize_revenue_ratio(base_score, fallback=0.0)

    if pipeline_stage in {"intake", "qualified", "follow_up"}:
        action = "send follow-up"
        reason = "Opportunity is in an early engagement stage and benefits from active follow-up."
    elif pipeline_stage in {"proposal_pending", "negotiation"}:
        action = "generate offer"
        reason = "Pipeline stage indicates proposal shaping is the highest-value governed next step."
    elif pipeline_stage == "onboarding":
        action = "request onboarding info"
        reason = "Opportunity is near delivery and needs onboarding details to convert safely."
    elif pipeline_stage == "delivery":
        action = "prioritize high-value opportunity" if base_score >= 0.6 else "delay low-value opportunity"
        reason = "Delivery-stage opportunities are prioritized by combined revenue activation score."
    elif pipeline_stage in {"closed_won", "closed_lost"}:
        action = "delay low-value opportunity"
        reason = "Closed opportunities should not be reactivated automatically."
        base_score = min(base_score, 0.15)
    else:
        action = "escalate human review"
        reason = "Pipeline posture is unclear and requires operator judgment."
        base_score = min(base_score, 0.3)

    if base_score >= 0.72 and conversion_probability >= 0.7:
        action = "prioritize high-value opportunity"
        reason = "Combined execution, ROI, conversion, and urgency signals indicate high value."
    return (action, base_score, reason)


def _derive_revenue_workflow_readiness(
    *,
    governance_status: str,
    governance_outcome: str,
    enforcement_status: str,
    highest_value_next_action_score: float,
    conversion_probability: float,
    roi_estimate: float,
) -> tuple[str, bool, str, str, bool]:
    if governance_status == "blocked" or governance_outcome == "stop" or enforcement_status == "blocked":
        return (
            "blocked_for_revenue_action",
            False,
            "Governance/enforcement hard block is active.",
            "high",
            True,
        )
    if enforcement_status in {"approval_required", "manual_review_required", "hold"}:
        return (
            "needs_operator_review",
            False,
            "Workflow is gated by approval or manual review policy.",
            "high",
            True,
        )
    if conversion_probability < 0.2 and roi_estimate < 0.25:
        return (
            "low_value_deferred",
            False,
            "Opportunity value signal is below activation threshold.",
            "low",
            False,
        )
    if highest_value_next_action_score < 0.28:
        return (
            "needs_revision",
            False,
            "Revenue action confidence is too weak; revise package context.",
            "medium",
            True,
        )
    priority = "high" if highest_value_next_action_score >= 0.72 else "medium"
    return ("ready_for_revenue_action", True, "", priority, False)


def _derive_revenue_candidate_status(workflow_status: str) -> str:
    status = str(workflow_status or "").strip().lower()
    mapped = {
        "ready_for_revenue_action": "ready",
        "blocked_for_revenue_action": "blocked",
        "low_value_deferred": "deferred",
        "needs_operator_review": "review_required",
        "needs_revision": "review_required",
    }.get(status, "review_required")
    if mapped not in REVENUE_CANDIDATE_STATUSES:
        return "review_required"
    return mapped


def _derive_rank_from_score(score: float) -> int:
    bounded = _normalize_revenue_ratio(score, fallback=0.0)
    return int(round(bounded * 100.0))


def _normalize_operator_action_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OPERATOR_ACTION_TYPES:
        return "send_human_follow_up"
    return normalized


def _normalize_operator_action_priority(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OPERATOR_ACTION_PRIORITIES:
        return "medium"
    return normalized


def _derive_operator_action_deadline_days(
    *,
    queue_status: str,
    time_sensitivity: float,
    pipeline_stage: str,
) -> int:
    if queue_status == "blocked_operator_action":
        return 1
    if queue_status == "deferred_operator_action":
        return 14
    if queue_status == "review_required_operator_action":
        return 3
    if pipeline_stage in {"proposal_pending", "negotiation"} and time_sensitivity >= 0.6:
        return 1
    if time_sensitivity >= 0.75:
        return 1
    if time_sensitivity >= 0.5:
        return 3
    return 7


def _derive_operator_action_queue_fields(
    *,
    revenue_candidate_status: str,
    revenue_candidate_reason: str,
    pipeline_stage: str,
    execution_score: float,
    roi_estimate: float,
    conversion_probability: float,
    time_sensitivity: float,
    revenue_workflow_ready: bool,
    governance_status: str,
    governance_outcome: str,
    enforcement_status: str,
    highest_value_next_action_score: float,
) -> dict[str, Any]:
    if revenue_candidate_status == "blocked":
        queue_status = "blocked_operator_action"
        action_type = "review_blocked_opportunity"
        action_reason = revenue_candidate_reason or "Hard governance or enforcement block is active."
        action_priority = "high"
    elif revenue_candidate_status == "deferred":
        queue_status = "deferred_operator_action"
        action_type = "defer_low_value_opportunity"
        action_reason = revenue_candidate_reason or "Revenue signal is below activation thresholds."
        action_priority = "low"
    elif revenue_candidate_status == "review_required" or not revenue_workflow_ready:
        queue_status = "review_required_operator_action"
        action_type = "send_human_follow_up"
        action_reason = revenue_candidate_reason or "Operator review is required before safe progression."
        action_priority = "high" if highest_value_next_action_score >= 0.6 else "medium"
    else:
        queue_status = "ready_operator_action"
        if pipeline_stage == "negotiation":
            action_type = "escalate_negotiation"
            action_reason = "Opportunity is in negotiation with strong readiness."
        elif pipeline_stage == "proposal_pending":
            action_type = "approve_proposal_generation"
            action_reason = "Proposal-ready opportunity should move through operator approval."
        elif pipeline_stage == "onboarding":
            action_type = "request_missing_onboarding_details"
            action_reason = "Onboarding-stage opportunity requires details to progress safely."
        elif conversion_probability >= 0.72 and roi_estimate >= 0.7:
            action_type = "review_high_value_lead"
            action_reason = "Combined conversion and ROI indicate a high-value lead."
        else:
            action_type = "send_human_follow_up"
            action_reason = "Opportunity is ready for governed human follow-up."
        action_priority = "high" if (highest_value_next_action_score >= 0.72 or time_sensitivity >= 0.75) else "medium"

    queue_status = (
        queue_status
        if queue_status in OPERATOR_ACTION_QUEUE_STATUSES
        else "review_required_operator_action"
    )
    normalized_action_type = _normalize_operator_action_type(action_type)
    normalized_action_priority = _normalize_operator_action_priority(action_priority)

    from datetime import timedelta

    deadline_days = _derive_operator_action_deadline_days(
        queue_status=queue_status,
        time_sensitivity=time_sensitivity,
        pipeline_stage=pipeline_stage,
    )
    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)
    queue_rank = _derive_rank_from_score(highest_value_next_action_score)
    if queue_status == "blocked_operator_action":
        queue_rank = min(queue_rank, 25)
    elif queue_status == "deferred_operator_action":
        queue_rank = min(queue_rank, 20)
    elif queue_status == "review_required_operator_action":
        queue_rank = min(queue_rank, 65)

    return {
        "operator_action_queue_status": queue_status,
        "operator_action_queue_rank": queue_rank,
        "operator_action_type": normalized_action_type,
        "operator_action_reason": str(action_reason or "").strip(),
        "operator_action_deadline": deadline.replace(microsecond=0).isoformat(),
        "operator_action_priority": normalized_action_priority,
        "operator_action_trace": {
            "governance_status": governance_status,
            "governance_routing_outcome": governance_outcome,
            "enforcement_status": enforcement_status,
            "pipeline_stage": pipeline_stage,
            "execution_score": execution_score,
            "roi_estimate": roi_estimate,
            "conversion_probability": conversion_probability,
            "time_sensitivity": time_sensitivity,
            "highest_value_next_action_score": highest_value_next_action_score,
        },
    }


def _normalize_communication_channel(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMMUNICATION_CHANNELS:
        return "none"
    return normalized


def _normalize_communication_intent(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMMUNICATION_INTENTS:
        return "none"
    return normalized


def _normalize_communication_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMMUNICATION_STATUSES:
        return "not_prepared"
    return normalized


def _normalize_communication_approval_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMMUNICATION_APPROVAL_STATUSES:
        return "pending"
    return normalized


def _normalize_communication_delivery_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMMUNICATION_DELIVERY_STATUSES:
        return "not_sent"
    return normalized


def _normalize_follow_up_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_STATUSES:
        return "not_ready"
    return normalized


def _normalize_action_sequence_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in ACTION_SEQUENCE_STATUSES:
        return "not_started"
    return normalized


def _normalize_action_sequence_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in ACTION_SEQUENCE_TYPES:
        return "general"
    return normalized


def _normalize_follow_up_intelligence_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_INTELLIGENCE_STATUSES:
        return "not_applicable"
    return normalized


def _normalize_follow_up_priority(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_PRIORITIES:
        return "medium"
    return normalized


def _normalize_follow_up_recommendation(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_RECOMMENDATION_TYPES:
        return "wait_for_response"
    return normalized


def _normalize_follow_up_window_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_WINDOW_STATUSES:
        return "no_window"
    return normalized


def _normalize_follow_up_dropoff_risk(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FOLLOW_UP_DROPOFF_RISKS:
        return "low"
    return normalized


def _normalize_operator_action_lifecycle_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OPERATOR_ACTION_LIFECYCLE_STATUSES:
        return "pending"
    return normalized


def _normalize_operator_action_attention_status(value: Any, *, fallback: str = "normal") -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OPERATOR_ACTION_ATTENTION_STATUSES:
        normalized = str(fallback or "normal").strip().lower()
    if normalized not in OPERATOR_ACTION_ATTENTION_STATUSES:
        return "normal"
    return normalized


def _normalize_operator_action_revenue_effect(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OPERATOR_ACTION_REVENUE_EFFECTS:
        return "unknown"
    return normalized


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _normalize_operator_action_history(value: Any) -> list[dict[str, Any]]:
    history = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in history[-100:]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "event_at": str(item.get("event_at") or item.get("at") or ""),
                "event_type": str(item.get("event_type") or "status_update").strip().lower(),
                "operator_action_status": _normalize_operator_action_lifecycle_status(item.get("operator_action_status") or item.get("status")),
                "operator_action_actor": str(item.get("operator_action_actor") or item.get("actor") or "").strip(),
                "operator_action_notes": str(item.get("operator_action_notes") or item.get("notes") or ""),
                "linked_execution_result": str(item.get("linked_execution_result") or ""),
                "linked_conversion_result": str(item.get("linked_conversion_result") or ""),
                "linked_revenue_realized": _normalize_revenue_ratio(item.get("linked_revenue_realized"), fallback=0.0),
                "linked_communication_delivery_status": _normalize_communication_delivery_status(item.get("linked_communication_delivery_status")),
                "operator_action_effect_on_revenue": _normalize_operator_action_revenue_effect(item.get("operator_action_effect_on_revenue")),
                "operator_action_effect_reason": str(item.get("operator_action_effect_reason") or ""),
            }
        )
    return normalized[-50:]


def _normalize_action_sequence_history(value: Any) -> list[dict[str, Any]]:
    history = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in history[-100:]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "event_at": str(item.get("event_at") or item.get("at") or ""),
                "event_type": str(item.get("event_type") or "sequence_update").strip().lower(),
                "action_sequence_status": _normalize_action_sequence_status(item.get("action_sequence_status")),
                "action_sequence_step": max(0, int(item.get("action_sequence_step") or 0)),
                "action_sequence_total_steps": max(1, int(item.get("action_sequence_total_steps") or 1)),
                "action_sequence_next_step": str(item.get("action_sequence_next_step") or ""),
                "action_sequence_next_step_due_at": str(item.get("action_sequence_next_step_due_at") or ""),
                "action_sequence_actor": str(item.get("action_sequence_actor") or item.get("actor") or "").strip(),
                "action_sequence_notes": str(item.get("action_sequence_notes") or item.get("notes") or ""),
            }
        )
    return normalized[-50:]


def _derive_operator_action_attention_fields(
    *,
    operator_action_status: str,
    operator_action_due_at: str,
    operator_action_priority: str,
    operator_action_queue_status: str,
) -> dict[str, Any]:
    status = _normalize_operator_action_lifecycle_status(operator_action_status)
    due_at = str(operator_action_due_at or "").strip()
    queue_status = str(operator_action_queue_status or "").strip().lower()
    priority = _normalize_operator_action_priority(operator_action_priority)
    now = datetime.now(timezone.utc)
    parsed_due = _parse_iso_datetime(due_at)
    overdue = bool(
        parsed_due
        and parsed_due.tzinfo is not None
        and parsed_due < now
        and status in {"pending", "acknowledged", "in_progress"}
    )

    attention_status = "normal"
    attention_reason = ""
    if overdue:
        attention_status = "overdue"
        attention_reason = "Operator action due time has passed."
    elif queue_status == "blocked_operator_action":
        attention_status = "escalated"
        attention_reason = "Action is blocked and requires explicit human review."
    elif status in {"pending", "acknowledged"} and priority == "high":
        attention_status = "needs_attention"
        attention_reason = "High-priority operator action is still not completed."
    elif status == "failed":
        attention_status = "needs_attention"
        attention_reason = "Operator action failed and needs human follow-up."

    return {
        "operator_action_attention_status": _normalize_operator_action_attention_status(attention_status),
        "operator_action_attention_reason": str(attention_reason or ""),
        "operator_action_overdue": bool(overdue),
    }


def _derive_operator_action_performance_signals(
    *,
    operator_action_history: list[dict[str, Any]],
    operator_action_status: str,
    linked_conversion_result: str,
    linked_communication_delivery_status: str,
) -> dict[str, Any]:
    history = [item for item in operator_action_history if isinstance(item, dict)]
    total_events = len(history)
    status_events = [str(item.get("operator_action_status") or "").strip().lower() for item in history]
    completed_count = sum(1 for s in status_events if s == "completed")
    terminal_count = sum(1 for s in status_events if s in {"completed", "failed", "ignored", "cancelled"})
    progressed_count = sum(1 for s in status_events if s in {"in_progress", "completed", "failed", "ignored", "cancelled"})
    reply_count = sum(
        1
        for item in history
        if str(item.get("linked_communication_delivery_status") or "").strip().lower()
        in {"delivery_pending", "delivered"}
    )
    conversion_count = sum(
        1
        for item in history
        if str(item.get("linked_conversion_result") or "").strip().lower()
        in {"converted", "closed_won", "won", "success"}
    )

    current_status = _normalize_operator_action_lifecycle_status(operator_action_status)
    if total_events == 0 and current_status:
        total_events = 1
        if current_status == "completed":
            completed_count = 1
            terminal_count = 1
            progressed_count = 1
        elif current_status in {"failed", "ignored", "cancelled"}:
            terminal_count = 1
            progressed_count = 1
        elif current_status == "in_progress":
            progressed_count = 1

    if str(linked_communication_delivery_status or "").strip().lower() in {"delivery_pending", "delivered"}:
        reply_count = max(reply_count, 1)
    if str(linked_conversion_result or "").strip().lower() in {"converted", "closed_won", "won", "success"}:
        conversion_count = max(conversion_count, 1)

    denominator_terminal = terminal_count if terminal_count > 0 else total_events if total_events > 0 else 1
    denominator_total = total_events if total_events > 0 else 1

    return {
        "action_success_rate": round(completed_count / denominator_terminal, 4),
        "action_follow_through_rate": round(progressed_count / denominator_total, 4),
        "action_to_reply_rate": round(reply_count / denominator_total, 4),
        "action_to_conversion_rate": round(conversion_count / denominator_total, 4),
    }


def _derive_operator_action_memory_fields(
    *,
    package: dict[str, Any],
    operator_action_fields: dict[str, Any],
    communication_fields: dict[str, Any],
    revenue_candidate_status: str,
) -> dict[str, Any]:
    p = dict(package or {})
    metadata = dict(p.get("metadata") or {})
    now_iso = _utc_now_iso()
    operator_action_id = str(p.get("operator_action_id") or "").strip() or f"opact-{uuid.uuid4().hex[:12]}"
    created_at = str(p.get("operator_action_created_at") or now_iso).strip()
    due_at = str(p.get("operator_action_due_at") or p.get("operator_action_deadline") or operator_action_fields.get("operator_action_deadline") or "").strip()
    status = _normalize_operator_action_lifecycle_status(p.get("operator_action_status"))
    actor = str(p.get("operator_action_actor") or "").strip()
    notes = str(p.get("operator_action_notes") or "")
    linked_execution_result = str(p.get("linked_execution_result") or "")
    linked_conversion_result = str(p.get("linked_conversion_result") or "")
    linked_revenue_realized = _normalize_revenue_ratio(p.get("linked_revenue_realized"), fallback=0.0)
    linked_delivery_status = _normalize_communication_delivery_status(
        p.get("linked_communication_delivery_status") or communication_fields.get("communication_delivery_status")
    )
    effect_on_revenue = _normalize_operator_action_revenue_effect(
        p.get("operator_action_effect_on_revenue")
        or ("negative" if revenue_candidate_status == "blocked" else "unknown")
    )
    effect_reason = str(p.get("operator_action_effect_reason") or "")
    history = _normalize_operator_action_history(
        p.get("operator_action_history")
        or metadata.get("operator_action_history")
    )
    if not history:
        history = [
            {
                "event_at": created_at,
                "event_type": "created",
                "operator_action_status": status,
                "operator_action_actor": actor,
                "operator_action_notes": notes or "Operator action memory initialized.",
                "linked_execution_result": linked_execution_result,
                "linked_conversion_result": linked_conversion_result,
                "linked_revenue_realized": linked_revenue_realized,
                "linked_communication_delivery_status": linked_delivery_status,
                "operator_action_effect_on_revenue": effect_on_revenue,
                "operator_action_effect_reason": effect_reason,
            }
        ]
    attention_fields = _derive_operator_action_attention_fields(
        operator_action_status=status,
        operator_action_due_at=due_at,
        operator_action_priority=str(operator_action_fields.get("operator_action_priority") or "medium"),
        operator_action_queue_status=str(operator_action_fields.get("operator_action_queue_status") or ""),
    )
    performance_signals = _derive_operator_action_performance_signals(
        operator_action_history=history,
        operator_action_status=status,
        linked_conversion_result=linked_conversion_result,
        linked_communication_delivery_status=linked_delivery_status,
    )
    latest_memory = history[-1] if history else {}
    return {
        "operator_action_id": operator_action_id,
        "operator_action_status": status,
        "operator_action_created_at": created_at,
        "operator_action_acknowledged_at": str(p.get("operator_action_acknowledged_at") or ""),
        "operator_action_started_at": str(p.get("operator_action_started_at") or ""),
        "operator_action_completed_at": str(p.get("operator_action_completed_at") or ""),
        "operator_action_failed_at": str(p.get("operator_action_failed_at") or ""),
        "operator_action_ignored_at": str(p.get("operator_action_ignored_at") or ""),
        "operator_action_actor": actor,
        "operator_action_notes": notes,
        "operator_action_due_at": due_at,
        **attention_fields,
        "linked_execution_result": linked_execution_result,
        "linked_conversion_result": linked_conversion_result,
        "linked_revenue_realized": linked_revenue_realized,
        "linked_communication_delivery_status": linked_delivery_status,
        "operator_action_effect_on_revenue": effect_on_revenue,
        "operator_action_effect_reason": effect_reason,
        "operator_action_history": history[-50:],
        "operator_action_history_count": len(history[-50:]),
        "operator_action_latest_memory": latest_memory,
        **performance_signals,
    }


def _derive_communication_intent(pipeline_stage: str, operator_action_type: str) -> str:
    if pipeline_stage == "proposal_pending":
        return "proposal_nudge"
    if pipeline_stage == "negotiation":
        return "negotiation_checkpoint"
    if pipeline_stage == "onboarding":
        return "onboarding_request"
    if operator_action_type == "send_human_follow_up":
        return "revenue_follow_up"
    if pipeline_stage in {"follow_up", "qualified", "intake"}:
        return "reactivation_touchpoint"
    return "revenue_follow_up"


def _derive_email_subject(
    *,
    pipeline_stage: str,
    intent: str,
    business_function: str,
    opportunity_id: str,
    client_id: str,
) -> str:
    scope = opportunity_id or client_id or "opportunity"
    function_tag = business_function.replace("_", " ").strip() or "business"
    if intent == "proposal_nudge":
        return f"Proposal alignment for {scope}"
    if intent == "negotiation_checkpoint":
        return f"Negotiation checkpoint for {scope}"
    if intent == "onboarding_request":
        return f"Onboarding details needed for {scope}"
    if pipeline_stage == "follow_up":
        return f"Follow-up on {scope} next steps"
    return f"{function_tag.title()} update for {scope}"


def _derive_email_body(
    *,
    subject: str,
    pipeline_stage: str,
    intent: str,
    highest_value_next_action: str,
    operator_action_type: str,
    opportunity_id: str,
    client_id: str,
) -> str:
    reference = opportunity_id or client_id or "this opportunity"
    intent_note = {
        "proposal_nudge": "confirm proposal scope and timing",
        "negotiation_checkpoint": "align on open negotiation points",
        "onboarding_request": "collect onboarding details",
        "revenue_follow_up": "move next steps forward",
        "reactivation_touchpoint": "re-engage on the opportunity",
    }.get(intent, "progress revenue planning")
    lines = [
        f"Subject context: {subject}",
        "",
        f"Hello, this is a governed outreach draft regarding {reference}.",
        f"We are currently at pipeline stage '{pipeline_stage}'.",
        f"Recommended intent is to {intent_note}.",
        f"Suggested next action: {highest_value_next_action or operator_action_type or 'review next best action'}.",
        "",
        "If this direction looks right, please confirm a preferred time for a short follow-up.",
        "",
        "Best regards,",
        "FORGE Operator Team",
    ]
    return "\n".join(lines).strip()


def _derive_email_preview(subject: str, body: str) -> str:
    first_line = ""
    for line in str(body or "").splitlines():
        text = str(line or "").strip()
        if text:
            first_line = text
            break
    preview = f"{subject} | {first_line}" if first_line else subject
    return preview[:280]


def _derive_follow_up_foundation(
    *,
    communication_status: str,
    communication_delivery_status: str,
    communication_sent_at: str,
    pipeline_stage: str,
    time_sensitivity: float,
    follow_up_due_at: str,
    follow_up_status: str,
    follow_up_reason: str,
    follow_up_sequence_step: int,
) -> dict[str, Any]:
    sent = bool(str(communication_sent_at or "").strip())
    delivered = communication_delivery_status == "delivered"
    failed = communication_delivery_status == "failed"
    recommended = sent and (delivered or communication_delivery_status == "delivery_pending")
    if failed:
        recommended = True
    reason = str(follow_up_reason or "").strip()
    if not reason:
        if failed:
            reason = "Prior send attempt failed and needs operator follow-up decision."
        elif communication_status == "sent":
            reason = "Sent communication should be reviewed for governed follow-up timing."
        elif not sent:
            reason = "Follow-up is not ready until communication is sent."
        else:
            reason = "Follow-up should be scheduled based on delivery outcome."
    normalized_due_at = str(follow_up_due_at or "").strip()
    normalized_status = _normalize_follow_up_status(follow_up_status)
    if not recommended:
        normalized_status = "not_ready"
        normalized_due_at = ""
    elif normalized_status == "not_ready":
        normalized_status = "follow_up_due"
    if time_sensitivity >= 0.75 and normalized_status == "follow_up_due" and not normalized_due_at:
        from datetime import timedelta

        normalized_due_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    elif normalized_status == "follow_up_due" and not normalized_due_at:
        from datetime import timedelta

        days = 3 if pipeline_stage in {"proposal_pending", "negotiation"} else 5
        normalized_due_at = (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()
    sequence_step = max(0, int(follow_up_sequence_step or 0))
    if recommended and sequence_step <= 0:
        sequence_step = 1
    return {
        "follow_up_recommended": bool(recommended),
        "follow_up_due_at": normalized_due_at,
        "follow_up_status": normalized_status,
        "follow_up_reason": reason,
        "follow_up_sequence_step": sequence_step,
    }


def _derive_action_sequence_total_steps(pipeline_stage: str) -> int:
    if pipeline_stage in {"proposal_pending", "negotiation"}:
        return 4
    if pipeline_stage in {"follow_up", "qualified", "intake"}:
        return 3
    if pipeline_stage == "onboarding":
        return 2
    return 3


def _derive_action_sequence_fields(
    *,
    package: dict[str, Any],
    pipeline_stage: str,
    follow_up_fields: dict[str, Any],
    operator_action_memory_fields: dict[str, Any],
) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    conversion_result = str(operator_action_memory_fields.get("linked_conversion_result") or "").strip().lower()
    operator_action_status = _normalize_operator_action_lifecycle_status(operator_action_memory_fields.get("operator_action_status"))
    follow_up_status = _normalize_follow_up_status(follow_up_fields.get("follow_up_status"))
    follow_up_due_at = str(follow_up_fields.get("follow_up_due_at") or "").strip()

    sequence_id = str(package.get("action_sequence_id") or "").strip() or f"aseq-{str(package.get('package_id') or uuid.uuid4().hex[:12])}"
    sequence_type_map = {
        "proposal_pending": "proposal",
        "negotiation": "negotiation",
        "onboarding": "onboarding",
        "follow_up": "follow_up",
        "qualified": "follow_up",
        "intake": "follow_up",
    }
    sequence_type = _normalize_action_sequence_type(
        package.get("action_sequence_type") or sequence_type_map.get(pipeline_stage, "general")
    )
    total_steps = max(1, int(package.get("action_sequence_total_steps") or _derive_action_sequence_total_steps(pipeline_stage)))
    step = max(
        0,
        int(
            package.get("action_sequence_step")
            or follow_up_fields.get("follow_up_sequence_step")
            or 0
        ),
    )

    explicit_status = _normalize_action_sequence_status(package.get("action_sequence_status"))
    derived_status = "not_started"
    converted = conversion_result in {"converted", "closed_won", "won", "success"}
    if converted or operator_action_status == "completed":
        derived_status = "completed"
    elif operator_action_status in {"ignored", "cancelled"}:
        derived_status = "abandoned"
    elif follow_up_status == "follow_up_due" and follow_up_due_at and _parse_iso_datetime(follow_up_due_at):
        parsed_due = _parse_iso_datetime(follow_up_due_at)
        if parsed_due and parsed_due.tzinfo is not None and parsed_due < datetime.now(timezone.utc):
            derived_status = "stalled"
        else:
            derived_status = "active"
    elif follow_up_status == "follow_up_scheduled":
        derived_status = "waiting"
    elif operator_action_status in {"pending", "acknowledged", "in_progress"} or bool(follow_up_fields.get("follow_up_recommended")):
        derived_status = "active"
    status = explicit_status if explicit_status != "not_started" else derived_status
    if status in {"completed", "abandoned"}:
        status = status
    elif derived_status in {"completed", "abandoned", "stalled"}:
        status = derived_status

    if status in {"active", "waiting", "stalled"} and step <= 0:
        step = 1
    if status == "completed":
        step = max(step, total_steps)

    next_step = str(package.get("action_sequence_next_step") or "").strip()
    if status in {"completed", "abandoned"}:
        next_step = ""
    elif not next_step:
        next_step = f"follow_up_step_{min(step + 1, total_steps)}"

    next_step_due_at = str(package.get("action_sequence_next_step_due_at") or follow_up_due_at or "").strip()
    if status in {"completed", "abandoned"}:
        next_step_due_at = ""

    started_at = str(package.get("action_sequence_started_at") or "")
    if not started_at and status in {"active", "waiting", "stalled", "completed", "abandoned"}:
        started_at = now_iso
    completed_at = str(package.get("action_sequence_completed_at") or "")
    abandoned_at = str(package.get("action_sequence_abandoned_at") or "")
    if status == "completed" and not completed_at:
        completed_at = now_iso
    if status == "abandoned" and not abandoned_at:
        abandoned_at = now_iso

    base_progress = round(min(1.0, max(0.0, step / max(total_steps, 1))), 4)
    if status == "completed":
        progress_score = 1.0
    elif status == "abandoned":
        progress_score = round(min(1.0, base_progress * 0.5), 4)
    elif status == "stalled":
        progress_score = round(min(1.0, base_progress * 0.75), 4)
    else:
        progress_score = base_progress

    history = _normalize_action_sequence_history(
        package.get("action_sequence_history")
        or (dict(package.get("metadata") or {}).get("action_sequence_history"))
    )

    return {
        "action_sequence_id": sequence_id,
        "action_sequence_type": sequence_type,
        "action_sequence_step": step,
        "action_sequence_total_steps": total_steps,
        "action_sequence_status": status,
        "action_sequence_started_at": started_at,
        "action_sequence_updated_at": now_iso,
        "action_sequence_completed_at": completed_at if status == "completed" else "",
        "action_sequence_abandoned_at": abandoned_at if status == "abandoned" else "",
        "action_sequence_next_step": next_step,
        "action_sequence_next_step_due_at": next_step_due_at,
        "action_sequence_progress_score": progress_score,
        "action_sequence_history": history,
    }


def _derive_action_sequence_dropoff_fields(
    *,
    package: dict[str, Any],
    action_sequence_fields: dict[str, Any],
    follow_up_fields: dict[str, Any],
    operator_action_memory_fields: dict[str, Any],
    conversion_probability: float,
    roi_estimate: float,
) -> dict[str, Any]:
    sequence_status = _normalize_action_sequence_status(action_sequence_fields.get("action_sequence_status"))
    sequence_step = max(0, int(action_sequence_fields.get("action_sequence_step") or 0))
    follow_up_due_at = str(follow_up_fields.get("follow_up_due_at") or "").strip()
    follow_up_status = _normalize_follow_up_status(follow_up_fields.get("follow_up_status"))
    communication_sent_at = str(package.get("communication_sent_at") or "").strip()
    operator_overdue = bool(operator_action_memory_fields.get("operator_action_overdue"))
    action_to_reply_rate = _normalize_revenue_ratio(operator_action_memory_fields.get("action_to_reply_rate"), fallback=0.0)
    action_to_conversion_rate = _normalize_revenue_ratio(operator_action_memory_fields.get("action_to_conversion_rate"), fallback=0.0)
    converted = str(operator_action_memory_fields.get("linked_conversion_result") or "").strip().lower() in {
        "converted",
        "closed_won",
        "won",
        "success",
    }

    reason = ""
    recovery = "wait_for_response"
    detected = False

    due_dt = _parse_iso_datetime(follow_up_due_at)
    overdue_follow_up = bool(due_dt and due_dt.tzinfo is not None and due_dt < datetime.now(timezone.utc))

    if sequence_status == "stalled":
        detected = True
        reason = "sequence_stalled"
        recovery = "escalate_to_human_review"
    elif communication_sent_at and overdue_follow_up and not converted:
        detected = True
        reason = "no_response_window_elapsed"
        recovery = "send_second_follow_up" if sequence_step <= 1 else "schedule_final_attempt"
    elif (conversion_probability >= 0.6 or roi_estimate >= 0.6) and operator_overdue:
        detected = True
        reason = "high_value_no_operator_follow_through"
        recovery = "escalate_to_human_review"
    elif sequence_step >= 2 and action_to_reply_rate < 0.2 and action_to_conversion_rate < 0.1 and not converted:
        detected = True
        reason = "repeated_follow_up_no_progress"
        recovery = "defer_low_value_follow_up"

    if not detected and follow_up_status == "follow_up_not_needed":
        recovery = "wait_for_response"

    return {
        "action_sequence_dropoff_detected": bool(detected),
        "action_sequence_dropoff_reason": reason,
        "action_sequence_recovery_recommendation": _normalize_follow_up_recommendation(recovery),
    }


def _derive_follow_up_intelligence_fields(
    *,
    package: dict[str, Any],
    action_sequence_fields: dict[str, Any],
    follow_up_fields: dict[str, Any],
    dropoff_fields: dict[str, Any],
    conversion_probability: float,
    roi_estimate: float,
    time_sensitivity: float,
    opportunity_classification: str,
) -> dict[str, Any]:
    status = _normalize_action_sequence_status(action_sequence_fields.get("action_sequence_status"))
    due_at = str(follow_up_fields.get("follow_up_due_at") or "").strip()
    due_dt = _parse_iso_datetime(due_at)
    now = datetime.now(timezone.utc)
    overdue = bool(due_dt and due_dt.tzinfo is not None and due_dt < now)
    window_status = "no_window"
    if due_dt and due_dt.tzinfo is not None:
        if due_dt < now:
            window_status = "overdue"
        elif (due_dt - now).total_seconds() <= 12 * 3600:
            window_status = "due_now"
        else:
            window_status = "upcoming"

    recommendation = "wait_for_response"
    recommendation_reason = "Awaiting next governed follow-up checkpoint."
    intelligence_status = "not_applicable"
    priority = "medium"
    dropoff_risk = "low"

    if status in {"completed", "abandoned"}:
        intelligence_status = "not_applicable"
        recommendation = "wait_for_response"
        recommendation_reason = "Action sequence is in a terminal state."
        priority = "low"
    elif bool(dropoff_fields.get("action_sequence_dropoff_detected")):
        intelligence_status = "dropoff_risk"
        recommendation = str(dropoff_fields.get("action_sequence_recovery_recommendation") or "escalate_to_human_review")
        recommendation_reason = str(dropoff_fields.get("action_sequence_dropoff_reason") or "Drop-off risk detected.")
        priority = "critical" if (conversion_probability >= 0.6 or roi_estimate >= 0.6) else "high"
        dropoff_risk = "high"
    elif str(package.get("communication_status") or "").strip().lower() != "sent":
        intelligence_status = "pending_send"
        recommendation = "prepare_offer" if str(package.get("pipeline_stage") or "").strip().lower() == "proposal_pending" else "wait_for_response"
        recommendation_reason = "Follow-up sequence is gated until governed communication send occurs."
        priority = "high" if time_sensitivity >= 0.7 else "medium"
        dropoff_risk = "medium" if time_sensitivity >= 0.7 else "low"
    elif overdue:
        intelligence_status = "overdue_action"
        recommendation = "send_second_follow_up" if int(action_sequence_fields.get("action_sequence_step") or 0) <= 1 else "schedule_final_attempt"
        recommendation_reason = "Follow-up window is overdue for this sequence step."
        priority = "high" if conversion_probability >= 0.5 else "medium"
        dropoff_risk = "high" if conversion_probability >= 0.5 else "medium"
    elif str(package.get("communication_delivery_status") or "").strip().lower() in {"delivery_pending", "delivered"}:
        intelligence_status = "waiting_response"
        recommendation = "wait_for_response"
        recommendation_reason = "Communication is sent; waiting within governed response window."
        priority = "medium"
        dropoff_risk = "medium" if opportunity_classification in {"strategic", "hot"} else "low"
    else:
        intelligence_status = "action_recommended"
        recommendation = "send_second_follow_up"
        recommendation_reason = "Next governed follow-up action is recommended."
        priority = "high" if (roi_estimate >= 0.6 or time_sensitivity >= 0.7) else "medium"
        dropoff_risk = "medium"

    return {
        "follow_up_intelligence_status": _normalize_follow_up_intelligence_status(intelligence_status),
        "follow_up_priority": _normalize_follow_up_priority(priority),
        "follow_up_recommendation": _normalize_follow_up_recommendation(recommendation),
        "follow_up_recommendation_reason": str(recommendation_reason or ""),
        "follow_up_sequence_step": max(0, int(action_sequence_fields.get("action_sequence_step") or 0)),
        "follow_up_overdue": bool(overdue),
        "follow_up_dropoff_risk": _normalize_follow_up_dropoff_risk(dropoff_risk),
        "follow_up_window_status": _normalize_follow_up_window_status(window_status),
    }


def _derive_follow_up_performance_signals(
    *,
    operator_action_history: list[dict[str, Any]],
    action_sequence_history: list[dict[str, Any]],
    action_sequence_status: str,
    action_sequence_step: int,
) -> dict[str, Any]:
    action_events = [item for item in operator_action_history if isinstance(item, dict)]
    sequence_events = [item for item in action_sequence_history if isinstance(item, dict)]

    follow_up_attempts = max(
        1,
        sum(
            1
            for item in action_events
            if str(item.get("operator_action_status") or "").strip().lower() in {"acknowledged", "in_progress", "completed", "failed", "ignored"}
        ),
    )
    follow_up_responses = sum(
        1
        for item in action_events
        if str(item.get("linked_conversion_result") or "").strip().lower() in {"replied", "converted", "closed_won", "won", "success"}
    )

    sequence_started = max(
        1,
        sum(
            1
            for item in sequence_events
            if str(item.get("action_sequence_status") or "").strip().lower() in {"active", "waiting", "stalled", "completed", "abandoned"}
        )
        or (1 if action_sequence_step > 0 or action_sequence_status != "not_started" else 0),
    )
    sequence_completed = sum(
        1
        for item in sequence_events
        if str(item.get("action_sequence_status") or "").strip().lower() == "completed"
    ) or (1 if action_sequence_status == "completed" else 0)
    stalled_sequences = sum(
        1
        for item in sequence_events
        if str(item.get("action_sequence_status") or "").strip().lower() == "stalled"
    ) or (1 if action_sequence_status == "stalled" else 0)

    second_follow_up_attempts = sum(
        1
        for item in sequence_events
        if int(item.get("action_sequence_step") or 0) >= 2
    ) or (1 if action_sequence_step >= 2 else 0)
    second_follow_up_successes = sum(
        1
        for item in action_events
        if str(item.get("linked_conversion_result") or "").strip().lower() in {"converted", "closed_won", "won", "success"}
    )

    return {
        "follow_up_response_rate": round(min(1.0, follow_up_responses / max(1, follow_up_attempts)), 4),
        "sequence_completion_rate": round(min(1.0, sequence_completed / max(1, sequence_started)), 4),
        "second_follow_up_success_rate": round(min(1.0, second_follow_up_successes / max(1, second_follow_up_attempts)), 4),
        "stalled_sequence_rate": round(min(1.0, stalled_sequences / max(1, sequence_started)), 4),
    }


def _derive_communication_fields(
    *,
    package: dict[str, Any],
    pipeline_stage: str,
    business_function: str,
    opportunity_id: str,
    client_id: str,
    highest_value_next_action: str,
    time_sensitivity: float,
    governance_status: str,
    governance_outcome: str,
    enforcement_status: str,
    revenue_workflow_ready: bool,
    revenue_candidate_status: str,
    operator_action_queue_status: str,
    operator_action_type: str,
) -> dict[str, Any]:
    hard_blocked = (
        governance_status == "blocked"
        or governance_outcome == "stop"
        or enforcement_status == "blocked"
        or revenue_candidate_status == "blocked"
        or operator_action_queue_status == "blocked_operator_action"
    )
    channel = _normalize_communication_channel(package.get("communication_channel") or ("none" if hard_blocked else "email"))
    intent = _normalize_communication_intent(
        package.get("communication_intent")
        or (
            _derive_communication_intent(pipeline_stage, operator_action_type)
            if channel == "email"
            else "none"
        )
    )
    derived_subject = ""
    derived_body = ""
    derived_preview = ""
    if channel == "email" and not hard_blocked:
        derived_subject = _derive_email_subject(
            pipeline_stage=pipeline_stage,
            intent=intent,
            business_function=business_function,
            opportunity_id=opportunity_id,
            client_id=client_id,
        )
        derived_body = _derive_email_body(
            subject=derived_subject,
            pipeline_stage=pipeline_stage,
            intent=intent,
            highest_value_next_action=highest_value_next_action,
            operator_action_type=operator_action_type,
            opportunity_id=opportunity_id,
            client_id=client_id,
        )
        derived_preview = _derive_email_preview(derived_subject, derived_body)

    draft_subject = str(package.get("draft_message_subject") or derived_subject)
    draft_body = str(package.get("draft_message_body") or derived_body)
    draft_preview = str(package.get("draft_message_preview") or derived_preview or _derive_email_preview(draft_subject, draft_body))
    has_draft = bool(draft_subject.strip() and draft_body.strip())

    requires_approval = bool(package.get("communication_requires_approval", channel == "email"))
    approval_status = _normalize_communication_approval_status(
        package.get("communication_approval_status")
        or ("pending" if requires_approval and has_draft else "not_required")
    )
    approved_at = str(package.get("communication_approved_at") or "")
    denied_reason = str(package.get("communication_denied_reason") or "")
    sent_at = str(package.get("communication_sent_at") or "")
    delivery_status = _normalize_communication_delivery_status(
        package.get("communication_delivery_status") or ("delivery_pending" if sent_at else "not_sent")
    )
    if approval_status == "denied" and not denied_reason:
        denied_reason = "Denied by operator decision."

    default_status = "not_prepared"
    if has_draft:
        default_status = "draft_ready"
        if approval_status == "pending":
            default_status = "awaiting_approval"
        if approval_status == "approved":
            default_status = "approved"
        if approval_status == "denied":
            default_status = "denied"
        if sent_at:
            default_status = "sent"
    communication_status = _normalize_communication_status(package.get("communication_status") or default_status)
    if not has_draft:
        communication_status = "not_prepared"
        if not sent_at:
            delivery_status = "not_sent"

    operator_review_required_for_send = bool(
        operator_action_queue_status in {"blocked_operator_action", "review_required_operator_action"}
        or not revenue_workflow_ready
        or enforcement_status in {"manual_review_required", "approval_required", "hold"}
    )
    block_reason = ""
    if hard_blocked:
        block_reason = "Governance or enforcement posture hard-blocks outbound communication."
    elif channel != "email":
        block_reason = "Communication channel is not configured for governed email."
    elif not has_draft:
        block_reason = "No email draft is prepared."
    elif approval_status != "approved":
        block_reason = "Email draft requires explicit approval before send."
    elif operator_review_required_for_send:
        block_reason = "Operator review gate must clear before send eligibility."
    elif sent_at:
        block_reason = "Email has already been sent."

    send_eligible = not bool(block_reason)
    follow_up = _derive_follow_up_foundation(
        communication_status=communication_status,
        communication_delivery_status=delivery_status,
        communication_sent_at=sent_at,
        pipeline_stage=pipeline_stage,
        time_sensitivity=time_sensitivity,
        follow_up_due_at=str(package.get("follow_up_due_at") or ""),
        follow_up_status=str(package.get("follow_up_status") or ""),
        follow_up_reason=str(package.get("follow_up_reason") or ""),
        follow_up_sequence_step=max(0, int(package.get("follow_up_sequence_step") or 0)),
    )
    return {
        "communication_channel": channel,
        "communication_intent": intent,
        "communication_status": communication_status,
        "draft_message_subject": draft_subject,
        "draft_message_body": draft_body,
        "draft_message_preview": draft_preview,
        "communication_requires_approval": requires_approval,
        "communication_approval_status": approval_status,
        "communication_approved_at": approved_at,
        "communication_denied_reason": denied_reason,
        "communication_sent_at": sent_at,
        "communication_delivery_status": delivery_status,
        "communication_send_eligible": bool(send_eligible),
        "communication_block_reason": str(block_reason or ""),
        "operator_review_required_for_send": operator_review_required_for_send,
        **follow_up,
    }


def _derive_revenue_activation_fields(package: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(package.get("metadata") or {})
    revenue_context = dict(metadata.get("revenue_pipeline_context") or {})
    revenue_preview = dict(metadata.get("revenue_preview") or {})
    cost_tracking = _normalize_cost_tracking(package.get("cost_tracking"), fallback_source="composed_operation")

    lead_id = _normalize_revenue_text(package.get("lead_id") or revenue_context.get("lead_id"))
    opportunity_id = _normalize_revenue_text(package.get("opportunity_id") or revenue_context.get("opportunity_id"))
    client_id = _normalize_revenue_text(package.get("client_id") or revenue_context.get("client_id"))
    business_function = _normalize_revenue_text(
        package.get("business_function") or revenue_context.get("business_function") or "general"
    ).lower()

    raw_pipeline_stage = (
        package.get("pipeline_stage")
        or revenue_context.get("pipeline_stage")
        or _derive_pipeline_stage_from_preview(revenue_preview)
    )
    pipeline_stage = _normalize_pipeline_stage(raw_pipeline_stage)

    conversion_probability = _derive_conversion_probability(preview=revenue_preview, package=package)
    time_sensitivity = _derive_time_sensitivity(preview=revenue_preview, package=package, pipeline_stage=pipeline_stage)
    roi_estimate = _derive_roi_estimate(
        preview=revenue_preview,
        package=package,
        conversion_probability=conversion_probability,
        cost_tracking=cost_tracking,
    )
    execution_score = _derive_execution_score(package)

    governance_status, governance_outcome, enforcement_status = _derive_governance_enforcement_posture(package)
    recent_outcomes = list(metadata.get("revenue_recent_outcomes") or [])
    won_count = sum(1 for item in recent_outcomes if str((item or {}).get("status") or "").strip().lower() == "closed_won")
    lost_count = sum(1 for item in recent_outcomes if str((item or {}).get("status") or "").strip().lower() == "closed_lost")
    recent_outcome_adjustment = _normalize_revenue_ratio((won_count - lost_count) * 0.02, fallback=0.0)

    highest_action, highest_action_score, highest_action_reason = _derive_highest_value_next_action(
        governance_status=governance_status,
        governance_outcome=governance_outcome,
        enforcement_status=enforcement_status,
        pipeline_stage=pipeline_stage,
        execution_score=execution_score,
        roi_estimate=roi_estimate,
        conversion_probability=conversion_probability,
        time_sensitivity=time_sensitivity,
        recent_outcome_adjustment=recent_outcome_adjustment,
    )
    next_revenue_action = _normalize_revenue_text(
        package.get("next_revenue_action") or revenue_context.get("next_revenue_action") or highest_action
    )
    revenue_action_reason = _normalize_revenue_text(
        package.get("revenue_action_reason") or revenue_context.get("revenue_action_reason") or highest_action_reason
    )

    workflow_status, workflow_ready, workflow_block_reason, workflow_priority, operator_review = _derive_revenue_workflow_readiness(
        governance_status=governance_status,
        governance_outcome=governance_outcome,
        enforcement_status=enforcement_status,
        highest_value_next_action_score=highest_action_score,
        conversion_probability=conversion_probability,
        roi_estimate=roi_estimate,
    )
    opportunity_classification, opportunity_classification_reason = _derive_opportunity_classification(
        roi_estimate=roi_estimate,
        conversion_probability=conversion_probability,
        time_sensitivity=time_sensitivity,
        pipeline_stage=pipeline_stage,
        governance_blocked=(workflow_status == "blocked_for_revenue_action"),
    )
    if opportunity_classification not in OPPORTUNITY_CLASSIFICATIONS:
        opportunity_classification = "cold"
    if workflow_status not in REVENUE_WORKFLOW_STATUSES:
        workflow_status = "needs_revision"
    if workflow_priority not in REVENUE_WORKFLOW_PRIORITIES:
        workflow_priority = "medium"
    revenue_candidate_status = _derive_revenue_candidate_status(workflow_status)
    revenue_candidate_rank = _derive_rank_from_score(highest_action_score)
    if revenue_candidate_status == "blocked":
        revenue_candidate_reason = "Governance or enforcement posture blocks this revenue candidate."
    elif revenue_candidate_status == "deferred":
        revenue_candidate_reason = "Value and conversion signals are below governed activation thresholds."
    elif revenue_candidate_status == "review_required":
        revenue_candidate_reason = workflow_block_reason or "Operator review is required before routing this candidate."
    else:
        revenue_candidate_reason = "Candidate is eligible for governed operator action routing."
    operator_action_fields = _derive_operator_action_queue_fields(
        revenue_candidate_status=revenue_candidate_status,
        revenue_candidate_reason=revenue_candidate_reason,
        pipeline_stage=pipeline_stage,
        execution_score=execution_score,
        roi_estimate=roi_estimate,
        conversion_probability=conversion_probability,
        time_sensitivity=time_sensitivity,
        revenue_workflow_ready=workflow_ready,
        governance_status=governance_status,
        governance_outcome=governance_outcome,
        enforcement_status=enforcement_status,
        highest_value_next_action_score=highest_action_score,
    )
    communication_fields = _derive_communication_fields(
        package=package,
        pipeline_stage=pipeline_stage,
        business_function=business_function,
        opportunity_id=opportunity_id,
        client_id=client_id,
        highest_value_next_action=highest_action,
        time_sensitivity=time_sensitivity,
        governance_status=governance_status,
        governance_outcome=governance_outcome,
        enforcement_status=enforcement_status,
        revenue_workflow_ready=workflow_ready,
        revenue_candidate_status=revenue_candidate_status,
        operator_action_queue_status=str(operator_action_fields.get("operator_action_queue_status") or ""),
        operator_action_type=str(operator_action_fields.get("operator_action_type") or ""),
    )
    operator_action_memory_fields = _derive_operator_action_memory_fields(
        package=package,
        operator_action_fields=operator_action_fields,
        communication_fields=communication_fields,
        revenue_candidate_status=revenue_candidate_status,
    )
    action_sequence_fields = _derive_action_sequence_fields(
        package=package,
        pipeline_stage=pipeline_stage,
        follow_up_fields=communication_fields,
        operator_action_memory_fields=operator_action_memory_fields,
    )
    dropoff_fields = _derive_action_sequence_dropoff_fields(
        package=package,
        action_sequence_fields=action_sequence_fields,
        follow_up_fields=communication_fields,
        operator_action_memory_fields=operator_action_memory_fields,
        conversion_probability=conversion_probability,
        roi_estimate=roi_estimate,
    )
    follow_up_intelligence_fields = _derive_follow_up_intelligence_fields(
        package=package,
        action_sequence_fields=action_sequence_fields,
        follow_up_fields=communication_fields,
        dropoff_fields=dropoff_fields,
        conversion_probability=conversion_probability,
        roi_estimate=roi_estimate,
        time_sensitivity=time_sensitivity,
        opportunity_classification=opportunity_classification,
    )
    follow_up_performance_fields = _derive_follow_up_performance_signals(
        operator_action_history=list(operator_action_memory_fields.get("operator_action_history") or []),
        action_sequence_history=list(action_sequence_fields.get("action_sequence_history") or []),
        action_sequence_status=str(action_sequence_fields.get("action_sequence_status") or "not_started"),
        action_sequence_step=int(action_sequence_fields.get("action_sequence_step") or 0),
    )

    return {
        "lead_id": lead_id,
        "opportunity_id": opportunity_id,
        "client_id": client_id,
        "business_function": business_function,
        "pipeline_stage": pipeline_stage,
        "next_revenue_action": next_revenue_action,
        "revenue_action_reason": revenue_action_reason,
        "execution_score": execution_score,
        "roi_estimate": roi_estimate,
        "conversion_probability": conversion_probability,
        "time_sensitivity": time_sensitivity,
        "highest_value_next_action": highest_action,
        "highest_value_next_action_score": highest_action_score,
        "highest_value_next_action_reason": highest_action_reason,
        "revenue_activation_status": workflow_status,
        "revenue_workflow_ready": workflow_ready,
        "revenue_workflow_block_reason": workflow_block_reason,
        "revenue_workflow_priority": workflow_priority,
        "operator_revenue_review_required": operator_review,
        "revenue_candidate_status": revenue_candidate_status,
        "revenue_candidate_rank": revenue_candidate_rank,
        "revenue_candidate_reason": revenue_candidate_reason,
        "opportunity_classification": opportunity_classification,
        "opportunity_classification_reason": opportunity_classification_reason,
        **operator_action_fields,
        **communication_fields,
        **operator_action_memory_fields,
        **action_sequence_fields,
        **dropoff_fields,
        **follow_up_intelligence_fields,
        **follow_up_performance_fields,
        "revenue_activation_trace": {
            "signals": {
                "execution_score": execution_score,
                "roi_estimate": roi_estimate,
                "conversion_probability": conversion_probability,
                "time_sensitivity": time_sensitivity,
                "pipeline_stage": pipeline_stage,
                "governance_status": governance_status,
                "governance_routing_outcome": governance_outcome,
                "enforcement_status": enforcement_status,
                "recent_outcome_adjustment": recent_outcome_adjustment,
            },
            "classification_reason": opportunity_classification_reason,
            "workflow_status": workflow_status,
            "revenue_candidate_status": revenue_candidate_status,
            "revenue_candidate_rank": revenue_candidate_rank,
            "operator_action_queue_status": operator_action_fields.get("operator_action_queue_status"),
            "operator_action_queue_rank": operator_action_fields.get("operator_action_queue_rank"),
            "operator_action_type": operator_action_fields.get("operator_action_type"),
            "operator_action_priority": operator_action_fields.get("operator_action_priority"),
            "operator_action_status": operator_action_memory_fields.get("operator_action_status"),
            "operator_action_attention_status": operator_action_memory_fields.get("operator_action_attention_status"),
            "operator_action_overdue": operator_action_memory_fields.get("operator_action_overdue"),
            "action_success_rate": operator_action_memory_fields.get("action_success_rate"),
            "action_follow_through_rate": operator_action_memory_fields.get("action_follow_through_rate"),
            "action_to_reply_rate": operator_action_memory_fields.get("action_to_reply_rate"),
            "action_to_conversion_rate": operator_action_memory_fields.get("action_to_conversion_rate"),
            "communication_status": communication_fields.get("communication_status"),
            "communication_send_eligible": communication_fields.get("communication_send_eligible"),
            "communication_approval_status": communication_fields.get("communication_approval_status"),
            "action_sequence_status": action_sequence_fields.get("action_sequence_status"),
            "action_sequence_step": action_sequence_fields.get("action_sequence_step"),
            "action_sequence_total_steps": action_sequence_fields.get("action_sequence_total_steps"),
            "action_sequence_progress_score": action_sequence_fields.get("action_sequence_progress_score"),
            "follow_up_intelligence_status": follow_up_intelligence_fields.get("follow_up_intelligence_status"),
            "follow_up_recommendation": follow_up_intelligence_fields.get("follow_up_recommendation"),
            "follow_up_priority": follow_up_intelligence_fields.get("follow_up_priority"),
            "follow_up_window_status": follow_up_intelligence_fields.get("follow_up_window_status"),
            "action_sequence_dropoff_detected": dropoff_fields.get("action_sequence_dropoff_detected"),
            "action_sequence_recovery_recommendation": dropoff_fields.get("action_sequence_recovery_recommendation"),
            "follow_up_response_rate": follow_up_performance_fields.get("follow_up_response_rate"),
            "sequence_completion_rate": follow_up_performance_fields.get("sequence_completion_rate"),
            "second_follow_up_success_rate": follow_up_performance_fields.get("second_follow_up_success_rate"),
            "stalled_sequence_rate": follow_up_performance_fields.get("stalled_sequence_rate"),
        },
    }


def build_delivery_summary_contract(package: dict[str, Any] | None) -> dict[str, Any]:
    """
    Build a governed delivery-summary and packaging contract from package state.
    This output is auditable and can be further redacted for client-safe surfaces.
    """
    p = dict(package or {})
    normalized = {
        "review_status": str(p.get("review_status") or "pending").strip().lower(),
        "decision_status": str(p.get("decision_status") or "pending").strip().lower(),
        "release_status": str(p.get("release_status") or "pending").strip().lower(),
        "execution_status": str(p.get("execution_status") or "pending").strip().lower(),
        "runtime_artifacts": [x for x in list(p.get("runtime_artifacts") or []) if isinstance(x, dict)][:20],
        "expected_outputs": [str(x).strip() for x in list(p.get("expected_outputs") or []) if str(x).strip()][:50],
        "metadata": dict(p.get("metadata") or {}),
    }
    progress_state = _delivery_progress_state_for_package(normalized)
    runtime_artifacts = [x for x in list(normalized.get("runtime_artifacts") or []) if isinstance(x, dict)]
    expected_outputs = [str(x).strip() for x in list(normalized.get("expected_outputs") or []) if str(x).strip()]
    delivered_types: list[str] = []
    delivered_labels: list[str] = []
    for item in expected_outputs:
        if item not in delivered_types:
            delivered_types.append(item)
            label = _delivery_artifact_label(item)
            if label and label not in delivered_labels:
                delivered_labels.append(label)
    for artifact in runtime_artifacts:
        artifact_type = str(artifact.get("artifact_type") or "").strip().lower()
        if not artifact_type:
            continue
        if artifact_type not in delivered_types:
            delivered_types.append(artifact_type)
            label = _delivery_artifact_label(artifact_type)
            if label and label not in delivered_labels:
                delivered_labels.append(label)
    delivered_count = len(delivered_types)
    if progress_state == "no_delivery_summary":
        delivery_status = "not_available"
        title = "No Delivery Summary Yet"
        summary = "No suitable delivery output is available for packaging at this time."
        notes = "Execution output has not produced packageable delivery artifacts yet."
        packaging_reason = "No suitable output exists for delivery summarization."
    elif progress_state == "delivery_in_progress":
        delivery_status = "in_progress"
        title = "Delivery In Progress"
        summary = "Work is in progress and a governed delivery summary is not finalized yet."
        notes = "Continue execution/review flow to produce packageable delivery outputs."
        packaging_reason = "Delivery output is still in progress."
    elif progress_state == "internal_review_required":
        delivery_status = "internal_review_required"
        title = "Internal Review Required"
        summary = "Delivery output exists but requires internal review before client-safe packaging."
        notes = "Review package state and approval gates before exposing client-ready summary."
        packaging_reason = "Outputs exist but are not yet approved for safe client packaging."
    elif progress_state == "client_safe_packaging_ready":
        delivery_status = "client_safe_ready"
        title = "Client-Ready Delivery Summary"
        summary = (
            f"Delivery package includes {delivered_count} artifact type(s): "
            f"{', '.join(delivered_labels[:6]) if delivered_labels else 'packaged outputs'}."
        )
        notes = "Summary is safe-packaged for client-facing read-only surfaces."
        packaging_reason = "Delivery outputs passed governed readiness for client-safe packaging."
    else:
        delivery_status = "ready"
        title = "Delivery Summary Ready"
        summary = (
            f"Delivery summary is available with {delivered_count} artifact type(s): "
            f"{', '.join(delivered_labels[:6]) if delivered_labels else 'packaged outputs'}."
        )
        notes = "Summary is available for operator review and governed packaging decisions."
        packaging_reason = "Suitable outputs were identified for delivery summarization."
    return {
        "delivery_status": delivery_status,
        "delivery_summary_title": title,
        "delivery_summary_text": summary,
        "delivered_artifact_types": delivered_types,
        "delivered_artifact_labels": delivered_labels[:12],
        "delivered_artifact_count": delivered_count,
        "delivery_progress_state": progress_state,
        "client_ready_notes": notes,
        "internal_details_redacted": progress_state != "delivery_summary_ready",
        "packaging_reason": packaging_reason,
        "authority_trace": dict((normalized.get("metadata") or {}).get("authority_traces") or {}),
        "governance_trace": dict((normalized.get("metadata") or {}).get("governance_trace") or {}),
    }


def normalize_execution_package(package: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize execution package to stable review-only contract shape.
    """
    p = package or {}
    package_id = str(p.get("package_id") or uuid.uuid4().hex[:16])
    approval_id_refs = [str(x) for x in (p.get("approval_id_refs") or []) if str(x).strip()][:20]
    runtime_artifacts = p.get("runtime_artifacts") or []
    if not isinstance(runtime_artifacts, list):
        runtime_artifacts = []
    review_checklist = p.get("review_checklist") or []
    if not isinstance(review_checklist, list):
        review_checklist = []
    defaults = build_default_hardening_fields(p)
    retry_policy = normalize_retry_policy(p.get("retry_policy"))
    idempotency = normalize_idempotency(p.get("idempotency"), package=p)
    failure_summary = normalize_failure_summary(p.get("failure_summary"))
    recovery_summary = normalize_recovery_summary(p.get("recovery_summary"))
    rollback_repair = normalize_rollback_repair(p.get("rollback_repair"))
    integrity_verification = normalize_integrity_verification(p.get("integrity_verification"))
    metadata = dict(p.get("metadata") or {})
    cursor_bridge_summary = _normalize_cursor_bridge_summary(p.get("cursor_bridge_summary") or metadata.get("cursor_bridge_summary"))
    cursor_bridge_artifacts_source = p.get("cursor_bridge_artifacts")
    if not isinstance(cursor_bridge_artifacts_source, list):
        cursor_bridge_artifacts_source = metadata.get("cursor_bridge_artifacts")
    if not isinstance(cursor_bridge_artifacts_source, list):
        cursor_bridge_artifacts_source = []
    cursor_bridge_artifacts = [
        _normalize_cursor_bridge_artifact_record(item) for item in cursor_bridge_artifacts_source[:20] if isinstance(item, dict)
    ]
    if not idempotency.get("idempotency_key"):
        idempotency["idempotency_key"] = derive_idempotency_key(p)
    if cursor_bridge_artifacts and cursor_bridge_summary:
        cursor_bridge_summary["artifact_count"] = len(cursor_bridge_artifacts)
        latest_artifact = cursor_bridge_artifacts[-1]
        cursor_bridge_summary["latest_artifact_type"] = str(latest_artifact.get("artifact_type") or "")
        cursor_bridge_summary["latest_validation_status"] = str(latest_artifact.get("validation_status") or "")
        cursor_bridge_summary["latest_recorded_at"] = str(latest_artifact.get("recorded_at") or "")
    if cursor_bridge_summary:
        metadata["cursor_bridge_summary"] = cursor_bridge_summary
    if cursor_bridge_artifacts:
        metadata["cursor_bridge_artifacts"] = cursor_bridge_artifacts
    normalized_cost_tracking = _normalize_cost_tracking(
        p.get("cost_tracking"),
        fallback_source="composed_operation",
    )
    if float(normalized_cost_tracking.get("cost_estimate") or 0.0) <= 0.0:
        normalized_cost_tracking = _estimate_package_cost_tracking(p)
    budget_caps = _resolve_package_budget_caps(p, str(p.get("project_path") or ""))
    provided_budget_control = p.get("budget_control")
    if isinstance(provided_budget_control, dict) and provided_budget_control:
        budget_control = normalize_budget_control(provided_budget_control)
    else:
        operation_cost = float(normalized_cost_tracking.get("cost_estimate") or 0.0)
        budget_control = evaluate_budget_controls(
            budget_caps=budget_caps,
            current_operation_cost=operation_cost,
            current_project_cost=operation_cost,
            current_session_cost=operation_cost,
        )
    budget_fields = _budget_fields_from_control(budget_control)
    revenue_fields = _derive_revenue_activation_fields(
        {
            **p,
            "metadata": metadata,
            "cost_tracking": normalized_cost_tracking,
            "evaluation_summary": normalize_evaluation_summary(p.get("evaluation_summary")),
            "local_analysis_summary": normalize_local_analysis_summary(p.get("local_analysis_summary")),
        }
    )

    return {
        "package_id": package_id,
        "package_version": str(p.get("package_version") or "1.0"),
        "package_kind": str(p.get("package_kind") or "review_only_execution_envelope"),
        "project_name": str(p.get("project_name") or ""),
        "project_path": str(p.get("project_path") or ""),
        "run_id": str(p.get("run_id") or ""),
        "created_at": str(p.get("created_at") or datetime.now().isoformat()),
        "package_status": str(p.get("package_status") or "review_pending").strip().lower(),
        "review_status": str(p.get("review_status") or "pending").strip().lower(),
        "sealed": bool(p.get("sealed", True)),
        "seal_reason": str(p.get("seal_reason") or "Review-only package; execution disabled in this phase."),
        "runtime_target_id": str(p.get("runtime_target_id") or "local"),
        "runtime_target_name": str(p.get("runtime_target_name") or p.get("runtime_target_id") or "local"),
        "execution_mode": str(p.get("execution_mode") or "manual_only"),
        "requested_action": str(p.get("requested_action") or "adapter_dispatch_call"),
        "requested_by": str(p.get("requested_by") or "workflow"),
        "requires_human_approval": bool(p.get("requires_human_approval", True)),
        "approval_id_refs": approval_id_refs,
        "aegis_decision": str(p.get("aegis_decision") or ""),
        "aegis_scope": str(p.get("aegis_scope") or ""),
        "reason": str(p.get("reason") or ""),
        "helix_contract_summary": dict(p.get("helix_contract_summary") or {}),
        "dispatch_plan_summary": dict(p.get("dispatch_plan_summary") or {}),
        "routing_summary": dict(p.get("routing_summary") or {}),
        "execution_summary": dict(p.get("execution_summary") or {}),
        "command_request": dict(p.get("command_request") or {}),
        "candidate_paths": [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50],
        "expected_outputs": [str(x) for x in (p.get("expected_outputs") or []) if str(x).strip()][:50],
        "review_checklist": [str(x) for x in review_checklist[:20]],
        "rollback_notes": [str(x) for x in (p.get("rollback_notes") or []) if str(x).strip()][:20],
        "runtime_artifacts": [x for x in runtime_artifacts[:20] if isinstance(x, dict)],
        "cursor_bridge_summary": cursor_bridge_summary,
        "cursor_bridge_artifacts": cursor_bridge_artifacts,
        "metadata": metadata,
        "decision_status": str(p.get("decision_status") or "pending").strip().lower(),
        "decision_timestamp": str(p.get("decision_timestamp") or ""),
        "decision_actor": str(p.get("decision_actor") or ""),
        "decision_notes": str(p.get("decision_notes") or ""),
        "decision_id": str(p.get("decision_id") or ""),
        "eligibility_status": str(p.get("eligibility_status") or "pending").strip().lower(),
        "eligibility_timestamp": str(p.get("eligibility_timestamp") or ""),
        "eligibility_reason": _normalize_eligibility_reason(p.get("eligibility_reason")),
        "eligibility_checked_by": str(p.get("eligibility_checked_by") or ""),
        "eligibility_check_id": str(p.get("eligibility_check_id") or ""),
        "release_status": str(p.get("release_status") or "pending").strip().lower(),
        "release_timestamp": str(p.get("release_timestamp") or ""),
        "release_actor": str(p.get("release_actor") or ""),
        "release_notes": str(p.get("release_notes") or ""),
        "release_id": str(p.get("release_id") or ""),
        "release_reason": _normalize_release_reason(p.get("release_reason")),
        "release_version": str(p.get("release_version") or "v1"),
        "handoff_status": str(p.get("handoff_status") or "pending").strip().lower(),
        "handoff_timestamp": str(p.get("handoff_timestamp") or ""),
        "handoff_actor": str(p.get("handoff_actor") or ""),
        "handoff_notes": str(p.get("handoff_notes") or ""),
        "handoff_id": str(p.get("handoff_id") or ""),
        "handoff_reason": _normalize_handoff_reason(p.get("handoff_reason")),
        "handoff_version": str(p.get("handoff_version") or "v1"),
        "handoff_executor_target_id": str(p.get("handoff_executor_target_id") or ""),
        "handoff_executor_target_name": str(p.get("handoff_executor_target_name") or ""),
        "handoff_aegis_result": _normalize_handoff_aegis_result(p.get("handoff_aegis_result")),
        "execution_status": str(p.get("execution_status") or "pending").strip().lower(),
        "execution_timestamp": str(p.get("execution_timestamp") or ""),
        "execution_actor": str(p.get("execution_actor") or ""),
        "execution_id": str(p.get("execution_id") or ""),
        "execution_reason": _normalize_execution_reason(p.get("execution_reason")),
        "execution_receipt": _normalize_execution_receipt(p.get("execution_receipt")),
        "execution_version": str(p.get("execution_version") or "v1"),
        "execution_executor_target_id": str(p.get("execution_executor_target_id") or ""),
        "execution_executor_target_name": str(p.get("execution_executor_target_name") or ""),
        "execution_executor_backend_id": _normalize_executor_backend_id(p.get("execution_executor_backend_id") or _resolve_executor_backend_id(p)),
        "execution_aegis_result": _normalize_handoff_aegis_result(p.get("execution_aegis_result")),
        "execution_started_at": str(p.get("execution_started_at") or ""),
        "execution_finished_at": str(p.get("execution_finished_at") or ""),
        "rollback_status": str(p.get("rollback_status") or "not_needed").strip().lower(),
        "rollback_timestamp": str(p.get("rollback_timestamp") or ""),
        "rollback_reason": _normalize_rollback_reason(p.get("rollback_reason")),
        "retry_policy": retry_policy or defaults["retry_policy"],
        "idempotency": idempotency or defaults["idempotency"],
        "failure_summary": failure_summary or defaults["failure_summary"],
        "recovery_summary": recovery_summary or defaults["recovery_summary"],
        "rollback_repair": rollback_repair or defaults["rollback_repair"],
        "integrity_verification": integrity_verification or defaults["integrity_verification"],
        "evaluation_status": _normalize_evaluation_status(p.get("evaluation_status")),
        "evaluation_timestamp": str(p.get("evaluation_timestamp") or ""),
        "evaluation_actor": str(p.get("evaluation_actor") or ""),
        "evaluation_id": str(p.get("evaluation_id") or ""),
        "evaluation_version": str(p.get("evaluation_version") or "v1"),
        "evaluation_reason": normalize_evaluation_reason(p.get("evaluation_reason")),
        "evaluation_basis": normalize_evaluation_basis(p.get("evaluation_basis")),
        "evaluation_summary": normalize_evaluation_summary(p.get("evaluation_summary")),
        "local_analysis_status": _normalize_local_analysis_status(p.get("local_analysis_status")),
        "local_analysis_timestamp": str(p.get("local_analysis_timestamp") or ""),
        "local_analysis_actor": str(p.get("local_analysis_actor") or "nemoclaw"),
        "local_analysis_id": str(p.get("local_analysis_id") or ""),
        "local_analysis_version": str(p.get("local_analysis_version") or "v1"),
        "local_analysis_reason": normalize_local_analysis_reason(p.get("local_analysis_reason")),
        "local_analysis_basis": normalize_local_analysis_basis(p.get("local_analysis_basis")),
        "local_analysis_summary": normalize_local_analysis_summary(p.get("local_analysis_summary")),
        "cost_tracking": normalized_cost_tracking,
        "budget_caps": budget_caps,
        "budget_control": budget_control,
        **budget_fields,
        **revenue_fields,
        "delivery_summary": build_delivery_summary_contract(
            {
                **p,
                "runtime_artifacts": [x for x in runtime_artifacts[:20] if isinstance(x, dict)],
                "expected_outputs": [str(x) for x in (p.get("expected_outputs") or []) if str(x).strip()][:50],
                "metadata": metadata,
            }
        ),
    }


def normalize_execution_package_journal_record(record: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize journal record to stable summary-only contract shape."""
    r = record or {}
    return {
        "package_id": str(r.get("package_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "run_id": str(r.get("run_id") or ""),
        "created_at": str(r.get("created_at") or ""),
        "package_status": str(r.get("package_status") or "review_pending").strip().lower(),
        "review_status": str(r.get("review_status") or "pending").strip().lower(),
        "runtime_target_id": str(r.get("runtime_target_id") or "local"),
        "requires_human_approval": bool(r.get("requires_human_approval", True)),
        "approval_id_refs": [str(x) for x in (r.get("approval_id_refs") or []) if str(x).strip()][:20],
        "sealed": bool(r.get("sealed", True)),
        "reason": str(r.get("reason") or ""),
        "helix_contract_summary": dict(r.get("helix_contract_summary") or {}),
        "package_file": str(r.get("package_file") or ""),
        "bridge_task_id": str(r.get("bridge_task_id") or ""),
        "cursor_bridge_status": str(r.get("cursor_bridge_status") or ""),
        "cursor_bridge_artifact_count": max(0, int(r.get("cursor_bridge_artifact_count") or 0)),
        "cursor_bridge_latest_artifact_type": str(r.get("cursor_bridge_latest_artifact_type") or ""),
        "cursor_bridge_latest_validation_status": str(r.get("cursor_bridge_latest_validation_status") or ""),
        "decision_status": str(r.get("decision_status") or "pending").strip().lower(),
        "decision_timestamp": str(r.get("decision_timestamp") or ""),
        "decision_actor": str(r.get("decision_actor") or ""),
        "decision_id": str(r.get("decision_id") or ""),
        "eligibility_status": str(r.get("eligibility_status") or "pending").strip().lower(),
        "eligibility_timestamp": str(r.get("eligibility_timestamp") or ""),
        "eligibility_reason": _normalize_eligibility_reason(r.get("eligibility_reason")),
        "eligibility_checked_by": str(r.get("eligibility_checked_by") or ""),
        "eligibility_check_id": str(r.get("eligibility_check_id") or ""),
        "release_status": str(r.get("release_status") or "pending").strip().lower(),
        "release_timestamp": str(r.get("release_timestamp") or ""),
        "release_actor": str(r.get("release_actor") or ""),
        "release_id": str(r.get("release_id") or ""),
        "release_reason": _normalize_release_reason(r.get("release_reason")),
        "release_version": str(r.get("release_version") or "v1"),
        "handoff_status": str(r.get("handoff_status") or "pending").strip().lower(),
        "handoff_timestamp": str(r.get("handoff_timestamp") or ""),
        "handoff_actor": str(r.get("handoff_actor") or ""),
        "handoff_id": str(r.get("handoff_id") or ""),
        "handoff_reason": _normalize_handoff_reason(r.get("handoff_reason")),
        "handoff_version": str(r.get("handoff_version") or "v1"),
        "handoff_executor_target_id": str(r.get("handoff_executor_target_id") or ""),
        "handoff_executor_target_name": str(r.get("handoff_executor_target_name") or ""),
        "execution_status": str(r.get("execution_status") or "pending").strip().lower(),
        "execution_timestamp": str(r.get("execution_timestamp") or ""),
        "execution_actor": str(r.get("execution_actor") or ""),
        "execution_id": str(r.get("execution_id") or ""),
        "execution_reason": _normalize_execution_reason(r.get("execution_reason")),
        "execution_version": str(r.get("execution_version") or "v1"),
        "execution_executor_target_id": str(r.get("execution_executor_target_id") or ""),
        "execution_executor_target_name": str(r.get("execution_executor_target_name") or ""),
        "execution_executor_backend_id": _normalize_executor_backend_id(r.get("execution_executor_backend_id")),
        "execution_receipt": _summarize_execution_receipt(r.get("execution_receipt")),
        "rollback_status": str(r.get("rollback_status") or "not_needed").strip().lower(),
        "rollback_timestamp": str(r.get("rollback_timestamp") or ""),
        "rollback_reason": _normalize_rollback_reason(r.get("rollback_reason")),
        "retry_policy": normalize_retry_policy(r.get("retry_policy")),
        "idempotency": normalize_idempotency(r.get("idempotency"), package=r),
        "failure_summary": normalize_failure_summary(r.get("failure_summary")),
        "recovery_summary": normalize_recovery_summary(r.get("recovery_summary")),
        "rollback_repair": normalize_rollback_repair(r.get("rollback_repair")),
        "integrity_verification": normalize_integrity_verification(r.get("integrity_verification")),
        "evaluation_status": _normalize_evaluation_status(r.get("evaluation_status")),
        "evaluation_timestamp": str(r.get("evaluation_timestamp") or ""),
        "evaluation_actor": str(r.get("evaluation_actor") or ""),
        "evaluation_id": str(r.get("evaluation_id") or ""),
        "evaluation_version": str(r.get("evaluation_version") or "v1"),
        "evaluation_reason": normalize_evaluation_reason(r.get("evaluation_reason")),
        "evaluation_basis": normalize_evaluation_basis(r.get("evaluation_basis")),
        "evaluation_summary": normalize_evaluation_summary(r.get("evaluation_summary")),
        "local_analysis_status": _normalize_local_analysis_status(r.get("local_analysis_status")),
        "local_analysis_timestamp": str(r.get("local_analysis_timestamp") or ""),
        "local_analysis_actor": str(r.get("local_analysis_actor") or "nemoclaw"),
        "local_analysis_id": str(r.get("local_analysis_id") or ""),
        "local_analysis_version": str(r.get("local_analysis_version") or "v1"),
        "local_analysis_reason": normalize_local_analysis_reason(r.get("local_analysis_reason")),
        "local_analysis_basis": normalize_local_analysis_basis(r.get("local_analysis_basis")),
        "local_analysis_summary": normalize_local_analysis_summary(r.get("local_analysis_summary")),
        "governance_conflict_status": str(r.get("governance_conflict_status") or ""),
        "governance_conflict_type": str(r.get("governance_conflict_type") or ""),
        "governance_resolution_state": str(r.get("governance_resolution_state") or ""),
        "governance_routing_outcome": str(r.get("governance_routing_outcome") or ""),
        "lead_id": str(r.get("lead_id") or ""),
        "opportunity_id": str(r.get("opportunity_id") or ""),
        "client_id": str(r.get("client_id") or ""),
        "business_function": str(r.get("business_function") or ""),
        "pipeline_stage": _normalize_pipeline_stage(r.get("pipeline_stage")),
        "next_revenue_action": str(r.get("next_revenue_action") or ""),
        "revenue_action_reason": str(r.get("revenue_action_reason") or ""),
        "execution_score": _normalize_revenue_ratio(r.get("execution_score"), fallback=0.0),
        "roi_estimate": _normalize_revenue_ratio(r.get("roi_estimate"), fallback=0.0),
        "conversion_probability": _normalize_revenue_ratio(r.get("conversion_probability"), fallback=0.0),
        "time_sensitivity": _normalize_revenue_ratio(r.get("time_sensitivity"), fallback=0.0),
        "highest_value_next_action": str(r.get("highest_value_next_action") or ""),
        "highest_value_next_action_score": _normalize_revenue_ratio(r.get("highest_value_next_action_score"), fallback=0.0),
        "highest_value_next_action_reason": str(r.get("highest_value_next_action_reason") or ""),
        "revenue_activation_status": str(r.get("revenue_activation_status") or "needs_revision"),
        "revenue_workflow_ready": bool(r.get("revenue_workflow_ready")),
        "revenue_workflow_block_reason": str(r.get("revenue_workflow_block_reason") or ""),
        "revenue_workflow_priority": str(r.get("revenue_workflow_priority") or "medium"),
        "operator_revenue_review_required": bool(r.get("operator_revenue_review_required")),
        "revenue_candidate_status": str(r.get("revenue_candidate_status") or "review_required"),
        "revenue_candidate_rank": max(0, int(r.get("revenue_candidate_rank") or 0)),
        "revenue_candidate_reason": str(r.get("revenue_candidate_reason") or ""),
        "operator_action_queue_status": str(r.get("operator_action_queue_status") or "review_required_operator_action"),
        "operator_action_queue_rank": max(0, int(r.get("operator_action_queue_rank") or 0)),
        "operator_action_type": _normalize_operator_action_type(r.get("operator_action_type")),
        "operator_action_reason": str(r.get("operator_action_reason") or ""),
        "operator_action_deadline": str(r.get("operator_action_deadline") or ""),
        "operator_action_priority": _normalize_operator_action_priority(r.get("operator_action_priority")),
        "operator_action_id": str(r.get("operator_action_id") or ""),
        "operator_action_status": _normalize_operator_action_lifecycle_status(r.get("operator_action_status")),
        "operator_action_created_at": str(r.get("operator_action_created_at") or ""),
        "operator_action_acknowledged_at": str(r.get("operator_action_acknowledged_at") or ""),
        "operator_action_started_at": str(r.get("operator_action_started_at") or ""),
        "operator_action_completed_at": str(r.get("operator_action_completed_at") or ""),
        "operator_action_failed_at": str(r.get("operator_action_failed_at") or ""),
        "operator_action_ignored_at": str(r.get("operator_action_ignored_at") or ""),
        "operator_action_actor": str(r.get("operator_action_actor") or ""),
        "operator_action_notes": str(r.get("operator_action_notes") or ""),
        "operator_action_due_at": str(r.get("operator_action_due_at") or ""),
        "operator_action_attention_status": _normalize_operator_action_attention_status(r.get("operator_action_attention_status")),
        "operator_action_attention_reason": str(r.get("operator_action_attention_reason") or ""),
        "operator_action_overdue": bool(r.get("operator_action_overdue")),
        "operator_action_history_count": max(0, int(r.get("operator_action_history_count") or 0)),
        "linked_execution_result": str(r.get("linked_execution_result") or ""),
        "linked_conversion_result": str(r.get("linked_conversion_result") or ""),
        "linked_revenue_realized": _normalize_revenue_ratio(r.get("linked_revenue_realized"), fallback=0.0),
        "linked_communication_delivery_status": _normalize_communication_delivery_status(r.get("linked_communication_delivery_status")),
        "operator_action_effect_on_revenue": _normalize_operator_action_revenue_effect(r.get("operator_action_effect_on_revenue")),
        "operator_action_effect_reason": str(r.get("operator_action_effect_reason") or ""),
        "action_success_rate": _normalize_revenue_ratio(r.get("action_success_rate"), fallback=0.0),
        "action_follow_through_rate": _normalize_revenue_ratio(r.get("action_follow_through_rate"), fallback=0.0),
        "action_to_reply_rate": _normalize_revenue_ratio(r.get("action_to_reply_rate"), fallback=0.0),
        "action_to_conversion_rate": _normalize_revenue_ratio(r.get("action_to_conversion_rate"), fallback=0.0),
        "opportunity_classification": str(r.get("opportunity_classification") or "cold"),
        "opportunity_classification_reason": str(r.get("opportunity_classification_reason") or ""),
        "communication_channel": _normalize_communication_channel(r.get("communication_channel")),
        "communication_intent": _normalize_communication_intent(r.get("communication_intent")),
        "communication_status": _normalize_communication_status(r.get("communication_status")),
        "draft_message_subject": str(r.get("draft_message_subject") or ""),
        "draft_message_body": str(r.get("draft_message_body") or ""),
        "draft_message_preview": str(r.get("draft_message_preview") or ""),
        "communication_requires_approval": bool(r.get("communication_requires_approval")),
        "communication_approval_status": _normalize_communication_approval_status(r.get("communication_approval_status")),
        "communication_approved_at": str(r.get("communication_approved_at") or ""),
        "communication_denied_reason": str(r.get("communication_denied_reason") or ""),
        "communication_sent_at": str(r.get("communication_sent_at") or ""),
        "communication_delivery_status": _normalize_communication_delivery_status(r.get("communication_delivery_status")),
        "communication_send_eligible": bool(r.get("communication_send_eligible")),
        "communication_block_reason": str(r.get("communication_block_reason") or ""),
        "operator_review_required_for_send": bool(r.get("operator_review_required_for_send")),
        "follow_up_recommended": bool(r.get("follow_up_recommended")),
        "follow_up_due_at": str(r.get("follow_up_due_at") or ""),
        "follow_up_status": _normalize_follow_up_status(r.get("follow_up_status")),
        "follow_up_reason": str(r.get("follow_up_reason") or ""),
        "follow_up_sequence_step": max(0, int(r.get("follow_up_sequence_step") or 0)),
        "action_sequence_id": str(r.get("action_sequence_id") or ""),
        "action_sequence_type": _normalize_action_sequence_type(r.get("action_sequence_type")),
        "action_sequence_step": max(0, int(r.get("action_sequence_step") or 0)),
        "action_sequence_total_steps": max(1, int(r.get("action_sequence_total_steps") or 1)),
        "action_sequence_status": _normalize_action_sequence_status(r.get("action_sequence_status")),
        "action_sequence_started_at": str(r.get("action_sequence_started_at") or ""),
        "action_sequence_updated_at": str(r.get("action_sequence_updated_at") or ""),
        "action_sequence_completed_at": str(r.get("action_sequence_completed_at") or ""),
        "action_sequence_abandoned_at": str(r.get("action_sequence_abandoned_at") or ""),
        "action_sequence_next_step": str(r.get("action_sequence_next_step") or ""),
        "action_sequence_next_step_due_at": str(r.get("action_sequence_next_step_due_at") or ""),
        "action_sequence_progress_score": _normalize_revenue_ratio(r.get("action_sequence_progress_score"), fallback=0.0),
        "action_sequence_dropoff_detected": bool(r.get("action_sequence_dropoff_detected")),
        "action_sequence_dropoff_reason": str(r.get("action_sequence_dropoff_reason") or ""),
        "action_sequence_recovery_recommendation": _normalize_follow_up_recommendation(r.get("action_sequence_recovery_recommendation")),
        "follow_up_intelligence_status": _normalize_follow_up_intelligence_status(r.get("follow_up_intelligence_status")),
        "follow_up_priority": _normalize_follow_up_priority(r.get("follow_up_priority")),
        "follow_up_recommendation": _normalize_follow_up_recommendation(r.get("follow_up_recommendation")),
        "follow_up_recommendation_reason": str(r.get("follow_up_recommendation_reason") or ""),
        "follow_up_overdue": bool(r.get("follow_up_overdue")),
        "follow_up_dropoff_risk": _normalize_follow_up_dropoff_risk(r.get("follow_up_dropoff_risk")),
        "follow_up_window_status": _normalize_follow_up_window_status(r.get("follow_up_window_status")),
        "follow_up_response_rate": _normalize_revenue_ratio(r.get("follow_up_response_rate"), fallback=0.0),
        "sequence_completion_rate": _normalize_revenue_ratio(r.get("sequence_completion_rate"), fallback=0.0),
        "second_follow_up_success_rate": _normalize_revenue_ratio(r.get("second_follow_up_success_rate"), fallback=0.0),
        "stalled_sequence_rate": _normalize_revenue_ratio(r.get("stalled_sequence_rate"), fallback=0.0),
        "cost_tracking": _normalize_cost_tracking(r.get("cost_tracking"), fallback_source="composed_operation"),
        "budget_caps": resolve_budget_caps(r.get("budget_caps") or {}),
        "budget_control": normalize_budget_control(r.get("budget_control") or {}),
        "budget_status": str(r.get("budget_status") or "within_budget"),
        "budget_scope": str(r.get("budget_scope") or "operation"),
        "budget_cap": float(r.get("budget_cap") or 0.0),
        "current_estimated_cost": float(r.get("current_estimated_cost") or 0.0),
        "remaining_estimated_budget": float(r.get("remaining_estimated_budget") or 0.0),
        "kill_switch_active": bool(r.get("kill_switch_active")),
        "budget_reason": str(r.get("budget_reason") or ""),
    }


def _is_review_pending_package(record: dict[str, Any] | None) -> bool:
    r = normalize_execution_package_journal_record(record)
    review_status = r.get("review_status") or ""
    package_status = r.get("package_status") or ""
    return review_status in ("pending", "review_pending") or package_status in ("pending", "review_pending")


def write_execution_package(project_path: str | None, package: dict[str, Any]) -> str | None:
    """
    Write a normalized package JSON file and append a journal entry.
    Returns package file path, or None on failure.
    """
    package_path = None
    journal_path = get_execution_package_journal_path(project_path)
    try:
        normalized = normalize_execution_package(package)
        package_path = get_execution_package_file_path(project_path, normalized.get("package_id"))
        if not package_path or not journal_path:
            return None

        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return package_path
    except Exception:
        return None


def write_execution_package_safe(project_path: str | None, package: dict[str, Any]) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return write_execution_package(project_path=project_path, package=package)
    except Exception:
        return None


def read_execution_package(project_path: str | None, package_id: str | None) -> dict[str, Any] | None:
    """Read a single persisted execution package by id."""
    path = get_execution_package_file_path(project_path, package_id)
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_execution_package(data)
    except Exception:
        return None
    return None


def read_execution_package_journal_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    """Read last n journal lines and parse JSONL."""
    path = get_execution_package_journal_path(project_path)
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(normalize_execution_package_journal_record(parsed))
        except json.JSONDecodeError:
            continue
    return out


def list_execution_package_journal_entries(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """List recent execution package journal entries sorted by created_at DESC."""
    limit = max(1, min(int(n or 20), MAX_EXECUTION_PACKAGE_LIST_LIMIT))
    rows = read_execution_package_journal_tail(project_path=project_path, n=MAX_EXECUTION_PACKAGE_LIST_LIMIT)
    rows = [normalize_execution_package_journal_record(r) for r in rows if isinstance(r, dict)]
    latest_by_package: dict[str, dict[str, Any]] = {}
    for row in reversed(rows):
        package_id = str(row.get("package_id") or "").strip()
        if not package_id or package_id in latest_by_package:
            continue
        latest_by_package[package_id] = row
    deduped = list(latest_by_package.values())
    deduped.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return deduped[:limit]


def list_reviewable_execution_packages(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    """List recent pending/reviewable execution package summaries sorted by created_at DESC."""
    limit = max(1, min(int(n or 20), MAX_EXECUTION_PACKAGE_LIST_LIMIT))
    rows = read_execution_package_journal_tail(project_path=project_path, n=MAX_EXECUTION_PACKAGE_LIST_LIMIT)
    reviewable = [normalize_execution_package_journal_record(r) for r in rows if _is_review_pending_package(r)]
    reviewable.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return reviewable[:limit]


def get_self_change_audit_path(project_path: str | None) -> str | None:
    state_dir = get_execution_package_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / SELF_CHANGE_AUDIT_FILENAME)


def normalize_self_change_audit_record(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record or {}
    target_files = r.get("target_files")
    if not isinstance(target_files, list):
        target_files = []
    rollback_target_files = r.get("rollback_target_files")
    if not isinstance(rollback_target_files, list):
        rollback_target_files = []
    protected_zones = r.get("protected_zones")
    if not isinstance(protected_zones, list):
        protected_zones = []
    comparison_dimensions = r.get("comparison_dimensions")
    if not isinstance(comparison_dimensions, list):
        comparison_dimensions = []
    rollback_target_components = r.get("rollback_target_components")
    if not isinstance(rollback_target_components, list):
        rollback_target_components = []
    rollback_sequence = r.get("rollback_sequence")
    if not isinstance(rollback_sequence, list):
        rollback_sequence = []
    budgeting_window = r.get("budgeting_window")
    if not isinstance(budgeting_window, dict):
        budgeting_window = {}
    trust_window = r.get("trust_window")
    if not isinstance(trust_window, dict):
        trust_window = {}
    return {
        "change_id": str(r.get("change_id") or ""),
        "recorded_at": str(r.get("recorded_at") or ""),
        "target_files": [str(item) for item in target_files if str(item).strip()][:50],
        "change_type": str(r.get("change_type") or ""),
        "risk_level": str(r.get("risk_level") or "medium_risk").strip().lower(),
        "protected_zones": [str(item) for item in protected_zones if str(item).strip()][:20],
        "protected_zone_hit": bool(r.get("protected_zone_hit")),
        "reason": str(r.get("reason") or ""),
        "expected_outcome": str(r.get("expected_outcome") or ""),
        "validation_plan": dict(r.get("validation_plan") or {}),
        "rollback_plan": dict(r.get("rollback_plan") or {}),
        "approval_requirement": str(r.get("approval_requirement") or ""),
        "approval_required": bool(r.get("approval_required")),
        "approval_status": str(r.get("approval_status") or "optional").strip().lower(),
        "approved_by": str(r.get("approved_by") or ""),
        "outcome_status": str(r.get("outcome_status") or "proposed").strip().lower(),
        "outcome_summary": str(r.get("outcome_summary") or ""),
        "validation_status": str(r.get("validation_status") or "pending").strip().lower(),
        "build_status": str(r.get("build_status") or "pending").strip().lower(),
        "regression_status": str(r.get("regression_status") or "pending").strip().lower(),
        "gate_outcome": str(r.get("gate_outcome") or "allow_for_review").strip().lower(),
        "release_lane": str(r.get("release_lane") or "experimental").strip().lower(),
        "sandbox_required": bool(r.get("sandbox_required")),
        "sandbox_status": str(r.get("sandbox_status") or "sandbox_pending").strip().lower(),
        "sandbox_result": str(r.get("sandbox_result") or "sandbox_pending").strip().lower(),
        "promotion_status": str(r.get("promotion_status") or "promotion_pending").strip().lower(),
        "promotion_reason": str(r.get("promotion_reason") or ""),
        "baseline_reference": str(r.get("baseline_reference") or ""),
        "candidate_reference": str(r.get("candidate_reference") or ""),
        "comparison_dimensions": [str(item) for item in comparison_dimensions if str(item).strip()][:20],
        "observed_improvement": dict(r.get("observed_improvement") or {}),
        "observed_regression": dict(r.get("observed_regression") or {}),
        "net_score": float(r.get("net_score") or 0.0) if str(r.get("net_score") or "").strip() not in ("", "None") else 0.0,
        "confidence_level": float(r.get("confidence_level") or 0.0)
        if str(r.get("confidence_level") or "").strip() not in ("", "None")
        else 0.0,
        "confidence_band": str(r.get("confidence_band") or "weak").strip().lower(),
        "comparison_status": str(r.get("comparison_status") or "insufficient_evidence").strip().lower(),
        "promotion_confidence": str(r.get("promotion_confidence") or "insufficient_evidence").strip().lower(),
        "recommendation": str(r.get("recommendation") or "hold_experimental").strip().lower(),
        "comparison_reason": str(r.get("comparison_reason") or ""),
        "promoted_at": str(r.get("promoted_at") or ""),
        "monitoring_window": str(r.get("monitoring_window") or "observation_window"),
        "monitoring_status": str(r.get("monitoring_status") or "pending_monitoring").strip().lower(),
        "observation_count": int(r.get("observation_count") or 0) if str(r.get("observation_count") or "").strip() not in ("", "None") else 0,
        "health_signals": dict(r.get("health_signals") or {}),
        "regression_detected": bool(r.get("regression_detected")),
        "rollback_triggered": bool(r.get("rollback_triggered")),
        "rollback_trigger_outcome": str(r.get("rollback_trigger_outcome") or "monitor_more").strip().lower(),
        "rollback_reason": str(r.get("rollback_reason") or ""),
        "stable_status": str(r.get("stable_status") or "provisionally_stable").strip().lower(),
        "rollback_required": bool(r.get("rollback_required")),
        "rollback_id": str(r.get("rollback_id") or ""),
        "rollback_scope": str(r.get("rollback_scope") or "file_only").strip().lower(),
        "rollback_target_files": [str(item) for item in rollback_target_files if str(item).strip()][:50],
        "rollback_target_components": [str(item).strip().lower() for item in rollback_target_components if str(item).strip()][:20],
        "blast_radius_level": str(r.get("blast_radius_level") or "low").strip().lower(),
        "rollback_status": str(r.get("rollback_status") or "rollback_pending").strip().lower(),
        "rollback_result": str(r.get("rollback_result") or ""),
        "rollback_execution_eligible": bool(r.get("rollback_execution_eligible")),
        "rollback_approval_required": bool(r.get("rollback_approval_required")),
        "rollback_sequence": [str(item).strip().lower() for item in rollback_sequence if str(item).strip()][:10],
        "rollback_follow_up_validation_required": bool(r.get("rollback_follow_up_validation_required")),
        "rollback_validation_status": str(r.get("rollback_validation_status") or "pending").strip().lower(),
        "budgeting_window": {
            "current_window_id": str(budgeting_window.get("current_window_id") or ""),
            "window_start": str(budgeting_window.get("window_start") or ""),
            "window_end": str(budgeting_window.get("window_end") or ""),
        },
        "attempted_changes_in_window": int(r.get("attempted_changes_in_window") or 0)
        if str(r.get("attempted_changes_in_window") or "").strip() not in ("", "None")
        else 0,
        "successful_changes_in_window": int(r.get("successful_changes_in_window") or 0)
        if str(r.get("successful_changes_in_window") or "").strip() not in ("", "None")
        else 0,
        "failed_changes_in_window": int(r.get("failed_changes_in_window") or 0)
        if str(r.get("failed_changes_in_window") or "").strip() not in ("", "None")
        else 0,
        "rollbacks_in_window": int(r.get("rollbacks_in_window") or 0)
        if str(r.get("rollbacks_in_window") or "").strip() not in ("", "None")
        else 0,
        "protected_zone_changes_in_window": int(r.get("protected_zone_changes_in_window") or 0)
        if str(r.get("protected_zone_changes_in_window") or "").strip() not in ("", "None")
        else 0,
        "mutation_rate_status": str(r.get("mutation_rate_status") or "within_budget").strip().lower(),
        "budget_remaining": int(r.get("budget_remaining") or 0)
        if str(r.get("budget_remaining") or "").strip() not in ("", "None")
        else 0,
        "cool_down_required": bool(r.get("cool_down_required")),
        "control_outcome": str(r.get("control_outcome") or "budget_available").strip().lower(),
        "budget_reason": str(r.get("budget_reason") or ""),
        "stability_state": str(r.get("stability_state") or "stable").strip().lower(),
        "turbulence_level": str(r.get("turbulence_level") or "low").strip().lower(),
        "protected_zone_instability": bool(r.get("protected_zone_instability")),
        "freeze_required": bool(r.get("freeze_required")),
        "freeze_scope": str(r.get("freeze_scope") or "project_scoped").strip().lower(),
        "recovery_only_mode": bool(r.get("recovery_only_mode")),
        "escalation_required": bool(r.get("escalation_required")),
        "escalation_reason": str(r.get("escalation_reason") or ""),
        "reentry_requirements": [str(item).strip().lower() for item in (r.get("reentry_requirements") or []) if str(item).strip()][:20],
        "checkpoint_required": bool(r.get("checkpoint_required")),
        "checkpoint_reason": str(r.get("checkpoint_reason") or ""),
        "checkpoint_scope": str(r.get("checkpoint_scope") or "project_scoped").strip().lower(),
        "checkpoint_status": str(r.get("checkpoint_status") or "not_required").strip().lower(),
        "executive_approval_required": bool(r.get("executive_approval_required")),
        "manual_hold_active": bool(r.get("manual_hold_active")),
        "manual_hold_scope": str(r.get("manual_hold_scope") or "project_scoped").strip().lower(),
        "hold_reason": str(r.get("hold_reason") or ""),
        "hold_release_requirements": [str(item).strip().lower() for item in (r.get("hold_release_requirements") or []) if str(item).strip()][:20],
        "override_status": str(r.get("override_status") or "no_override").strip().lower(),
        "rollout_stage": str(r.get("rollout_stage") or "limited_cohort").strip().lower(),
        "rollout_scope": str(r.get("rollout_scope") or ""),
        "rollout_status": str(r.get("rollout_status") or "rollout_pending").strip().lower(),
        "cohort_type": str(r.get("cohort_type") or "low_risk_subset").strip().lower(),
        "cohort_size": int(r.get("cohort_size") or 0) if str(r.get("cohort_size") or "").strip() not in ("", "None") else 0,
        "cohort_selection_reason": str(r.get("cohort_selection_reason") or ""),
        "stage_promotion_required": bool(r.get("stage_promotion_required")),
        "broader_rollout_blocked": bool(r.get("broader_rollout_blocked")),
        "rollout_reason": str(r.get("rollout_reason") or ""),
        "trust_status": str(r.get("trust_status") or "trusted_current").strip().lower(),
        "confidence_age": str(r.get("confidence_age") or ""),
        "decay_state": str(r.get("decay_state") or "fresh").strip().lower(),
        "revalidation_required": bool(r.get("revalidation_required")),
        "revalidation_reason": str(r.get("revalidation_reason") or ""),
        "trust_window": {
            "window_start": str(trust_window.get("window_start") or ""),
            "window_end": str(trust_window.get("window_end") or ""),
            "policy": str(trust_window.get("policy") or ""),
        },
        "last_validated_at": str(r.get("last_validated_at") or ""),
        "last_revalidated_at": str(r.get("last_revalidated_at") or ""),
        "drift_detected": bool(r.get("drift_detected")),
        "trust_outcome": str(r.get("trust_outcome") or "trust_retained").strip().lower(),
        "strategic_intent_category": str(r.get("strategic_intent_category") or "mission_out_of_scope").strip().lower(),
        "alignment_status": str(r.get("alignment_status") or "aligned_low_priority").strip().lower(),
        "alignment_score": float(r.get("alignment_score") or 0.0)
        if str(r.get("alignment_score") or "").strip() not in ("", "None")
        else 0.0,
        "alignment_reason": str(r.get("alignment_reason") or ""),
        "allowed_goal_class": str(r.get("allowed_goal_class") or ""),
        "prohibited_goal_hit": bool(r.get("prohibited_goal_hit")),
        "executive_priority_match": bool(r.get("executive_priority_match")),
        "mission_scope": str(r.get("mission_scope") or "core_mission"),
        "strategic_outcome": str(r.get("strategic_outcome") or "aligned_but_low_priority").strip().lower(),
        "expected_value": str(r.get("expected_value") or "medium").strip().lower(),
        "expected_cost": str(r.get("expected_cost") or "medium").strip().lower(),
        "expected_complexity": str(r.get("expected_complexity") or "medium").strip().lower(),
        "expected_risk_burden": str(r.get("expected_risk_burden") or "medium").strip().lower(),
        "expected_maintenance_burden": str(r.get("expected_maintenance_burden") or "low").strip().lower(),
        "roi_band": str(r.get("roi_band") or "medium_value").strip().lower(),
        "value_outcome": str(r.get("value_outcome") or "defer_for_later").strip().lower(),
        "value_status": str(r.get("value_status") or ""),
        "priority_value": str(r.get("priority_value") or "medium").strip().lower(),
        "value_reason": str(r.get("value_reason") or ""),
        "recommended_action": str(r.get("recommended_action") or "").strip().lower(),
        "validation_reasons": [str(item) for item in (r.get("validation_reasons") or []) if str(item).strip()][:20],
        "stable_state_ref": str(r.get("stable_state_ref") or ""),
        "success": bool(r.get("success")),
        "authority_trace": dict(r.get("authority_trace") or {}),
        "governance_trace": dict(r.get("governance_trace") or {}),
        "contract_status": str(r.get("contract_status") or ""),
    }


def append_self_change_audit_record(
    *,
    project_path: str | None,
    contract: dict[str, Any] | None,
    outcome_status: str | None = None,
    approved_by: str | None = None,
    approval_status: str | None = None,
    outcome_summary: str | None = None,
    validation_status: str | None = None,
    build_status: str | None = None,
    regression_status: str | None = None,
    stable_state_ref: str | None = None,
    release_lane: str | None = None,
) -> dict[str, Any]:
    audit_path = get_self_change_audit_path(project_path)
    if not audit_path:
        return {"status": "error", "reason": "Self-change audit storage unavailable.", "record": None}
    recent_audit_entries = list_self_change_audit_entries(project_path, n=200)
    record = build_self_change_audit_record(
        contract=contract,
        recent_audit_entries=recent_audit_entries,
        outcome_status=outcome_status,
        approved_by=approved_by,
        approval_status=approval_status,
        outcome_summary=outcome_summary,
        validation_status=validation_status,
        build_status=build_status,
        regression_status=regression_status,
        stable_state_ref=stable_state_ref,
        release_lane=release_lane,
    )
    record["recorded_at"] = record.get("recorded_at") or _utc_now_iso()
    governance_trace = dict(record.get("governance_trace") or {})
    governance_trace["recorded_at"] = record["recorded_at"]
    record["governance_trace"] = governance_trace
    normalized = normalize_self_change_audit_record(record)
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Self-change audit recorded.", "record": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist self-change audit record.", "record": None}


def append_self_change_audit_record_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return append_self_change_audit_record(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist self-change audit record.", "record": None}


def read_self_change_audit_tail(project_path: str | None, n: int = 50) -> list[dict[str, Any]]:
    audit_path = get_self_change_audit_path(project_path)
    if not audit_path:
        return []
    p = Path(audit_path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, int(n or 50)):]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(normalize_self_change_audit_record(parsed))
    return out


def list_self_change_audit_entries(project_path: str | None, n: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(n or 20), MAX_EXECUTION_PACKAGE_LIST_LIMIT))
    rows = read_self_change_audit_tail(project_path=project_path, n=MAX_EXECUTION_PACKAGE_LIST_LIMIT)
    rows.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return rows[:limit]


def record_cursor_bridge_artifact_return(
    *,
    project_path: str | None,
    package_id: str | None = None,
    artifact_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Persist a governed Cursor development artifact onto a linked execution package."""
    normalized_payload = normalize_cursor_artifact_return(artifact_payload)
    actor = str(normalized_payload.get("actor") or "cursor_bridge").strip() or "cursor_bridge"
    linked_package_id = str(package_id or normalized_payload.get("package_id") or "").strip()
    if not linked_package_id:
        validation = build_cursor_bridge_result(
            status="denied",
            operation="artifact_return",
            actor=actor,
            reason="Cursor artifact return requires package linkage.",
            authority_trace=normalized_payload.get("authority_trace"),
            governance_trace=normalized_payload.get("governance_trace"),
            extra_fields={"validation_status": "rejected_package_linkage", "artifact_payload": normalized_payload},
        )
        return {**validation, "package": None, "artifact_record": normalized_payload}

    package = read_execution_package(project_path=project_path, package_id=linked_package_id)
    if not package:
        validation = build_cursor_bridge_result(
            status="denied",
            operation="artifact_return",
            actor=actor,
            reason="Execution package not found for Cursor artifact return.",
            authority_trace=normalized_payload.get("authority_trace"),
            governance_trace=normalized_payload.get("governance_trace"),
            extra_fields={"validation_status": "rejected_package_linkage", "artifact_payload": normalized_payload},
        )
        return {**validation, "package": None, "artifact_record": normalized_payload}

    component_name = infer_component_name(actor) or "cursor_bridge"
    authority = enforce_component_authority_safe(
        component_name=component_name,
        actor=actor,
        requested_actions=["return_governed_artifacts"],
        allowed_components=["cursor_bridge"],
        authority_context={
            "package_id": linked_package_id,
            "bridge_task_id": normalized_payload.get("bridge_task_id"),
            "project_name": package.get("project_name"),
            "source_runtime": normalized_payload.get("source_runtime"),
        },
        denied_action="return_governed_artifacts",
        reason_override="Cursor may only return governed development artifacts; it cannot claim execution, approval, or governance authority.",
    )
    cursor_bridge_summary = _normalize_cursor_bridge_summary(package.get("cursor_bridge_summary"))
    package_governance_trace = _dict_value((package.get("metadata") or {}).get("governance_trace"))
    if not cursor_bridge_summary or not str(cursor_bridge_summary.get("bridge_task_id") or "").strip():
        validation = build_cursor_bridge_result(
            status="denied",
            operation="artifact_return",
            actor=actor,
            reason="Cursor artifact return requires a package already linked to a governed Cursor handoff.",
            authority_trace=normalized_payload.get("authority_trace"),
            governance_trace=normalized_payload.get("governance_trace") or package_governance_trace,
            extra_fields={"validation_status": "rejected_package_linkage", "artifact_payload": normalized_payload},
        )
        return {**validation, "package": package, "artifact_record": normalized_payload}
    if authority.get("status") == "denied":
        denial = build_cursor_bridge_result(
            status="denied",
            operation="artifact_return",
            actor=actor,
            reason=str((authority.get("authority_denial") or {}).get("reason") or "Cursor artifact return denied."),
            authority_trace=authority.get("authority_trace"),
            governance_trace=normalized_payload.get("governance_trace") or package_governance_trace,
            extra_fields={
                "validation_status": "rejected_authority_boundary",
                "artifact_payload": normalized_payload,
                "authority_denial": authority.get("authority_denial") or {},
            },
        )
        return {**denial, "package": package, "artifact_record": normalized_payload}

    raw_payload = dict(artifact_payload or {})
    validation = validate_cursor_artifact_return(
        {
            **raw_payload,
            **normalized_payload,
            "authority_trace": authority.get("authority_trace") or normalized_payload.get("authority_trace"),
            "governance_trace": normalized_payload.get("governance_trace") or package_governance_trace,
        },
        required_package_id=linked_package_id,
        expected_bridge_task_id=cursor_bridge_summary.get("bridge_task_id") or None,
    )
    if validation.get("status") != "ok":
        return {**validation, "package": package, "artifact_record": normalized_payload}

    artifact_record = _normalize_cursor_bridge_artifact_record(
        {
            **normalized_payload,
            "package_id": linked_package_id,
            "package_reference": {
                **_dict_value(normalized_payload.get("package_reference")),
                "package_id": linked_package_id,
            },
            "validation_status": str(validation.get("validation_status") or "validated"),
            "authority_trace": authority.get("authority_trace") or normalized_payload.get("authority_trace"),
            "governance_trace": normalized_payload.get("governance_trace") or package_governance_trace,
            "package_path": get_execution_package_file_path(project_path, linked_package_id) or "",
        }
    )

    runtime_artifact = {
        "artifact_type": "cursor_bridge_artifact_return",
        "bridge_task_id": artifact_record.get("bridge_task_id"),
        "package_id": linked_package_id,
        "artifact_summary": artifact_record.get("artifact_summary"),
        "changed_files": artifact_record.get("changed_files"),
        "patch_summary": artifact_record.get("patch_summary"),
        "validation_status": artifact_record.get("validation_status"),
        "source_runtime": artifact_record.get("source_runtime"),
        "actor": artifact_record.get("actor"),
        "recorded_at": artifact_record.get("recorded_at"),
        "status": artifact_record.get("status"),
        "authority_trace": artifact_record.get("authority_trace"),
    }
    runtime_artifacts = [x for x in list(package.get("runtime_artifacts") or []) if isinstance(x, dict)]
    runtime_artifacts.append(runtime_artifact)
    package["runtime_artifacts"] = runtime_artifacts[:20]

    metadata = dict(package.get("metadata") or {})
    cursor_artifacts = [
        _normalize_cursor_bridge_artifact_record(item)
        for item in list(metadata.get("cursor_bridge_artifacts") or [])
        if isinstance(item, dict)
    ]
    cursor_artifacts.append(artifact_record)
    metadata["cursor_bridge_artifacts"] = cursor_artifacts[:20]

    summary = _normalize_cursor_bridge_summary(package.get("cursor_bridge_summary") or metadata.get("cursor_bridge_summary"))
    summary["package_id"] = linked_package_id
    summary["package_reference"] = {
        **_dict_value(summary.get("package_reference")),
        "package_id": linked_package_id,
    }
    summary["artifact_count"] = len(metadata["cursor_bridge_artifacts"])
    summary["latest_artifact_type"] = str(artifact_record.get("artifact_type") or "")
    summary["latest_validation_status"] = str(artifact_record.get("validation_status") or "")
    summary["latest_recorded_at"] = str(artifact_record.get("recorded_at") or "")
    summary["bridge_status"] = "artifact_recorded"
    summary["status"] = "artifact_recorded"
    metadata["cursor_bridge_summary"] = summary
    package["cursor_bridge_summary"] = summary
    package["cursor_bridge_artifacts"] = metadata["cursor_bridge_artifacts"]
    package["metadata"] = metadata

    persisted = _persist_package_update(
        project_path=project_path,
        package_id=linked_package_id,
        package=package,
        status="ok",
        reason="Cursor artifact return recorded.",
    )
    return {
        **build_cursor_bridge_result(
            status="ok",
            operation="artifact_return",
            actor=actor,
            reason="Cursor artifact return recorded and linked to the execution package.",
            authority_trace=artifact_record.get("authority_trace"),
            governance_trace=artifact_record.get("governance_trace"),
            extra_fields={"validation_status": artifact_record.get("validation_status")},
        ),
        "package": persisted.get("package"),
        "artifact_record": artifact_record,
    }


def record_cursor_bridge_artifact_return_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_cursor_bridge_artifact_return(**kwargs)
    except Exception:
        return {
            "status": "error",
            "operation": "artifact_return",
            "actor": "cursor_bridge",
            "reason": "Failed to record Cursor artifact return.",
            "authority_trace": {},
            "governance_trace": {},
            "package": None,
            "artifact_record": {},
        }


def record_execution_package_decision(
    *,
    project_path: str | None,
    package_id: str | None,
    decision_status: str,
    decision_actor: str,
    decision_notes: str = "",
) -> dict[str, Any]:
    """Persist an immutable human decision onto a sealed package and append a summary journal record."""
    normalized_status = str(decision_status or "").strip().lower()
    if normalized_status not in ("approved", "rejected"):
        return {"status": "error", "reason": "decision_status must be approved or rejected.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    if not bool(package.get("sealed")):
        return {"status": "error", "reason": "Only sealed execution packages may be decided.", "package": package}
    if str(package.get("decision_status") or "pending").strip().lower() != "pending":
        return {"status": "error", "reason": "Execution package decision is immutable once set.", "package": package}
    package["decision_status"] = normalized_status
    package["decision_timestamp"] = _utc_now_iso()
    package["decision_actor"] = str(decision_actor or "").strip()
    package["decision_notes"] = str(decision_notes or "")
    package["decision_id"] = str(uuid.uuid4())
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id)
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution package decision recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package decision.", "package": None}


def record_execution_package_decision_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_decision(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package decision.", "package": None}


def evaluate_execution_package_eligibility(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a package is eligible for future execution without executing anything."""
    p = normalize_execution_package(package)
    if str(p.get("decision_status") or "").strip().lower() == "pending":
        return {
            "eligibility_status": "pending",
            "eligibility_reason": {
                "code": "decision_pending",
                "message": "Eligibility check requires a non-pending decision.",
            },
        }
    if not bool(p.get("sealed")):
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "not_sealed",
                "message": "Package must remain sealed to be eligible.",
            },
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "decision_not_approved",
                "message": "Package decision must be approved.",
            },
        }
    if not (p.get("approval_id_refs") or []):
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "approval_refs_missing",
                "message": "Approval references are required.",
            },
        }
    runtime_target_id = str(p.get("runtime_target_id") or "").strip().lower()
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(runtime_target_id) or {}
    except Exception:
        runtime_target = {}
    if not runtime_target or str(runtime_target.get("active_or_planned") or "").strip().lower() != "active":
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "runtime_target_invalid",
                "message": "Runtime target must be known and active.",
            },
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "eligibility_status": "ineligible",
            "eligibility_reason": {
                "code": "execution_detected",
                "message": "Package indicates execution has already occurred.",
            },
        }
    return {
        "eligibility_status": "eligible",
        "eligibility_reason": {
            "code": "eligible",
            "message": "Package is eligible for future execution review.",
        },
    }


def evaluate_execution_package_release(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a package can be released for future execution without executing it."""
    p = normalize_execution_package(package)
    if not bool(p.get("sealed")):
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "not_sealed",
                "message": "Package must remain sealed to be released.",
            },
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "decision_not_approved",
                "message": "Package decision must be approved.",
            },
        }
    if str(p.get("eligibility_status") or "").strip().lower() != "eligible":
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "eligibility_not_eligible",
                "message": "Package eligibility must be eligible before release.",
            },
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "release_status": "blocked",
            "release_reason": {
                "code": "execution_detected",
                "message": "Package indicates execution has already occurred.",
            },
        }
    return {
        "release_status": "released",
        "release_reason": {
            "code": "released",
            "message": "Package is released for future execution handling.",
        },
    }


def evaluate_execution_package_handoff(
    package: dict[str, Any] | None,
    *,
    executor_target_id: str | None,
) -> dict[str, Any]:
    """Evaluate whether a released package can be handed to a future executor without executing it."""
    p = normalize_execution_package(package)
    target_id = str(executor_target_id or "").strip().lower()
    empty = {
        "handoff_executor_target_id": target_id,
        "handoff_executor_target_name": "",
        "handoff_aegis_result": {},
    }

    if not bool(p.get("sealed")):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "not_sealed", "message": "Package must remain sealed to be handed off."},
            **empty,
        }
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "decision_not_approved", "message": "Package decision must be approved before handoff."},
            **empty,
        }
    eligibility_status = str(p.get("eligibility_status") or "").strip().lower()
    if eligibility_status == "pending":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "eligibility_pending", "message": "Package eligibility must not be pending before handoff."},
            **empty,
        }
    if eligibility_status != "eligible":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "eligibility_not_eligible", "message": "Package eligibility must be eligible before handoff."},
            **empty,
        }
    if str(p.get("release_status") or "").strip().lower() != "released":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "release_not_released", "message": "Package release status must be released before handoff."},
            **empty,
        }
    execution_summary = p.get("execution_summary") or {}
    runtime_artifacts = p.get("runtime_artifacts") or []
    if bool(execution_summary.get("can_execute")) or len(runtime_artifacts) > 0:
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "execution_detected", "message": "Package indicates execution has already occurred."},
            **empty,
        }

    runtime_target = {}
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(target_id) or {}
    except Exception:
        runtime_target = {}
    capabilities = [str(x).strip().lower() for x in (runtime_target.get("capabilities") or []) if str(x).strip()]
    target_name = str(runtime_target.get("display_name") or runtime_target.get("canonical_name") or "")
    backend_id = _resolve_executor_backend_id(p)
    if backend_id == "openclaw" and target_id != "openclaw":
        return {
            "handoff_status": "blocked",
            "handoff_reason": {
                "code": "executor_backend_target_mismatch",
                "message": "OpenClaw backend requires the openclaw executor target.",
            },
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name,
            "handoff_aegis_result": {},
        }
    if backend_id == "openclaw" and "controlled_executor" not in capabilities:
        return {
            "handoff_status": "blocked",
            "handoff_reason": {
                "code": "executor_capability_mismatch",
                "message": "OpenClaw backend requires a controlled_executor-capable target.",
            },
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name,
            "handoff_aegis_result": {},
        }
    if (
        not runtime_target
        or str(runtime_target.get("active_or_planned") or "").strip().lower() not in ("active", "planned")
        or "execute" not in capabilities
        or target_id == "windows_review_package"
    ):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {
                "code": "executor_target_invalid",
                "message": "Executor target must exist, be active or planned, support execute, and not be windows_review_package.",
            },
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name,
            "handoff_aegis_result": {},
        }

    try:
        from AEGIS.aegis_contract import normalize_aegis_result
        from AEGIS.aegis_core import evaluate_action_safe

        candidate_paths = [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50]
        routing = p.get("routing_summary") or {}
        tool_name = str(routing.get("tool_name") or "").strip().lower()
        aegis_request = {
            "project_name": p.get("project_name"),
            "project_path": p.get("project_path"),
            "runtime_target_id": target_id,
            "action": p.get("requested_action") or "adapter_dispatch_call",
            "action_mode": "execution",
            "requires_human_approval": bool(p.get("requires_human_approval")),
            "candidate_paths": candidate_paths,
            "requested_reads": candidate_paths,
        }
        if tool_name:
            aegis_request["tool_family"] = "file_write" if ("write" in tool_name or "patch" in tool_name) else "file_read"
        aegis_result = normalize_aegis_result(evaluate_action_safe(request=aegis_request))
    except Exception:
        aegis_result = _normalize_handoff_aegis_result(None)

    aegis_decision = str(aegis_result.get("aegis_decision") or "").strip().lower()
    workspace_valid = aegis_result.get("workspace_valid")
    file_guard_status = str(aegis_result.get("file_guard_status") or "").strip().lower()
    if aegis_decision in ("deny", "error_fallback"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "aegis_blocked", "message": "AEGIS denied or failed handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if workspace_valid is False:
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "workspace_invalid", "message": "AEGIS workspace validation failed during handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if file_guard_status in ("deny", "error_fallback"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "file_guard_blocked", "message": "AEGIS file guard blocked handoff re-evaluation."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    if aegis_decision not in ("allow", "approval_required"):
        return {
            "handoff_status": "blocked",
            "handoff_reason": {"code": "aegis_blocked", "message": "AEGIS did not return an allowed handoff decision."},
            "handoff_executor_target_id": target_id,
            "handoff_executor_target_name": target_name or target_id,
            "handoff_aegis_result": aegis_result,
        }
    return {
        "handoff_status": "authorized",
        "handoff_reason": {"code": "authorized", "message": "Package is authorized for future executor handoff."},
        "handoff_executor_target_id": target_id,
        "handoff_executor_target_name": target_name or target_id,
        "handoff_aegis_result": aegis_result,
    }


def evaluate_execution_package_execution(package: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate whether a handed-off package may execute through the controlled runtime boundary."""
    p = normalize_execution_package(package)
    target_id = str(p.get("handoff_executor_target_id") or p.get("runtime_target_id") or "").strip().lower()
    target_name = str(p.get("handoff_executor_target_name") or p.get("runtime_target_name") or target_id)
    retry_policy = normalize_retry_policy(p.get("retry_policy"))
    idempotency = normalize_idempotency(p.get("idempotency"), package=p)

    def _blocked(code: str, message: str, *, failure_class: str = "preflight_block", aegis_result: dict[str, Any] | None = None) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        failure_summary = summarize_failure(failure_class=failure_class, timestamp=timestamp)
        rollback_repair = normalize_rollback_repair(None)
        integrity = normalize_integrity_verification(None)
        return {
            "execution_status": "blocked",
            "execution_reason": {"code": code, "message": message},
            "execution_executor_target_id": target_id,
            "execution_executor_target_name": target_name,
            "execution_aegis_result": aegis_result or {},
            "execution_receipt": _empty_execution_receipt(result_status="blocked", failure_class=failure_class),
            "rollback_status": "not_needed",
            "rollback_reason": {"code": "", "message": ""},
            "failure_summary": failure_summary,
            "rollback_repair": rollback_repair,
            "integrity_verification": integrity,
            "recovery_summary": evaluate_recovery_summary(
                execution_status="blocked",
                failure_summary=failure_summary,
                retry_policy=retry_policy,
                rollback_repair=rollback_repair,
                integrity_verification=integrity,
            ),
            "retry_policy": retry_policy,
            "idempotency": idempotency,
        }

    if not bool(p.get("sealed")):
        return _blocked("not_sealed", "Package must remain sealed to execute.")
    if str(p.get("decision_status") or "").strip().lower() != "approved":
        return _blocked("decision_not_approved", "Package decision must be approved before execution.")
    if str(p.get("eligibility_status") or "").strip().lower() != "eligible":
        return _blocked("eligibility_not_eligible", "Package eligibility must be eligible before execution.")
    if str(p.get("release_status") or "").strip().lower() != "released":
        return _blocked("release_not_released", "Package release status must be released before execution.")
    if str(p.get("handoff_status") or "").strip().lower() != "authorized":
        return _blocked("handoff_not_authorized", "Package handoff must be authorized before execution.")
    if str(p.get("execution_status") or "").strip().lower() == "succeeded":
        if retry_policy.get("retry_authorized") is not True:
            idempotency["idempotency_status"] = "duplicate_success_blocked"
            idempotency["duplicate_success_blocked"] = True
            idempotency["last_success_execution_id"] = str(p.get("execution_id") or idempotency.get("last_success_execution_id") or "")
            return _blocked(
                "duplicate_success_blocked",
                "Package already succeeded; repeated execution is blocked unless a future retry policy explicitly authorizes it.",
                failure_class="duplicate_success_block",
            )
        if retry_policy.get("max_retry_attempts", 0) <= retry_policy.get("retry_count", 0):
            return _blocked(
                "retry_exhausted",
                "Package retry limit has been exhausted.",
                failure_class="retry_exhausted",
            )
        idempotency["idempotency_status"] = "retry_window_open"

    runtime_target = {}
    try:
        from NEXUS.runtime_target_registry import RUNTIME_TARGET_REGISTRY

        runtime_target = RUNTIME_TARGET_REGISTRY.get(target_id) or {}
    except Exception:
        runtime_target = {}
    capabilities = [str(x).strip().lower() for x in (runtime_target.get("capabilities") or []) if str(x).strip()]
    target_name = str(runtime_target.get("display_name") or runtime_target.get("canonical_name") or target_name)
    backend_id = _resolve_executor_backend_id(p)
    if backend_id == "openclaw" and target_id != "openclaw":
        return _blocked(
            "executor_backend_target_mismatch",
            "OpenClaw backend requires the openclaw executor target.",
        )
    if backend_id == "openclaw" and "controlled_executor" not in capabilities:
        return _blocked(
            "executor_capability_mismatch",
            "OpenClaw backend requires a controlled_executor-capable target.",
        )
    if (
        not runtime_target
        or str(runtime_target.get("active_or_planned") or "").strip().lower() != "active"
        or "execute" not in capabilities
        or target_id == "windows_review_package"
    ):
        return _blocked(
            "executor_target_invalid",
            "Executor target must be active, support execute, and not be windows_review_package.",
        )

    try:
        from AEGIS.aegis_contract import normalize_aegis_result
        from AEGIS.aegis_core import evaluate_action_safe

        candidate_paths = [str(x) for x in (p.get("candidate_paths") or []) if str(x).strip()][:50]
        routing = p.get("routing_summary") or {}
        tool_name = str(routing.get("tool_name") or "").strip().lower()
        aegis_request = {
            "project_name": p.get("project_name"),
            "project_path": p.get("project_path"),
            "runtime_target_id": target_id,
            "action": p.get("requested_action") or "adapter_dispatch_call",
            "action_mode": "execution",
            "requires_human_approval": bool(p.get("requires_human_approval")),
            "candidate_paths": candidate_paths,
            "requested_reads": candidate_paths,
        }
        if tool_name:
            aegis_request["tool_family"] = "file_write" if ("write" in tool_name or "patch" in tool_name) else "file_read"
        aegis_result = normalize_aegis_result(evaluate_action_safe(request=aegis_request))
    except Exception:
        aegis_result = _normalize_handoff_aegis_result(None)

    aegis_decision = str(aegis_result.get("aegis_decision") or "").strip().lower()
    workspace_valid = aegis_result.get("workspace_valid")
    file_guard_status = str(aegis_result.get("file_guard_status") or "").strip().lower()
    if aegis_decision in ("deny", "error_fallback"):
        return _blocked("aegis_blocked", "AEGIS denied or failed execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if workspace_valid is False:
        return _blocked("workspace_invalid", "AEGIS workspace validation failed during execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if file_guard_status in ("deny", "error_fallback"):
        return _blocked("file_guard_blocked", "AEGIS file guard blocked execution re-evaluation.", failure_class="aegis_block", aegis_result=aegis_result)
    if aegis_decision not in ("allow", "approval_required"):
        return _blocked("aegis_blocked", "AEGIS did not return an allowed execution decision.", failure_class="aegis_block", aegis_result=aegis_result)

    return {
        "execution_status": "ready",
        "execution_reason": {"code": "ready", "message": "Package is ready for controlled runtime execution."},
        "execution_executor_target_id": target_id,
        "execution_executor_target_name": target_name or target_id,
        "execution_aegis_result": aegis_result,
        "execution_receipt": _empty_execution_receipt(result_status="ready"),
        "rollback_status": "not_needed",
        "rollback_reason": {"code": "", "message": ""},
        "failure_summary": normalize_failure_summary(None),
        "recovery_summary": normalize_recovery_summary(None),
        "rollback_repair": normalize_rollback_repair(None),
        "integrity_verification": normalize_integrity_verification(None),
        "retry_policy": retry_policy,
        "idempotency": idempotency,
    }


def record_execution_package_eligibility(
    *,
    project_path: str | None,
    package_id: str | None,
    eligibility_checked_by: str,
) -> dict[str, Any]:
    """Evaluate and persist package eligibility using package-local facts only."""
    checked_by = str(eligibility_checked_by or "").strip()
    if not checked_by:
        return {"status": "error", "reason": "eligibility_checked_by required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_eligibility(package)
    if evaluation.get("eligibility_status") == "pending":
        return {
            "status": "error",
            "reason": str((evaluation.get("eligibility_reason") or {}).get("message") or "Eligibility check requires a non-pending decision."),
            "package": package,
        }
    package["eligibility_status"] = evaluation.get("eligibility_status") or "pending"
    package["eligibility_timestamp"] = _utc_now_iso()
    package["eligibility_reason"] = _normalize_eligibility_reason(evaluation.get("eligibility_reason"))
    package["eligibility_checked_by"] = checked_by
    package["eligibility_check_id"] = str(uuid.uuid4())
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id)
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution package eligibility recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package eligibility.", "package": None}


def record_execution_package_eligibility_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_eligibility(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package eligibility.", "package": None}


def record_execution_package_release(
    *,
    project_path: str | None,
    package_id: str | None,
    release_actor: str,
    release_notes: str = "",
) -> dict[str, Any]:
    """Evaluate and persist package release state using package-local facts only."""
    actor = str(release_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "release_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_release(package)
    package["release_status"] = evaluation.get("release_status") or "pending"
    package["release_timestamp"] = _utc_now_iso()
    package["release_actor"] = actor
    package["release_notes"] = str(release_notes or "")
    package["release_id"] = str(uuid.uuid4())
    package["release_reason"] = _normalize_release_reason(evaluation.get("release_reason"))
    package["release_version"] = "v1"
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id)
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution package release recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package release.", "package": None}


def record_execution_package_release_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_release(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package release.", "package": None}


def record_execution_package_handoff(
    *,
    project_path: str | None,
    package_id: str | None,
    handoff_actor: str,
    executor_target_id: str,
    handoff_notes: str = "",
) -> dict[str, Any]:
    """Evaluate and persist package handoff status using package JSON as the source of truth."""
    actor = str(handoff_actor or "").strip()
    target_id = str(executor_target_id or "").strip().lower()
    if not actor:
        return {"status": "error", "reason": "handoff_actor required.", "package": None}
    if not target_id:
        return {"status": "error", "reason": "executor_target_id required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    evaluation = evaluate_execution_package_handoff(package, executor_target_id=target_id)
    package["handoff_status"] = evaluation.get("handoff_status") or "pending"
    package["handoff_timestamp"] = _utc_now_iso()
    package["handoff_actor"] = actor
    package["handoff_notes"] = str(handoff_notes or "")
    package["handoff_id"] = str(uuid.uuid4())
    package["handoff_reason"] = _normalize_handoff_reason(evaluation.get("handoff_reason"))
    package["handoff_version"] = "v1"
    package["handoff_executor_target_id"] = str(evaluation.get("handoff_executor_target_id") or target_id)
    package["handoff_executor_target_name"] = str(evaluation.get("handoff_executor_target_name") or target_id)
    package["handoff_aegis_result"] = _normalize_handoff_aegis_result(evaluation.get("handoff_aegis_result"))
    normalized = normalize_execution_package(package)
    package_path = get_execution_package_file_path(project_path, package_id)
    journal_path = get_execution_package_journal_path(project_path)
    if not package_path or not journal_path:
        return {"status": "error", "reason": "Execution package storage unavailable.", "package": None}
    try:
        Path(package_path).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        journal_record = _build_execution_package_journal_record(normalized, package_path)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(journal_record, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Execution package handoff recorded.", "package": normalized}
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package handoff.", "package": None}


def record_execution_package_handoff_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_handoff(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package handoff.", "package": None}


def record_execution_package_execution(
    *,
    project_path: str | None,
    package_id: str | None,
    execution_actor: str,
) -> dict[str, Any]:
    """Evaluate and persist controlled runtime execution state for an authorized package."""
    actor = str(execution_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "execution_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    projected_execution_cost = _estimate_package_cost_tracking(package)
    projected_operation_cost = float(projected_execution_cost.get("cost_estimate") or 0.0)
    run_id = str(package.get("run_id") or "")
    journal_rows = list_execution_package_journal_entries(project_path, n=50)
    journal_cost_totals = summarize_journal_estimated_costs(journal_rows, run_id=run_id)
    budget_caps = _resolve_package_budget_caps(package, project_path)
    projected_budget_control = evaluate_budget_controls(
        budget_caps=budget_caps,
        current_operation_cost=projected_operation_cost,
        current_project_cost=float(journal_cost_totals.get("project_estimated_cost_total") or 0.0) + projected_operation_cost,
        current_session_cost=float(journal_cost_totals.get("session_estimated_cost_total") or 0.0) + projected_operation_cost,
    )
    package["budget_caps"] = projected_budget_control.get("budget_caps") or budget_caps
    package["budget_control"] = projected_budget_control
    package.update(_budget_fields_from_control(projected_budget_control))
    if bool(projected_budget_control.get("kill_switch_active")):
        blocked_at = _utc_now_iso()
        package["execution_status"] = "blocked"
        package["execution_timestamp"] = blocked_at
        package["execution_started_at"] = blocked_at
        package["execution_finished_at"] = blocked_at
        package["execution_actor"] = actor
        package["execution_id"] = str(uuid.uuid4())
        package["execution_version"] = "v1"
        package["execution_reason"] = _normalize_execution_reason(
            {
                "code": "budget_kill_switch_triggered",
                "message": str(projected_budget_control.get("budget_reason") or "Budget kill switch triggered."),
            }
        )
        package["execution_receipt"] = _normalize_execution_receipt(
            {
                "result_status": "blocked",
                "failure_class": "preflight_block",
                "stderr_summary": (
                    "Budget cap exceeded; progression blocked by kill switch without bypassing governance."
                ),
            }
        )
        package["rollback_status"] = "not_needed"
        package["rollback_timestamp"] = ""
        package["rollback_reason"] = _normalize_rollback_reason({"code": "", "message": ""})
        package["failure_summary"] = normalize_failure_summary(
            summarize_failure(failure_class="preflight_block", timestamp=blocked_at)
        )
        package["integrity_verification"] = verify_terminal_execution_integrity(package)
        package["recovery_summary"] = normalize_recovery_summary(
            evaluate_recovery_summary(
                execution_status="blocked",
                failure_summary=package.get("failure_summary"),
                retry_policy=package.get("retry_policy"),
                rollback_repair=package.get("rollback_repair"),
                integrity_verification=package.get("integrity_verification"),
            )
        )
        package["cost_tracking"] = {
            **projected_execution_cost,
            "cost_source": "runtime_execution",
            "cost_breakdown": {
                **dict(projected_execution_cost.get("cost_breakdown") or {}),
                "model": "forge_runtime_cost_estimator",
            },
        }
        return _persist_package_update(
            project_path=project_path,
            package_id=package_id,
            package=package,
            status="denied",
            reason=str(projected_budget_control.get("budget_reason") or "Budget kill switch triggered."),
        )
    execution_component = "openclaw"
    execution_authority = enforce_component_authority_safe(
        component_name=execution_component,
        actor=actor,
        requested_actions=["execute_package"],
        allowed_components=[execution_component],
        authority_context={
            "package_id": package_id,
            "project_name": package.get("project_name"),
            "runtime_target_id": package.get("handoff_executor_target_id") or package.get("runtime_target_id"),
        },
    )
    package = _with_package_authority_event(
        package,
        scope="execution",
        authority_trace=execution_authority.get("authority_trace"),
        authority_denial=execution_authority.get("authority_denial"),
    )
    execution_id = str(uuid.uuid4())
    started_at = _utc_now_iso()
    evaluation = evaluate_execution_package_execution(package)
    retry_policy = normalize_retry_policy(package.get("retry_policy"))
    idempotency = normalize_idempotency(package.get("idempotency"), package=package)
    prior_execution_status = str(package.get("execution_status") or "").strip().lower()
    package["execution_actor"] = actor
    package["execution_id"] = execution_id
    package["execution_version"] = "v1"
    package["execution_timestamp"] = started_at
    package["execution_started_at"] = started_at
    package["execution_executor_target_id"] = str(evaluation.get("execution_executor_target_id") or "")
    package["execution_executor_target_name"] = str(evaluation.get("execution_executor_target_name") or "")
    package["execution_executor_backend_id"] = _resolve_executor_backend_id(package)
    package["execution_aegis_result"] = _normalize_handoff_aegis_result(evaluation.get("execution_aegis_result"))
    package["retry_policy"] = normalize_retry_policy(evaluation.get("retry_policy") or retry_policy)
    package["idempotency"] = normalize_idempotency(evaluation.get("idempotency") or idempotency, package=package)
    package["failure_summary"] = normalize_failure_summary(evaluation.get("failure_summary"))
    package["recovery_summary"] = normalize_recovery_summary(evaluation.get("recovery_summary"))
    package["rollback_repair"] = normalize_rollback_repair(evaluation.get("rollback_repair"))
    package["integrity_verification"] = normalize_integrity_verification(evaluation.get("integrity_verification"))

    if execution_authority.get("status") == "denied":
        denial = execution_authority.get("authority_denial") or {}
        package["execution_status"] = "blocked"
        package["execution_reason"] = _normalize_execution_reason(
            {
                "code": "authority_denied",
                "message": str(denial.get("reason") or "Execution authority denied."),
            }
        )
        package["execution_receipt"] = _normalize_execution_receipt(
            {
                "result_status": "blocked",
                "failure_class": "preflight_block",
                "stderr_summary": str(denial.get("reason") or "authority_denied"),
            }
        )
        package["execution_finished_at"] = _utc_now_iso()
        package["rollback_status"] = "not_needed"
        package["rollback_timestamp"] = ""
        package["rollback_reason"] = _normalize_rollback_reason({"code": "", "message": ""})
        package["failure_summary"] = normalize_failure_summary(
            summarize_failure(failure_class="preflight_block", timestamp=package["execution_finished_at"])
        )
        package["cost_tracking"] = _build_estimated_cost_tracking(
            cost_source="runtime_execution",
            estimated_tokens=120,
            model="forge_runtime_cost_estimator",
        )
        package["recovery_summary"] = normalize_recovery_summary(
            evaluate_recovery_summary(
                execution_status="blocked",
                failure_summary=package.get("failure_summary"),
                retry_policy=package.get("retry_policy"),
                rollback_repair=package.get("rollback_repair"),
                integrity_verification=package.get("integrity_verification"),
            )
        )
        return _persist_package_update(
            project_path=project_path,
            package_id=package_id,
            package=package,
            status="denied",
            reason=str(denial.get("reason") or "Execution authority denied."),
        )

    if evaluation.get("execution_status") == "blocked":
        package["execution_status"] = "blocked"
        package["execution_reason"] = _normalize_execution_reason(evaluation.get("execution_reason"))
        package["execution_receipt"] = _normalize_execution_receipt(evaluation.get("execution_receipt"))
        package["execution_finished_at"] = _utc_now_iso()
        package["rollback_status"] = "not_needed"
        package["rollback_timestamp"] = ""
        package["rollback_reason"] = _normalize_rollback_reason(evaluation.get("rollback_reason"))
    else:
        if prior_execution_status in ("succeeded", "failed", "blocked", "rolled_back") and package["retry_policy"].get("retry_authorized"):
            package["retry_policy"] = normalize_retry_policy(
                {
                    **(package.get("retry_policy") or {}),
                    "retry_count": int((package.get("retry_policy") or {}).get("retry_count") or 0) + 1,
                    "policy_status": "retry_authorized",
                }
            )
        try:
            from NEXUS.execution_package_executor import execute_execution_package_safe

            exec_result = execute_execution_package_safe(
                project_path=project_path,
                package=package,
                execution_id=execution_id,
                execution_actor=actor,
            )
        except Exception:
            exec_result = {
                "execution_status": "failed",
                "execution_reason": {"code": "runtime_start_failed", "message": "Runtime execution bridge unavailable."},
                "execution_receipt": _empty_execution_receipt(result_status="failed", failure_class="runtime_start_failure"),
                "rollback_status": "not_needed",
                "rollback_timestamp": "",
                "rollback_reason": {"code": "", "message": ""},
                "runtime_artifact": {},
                "execution_finished_at": _utc_now_iso(),
            }
        package["execution_status"] = str(exec_result.get("execution_status") or "failed")
        package["execution_reason"] = _normalize_execution_reason(exec_result.get("execution_reason"))
        package["execution_receipt"] = _normalize_execution_receipt(exec_result.get("execution_receipt"))
        package["execution_finished_at"] = str(exec_result.get("execution_finished_at") or _utc_now_iso())
        if package["execution_started_at"] and package["execution_finished_at"] and package["execution_started_at"] > package["execution_finished_at"]:
            package["execution_started_at"] = package["execution_finished_at"]
        package["execution_timestamp"] = package["execution_finished_at"]
        package["rollback_status"] = str(exec_result.get("rollback_status") or "not_needed")
        package["rollback_timestamp"] = str(exec_result.get("rollback_timestamp") or "")
        package["rollback_reason"] = _normalize_rollback_reason(exec_result.get("rollback_reason"))
        package["failure_summary"] = normalize_failure_summary(exec_result.get("failure_summary"))
        package["rollback_repair"] = normalize_rollback_repair(exec_result.get("rollback_repair"))
        package = _with_package_authority_event(
            package,
            scope="execution",
            authority_trace=exec_result.get("authority_trace") or execution_authority.get("authority_trace"),
            authority_denial=exec_result.get("authority_denial") or execution_authority.get("authority_denial"),
        )
        runtime_artifact = exec_result.get("runtime_artifact")
        if isinstance(runtime_artifact, dict) and runtime_artifact:
            artifacts = list(package.get("runtime_artifacts") or [])
            artifacts.append(runtime_artifact)
            package["runtime_artifacts"] = [x for x in artifacts[:20] if isinstance(x, dict)]
        if package["execution_status"] == "succeeded":
            package["idempotency"] = normalize_idempotency(
                {
                    **(package.get("idempotency") or {}),
                    "idempotency_status": "active",
                    "last_success_execution_id": execution_id,
                    "duplicate_success_blocked": False,
                },
                package=package,
            )
        if package["execution_status"] in ("blocked", "failed", "rolled_back", "succeeded"):
            package["integrity_verification"] = verify_terminal_execution_integrity(package)
            package["recovery_summary"] = evaluate_recovery_summary(
                execution_status=package["execution_status"],
                failure_summary=package.get("failure_summary"),
                retry_policy=package.get("retry_policy"),
                rollback_repair=package.get("rollback_repair"),
                integrity_verification=package.get("integrity_verification"),
            )

    if package.get("execution_status") == "blocked":
        package["integrity_verification"] = verify_terminal_execution_integrity(package)
        package["recovery_summary"] = evaluate_recovery_summary(
            execution_status=package["execution_status"],
            failure_summary=package.get("failure_summary"),
            retry_policy=package.get("retry_policy"),
            rollback_repair=package.get("rollback_repair"),
            integrity_verification=package.get("integrity_verification"),
        )
    execution_cost = _estimate_package_cost_tracking(package)
    package["cost_tracking"] = {
        **execution_cost,
        "cost_source": "runtime_execution",
        "cost_breakdown": {
            **dict(execution_cost.get("cost_breakdown") or {}),
            "model": "forge_runtime_cost_estimator",
        },
    }
    post_journal_rows = list_execution_package_journal_entries(project_path, n=50)
    post_cost_totals = summarize_journal_estimated_costs(post_journal_rows, run_id=run_id)
    operation_cost = float(package["cost_tracking"].get("cost_estimate") or 0.0)
    budget_control = evaluate_budget_controls(
        budget_caps=_resolve_package_budget_caps(package, project_path),
        current_operation_cost=operation_cost,
        current_project_cost=float(post_cost_totals.get("project_estimated_cost_total") or 0.0) + operation_cost,
        current_session_cost=float(post_cost_totals.get("session_estimated_cost_total") or 0.0) + operation_cost,
    )
    package["budget_caps"] = budget_control.get("budget_caps") or _resolve_package_budget_caps(package, project_path)
    package["budget_control"] = budget_control
    package.update(_budget_fields_from_control(budget_control))

    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package execution recorded.",
    )


def record_execution_package_execution_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_execution(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package execution.", "package": None}


def record_execution_package_evaluation(
    *,
    project_path: str | None,
    package_id: str | None,
    evaluation_actor: str,
) -> dict[str, Any]:
    """Persist explicit Abacus evaluation derived only from package-local fields."""
    actor = str(evaluation_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "evaluation_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    component_name = infer_component_name(actor)
    evaluation_authority = enforce_component_authority_safe(
        component_name=component_name,
        actor=actor,
        requested_actions=["evaluate_execution"],
        allowed_components=["abacus"],
        authority_context={"package_id": package_id, "project_name": package.get("project_name")},
    )
    package = _with_package_authority_event(
        package,
        scope="evaluation",
        authority_trace=evaluation_authority.get("authority_trace"),
        authority_denial=evaluation_authority.get("authority_denial"),
    )
    if evaluation_authority.get("status") == "denied":
        return _persist_package_update(
            project_path=project_path,
            package_id=package_id,
            package=package,
            status="denied",
            reason=str(((evaluation_authority.get("authority_denial") or {}).get("reason")) or "Evaluation authority denied."),
        )

    evaluation = evaluate_execution_package_safe(package)
    package["evaluation_status"] = _normalize_evaluation_status(evaluation.get("evaluation_status"))
    package["evaluation_timestamp"] = _utc_now_iso()
    package["evaluation_actor"] = actor
    package["evaluation_id"] = str(uuid.uuid4())
    package["evaluation_version"] = "v1"
    package["evaluation_reason"] = normalize_evaluation_reason(evaluation.get("evaluation_reason"))
    package["evaluation_basis"] = normalize_evaluation_basis(evaluation.get("evaluation_basis"))
    package["evaluation_summary"] = normalize_evaluation_summary(evaluation.get("evaluation_summary"))

    persisted = _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package evaluation recorded.",
    )
    if persisted.get("status") == "ok":
        normalized = persisted.get("package") or {}
        write_governed_memory_safe(
            actor="abacus",
            entry={
                "source_type": "abacus_evaluation",
                "source_project": str(normalized.get("project_name") or ""),
                "scope": "cross_project",
                "category": f"evaluation:{((normalized.get('evaluation_reason') or {}).get('code') or 'unknown')}",
                "summary": (
                    f"Abacus evaluation observed execution_status="
                    f"{str(normalized.get('execution_status') or 'unknown')} with failure_risk_band="
                    f"{str(((normalized.get('evaluation_summary') or {}).get('failure_risk_band') or 'unknown'))}."
                ),
                "evidence": [
                    f"package_id:{str(normalized.get('package_id') or '')}",
                    f"evaluation_id:{str(normalized.get('evaluation_id') or '')}",
                    f"reason_code:{str(((normalized.get('evaluation_reason') or {}).get('code') or 'unknown'))}",
                ],
                "confidence": 0.8,
                "attribution": "abacus:evaluation_pipeline",
                "status": "active",
                "governance_trace": {
                    "advisory_only": True,
                    "origin": "record_execution_package_evaluation",
                    "package_id": normalized.get("package_id"),
                    "evaluation_status": normalized.get("evaluation_status"),
                },
            },
            allowed_components=("abacus",),
            reason="Abacus evaluation pattern recorded through governed memory.",
        )
    return persisted


def record_execution_package_evaluation_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_evaluation(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package evaluation.", "package": None}


def record_execution_package_local_analysis(
    *,
    project_path: str | None,
    package_id: str | None,
    analysis_actor: str,
) -> dict[str, Any]:
    """Persist advisory-only NemoClaw local analysis onto a package."""
    actor = str(analysis_actor or "").strip() or "nemoclaw"
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    component_name = infer_component_name(actor)
    analysis_authority = enforce_component_authority_safe(
        component_name=component_name,
        actor=actor,
        requested_actions=["analyze_locally"],
        allowed_components=["nemoclaw"],
        authority_context={"package_id": package_id, "project_name": package.get("project_name")},
    )
    package = _with_package_authority_event(
        package,
        scope="local_analysis",
        authority_trace=analysis_authority.get("authority_trace"),
        authority_denial=analysis_authority.get("authority_denial"),
    )
    if analysis_authority.get("status") == "denied":
        return _persist_package_update(
            project_path=project_path,
            package_id=package_id,
            package=package,
            status="denied",
            reason=str(((analysis_authority.get("authority_denial") or {}).get("reason")) or "Local analysis authority denied."),
        )

    analysis = analyze_execution_package_locally_safe(package)
    package["local_analysis_status"] = _normalize_local_analysis_status(analysis.get("local_analysis_status"))
    package["local_analysis_timestamp"] = _utc_now_iso()
    package["local_analysis_actor"] = actor
    package["local_analysis_id"] = str(uuid.uuid4())
    package["local_analysis_version"] = "v1"
    package["local_analysis_reason"] = normalize_local_analysis_reason(analysis.get("local_analysis_reason"))
    package["local_analysis_basis"] = normalize_local_analysis_basis(analysis.get("local_analysis_basis"))
    package["local_analysis_summary"] = normalize_local_analysis_summary(analysis.get("local_analysis_summary"))

    persisted = _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package local analysis recorded.",
    )
    if persisted.get("status") == "ok":
        normalized = persisted.get("package") or {}
        write_governed_memory_safe(
            actor="nemoclaw",
            entry={
                "source_type": "nemoclaw_advisory",
                "source_project": str(normalized.get("project_name") or ""),
                "scope": "project",
                "category": f"local_analysis:{((normalized.get('local_analysis_summary') or {}).get('suggested_next_action') or 'unknown')}",
                "summary": (
                    f"NemoClaw advisory suggested next_action="
                    f"{str(((normalized.get('local_analysis_summary') or {}).get('suggested_next_action') or 'unknown'))} "
                    f"for execution_status={str(normalized.get('execution_status') or 'unknown')}."
                ),
                "evidence": [
                    f"package_id:{str(normalized.get('package_id') or '')}",
                    f"local_analysis_id:{str(normalized.get('local_analysis_id') or '')}",
                    f"confidence_band:{str(((normalized.get('local_analysis_summary') or {}).get('confidence_band') or 'unknown'))}",
                ],
                "confidence": 0.7,
                "attribution": "nemoclaw:local_analysis_pipeline",
                "status": "active",
                "governance_trace": {
                    "advisory_only": True,
                    "origin": "record_execution_package_local_analysis",
                    "package_id": normalized.get("package_id"),
                    "local_analysis_status": normalized.get("local_analysis_status"),
                },
            },
            allowed_components=("nemoclaw",),
            reason="NemoClaw advisory pattern recorded through governed memory.",
        )
    return persisted


def record_execution_package_local_analysis_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_local_analysis(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package local analysis.", "package": None}


def record_execution_package_governance(
    *,
    project_path: str | None,
    package_id: str | None,
    governance_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Persist governance conflict and pause semantics onto an existing package."""
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    result = governance_result if isinstance(governance_result, dict) else {}
    metadata = dict(package.get("metadata") or {})
    metadata["governance_conflict"] = dict(result.get("governance_conflict") or {})
    metadata["governance_trace"] = dict(result.get("governance_trace") or {})
    metadata["governance_resolution_state"] = str(result.get("resolution_state") or "")
    metadata["governance_routing_outcome"] = str(result.get("routing_outcome") or "")
    metadata["governance_status"] = str(result.get("governance_status") or "")
    package["metadata"] = metadata
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package governance metadata recorded.",
    )


def record_execution_package_governance_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_governance(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package governance metadata.", "package": None}


def record_execution_package_revenue_activation(
    *,
    project_path: str | None,
    package_id: str | None,
    governance_result: dict[str, Any] | None = None,
    enforcement_result: dict[str, Any] | None = None,
    project_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persist governance/enforcement-backed revenue activation context for a package.

    This function is evaluation-only metadata persistence. It never triggers
    workflow transitions, outbound communication, or any execution side effects.
    """
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}

    gr = governance_result if isinstance(governance_result, dict) else {}
    er = enforcement_result if isinstance(enforcement_result, dict) else {}
    ps = project_state if isinstance(project_state, dict) else {}
    metadata = dict(package.get("metadata") or {})
    metadata["governance_status"] = str(gr.get("governance_status") or metadata.get("governance_status") or "")
    metadata["governance_routing_outcome"] = str(gr.get("routing_outcome") or metadata.get("governance_routing_outcome") or "")
    metadata["enforcement_status"] = str(er.get("enforcement_status") or metadata.get("enforcement_status") or "")
    metadata["revenue_recent_outcomes"] = [
        {
            "status": str((item or {}).get("status") or ""),
            "at": str((item or {}).get("at") or ""),
            "reason": str((item or {}).get("reason") or ""),
        }
        for item in list(ps.get("revenue_recent_outcomes") or metadata.get("revenue_recent_outcomes") or [])
        if isinstance(item, dict)
    ][:20]
    package["metadata"] = metadata
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package revenue activation metadata recorded.",
    )


def record_execution_package_revenue_activation_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_revenue_activation(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to persist execution package revenue activation metadata.", "package": None}


def _append_communication_audit_event(
    package: dict[str, Any],
    *,
    action: str,
    actor: str,
    notes: str = "",
) -> dict[str, Any]:
    p = dict(package or {})
    metadata = dict(p.get("metadata") or {})
    audit = [item for item in list(metadata.get("communication_audit") or []) if isinstance(item, dict)]
    audit.append(
        {
            "at": _utc_now_iso(),
            "action": str(action or "").strip().lower(),
            "actor": str(actor or "").strip(),
            "notes": str(notes or ""),
        }
    )
    metadata["communication_audit"] = audit[-50:]
    p["metadata"] = metadata
    return p


def _append_operator_action_history_event(
    package: dict[str, Any],
    *,
    event_type: str,
    operator_action_status: str,
    operator_action_actor: str,
    operator_action_notes: str = "",
    linked_execution_result: str = "",
    linked_conversion_result: str = "",
    linked_revenue_realized: float = 0.0,
    linked_communication_delivery_status: str = "not_sent",
    operator_action_effect_on_revenue: str = "unknown",
    operator_action_effect_reason: str = "",
) -> dict[str, Any]:
    p = dict(package or {})
    history = _normalize_operator_action_history(p.get("operator_action_history"))
    history.append(
        {
            "event_at": _utc_now_iso(),
            "event_type": str(event_type or "status_update").strip().lower(),
            "operator_action_status": _normalize_operator_action_lifecycle_status(operator_action_status),
            "operator_action_actor": str(operator_action_actor or "").strip(),
            "operator_action_notes": str(operator_action_notes or ""),
            "linked_execution_result": str(linked_execution_result or ""),
            "linked_conversion_result": str(linked_conversion_result or ""),
            "linked_revenue_realized": _normalize_revenue_ratio(linked_revenue_realized, fallback=0.0),
            "linked_communication_delivery_status": _normalize_communication_delivery_status(linked_communication_delivery_status),
            "operator_action_effect_on_revenue": _normalize_operator_action_revenue_effect(operator_action_effect_on_revenue),
            "operator_action_effect_reason": str(operator_action_effect_reason or ""),
        }
    )
    p["operator_action_history"] = history[-50:]
    return p


def _append_action_sequence_history_event(
    package: dict[str, Any],
    *,
    event_type: str,
    action_sequence_status: str,
    action_sequence_step: int,
    action_sequence_total_steps: int,
    action_sequence_next_step: str = "",
    action_sequence_next_step_due_at: str = "",
    action_sequence_actor: str = "",
    action_sequence_notes: str = "",
) -> dict[str, Any]:
    p = dict(package or {})
    history = _normalize_action_sequence_history(p.get("action_sequence_history"))
    history.append(
        {
            "event_at": _utc_now_iso(),
            "event_type": str(event_type or "sequence_update").strip().lower(),
            "action_sequence_status": _normalize_action_sequence_status(action_sequence_status),
            "action_sequence_step": max(0, int(action_sequence_step or 0)),
            "action_sequence_total_steps": max(1, int(action_sequence_total_steps or 1)),
            "action_sequence_next_step": str(action_sequence_next_step or ""),
            "action_sequence_next_step_due_at": str(action_sequence_next_step_due_at or ""),
            "action_sequence_actor": str(action_sequence_actor or "").strip(),
            "action_sequence_notes": str(action_sequence_notes or ""),
        }
    )
    p["action_sequence_history"] = history[-50:]
    return p


def record_execution_package_operator_action_lifecycle(
    *,
    project_path: str | None,
    package_id: str | None,
    operator_action_status: str,
    operator_action_actor: str,
    operator_action_notes: str = "",
    linked_execution_result: str | None = None,
    linked_conversion_result: str | None = None,
    linked_revenue_realized: float | None = None,
    linked_communication_delivery_status: str | None = None,
    operator_action_effect_on_revenue: str | None = None,
    operator_action_effect_reason: str | None = None,
) -> dict[str, Any]:
    actor = str(operator_action_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "operator_action_actor required.", "package": None}
    next_status = _normalize_operator_action_lifecycle_status(operator_action_status)
    if next_status == "pending":
        return {"status": "error", "reason": "operator_action_status must be a lifecycle transition value.", "package": None}

    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    normalized = normalize_execution_package(package)
    current_status = _normalize_operator_action_lifecycle_status(normalized.get("operator_action_status"))

    allowed_transitions = {
        "pending": {"acknowledged", "in_progress", "completed", "failed", "ignored", "cancelled"},
        "acknowledged": {"in_progress", "completed", "failed", "ignored", "cancelled"},
        "in_progress": {"completed", "failed", "ignored", "cancelled"},
        "completed": {"completed"},
        "failed": {"failed"},
        "ignored": {"ignored"},
        "cancelled": {"cancelled"},
    }
    if next_status not in allowed_transitions.get(current_status, set()):
        return {
            "status": "error",
            "reason": f"Invalid operator action transition: {current_status} -> {next_status}.",
            "package": normalized,
        }

    now_iso = _utc_now_iso()
    package["operator_action_status"] = next_status
    package["operator_action_actor"] = actor
    package["operator_action_notes"] = str(operator_action_notes or "")
    package["operator_action_created_at"] = str(normalized.get("operator_action_created_at") or now_iso)
    package["operator_action_id"] = str(normalized.get("operator_action_id") or f"opact-{uuid.uuid4().hex[:12]}")
    package["operator_action_due_at"] = str(
        normalized.get("operator_action_due_at") or normalized.get("operator_action_deadline") or ""
    )

    if next_status == "acknowledged" and not str(normalized.get("operator_action_acknowledged_at") or "").strip():
        package["operator_action_acknowledged_at"] = now_iso
    if next_status == "in_progress":
        if not str(normalized.get("operator_action_acknowledged_at") or "").strip():
            package["operator_action_acknowledged_at"] = now_iso
        if not str(normalized.get("operator_action_started_at") or "").strip():
            package["operator_action_started_at"] = now_iso
    if next_status == "completed":
        if not str(normalized.get("operator_action_started_at") or "").strip():
            package["operator_action_started_at"] = now_iso
        package["operator_action_completed_at"] = now_iso
    if next_status == "failed":
        if not str(normalized.get("operator_action_started_at") or "").strip():
            package["operator_action_started_at"] = now_iso
        package["operator_action_failed_at"] = now_iso
    if next_status == "ignored":
        package["operator_action_ignored_at"] = now_iso

    if linked_execution_result is not None:
        package["linked_execution_result"] = str(linked_execution_result or "")
    if linked_conversion_result is not None:
        package["linked_conversion_result"] = str(linked_conversion_result or "")
    if linked_revenue_realized is not None:
        package["linked_revenue_realized"] = _normalize_revenue_ratio(linked_revenue_realized, fallback=0.0)
    if linked_communication_delivery_status is not None:
        package["linked_communication_delivery_status"] = _normalize_communication_delivery_status(linked_communication_delivery_status)
    if operator_action_effect_on_revenue is not None:
        package["operator_action_effect_on_revenue"] = _normalize_operator_action_revenue_effect(operator_action_effect_on_revenue)
    if operator_action_effect_reason is not None:
        package["operator_action_effect_reason"] = str(operator_action_effect_reason or "")

    package = _append_operator_action_history_event(
        package,
        event_type=f"lifecycle_{next_status}",
        operator_action_status=next_status,
        operator_action_actor=actor,
        operator_action_notes=str(operator_action_notes or ""),
        linked_execution_result=str(package.get("linked_execution_result") or ""),
        linked_conversion_result=str(package.get("linked_conversion_result") or ""),
        linked_revenue_realized=_normalize_revenue_ratio(package.get("linked_revenue_realized"), fallback=0.0),
        linked_communication_delivery_status=str(package.get("linked_communication_delivery_status") or "not_sent"),
        operator_action_effect_on_revenue=str(package.get("operator_action_effect_on_revenue") or "unknown"),
        operator_action_effect_reason=str(package.get("operator_action_effect_reason") or ""),
    )
    normalized_for_sequence = normalize_execution_package(package)
    package = _append_action_sequence_history_event(
        package,
        event_type=f"operator_action_{next_status}",
        action_sequence_status=str(normalized_for_sequence.get("action_sequence_status") or "not_started"),
        action_sequence_step=int(normalized_for_sequence.get("action_sequence_step") or 0),
        action_sequence_total_steps=int(normalized_for_sequence.get("action_sequence_total_steps") or 1),
        action_sequence_next_step=str(normalized_for_sequence.get("action_sequence_next_step") or ""),
        action_sequence_next_step_due_at=str(normalized_for_sequence.get("action_sequence_next_step_due_at") or ""),
        action_sequence_actor=actor,
        action_sequence_notes=str(operator_action_notes or ""),
    )

    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package operator action lifecycle updated.",
    )


def record_execution_package_operator_action_lifecycle_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_operator_action_lifecycle(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to update execution package operator action lifecycle.", "package": None}


def record_execution_package_action_sequence_update(
    *,
    project_path: str | None,
    package_id: str | None,
    sequence_action: str,
    sequence_actor: str,
    sequence_notes: str = "",
    sequence_step_increment: int = 1,
    next_step_due_at: str = "",
) -> dict[str, Any]:
    actor = str(sequence_actor or "").strip()
    action = str(sequence_action or "").strip().lower()
    if not actor:
        return {"status": "error", "reason": "sequence_actor required.", "package": None}
    if action not in {"advance", "pause", "complete", "abandon"}:
        return {"status": "error", "reason": "sequence_action must be one of advance, pause, complete, abandon.", "package": None}

    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}

    normalized = normalize_execution_package(package)
    current_status = _normalize_action_sequence_status(normalized.get("action_sequence_status"))
    step = max(0, int(normalized.get("action_sequence_step") or 0))
    total = max(1, int(normalized.get("action_sequence_total_steps") or 1))
    now_iso = _utc_now_iso()

    if current_status in {"completed", "abandoned"} and action in {"advance", "pause"}:
        return {
            "status": "error",
            "reason": f"Cannot {action} a terminal sequence ({current_status}).",
            "package": normalized,
        }

    if action == "advance":
        increment = max(1, int(sequence_step_increment or 1))
        step = min(total, max(1, step) + increment - 1)
        next_status = "completed" if step >= total else "active"
        next_step = "" if next_status == "completed" else f"follow_up_step_{min(step + 1, total)}"
    elif action == "pause":
        next_status = "waiting"
        next_step = str(normalized.get("action_sequence_next_step") or f"follow_up_step_{min(max(step, 1), total)}")
        if step <= 0:
            step = 1
    elif action == "complete":
        next_status = "completed"
        step = max(step, total)
        next_step = ""
    else:
        next_status = "abandoned"
        if step <= 0:
            step = 1
        next_step = ""

    package["action_sequence_status"] = next_status
    package["action_sequence_step"] = step
    package["action_sequence_total_steps"] = total
    package["action_sequence_updated_at"] = now_iso
    package["action_sequence_started_at"] = str(normalized.get("action_sequence_started_at") or now_iso)
    package["action_sequence_completed_at"] = now_iso if next_status == "completed" else ""
    package["action_sequence_abandoned_at"] = now_iso if next_status == "abandoned" else ""
    package["action_sequence_next_step"] = next_step
    package["action_sequence_next_step_due_at"] = str(next_step_due_at or normalized.get("action_sequence_next_step_due_at") or "")
    package["follow_up_sequence_step"] = step
    if next_status == "completed":
        package["follow_up_status"] = "follow_up_not_needed"
    elif next_status == "waiting":
        package["follow_up_status"] = "follow_up_scheduled"
    elif next_status == "abandoned":
        package["follow_up_status"] = "follow_up_not_needed"
    else:
        package["follow_up_status"] = str(normalized.get("follow_up_status") or "follow_up_due")

    package = _append_action_sequence_history_event(
        package,
        event_type=f"manual_{action}",
        action_sequence_status=next_status,
        action_sequence_step=step,
        action_sequence_total_steps=total,
        action_sequence_next_step=next_step,
        action_sequence_next_step_due_at=str(package.get("action_sequence_next_step_due_at") or ""),
        action_sequence_actor=actor,
        action_sequence_notes=str(sequence_notes or ""),
    )
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason=f"Execution package action sequence {action} recorded.",
    )


def record_execution_package_action_sequence_update_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_action_sequence_update(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to update execution package action sequence.", "package": None}


def record_execution_package_communication_approval(
    *,
    project_path: str | None,
    package_id: str | None,
    approval_actor: str,
    approval_notes: str = "",
) -> dict[str, Any]:
    actor = str(approval_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "approval_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    normalized = normalize_execution_package(package)
    if str(normalized.get("communication_channel") or "") != "email":
        return {"status": "error", "reason": "Communication channel is not email.", "package": normalized}
    if not str(normalized.get("draft_message_subject") or "").strip() or not str(normalized.get("draft_message_body") or "").strip():
        return {"status": "error", "reason": "Email draft is not prepared.", "package": normalized}
    if not bool(normalized.get("communication_requires_approval", True)):
        return {"status": "error", "reason": "Communication approval is not required for this package.", "package": normalized}
    if str(normalized.get("communication_sent_at") or "").strip():
        return {"status": "error", "reason": "Email already marked as sent.", "package": normalized}
    if str(normalized.get("communication_approval_status") or "").strip().lower() == "approved":
        return {"status": "error", "reason": "Email draft is already approved.", "package": normalized}
    if str(normalized.get("revenue_activation_status") or "").strip().lower() == "blocked_for_revenue_action":
        return {"status": "error", "reason": "Governance/enforcement block prevents communication approval.", "package": normalized}
    package["communication_requires_approval"] = True
    package["communication_approval_status"] = "approved"
    package["communication_approved_at"] = _utc_now_iso()
    package["communication_denied_reason"] = ""
    package["communication_status"] = "approved"
    package = _append_communication_audit_event(
        package,
        action="approved",
        actor=actor,
        notes=approval_notes or "Email draft approved by operator.",
    )
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package email draft approved.",
    )


def record_execution_package_communication_approval_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_communication_approval(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to approve execution package email draft.", "package": None}


def record_execution_package_communication_denial(
    *,
    project_path: str | None,
    package_id: str | None,
    denial_actor: str,
    denial_reason: str = "",
) -> dict[str, Any]:
    actor = str(denial_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "denial_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    normalized = normalize_execution_package(package)
    if str(normalized.get("communication_channel") or "") != "email":
        return {"status": "error", "reason": "Communication channel is not email.", "package": normalized}
    if str(normalized.get("communication_sent_at") or "").strip():
        return {"status": "error", "reason": "Email already marked as sent.", "package": normalized}
    reason = str(denial_reason or "").strip() or "Denied by operator."
    package["communication_requires_approval"] = True
    package["communication_approval_status"] = "denied"
    package["communication_denied_reason"] = reason
    package["communication_status"] = "denied"
    package = _append_communication_audit_event(
        package,
        action="denied",
        actor=actor,
        notes=reason,
    )
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package email draft denied.",
    )


def record_execution_package_communication_denial_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_communication_denial(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to deny execution package email draft.", "package": None}


def record_execution_package_communication_sent(
    *,
    project_path: str | None,
    package_id: str | None,
    send_actor: str,
    delivery_status: str = "delivery_pending",
    send_notes: str = "",
) -> dict[str, Any]:
    actor = str(send_actor or "").strip()
    if not actor:
        return {"status": "error", "reason": "send_actor required.", "package": None}
    package = read_execution_package(project_path=project_path, package_id=package_id)
    if not package:
        return {"status": "error", "reason": "Execution package not found.", "package": None}
    normalized = normalize_execution_package(package)
    if str(normalized.get("communication_channel") or "") != "email":
        return {"status": "error", "reason": "Communication channel is not email.", "package": normalized}
    if str(normalized.get("communication_approval_status") or "").strip().lower() != "approved":
        return {"status": "error", "reason": "Email send requires explicit approved communication_approval_status.", "package": normalized}
    if not bool(normalized.get("communication_send_eligible")):
        return {
            "status": "error",
            "reason": str(normalized.get("communication_block_reason") or "Email send is not currently eligible."),
            "package": normalized,
        }
    if str(normalized.get("communication_sent_at") or "").strip():
        return {"status": "error", "reason": "Email already marked as sent.", "package": normalized}
    normalized_delivery = _normalize_communication_delivery_status(delivery_status)
    if normalized_delivery == "not_sent":
        normalized_delivery = "delivery_pending"
    package["communication_sent_at"] = _utc_now_iso()
    package["communication_delivery_status"] = normalized_delivery
    package["communication_status"] = "sent"
    package = _append_communication_audit_event(
        package,
        action="sent",
        actor=actor,
        notes=send_notes or "Email marked as sent through governed command path.",
    )
    return _persist_package_update(
        project_path=project_path,
        package_id=package_id,
        package=package,
        status="ok",
        reason="Execution package email marked as sent.",
    )


def record_execution_package_communication_sent_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return record_execution_package_communication_sent(**kwargs)
    except Exception:
        return {"status": "error", "reason": "Failed to mark execution package email as sent.", "package": None}
