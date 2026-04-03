"""
NEXUS Claude runtime adapter.

Review-only advisory target. No repo mutation, no direct execution,
no autonomous external actions. Produces advisory outputs only.

Dispatch-disabled by default (active_or_planned=planned in registry).
Enable by setting active_or_planned to active in runtime_target_registry.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from NEXUS.authority_model import enforce_component_authority_safe
from NEXUS.runtime_execution import build_runtime_execution_result

CLAUDE_BRIDGE_PHASE = "phase_3_action_proposer"
CLAUDE_BRIDGE_CONTRACT_VERSION = "3.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any, *, limit: int = 50) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = str(item or "").strip()
        if normalized:
            out.append(normalized)
    return out[:limit]


# Task-type → artifact-type mapping for Phase 2 controlled artifact production.
# Unknown or unmapped task types default to "review_memo" (Option A).
_TASK_TYPE_ARTIFACT_MAP: dict[str, str] = {
    "review": "review_memo",
    "planning": "planning_memo",
    "analysis": "failure_analysis",
    "summary": "operator_summary",
}

_VALID_RECOMMENDED_ACTIONS = frozenset({
    "route_to_codex",
    "route_to_cursor_review",
    "require_human_review",
    "no_action_required",
})

_VALID_RISK_LEVELS = frozenset({"low", "medium", "high"})

# Allowed Phase 3 proposed action types.
# Any value outside this set is normalized to "require_human_review" at build time.
_VALID_PROPOSAL_ACTION_TYPES = frozenset({
    "route_to_codex",
    "route_to_cursor_review",
    "create_followup_package",
    "require_human_review",
    "no_action_required",
})

_PROPOSAL_TARGET_MAX = 200
_PROPOSAL_JUSTIFICATION_MAX = 500
_PROPOSED_ACTIONS_MAX = 20


def _normalize_proposed_action(item: Any) -> dict[str, Any] | None:
    """
    Normalize one raw proposed action dict.

    Returns a safe, validated dict or None if the item is not a dict.
    Unknown action_type values are clamped to "require_human_review".
    required_approval defaults to True for safety.
    """
    if not isinstance(item, dict):
        return None
    action_type = str(item.get("action_type") or "").strip().lower()
    if action_type not in _VALID_PROPOSAL_ACTION_TYPES:
        action_type = "require_human_review"
    return {
        "action_type": action_type,
        "target": str(item.get("target") or "").strip()[:_PROPOSAL_TARGET_MAX],
        "justification": str(item.get("justification") or "").strip()[:_PROPOSAL_JUSTIFICATION_MAX],
        "required_approval": bool(item.get("required_approval", True)),
    }


def _map_artifact_type(task_type: Any) -> str:
    """Return the Phase 2 artifact type for a given task type string."""
    return _TASK_TYPE_ARTIFACT_MAP.get(str(task_type or "").strip().lower(), "review_memo")


def _clamp_confidence(value: Any) -> float:
    """Clamp a confidence score to the valid [0.0, 1.0] range."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def build_claude_runtime_artifact(
    *,
    task_type: Any = "review",
    title: Any = "",
    summary: Any = "",
    key_findings: Any = None,
    risks: Any = None,
    recommended_action: Any = "require_human_review",
    confidence_score: Any = 0.5,
    risk_level: Any = "medium",
    requires_approval: Any = True,
    proposed_actions: Any = None,
) -> dict[str, Any]:
    """
    Build a normalized Phase 3 Claude runtime artifact.

    Review-only advisory output. No execution authority.
    All fields are advisory; downstream routing consumes them via
    runtime_dispatcher.py which applies its own policy gates.

    Schema is stable and additive:
    - Phase 1 routing fields preserved (confidence_score, risk_level,
      recommended_action, requires_approval)
    - Phase 2 content fields preserved (title, summary, key_findings, risks)
    - Phase 3 adds: proposed_actions (list of governed action proposals)

    proposed_actions are proposals only — not execution instructions.
    NEXUS remains the authority that decides whether proposals become
    packages, reviews, or approvals.
    """
    _rec = str(recommended_action or "require_human_review").strip().lower()
    if _rec not in _VALID_RECOMMENDED_ACTIONS:
        _rec = "require_human_review"

    _risk = str(risk_level or "medium").strip().lower()
    if _risk not in _VALID_RISK_LEVELS:
        _risk = "medium"

    _summary = str(summary or "").strip()

    # Normalize proposed_actions: validate each item, drop non-dicts, cap at max.
    _raw_proposals = proposed_actions if isinstance(proposed_actions, (list, tuple, set)) else []
    _proposals: list[dict[str, Any]] = []
    for _item in _raw_proposals:
        _normalized = _normalize_proposed_action(_item)
        if _normalized is not None:
            _proposals.append(_normalized)
        if len(_proposals) >= _PROPOSED_ACTIONS_MAX:
            break

    return {
        # Phase 2 typed artifact identity
        "artifact_type": _map_artifact_type(task_type),
        "source_runtime": "claude",
        # Human-readable content fields (Phase 2)
        "title": str(title or "").strip(),
        "summary": _summary,
        "analysis_summary": _summary,       # backward-compat alias for Phase 1 consumers
        "key_findings": _string_list(key_findings),
        "risks": _string_list(risks),
        # Phase 1 routing fields — preserved for dispatcher policy gates
        "recommended_action": _rec,
        "confidence_score": _clamp_confidence(confidence_score),
        "risk_level": _risk,
        "requires_approval": bool(requires_approval),
        # Phase 3 action proposals — advisory only, never executed directly
        "proposed_actions": _proposals,
    }


