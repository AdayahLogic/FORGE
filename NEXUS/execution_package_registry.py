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
    record_billing_usage_from_cost_tracking,
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
STRATEGY_EXECUTION_POLICY_STATUSES = {"allowed", "allowed_with_review", "blocked", "deferred"}
STRATEGY_EXPERIMENTATION_STATUSES = {
    "enabled_bounded",
    "enabled_review_required",
    "disabled_policy_block",
    "disabled_low_maturity",
    "disabled_conservative_mode",
}
STRATEGY_VARIANT_TYPES = {
    "conservative_follow_up_variant",
    "timing_variant_a",
    "channel_mix_variant_b",
    "manual_high_touch_variant",
    "none",
}
STRATEGY_VARIANT_GUARDRAIL_STATUSES = {
    "bounded",
    "operator_review_required",
    "conservative_only",
    "hard_block",
    "disabled",
}
STRATEGY_COMPARISON_STATUSES = {"active_tracking", "baseline_only", "not_enabled"}


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
        "opportunity_classification": str(normalized.get("opportunity_classification") or "cold"),
        "opportunity_classification_reason": str(normalized.get("opportunity_classification_reason") or ""),
        "strategy_execution_policy": str(normalized.get("strategy_execution_policy") or "conservative_defer_policy"),
        "strategy_execution_policy_status": str(normalized.get("strategy_execution_policy_status") or "deferred"),
        "strategy_execution_policy_reason": str(normalized.get("strategy_execution_policy_reason") or ""),
        "strategy_execution_allowed": bool(normalized.get("strategy_execution_allowed")),
        "strategy_execution_block_reason": str(normalized.get("strategy_execution_block_reason") or ""),
        "strategy_execution_requires_operator_review": bool(normalized.get("strategy_execution_requires_operator_review")),
        "strategy_experimentation_enabled": bool(normalized.get("strategy_experimentation_enabled")),
        "strategy_experimentation_status": str(normalized.get("strategy_experimentation_status") or "disabled_conservative_mode"),
        "strategy_variant_id": str(normalized.get("strategy_variant_id") or ""),
        "strategy_variant_type": str(normalized.get("strategy_variant_type") or "none"),
        "strategy_variant_reason": str(normalized.get("strategy_variant_reason") or ""),
        "strategy_variant_confidence": _normalize_revenue_ratio(normalized.get("strategy_variant_confidence"), fallback=0.0),
        "strategy_variant_guardrail_status": str(normalized.get("strategy_variant_guardrail_status") or "disabled"),
        "strategy_variant_guardrail_reason": str(normalized.get("strategy_variant_guardrail_reason") or ""),
        "strategy_comparison_group": str(normalized.get("strategy_comparison_group") or ""),
        "strategy_comparison_status": str(normalized.get("strategy_comparison_status") or "not_enabled"),
        "strategy_comparison_reason": str(normalized.get("strategy_comparison_reason") or ""),
        "strategy_baseline_reference": str(normalized.get("strategy_baseline_reference") or ""),
        "strategy_variant_reference": str(normalized.get("strategy_variant_reference") or ""),
        "strategy_comparison_outcome_signal": str(normalized.get("strategy_comparison_outcome_signal") or "not_tracking"),
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


def _normalize_slug(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    out: list[str] = []
    for ch in raw:
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
        elif ch in {" ", "-", "_", "/", "."}:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unknown"


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
        "opportunity_classification": opportunity_classification,
        "opportunity_classification_reason": opportunity_classification_reason,
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
        },
    }


