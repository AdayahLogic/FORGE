"""
NEXUS runtime dispatch system.

Reads dispatch_plan, selects runtime adapter, and returns dispatch result.
Simulation only; no real execution.
"""

from __future__ import annotations

from typing import Any

from NEXUS.authority_model import build_authority_denial, enforce_component_authority_safe
from NEXUS.runtimes import RUNTIME_ADAPTERS
from NEXUS.runtime_execution import (
    build_runtime_target_selection_snapshot,
    build_runtime_execution_error,
    build_runtime_execution_skipped,
    build_runtime_execution_result,
)
from NEXUS.runtime_target_selector import select_runtime_target


def _build_review_package_artifact(*, package_id: str | None, package_path: str | None) -> list[dict[str, Any]]:
    if not package_id and not package_path:
        return []
    return [{
        "artifact_type": "execution_package",
        "package_id": package_id,
        "package_path": package_path,
    }]


def _create_review_only_execution_package(
    *,
    dispatch_plan: dict[str, Any],
    aegis_res: dict[str, Any] | None = None,
    approval_record: dict[str, Any] | None = None,
    approval_id: str | None = None,
    package_reason: str,
    authority_trace: dict[str, Any] | None = None,
    cursor_bridge_summary: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Persist a sealed review-only execution package and return (id, path)."""
    try:
        from NEXUS.execution_package_builder import build_execution_package_safe
        from NEXUS.execution_package_registry import write_execution_package_safe

        package = build_execution_package_safe(
            dispatch_plan=dispatch_plan,
            aegis_result=aegis_res,
            approval_record=approval_record,
            approval_id=approval_id,
            package_reason=package_reason,
            authority_trace=authority_trace,
            cursor_bridge_summary=cursor_bridge_summary,
        )
        package_id = package.get("package_id")
        if isinstance(cursor_bridge_summary, dict) and cursor_bridge_summary:
            summary = {
                **cursor_bridge_summary,
                "package_id": str(package_id or cursor_bridge_summary.get("package_id") or ""),
                "package_reference": {
                    **dict(cursor_bridge_summary.get("package_reference") or {}),
                    "package_id": str(package_id or cursor_bridge_summary.get("package_id") or ""),
                },
            }
            metadata = dict(package.get("metadata") or {})
            metadata["cursor_bridge_summary"] = summary
            package["metadata"] = metadata
            package["cursor_bridge_summary"] = summary
        package_path = write_execution_package_safe(
            project_path=(dispatch_plan.get("project") or {}).get("project_path"),
            package=package,
        )
        return (str(package_id) if package_id else None, package_path)
    except Exception:
        return (None, None)


def dispatch(dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch plan to the selected runtime adapter.

    If ready_for_dispatch is False, returns skipped.
    Otherwise chooses adapter by runtime_target_id, calls it, returns result.
    """
    exec_block = (dispatch_plan or {}).get("execution") or {}
    runtime_target_id = (exec_block.get("runtime_target_id") or "").strip().lower()
    routing_block = (dispatch_plan or {}).get("routing") or {}
    request_block = (dispatch_plan or {}).get("request") or {}
    governance_block = (dispatch_plan or {}).get("governance") or {}
    project_block = (dispatch_plan or {}).get("project") or {}
    nexus_authority = enforce_component_authority_safe(
        component_name="nexus",
        actor="nexus",
        requested_actions=["route_dispatch"],
        allowed_components=["nexus"],
        authority_context={
            "project_name": project_block.get("project_name"),
            "runtime_target_id": runtime_target_id or "local",
            "dispatch_ready": bool((dispatch_plan or {}).get("ready_for_dispatch", False)),
        },
    )
    nexus_trace = nexus_authority.get("authority_trace") or {}

    if nexus_authority.get("status") == "denied":
        blocked = build_runtime_execution_result(
            runtime=runtime_target_id or "",
            status="blocked",
            message=str((nexus_authority.get("authority_denial") or {}).get("reason") or "Authority enforcement denied runtime dispatch."),
            execution_status="blocked",
            execution_mode="safe_simulation",
            next_action="human_review",
            artifacts=[],
            errors=[{"reason": str((nexus_authority.get("authority_denial") or {}).get("reason") or "authority_denied")}],
            extra_fields={
                "authority_denial": nexus_authority.get("authority_denial") or {},
                "authority_trace": nexus_trace,
            },
        )
        return {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": blocked,
        }

    selection = select_runtime_target(
        requested_target_id=runtime_target_id or None,
        agent_name=routing_block.get("agent_name") or routing_block.get("runtime_node"),
        tool_name=routing_block.get("tool_name"),
        action_type=request_block.get("request_type"),
        task_type=request_block.get("task_type"),
        sensitivity=governance_block.get("risk_level"),
        review_context=governance_block.get("approval_status"),
    )
    selection_snapshot = build_runtime_target_selection_snapshot(selection)
    selected_target_id = str(selection_snapshot.get("selected_target_id") or "").strip().lower()

    if not dispatch_plan or not dispatch_plan.get("ready_for_dispatch", False):
        skipped = build_runtime_execution_skipped(
            runtime=selected_target_id or runtime_target_id or "",
            message="Dispatch skipped: dispatch plan not ready.",
            reason="not_ready",
        )
        skipped["authority_trace"] = nexus_trace
        skipped["runtime_target_selection"] = selection_snapshot
        return {
            "dispatch_status": "skipped",
            "runtime_target": selected_target_id or runtime_target_id,
            "dispatch_result": skipped,
        }

    if selection_snapshot.get("status") == "unavailable":
        unavailable = build_runtime_execution_skipped(
            runtime=runtime_target_id or "",
            message=str(selection_snapshot.get("selection_reason") or "No dispatch-ready runtime target is available."),
            reason=str(selection_snapshot.get("denial_reason") or "target_unavailable"),
            execution_mode="manual_only",
        )
        unavailable["next_action"] = "select_supported_runtime"
        unavailable["authority_trace"] = nexus_trace
        unavailable["runtime_target_selection"] = selection_snapshot
        return {
            "dispatch_status": "skipped",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": unavailable,
        }

    if selection_snapshot.get("status") == "denied":
        blocked = build_runtime_execution_result(
            runtime=runtime_target_id or "",
            status="blocked",
            message=str(selection_snapshot.get("selection_reason") or "Runtime target selection was denied."),
            execution_status="blocked",
            execution_mode="manual_only",
            next_action="human_review",
            artifacts=[],
            errors=[{"reason": str(selection_snapshot.get("denial_reason") or "target_selection_denied")}],
            extra_fields={
                "authority_trace": nexus_trace,
                "runtime_target_selection": selection_snapshot,
            },
        )
        return {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": blocked,
        }

    runtime_target_id = selected_target_id

    # AEGIS MVP (Phase 7): policy enforcement gate before any adapter call.
    aegis_res: dict[str, Any] | None = None
    try:
        from AEGIS.aegis_core import evaluate_action_safe
        from AEGIS.aegis_contract import normalize_aegis_result

        project_path = (dispatch_plan.get("project") or {}).get("project_path")
        exec_block = (dispatch_plan or {}).get("execution") or {}

        aegis_request = {
            "project_name": (dispatch_plan.get("project") or {}).get("project_name"),
            "project_path": project_path,
            "runtime_target_id": runtime_target_id,
            "requires_human_approval": bool(exec_block.get("requires_human_approval", False)),
            "action": "adapter_dispatch_call",
        }

        aegis_res = normalize_aegis_result(evaluate_action_safe(request=aegis_request))
        aegis_decision = str(aegis_res.get("aegis_decision") or "allow").strip().lower()
        aegis_reason = str(aegis_res.get("aegis_reason") or "")
        aegis_scope = str(aegis_res.get("aegis_scope") or "runtime_dispatch_only").strip().lower()

        if aegis_decision in ("deny", "error_fallback"):
            blocked = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="blocked",
                message=f"AEGIS({aegis_scope}) deny: {aegis_reason or 'Policy denied action.'}",
                execution_status="blocked",
                execution_mode="safe_simulation",
                next_action="human_review",
                artifacts=[],
                errors=[{"reason": f"{aegis_scope}: {aegis_reason or 'aegis_deny'}"}],
            )
            if isinstance(blocked, dict):
                blocked["aegis"] = aegis_res
                blocked["runtime_target_selection"] = selection_snapshot
            return {
                "dispatch_status": "blocked",
                "runtime_target": runtime_target_id,
                "dispatch_result": blocked,
            }

        if aegis_decision == "approval_required":
            # Phase 18: create approval record and persist before blocking
            approval_record: dict[str, Any] | None = None
            try:
                from NEXUS.approval_builder import build_approval_record
                from NEXUS.approval_registry import append_approval_record_safe

                approval_record = build_approval_record(
                    dispatch_plan=dispatch_plan,
                    aegis_result=aegis_res,
                    approval_type="aegis_policy",
                    reason=aegis_reason or "Human approval required.",
                )
                append_approval_record_safe(project_path=project_path, record=approval_record)
                approval_id = approval_record.get("approval_id")
            except Exception:
                approval_id = None
            package_id, package_path = _create_review_only_execution_package(
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
                approval_record=approval_record,
                approval_id=approval_id,
                package_reason=aegis_reason or "Human approval required before any execution handoff.",
                authority_trace=nexus_trace,
            )
            queued = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="skipped",
                message=f"AEGIS({aegis_scope}) approval_required: sealed review package created; {aegis_reason or 'Human approval required.'}",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="review_execution_package",
                artifacts=_build_review_package_artifact(package_id=package_id, package_path=package_path),
                errors=[{"reason": f"{aegis_scope}: {aegis_reason or 'aegis_approval_required'}"}],
            )
            if isinstance(queued, dict):
                queued["aegis"] = aegis_res
                queued["authority_trace"] = nexus_trace
                queued["runtime_target_selection"] = selection_snapshot
                if approval_id:
                    queued["approval_id"] = approval_id
                    queued["approval_required"] = True
                if package_id:
                    queued["execution_package_id"] = package_id
                    queued["execution_package_path"] = package_path
                    queued["package_review_required"] = True
            return {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": queued,
            }

        # Phase 18: when AEGIS allows but dispatch plan requires human approval, gate before execution
        if aegis_decision == "allow" and bool(exec_block.get("requires_human_approval")):
            approval_record: dict[str, Any] | None = None
            try:
                from NEXUS.approval_builder import build_approval_record
                from NEXUS.approval_registry import append_approval_record_safe

                approval_record = build_approval_record(
                    dispatch_plan=dispatch_plan,
                    aegis_result=aegis_res,
                    approval_type="dispatch_plan",
                    reason="Dispatch plan requires human approval before execution.",
                )
                append_approval_record_safe(project_path=project_path, record=approval_record)
                approval_id = approval_record.get("approval_id")
            except Exception:
                approval_id = None
            package_id, package_path = _create_review_only_execution_package(
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
                approval_record=approval_record,
                approval_id=approval_id,
                package_reason="Dispatch plan requires review-only packaging before any later execution.",
                authority_trace=nexus_trace,
            )
            gated = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="skipped",
                message="Approval required: sealed review package created; dispatch plan requires human approval before execution.",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="review_execution_package",
                artifacts=_build_review_package_artifact(package_id=package_id, package_path=package_path),
                errors=[{"reason": "approval_gate: requires_human_approval"}],
            )
            if isinstance(gated, dict):
                gated["aegis"] = aegis_res
                gated["authority_trace"] = nexus_trace
                gated["runtime_target_selection"] = selection_snapshot
                if approval_id:
                    gated["approval_id"] = approval_id
                    gated["approval_required"] = True
                if package_id:
                    gated["execution_package_id"] = package_id
                    gated["execution_package_path"] = package_path
                    gated["package_review_required"] = True
            return {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": gated,
            }

        if aegis_decision == "allow" and runtime_target_id == "windows_review_package":
            package_id, package_path = _create_review_only_execution_package(
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
                approval_record=None,
                approval_id=None,
                package_reason="Windows review-only execution target selected; package created and execution intentionally stopped.",
                authority_trace=nexus_trace,
            )
            packaged = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="accepted",
                message="Review-only Windows execution package created; no action executed.",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="review_execution_package",
                artifacts=_build_review_package_artifact(package_id=package_id, package_path=package_path),
                errors=[],
            )
            if isinstance(packaged, dict):
                packaged["aegis"] = aegis_res
                packaged["authority_trace"] = nexus_trace
                packaged["runtime_target_selection"] = selection_snapshot
                if package_id:
                    packaged["execution_package_id"] = package_id
                    packaged["execution_package_path"] = package_path
                    packaged["package_review_required"] = True
            return {
                "dispatch_status": "accepted",
                "runtime_target": runtime_target_id,
                "dispatch_result": packaged,
            }
    except Exception:
        aegis_bypass_denial = build_authority_denial(
            denied_action="bypass_aegis_for_governed_dispatch",
            actor="nexus",
            authority_trace=nexus_trace,
            required_role="approval_authority",
            reason="NEXUS must not bypass AEGIS for governed dispatch actions.",
        )
        blocked = build_runtime_execution_result(
            runtime=runtime_target_id,
            status="blocked",
            message=aegis_bypass_denial["reason"],
            execution_status="blocked",
            execution_mode="safe_simulation",
            next_action="human_review",
            artifacts=[],
            errors=[{"reason": aegis_bypass_denial["reason"]}],
            extra_fields={
                "authority_denial": aegis_bypass_denial,
                "authority_trace": nexus_trace,
                "runtime_target_selection": selection_snapshot,
            },
        )
        return {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id,
            "dispatch_result": blocked,
        }
    adapter = RUNTIME_ADAPTERS.get(runtime_target_id)
    if not adapter:
        no_adapter = build_runtime_execution_skipped(
            runtime=runtime_target_id,
            message=f"No adapter for runtime '{runtime_target_id}' (simulated).",
            reason="no_adapter",
        )
        # keep status vocabulary aligned: top-level no_adapter, nested no_adapter
        no_adapter["status"] = "no_adapter"
        no_adapter["execution_mode"] = "manual_only"
        no_adapter["next_action"] = "human_review"
        if isinstance(aegis_res, dict):
            no_adapter["aegis"] = aegis_res
        no_adapter["authority_trace"] = nexus_trace
        no_adapter["runtime_target_selection"] = selection_snapshot
        return {
            "dispatch_status": "no_adapter",
            "runtime_target": runtime_target_id,
            "dispatch_result": no_adapter,
        }
    try:
        dispatch_result = adapter(dispatch_plan)
        # Adapters already return normalized schema in Step 59; enforce minimal keys just in case.
        if not isinstance(dispatch_result, dict):
            dispatch_result = build_runtime_execution_error(
                runtime=runtime_target_id,
                message="Adapter returned non-dict result.",
                error=str(type(dispatch_result)),
            )
        # Attach AEGIS outcome for persistence/consumption by downstream engines.
        if isinstance(dispatch_result, dict) and isinstance(aegis_res, dict):
            dispatch_result["aegis"] = aegis_res
        if isinstance(dispatch_result, dict):
            dispatch_result["authority_trace"] = nexus_trace
            dispatch_result["runtime_target_selection"] = selection_snapshot
        if runtime_target_id == "claude" and isinstance(dispatch_result, dict) and dispatch_result.get("status") != "blocked":
            # Phase 9: consume Claude advisory runtime_artifact and apply routing policy.
            # No execution is triggered here; routing decisions are advisory hints only.
            # AEGIS and authority enforcement have already run before this point.
            _artifact = dict(dispatch_result.get("runtime_artifact") or {})
            _confidence = float(_artifact.get("confidence_score") or 0.0)
            _risk = str(_artifact.get("risk_level") or "medium").strip().lower()
            _rec_action = str(_artifact.get("recommended_action") or "require_human_review").strip().lower()

            # Routing policy (order matters: risk and confidence gates take precedence).
            if _risk == "high":
                _routing_outcome = "human_review"
                _routing_reason = "Claude advisory risk_level is high; operator review required before any next step."
            elif _confidence < 0.55:
                _routing_outcome = "human_review"
                _routing_reason = (
                    f"Claude advisory confidence_score={_confidence:.2f} is below threshold 0.55; "
                    "operator review required before any next step."
                )
            elif _rec_action == "route_to_codex":
                _routing_outcome = "route_to_codex"
                _routing_reason = "Claude advisory recommends routing to Codex for code generation or refactor drafting."
            elif _rec_action == "route_to_cursor_review":
                _routing_outcome = "route_to_cursor_review"
                _routing_reason = "Claude advisory recommends routing to Cursor for repo-aware review."
            elif _rec_action == "no_action_required":
                _routing_outcome = "no_action_required"
                _routing_reason = "Claude advisory determined no further action is required."
            else:
                # require_human_review or any unrecognised value → safe default
                _routing_outcome = "human_review"
                _routing_reason = (
                    f"Claude advisory recommended_action='{_rec_action}'; "
                    "routing to human review as governed safe default."
                )

            # Attach the routing decision as a traceable, inert field.
            dispatch_result["claude_routing_decision"] = {
                "routing_outcome": _routing_outcome,
                "routing_reason": _routing_reason,
                "policy_inputs": {
                    "risk_level": _risk,
                    "confidence_score": _confidence,
                    "recommended_action": _rec_action,
                },
                "policy_rules_applied": [
                    "high_risk_requires_human_review",
                    "low_confidence_requires_human_review",
                    "follow_recommended_action_if_eligible",
                ],
                "requires_approval": bool(_artifact.get("requires_approval", True)),
            }

            # Propagate the routing outcome into the standard next_action field
            # so existing consumers (governance_layer, automation_layer) receive it.
            if _routing_outcome == "human_review":
                dispatch_result["next_action"] = "human_review"
                dispatch_result["requires_approval"] = True
            elif _routing_outcome == "route_to_codex":
                dispatch_result["next_action"] = "route_to_codex"
                dispatch_result["suggested_runtime_target"] = "codex"
            elif _routing_outcome == "route_to_cursor_review":
                dispatch_result["next_action"] = "route_to_cursor_review"
                dispatch_result["suggested_runtime_target"] = "cursor"
            elif _routing_outcome == "no_action_required":
                dispatch_result["next_action"] = "none"
                dispatch_result["stop_reason"] = "claude_advisory_no_action_required"

            # Phase 3: normalize and surface Claude proposed_actions.
            # Proposals are advisory only — no packages are created, no routing
            # is changed, no governance is bypassed. NEXUS governance and the
            # operator remain the sole authority on what happens next.
            _PHASE3_VALID_TYPES = frozenset({
                "route_to_codex",
                "route_to_cursor_review",
                "create_followup_package",
                "require_human_review",
                "no_action_required",
            })
            _raw_proposals = _artifact.get("proposed_actions")
            _raw_proposals = _raw_proposals if isinstance(_raw_proposals, (list, tuple)) else []
            _normalized_proposals: list[dict] = []
            _followup_package_requested = False
            for _p in _raw_proposals:
                if not isinstance(_p, dict):
                    continue
                _p_action = str(_p.get("action_type") or "").strip().lower()
                if _p_action not in _PHASE3_VALID_TYPES:
                    _p_action = "require_human_review"
                _normalized_proposals.append({
                    "action_type": _p_action,
                    "target": str(_p.get("target") or "").strip()[:200],
                    "justification": str(_p.get("justification") or "").strip()[:500],
                    "required_approval": bool(_p.get("required_approval", True)),
                })
                if _p_action == "create_followup_package":
                    _followup_package_requested = True
                if len(_normalized_proposals) >= 20:
                    break

            # Attach normalized proposals as an inert traceable field.
            dispatch_result["claude_proposed_actions"] = _normalized_proposals

            # Raise the followup package flag if any proposal requested one.
            # This is an advisory flag only — no package is created here.
            if _followup_package_requested:
                dispatch_result["followup_package_requested"] = True

            # Phase 4: translate proposals into governed system objects via bridge.
            # All governed objects are sealed, review-pending, require existing
            # approval/review lifecycle. No execution is triggered here.
            try:
                from NEXUS.claude_proposal_bridge import translate_claude_proposals_safe
                _translation_summary = translate_claude_proposals_safe(
                    proposed_actions=_normalized_proposals,
                    dispatch_plan=dispatch_plan,
                    aegis_res=aegis_res,
                    authority_trace=nexus_trace,
                    runtime_artifact=_artifact,
                )
            except Exception:
                _translation_summary = {
                    "translation_count": 0,
                    "source_runtime": "claude",
                    "translations": [],
                    "followup_package_ids": [],
                    "approval_ids": [],
                    "review_candidate_ids": [],
                    "outcome": "error_fallback",
                }
            dispatch_result["claude_proposal_translations"] = _translation_summary
            # Upgrade followup_package_requested to True if translation created packages.
            if _translation_summary.get("followup_package_ids"):
                dispatch_result["followup_package_requested"] = True

        if runtime_target_id == "cursor" and isinstance(dispatch_result, dict) and dispatch_result.get("status") != "blocked":
            cursor_bridge_summary = dict(dispatch_result.get("cursor_bridge_summary") or {})
            package_id, package_path = _create_review_only_execution_package(
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
                approval_record=None,
                approval_id=None,
                package_reason="Governed Cursor bridge handoff created; development artifacts must return through package-linked validation.",
                authority_trace=nexus_trace,
                cursor_bridge_summary=cursor_bridge_summary,
            )
            updated_summary = {
                **cursor_bridge_summary,
                "package_id": str(package_id or cursor_bridge_summary.get("package_id") or ""),
                "package_reference": {
                    **dict(cursor_bridge_summary.get("package_reference") or {}),
                    "package_id": str(package_id or cursor_bridge_summary.get("package_id") or ""),
                    "package_path": str(package_path or ""),
                },
                "package_path": str(package_path or ""),
            }
            dispatch_result["cursor_bridge_summary"] = updated_summary
            if isinstance(dispatch_result.get("cursor_bridge_result"), dict):
                dispatch_result["cursor_bridge_result"] = {
                    **dispatch_result["cursor_bridge_result"],
                    "package_id": str(package_id or ""),
                }
            if package_id:
                dispatch_result["execution_package_id"] = package_id
                dispatch_result["execution_package_path"] = package_path
                dispatch_result["package_review_required"] = True
                artifacts = list(dispatch_result.get("artifacts") or [])
                artifacts.extend(_build_review_package_artifact(package_id=package_id, package_path=package_path))
                dispatch_result["artifacts"] = artifacts[:20]
                dispatch_result["message"] = (
                    "Governed Cursor bridge handoff prepared and linked to a sealed execution package."
                )
                dispatch_result["next_action"] = "review_execution_package"
        return {
            "dispatch_status": "accepted",
            "runtime_target": runtime_target_id,
            "dispatch_result": dispatch_result,
        }
    except Exception as e:
        err = build_runtime_execution_error(
            runtime=runtime_target_id,
            message="Dispatch adapter error.",
            error=str(e),
        )
        if isinstance(err, dict) and isinstance(aegis_res, dict):
            err["aegis"] = aegis_res
        if isinstance(err, dict):
            err["authority_trace"] = nexus_trace
            err["runtime_target_selection"] = selection_snapshot
        return {
            "dispatch_status": "error",
            "runtime_target": runtime_target_id,
            "dispatch_result": err,
        }