def build_claude_bridge_result(
    *,
    status: str,
    operation: str,
    actor: str,
    reason: str,
    authority_trace: dict[str, Any] | None = None,
    governance_trace: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": str(status or "error").strip().lower(),
        "operation": str(operation or "").strip().lower(),
        "actor": str(actor or "claude_bridge").strip() or "claude_bridge",
        "reason": str(reason or "").strip(),
        "authority_trace": _dict_value(authority_trace),
        "governance_trace": _dict_value(governance_trace),
    }
    if isinstance(extra_fields, dict):
        result.update(extra_fields)
    return result


def normalize_claude_bridge_handoff(
    dispatch_plan: dict[str, Any] | None,
    *,
    authority_trace: dict[str, Any] | None = None,
    governance_trace: dict[str, Any] | None = None,
    status: str = "prepared",
) -> dict[str, Any]:
    plan = dispatch_plan if isinstance(dispatch_plan, dict) else {}
    project = _dict_value(plan.get("project"))
    request = _dict_value(plan.get("request"))
    artifacts = _dict_value(plan.get("artifacts"))
    routing = _dict_value(plan.get("routing"))
    execution = _dict_value(plan.get("execution"))
    constraints = _dict_value(plan.get("constraints"))

    scope = {
        "project_path": str(plan.get("project_path") or project.get("project_path") or "").strip(),
        "target_files": _string_list(plan.get("target_files") or artifacts.get("target_files")),
        "expected_outputs": _string_list(
            artifacts.get("expected_outputs") or ["advisory_output", "analysis_summary"]
        ),
    }

    normalized_constraints = {
        "requires_human_approval": bool(execution.get("requires_human_approval", False)),
        "execution_mode": "manual_only",
        "can_execute": False,
        "review_only": True,
        "constraints": constraints,
    }

    return {
        "contract_version": CLAUDE_BRIDGE_CONTRACT_VERSION,
        "bridge_task_id": str(plan.get("bridge_task_id") or uuid.uuid4().hex[:16]),
        "project_id": str(
            plan.get("project_id") or project.get("project_id")
            or plan.get("project_name") or project.get("project_name") or ""
        ).strip(),
        "task_type": str(
            plan.get("task_type") or request.get("task_type")
            or request.get("request_type") or "advisory"
        ).strip().lower(),
        "objective": str(
            plan.get("objective") or request.get("summary") or request.get("objective") or ""
        ).strip(),
        "scope": scope,
        "constraints": normalized_constraints,
        "requested_artifacts": ["advisory_output", "analysis_summary"],
        "actor": str(
            plan.get("actor") or routing.get("agent_name")
            or routing.get("runtime_node") or "claude_bridge"
        ).strip(),
        "created_at": str(
            plan.get("created_at")
            or ((plan.get("timestamps") or {}).get("planned_at"))
            or _utc_now_iso()
        ),
        "status": str(status or "prepared").strip().lower(),
        "source_runtime": "claude",
        "authority_scope": "advisory_only",
        "execution_enabled": False,
        "authority_trace": _dict_value(authority_trace or plan.get("authority_trace")),
        "governance_trace": _dict_value(governance_trace or plan.get("governance_trace")),
    }