def _derive_strategy_execution_policy_fields(package: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(package.get("metadata") or {})
    governance_status, governance_outcome, enforcement_status = _derive_governance_enforcement_posture(package)
    revenue_activation_status = str(package.get("revenue_activation_status") or "").strip().lower()
    opportunity_classification = str(package.get("opportunity_classification") or "cold").strip().lower()
    pipeline_stage = _normalize_pipeline_stage(package.get("pipeline_stage"))
    highest_value_next_action_score = _normalize_revenue_ratio(package.get("highest_value_next_action_score"), fallback=0.0)
    conversion_probability = _normalize_revenue_ratio(package.get("conversion_probability"), fallback=0.0)
    roi_estimate = _normalize_revenue_ratio(package.get("roi_estimate"), fallback=0.0)
    time_sensitivity = _normalize_revenue_ratio(package.get("time_sensitivity"), fallback=0.0)

    strategy_confidence_level = str(package.get("strategy_confidence_level") or "").strip().lower()
    if strategy_confidence_level not in {"low", "medium", "high"}:
        if highest_value_next_action_score >= 0.72:
            strategy_confidence_level = "high"
        elif highest_value_next_action_score >= 0.45:
            strategy_confidence_level = "medium"
        else:
            strategy_confidence_level = "low"

    data_maturity_level = str(package.get("data_maturity_level") or "").strip().lower()
    if data_maturity_level not in {"low", "medium", "high"}:
        inferred_data_points = len(list(metadata.get("revenue_recent_outcomes") or []))
        if inferred_data_points >= 12:
            data_maturity_level = "high"
        elif inferred_data_points >= 5:
            data_maturity_level = "medium"
        else:
            data_maturity_level = "low"

    hard_blocked = (
        governance_status == "blocked"
        or governance_outcome == "stop"
        or enforcement_status in {"blocked", "hold"}
        or revenue_activation_status == "blocked_for_revenue_action"
    )
    operator_gate = enforcement_status in {"approval_required", "manual_review_required"}
    low_signal = strategy_confidence_level == "low" or data_maturity_level == "low"
    value_weak = conversion_probability < 0.25 and roi_estimate < 0.3

    if hard_blocked:
        policy_status = "blocked"
        policy_name = "hard_governance_block"
        policy_reason = "Execution policy blocks strategy due to governance/enforcement hard-block posture."
        allowed = False
        requires_operator_review = False
        block_reason = "Hard block state cannot be converted into executable strategy behavior."
    elif operator_gate or revenue_activation_status == "needs_operator_review":
        policy_status = "allowed_with_review"
        policy_name = "operator_gated_execution"
        policy_reason = "Execution policy permits only operator-reviewed strategy progression."
        allowed = True
        requires_operator_review = True
        block_reason = ""
    elif low_signal or value_weak or revenue_activation_status in {"low_value_deferred", "needs_revision"}:
        policy_status = "deferred"
        policy_name = "conservative_defer_policy"
        policy_reason = "Execution policy defers action pending stronger confidence, maturity, or value evidence."
        allowed = False
        requires_operator_review = False
        block_reason = "Deferred until confidence/data maturity conditions improve."
    else:
        policy_status = "allowed"
        policy_name = "bounded_execution_allowed"
        policy_reason = "Execution policy allows governed progression under current confidence and value posture."
        allowed = True
        requires_operator_review = False
        block_reason = ""

    experimentation_enabled = False
    experimentation_status = "disabled_conservative_mode"
    variant_type = "none"
    variant_reason = "No strategy variant suggested."
    variant_confidence = _normalize_revenue_ratio(
        (highest_value_next_action_score * 0.6) + (conversion_probability * 0.4),
        fallback=0.0,
    )
    variant_guardrail_status = "disabled"
    variant_guardrail_reason = "Experimentation is disabled."

    if hard_blocked:
        experimentation_status = "disabled_policy_block"
        variant_guardrail_status = "hard_block"
        variant_guardrail_reason = "Hard-blocked opportunities are never eligible for strategy experiments."
    elif policy_status == "allowed_with_review":
        experimentation_enabled = True
        experimentation_status = "enabled_review_required"
        variant_guardrail_status = "operator_review_required"
        variant_guardrail_reason = "Variant tests require explicit operator review before action."
    elif policy_status == "allowed" and data_maturity_level in {"medium", "high"} and strategy_confidence_level in {"medium", "high"}:
        experimentation_enabled = True
        experimentation_status = "enabled_bounded"
        variant_guardrail_status = "bounded"
        variant_guardrail_reason = "Only bounded strategy variants are permitted in governed mode."
    elif data_maturity_level == "low" or strategy_confidence_level == "low":
        experimentation_status = "disabled_low_maturity"
        variant_guardrail_status = "conservative_only"
        variant_guardrail_reason = "Low maturity/confidence keeps strategy in conservative non-experimental mode."

    if experimentation_enabled:
        if time_sensitivity >= 0.7:
            variant_type = "timing_variant_a"
            variant_reason = "Urgency signal supports bounded timing variation."
        elif opportunity_classification in {"strategic", "high_margin"}:
            variant_type = "manual_high_touch_variant"
            variant_reason = "Strategic/high-margin context favors manual high-touch bounded variant."
        elif pipeline_stage in {"intake", "qualified", "follow_up"}:
            variant_type = "channel_mix_variant_b"
            variant_reason = "Early pipeline stage can safely compare a bounded channel-mix variant."
        else:
            variant_type = "conservative_follow_up_variant"
            variant_reason = "Fallback conservative follow-up variant supports low-risk experimentation."
    elif policy_status in {"deferred", "blocked"}:
        variant_type = "conservative_follow_up_variant"
        variant_reason = "Conservative baseline variant retained for rationale visibility only."

    if variant_type not in STRATEGY_VARIANT_TYPES:
        variant_type = "none"
    if policy_status not in STRATEGY_EXECUTION_POLICY_STATUSES:
        policy_status = "deferred"
    if experimentation_status not in STRATEGY_EXPERIMENTATION_STATUSES:
        experimentation_status = "disabled_conservative_mode"
    if variant_guardrail_status not in STRATEGY_VARIANT_GUARDRAIL_STATUSES:
        variant_guardrail_status = "disabled"

    package_id = str(package.get("package_id") or "unknown").strip().lower()
    policy_seed = f"{package_id}:{policy_name}:{variant_type}:{policy_status}"
    variant_id = f"var-{uuid.uuid5(uuid.NAMESPACE_URL, policy_seed).hex[:12]}" if variant_type != "none" else ""

    comparison_group = ""
    comparison_status = "not_enabled"
    comparison_reason = "No active strategy comparison group."
    baseline_reference = f"baseline:{str(package.get('highest_value_next_action') or 'none').strip().lower().replace(' ', '_')}"
    variant_reference = f"{variant_type}:{variant_id}" if variant_id else ""
    comparison_outcome_signal = "pending_outcome_signal" if experimentation_enabled else "not_tracking"
    if experimentation_enabled:
        comparison_group = (
            f"cmp-{_normalize_slug(pipeline_stage)}-"
            f"{_normalize_slug(opportunity_classification)}-"
            f"{_normalize_slug(policy_status)}"
        )
        comparison_status = "active_tracking"
        comparison_reason = "Bounded comparison tracks baseline versus governed strategy variant outcomes."
    elif policy_status in {"allowed", "allowed_with_review", "deferred"}:
        comparison_status = "baseline_only"
        comparison_reason = "Comparison remains baseline-only because experimentation is disabled."

    if comparison_status not in STRATEGY_COMPARISON_STATUSES:
        comparison_status = "not_enabled"

    return {
        "strategy_execution_policy": policy_name,
        "strategy_execution_policy_status": policy_status,
        "strategy_execution_policy_reason": policy_reason,
        "strategy_execution_allowed": bool(allowed),
        "strategy_execution_block_reason": block_reason,
        "strategy_execution_requires_operator_review": bool(requires_operator_review),
        "strategy_experimentation_enabled": bool(experimentation_enabled),
        "strategy_experimentation_status": experimentation_status,
        "strategy_variant_id": variant_id,
        "strategy_variant_type": variant_type,
        "strategy_variant_reason": variant_reason,
        "strategy_variant_confidence": variant_confidence,
        "strategy_variant_guardrail_status": variant_guardrail_status,
        "strategy_variant_guardrail_reason": variant_guardrail_reason,
        "strategy_comparison_group": comparison_group,
        "strategy_comparison_status": comparison_status,
        "strategy_comparison_reason": comparison_reason,
        "strategy_baseline_reference": baseline_reference,
        "strategy_variant_reference": variant_reference,
        "strategy_comparison_outcome_signal": comparison_outcome_signal,
        "strategy_policy_trace": {
            "governance_posture": {
                "governance_status": governance_status,
                "governance_routing_outcome": governance_outcome,
                "enforcement_status": enforcement_status,
            },
            "policy_inputs": {
                "revenue_activation_status": revenue_activation_status,
                "strategy_confidence_level": strategy_confidence_level,
                "data_maturity_level": data_maturity_level,
                "opportunity_classification": opportunity_classification,
                "roi_estimate": roi_estimate,
                "conversion_probability": conversion_probability,
                "time_sensitivity": time_sensitivity,
            },
            "operator_visibility": {
                "policy_status": policy_status,
                "experimentation_status": experimentation_status,
                "comparison_status": comparison_status,
            },
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
    strategy_policy_fields = _derive_strategy_execution_policy_fields(
        {
            **p,
            "metadata": metadata,
            **revenue_fields,
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
        **strategy_policy_fields,
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
        "opportunity_classification": str(r.get("opportunity_classification") or "cold"),
        "opportunity_classification_reason": str(r.get("opportunity_classification_reason") or ""),
        "strategy_execution_policy": str(r.get("strategy_execution_policy") or "conservative_defer_policy"),
        "strategy_execution_policy_status": str(r.get("strategy_execution_policy_status") or "deferred"),
        "strategy_execution_policy_reason": str(r.get("strategy_execution_policy_reason") or ""),
        "strategy_execution_allowed": bool(r.get("strategy_execution_allowed")),
        "strategy_execution_block_reason": str(r.get("strategy_execution_block_reason") or ""),
        "strategy_execution_requires_operator_review": bool(r.get("strategy_execution_requires_operator_review")),
        "strategy_experimentation_enabled": bool(r.get("strategy_experimentation_enabled")),
        "strategy_experimentation_status": str(r.get("strategy_experimentation_status") or "disabled_conservative_mode"),
        "strategy_variant_id": str(r.get("strategy_variant_id") or ""),
        "strategy_variant_type": str(r.get("strategy_variant_type") or "none"),
        "strategy_variant_reason": str(r.get("strategy_variant_reason") or ""),
        "strategy_variant_confidence": _normalize_revenue_ratio(r.get("strategy_variant_confidence"), fallback=0.0),
        "strategy_variant_guardrail_status": str(r.get("strategy_variant_guardrail_status") or "disabled"),
        "strategy_variant_guardrail_reason": str(r.get("strategy_variant_guardrail_reason") or ""),
        "strategy_comparison_group": str(r.get("strategy_comparison_group") or ""),
        "strategy_comparison_status": str(r.get("strategy_comparison_status") or "not_enabled"),
        "strategy_comparison_reason": str(r.get("strategy_comparison_reason") or ""),
        "strategy_baseline_reference": str(r.get("strategy_baseline_reference") or ""),
        "strategy_variant_reference": str(r.get("strategy_variant_reference") or ""),
        "strategy_comparison_outcome_signal": str(r.get("strategy_comparison_outcome_signal") or "not_tracking"),
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
    billing_customer_id = str(
        package.get("client_id")
        or ((package.get("metadata") or {}).get("revenue_pipeline_context") or {}).get("client_id")
        or ""
    )
    package["billing_usage"] = record_billing_usage_from_cost_tracking(
        customer_id=billing_customer_id,
        cost_tracking=package.get("cost_tracking"),
        package_id=package_id,
        run_id=run_id,
        source="execution_package_execution",
    )
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
