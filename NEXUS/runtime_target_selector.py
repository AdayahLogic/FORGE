"""
NEXUS runtime target selection layer.

Single source of truth for governed execution-target eligibility and selection.
Selection only; no actual dispatch or execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from NEXUS.runtime_target_registry import (
    RUNTIME_TARGET_REGISTRY,
    get_runtime_target_entry,
    get_runtime_target_health,
)


DEFAULT_FALLBACK_TARGET = "local"
TARGET_PRIORITY = {
    "local": 0,
    "cursor": 1,
    "codex": 2,
    "windows_review_package": 3,
    "openclaw": 4,
    "claude": 5,
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _normalize_target_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = _normalize_target_id(item)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _requires_review(target_id: str, *, review_context: str | None = None, sensitivity: str | None = None) -> bool:
    entry = get_runtime_target_entry(target_id)
    review_required = str(entry.get("approval_level") or "").strip().lower() == "human_review"
    if str(review_context or "").strip():
        review_required = True
    if str(sensitivity or "").strip().lower() in ("high", "review"):
        review_required = True
    return review_required


def _priority_rank(target_id: str) -> tuple[int, str]:
    return (TARGET_PRIORITY.get(target_id, 99), target_id)


def _infer_selection_intent(
    *,
    agent_name: str | None = None,
    tool_name: str | None = None,
    action_type: str | None = None,
    task_type: str | None = None,
) -> dict[str, str]:
    agent = str(agent_name or "").strip().lower()
    tool = str(tool_name or "").strip().lower()
    action = str(action_type or "").strip().lower()
    task = str(task_type or "").strip().lower()

    ideal = DEFAULT_FALLBACK_TARGET
    reason = "Default local execution target inferred."
    required_capability = "execute"

    if tool in ("file_modification", "diff_patch") or action in ("edit_file", "patch", "apply_patch"):
        ideal = "cursor"
        reason = "Repo-aware code editing inferred; Cursor is the governed target."
        required_capability = "file_ops"
    elif agent in ("coder",) and tool not in ("file_modification", "diff_patch"):
        ideal = "codex"
        reason = "Code generation or refactor drafting inferred; Codex is the governed target."
        required_capability = "agent_routing"
    elif agent in ("architect", "planner") or task in ("planning", "plan") or action in ("plan", "planning"):
        ideal = "local"
        reason = "Planning workflow inferred; Local is the governed target."
        required_capability = "planning"
    elif task in ("review_package", "execution_package") or action in ("review_package", "package_for_review"):
        ideal = "windows_review_package"
        reason = "Review-only execution packaging inferred; Windows review package target is required."
        required_capability = "review_package"
    elif task in ("isolated", "container") or action in ("isolated", "container"):
        ideal = "container_worker"
        reason = "Isolated execution was requested; container worker is the intended target."
        required_capability = "execute"
    elif task in ("analysis", "review", "advisory") or action in ("analyze", "review", "advise"):
        ideal = "claude"
        reason = "Advisory or analysis task inferred; Claude is the governed target."
        required_capability = "advisory"
    elif agent in ("tester", "docs", "executor", "workspace", "operator", "supervisor"):
        ideal = "local"
        reason = f"Agent '{agent}' defaults to governed local execution."
        required_capability = "execute"

    return {
        "ideal_target_id": ideal,
        "inference_reason": reason,
        "required_capability": required_capability,
    }


def _evaluate_target_candidate(
    *,
    target_id: str,
    required_capability: str,
    requested_target_id: str,
    inferred_target_id: str,
    review_context: str | None = None,
    sensitivity: str | None = None,
) -> dict[str, Any]:
    entry = get_runtime_target_entry(target_id)
    health = get_runtime_target_health(target_id)
    capabilities = list(entry.get("capabilities", []))
    target_type = str(health.get("target_type") or entry.get("runtime_type") or "unknown").strip().lower()
    capability_match = required_capability in capabilities if required_capability else bool(entry)
    availability_status = str(health.get("availability_status") or "unknown").strip().lower()
    readiness_status = str(health.get("readiness_status") or "unknown_target").strip().lower()
    denial_reason = str(health.get("denial_reason") or "").strip()
    review_required = _requires_review(
        target_id,
        review_context=review_context,
        sensitivity=sensitivity,
    )

    if not entry and not denial_reason:
        denial_reason = "unknown_target"
    elif not capability_match:
        denial_reason = "capability_mismatch"

    eligible = bool(entry) and capability_match and availability_status == "available" and bool(health.get("dispatch_ready"))
    if not eligible and not denial_reason:
        denial_reason = "target_not_eligible"

    if requested_target_id and target_id == requested_target_id:
        priority_basis = "requested_target"
    elif inferred_target_id and target_id == inferred_target_id:
        priority_basis = "inferred_target"
    else:
        priority_basis = "deterministic_priority"

    return {
        "target_id": target_id,
        "target_type": target_type,
        "capabilities": capabilities,
        "capability_match": capability_match,
        "availability_status": availability_status,
        "readiness_status": readiness_status,
        "denial_reason": denial_reason,
        "eligible": eligible,
        "review_required": review_required,
        "priority_basis": priority_basis,
    }


def select_runtime_target(
    agent_name: str | None = None,
    tool_name: str | None = None,
    action_type: str | None = None,
    task_type: str | None = None,
    sensitivity: str | None = None,
    review_context: str | None = None,
    requested_target_id: str | None = None,
    candidate_target_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Select a governed execution target using one shared evaluation path.

    Returns the Phase 8 target-selection contract plus backward-compatible keys
    (`selected_target`, `fallback_target`, `selection_status`, `review_required`,
    `reason`, `inputs_considered`) consumed by existing code.
    """
    inputs_considered: dict[str, Any] = {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "action_type": action_type,
        "task_type": task_type,
        "sensitivity": sensitivity,
        "review_context": review_context,
        "requested_target_id": requested_target_id,
        "candidate_target_ids": list(candidate_target_ids or []),
    }
    requested = _normalize_target_id(requested_target_id)
    intent = _infer_selection_intent(
        agent_name=agent_name,
        tool_name=tool_name,
        action_type=action_type,
        task_type=task_type,
    )
    inferred_target_id = _normalize_target_id(intent.get("ideal_target_id"))
    required_capability = str(intent.get("required_capability") or "execute").strip().lower()

    candidates = _string_list(candidate_target_ids)
    if requested and requested not in candidates:
        candidates.append(requested)
    if not candidates and inferred_target_id:
        candidates.append(inferred_target_id)
    if not candidates:
        candidates = sorted(RUNTIME_TARGET_REGISTRY.keys(), key=_priority_rank)
    candidates = sorted(set(candidates), key=_priority_rank)

    evaluations: dict[str, Any] = {}
    eligible_targets: list[str] = []
    for target_id in candidates:
        evaluation = _evaluate_target_candidate(
            target_id=target_id,
            required_capability=required_capability,
            requested_target_id=requested,
            inferred_target_id=inferred_target_id,
            review_context=review_context,
            sensitivity=sensitivity,
        )
        evaluations[target_id] = evaluation
        if evaluation.get("eligible"):
            eligible_targets.append(target_id)

    selected_target_id = ""
    selection_reason = ""
    priority_basis = ""
    if requested and requested in eligible_targets:
        selected_target_id = requested
        selection_reason = "Requested runtime target remained eligible under current readiness and capability checks."
        priority_basis = "requested_target > inferred_target > target_priority > target_id"
    elif inferred_target_id and inferred_target_id in eligible_targets:
        selected_target_id = inferred_target_id
        selection_reason = str(intent.get("inference_reason") or "Inferred target remained eligible.")
        priority_basis = "inferred_target > target_priority > target_id"
    elif eligible_targets:
        selected_target_id = sorted(eligible_targets, key=_priority_rank)[0]
        selection_reason = "Selected the highest-priority eligible execution target deterministically."
        priority_basis = "target_priority > target_id"

    selected_eval = evaluations.get(selected_target_id) if selected_target_id else {}
    if selected_target_id:
        status = "selected"
        routing_outcome = "continue"
        target_type = str(selected_eval.get("target_type") or "").strip().lower()
        capability_match = bool(selected_eval.get("capability_match"))
        readiness_status = str(selected_eval.get("readiness_status") or "ready")
        availability_status = str(selected_eval.get("availability_status") or "available")
        denial_reason = ""
        review_required = bool(selected_eval.get("review_required"))
    else:
        unavailable = any(
            evaluations[target_id].get("denial_reason") in ("target_not_active", "dispatch_adapter_missing", "target_not_dispatch_ready", "unknown_target")
            for target_id in candidates
        )
        status = "unavailable" if unavailable else "denied"
        routing_outcome = "defer" if status == "unavailable" else "stop"
        target_type = ""
        capability_match = False
        readiness_status = "unavailable" if status == "unavailable" else "denied"
        availability_status = "unavailable" if status == "unavailable" else "available"
        denial_reason = ""
        if requested and requested in evaluations:
            denial_reason = str(evaluations[requested].get("denial_reason") or "")
        if not denial_reason and candidates:
            denial_reason = str((evaluations.get(candidates[0]) or {}).get("denial_reason") or "no_eligible_target")
        selection_reason = (
            "No eligible execution target exists for the current request; target selection was denied."
            if status == "denied"
            else "No dispatch-ready execution target is currently available for the current request."
        )
        priority_basis = "requested_target > inferred_target > target_priority > target_id"
        review_required = True

    result = {
        "status": status,
        "selected_target_id": selected_target_id,
        "candidate_target_ids": candidates,
        "target_type": target_type,
        "capability_match": capability_match,
        "readiness_status": readiness_status,
        "availability_status": availability_status,
        "denial_reason": denial_reason,
        "selection_reason": selection_reason,
        "routing_outcome": routing_outcome,
        "governance_trace": {
            "inputs_considered": inputs_considered,
            "required_capability": required_capability,
            "requested_target_id": requested,
            "inferred_target_id": inferred_target_id,
            "target_evaluations": evaluations,
            "selection_policy": [
                "requested_target_if_eligible",
                "inferred_target_if_eligible",
                "target_priority_tie_break",
                "no_implicit_runtime_fallback",
            ],
        },
        "recorded_at": _now_iso(),
        "selected_target": selected_target_id,
        "fallback_target": "",
        "selection_status": status,
        "review_required": review_required,
        "reason": selection_reason,
        "inputs_considered": inputs_considered,
        "required_capability": required_capability,
    }
    return result


def get_selection_defaults_summary() -> dict[str, Any]:
    """Return a short summary of governed target-selection defaults."""
    return {
        "default_fallback": DEFAULT_FALLBACK_TARGET,
        "selection_source_of_truth": "runtime_target_selector",
        "mappings": [
            {"inputs": "planning, general workflow", "target": "local", "required_capability": "planning"},
            {"inputs": "repo-aware code editing (file_modification, diff_patch)", "target": "cursor", "required_capability": "file_ops"},
            {"inputs": "code generation / refactor drafting (coder)", "target": "codex", "required_capability": "agent_routing"},
            {"inputs": "review-only execution package", "target": "windows_review_package", "required_capability": "review_package"},
            {"inputs": "isolated execution", "target": "container_worker", "required_capability": "execute"},
            {"inputs": "analysis, review, advisory tasks", "target": "claude", "required_capability": "advisory"},
            {"inputs": "unknown", "target": "local", "required_capability": "execute"},
        ],
        "selection_policy": [
            "requested_target_if_eligible",
            "inferred_target_if_eligible",
            "target_priority_tie_break",
            "no_implicit_runtime_fallback",
        ],
    }