def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare a review-only advisory handoff to the Claude runtime.

    No repo mutation, no execution authority, no autonomous external actions.
    Returns queued status with manual_only execution mode.
    """
    execution = (dispatch_plan or {}).get("execution") or {}
    execution_requested = (
        bool(execution.get("can_execute"))
        or str(execution.get("execution_mode") or "").strip().lower()
        in ("direct_local", "external_runtime")
    )

    enforcement = enforce_component_authority_safe(
        component_name="claude_bridge",
        actor="claude_bridge",
        requested_actions=["prepare_advisory_handoff"],
        allowed_components=["claude_bridge"],
        authority_context={
            "runtime_target_id": "claude",
            "execution_requested": execution_requested,
        },
        denied_action="execute_package" if execution_requested else "",
        reason_override=(
            "Claude bridge is review-only and cannot gain execution authority."
            if execution_requested else None
        ),
    )
    authority_trace = enforcement.get("authority_trace") or {}

    if enforcement.get("status") == "denied":
        claude_bridge_summary = normalize_claude_bridge_handoff(
            dispatch_plan,
            authority_trace=authority_trace,
            status="denied",
        )
        return build_runtime_execution_result(
            runtime="claude",
            status="blocked",
            message=str(
                (enforcement.get("authority_denial") or {}).get("reason")
                or "Claude bridge authority denied."
            ),
            execution_status="blocked",
            execution_mode="safe_simulation",
            next_action="human_review",
            extra_fields={
                "authority_denial": enforcement.get("authority_denial") or {},
                "authority_trace": authority_trace,
                "claude_bridge_result": build_claude_bridge_result(
                    status="denied",
                    operation="handoff",
                    actor="claude_bridge",
                    reason=str(
                        (enforcement.get("authority_denial") or {}).get("reason")
                        or "Claude bridge authority denied."
                    ),
                    authority_trace=authority_trace,
                ),
                "claude_bridge_summary": {
                    **claude_bridge_summary,
                    "bridge_status": "denied",
                    "bridge_phase": CLAUDE_BRIDGE_PHASE,
                },
            },
        )

    claude_bridge_summary = normalize_claude_bridge_handoff(
        dispatch_plan,
        authority_trace=authority_trace,
        status="prepared",
    )

    # Derive advisory fields from dispatch_plan for the Phase 2 runtime_artifact.
    # Conservative defaults: confidence_score=0.5 sits below the 0.55 dispatcher
    # threshold so all dispatches require human review until a real inference call
    # populates these fields in a later phase.
    governance_block = _dict_value((dispatch_plan or {}).get("governance"))
    request_block = _dict_value((dispatch_plan or {}).get("request"))

    # task_type lookup mirrors normalize_claude_bridge_handoff for consistency.
    _task_type = str(
        (dispatch_plan or {}).get("task_type")
        or request_block.get("task_type")
        or request_block.get("request_type")
        or "review"
    ).strip().lower()

    _artifact_risk_level = str(governance_block.get("risk_level") or "medium").strip().lower()
    _artifact_title = str(
        request_block.get("summary") or request_block.get("objective") or ""
    ).strip()

    runtime_artifact: dict[str, Any] = build_claude_runtime_artifact(
        task_type=_task_type,
        title=_artifact_title,
        summary=_artifact_title,
        risk_level=_artifact_risk_level,
        # Phase 2 conservative defaults — populated by real inference in a later phase
        confidence_score=0.5,
        recommended_action="require_human_review",
        requires_approval=True,
        key_findings=[],
        risks=[],
        # Phase 3 conservative default — populated by real inference in a later phase
        proposed_actions=[],
    )

    return build_runtime_execution_result(
        runtime="claude",
        status="accepted",
        message="Claude advisory handoff prepared (review-only).",
        execution_status="queued",
        execution_mode="manual_only",
        next_action="review_claude_output",
        extra_fields={
            "authority_trace": authority_trace,
            "runtime_artifact": runtime_artifact,
            "claude_bridge_result": build_claude_bridge_result(
                status="ok",
                operation="handoff",
                actor="claude_bridge",
                reason="Claude bridge handoff prepared under governed review-only advisory scope.",
                authority_trace=authority_trace,
            ),
            "claude_bridge_summary": {
                **claude_bridge_summary,
                "bridge_status": "prepared",
                "bridge_phase": CLAUDE_BRIDGE_PHASE,
            },
        },
    )


def dispatch_safe(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return dispatch(dispatch_plan)
    except Exception as e:
        return build_runtime_execution_result(
            runtime="claude",
            status="blocked",
            message=f"Claude bridge dispatch failed: {e}",
            execution_status="blocked",
            execution_mode="safe_simulation",
            next_action="human_review",
        )
