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
from NEXUS.execution_truth import resolve_dispatch_truth
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
        result_payload = {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": blocked,
        }
        blocked["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=blocked,
        )
        return result_payload

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
        result_payload = {
            "dispatch_status": "skipped",
            "runtime_target": selected_target_id or runtime_target_id,
            "dispatch_result": skipped,
        }
        skipped["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=skipped,
        )
        return result_payload

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
        result_payload = {
            "dispatch_status": "skipped",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": unavailable,
        }
        unavailable["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=unavailable,
        )
        return result_payload

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
        result_payload = {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id or "",
            "dispatch_result": blocked,
        }
        blocked["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=blocked,
        )
        return result_payload

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
            result_payload = {
                "dispatch_status": "blocked",
                "runtime_target": runtime_target_id,
                "dispatch_result": blocked,
            }
            blocked["execution_truth_status"] = resolve_dispatch_truth(
                dispatch_status=result_payload.get("dispatch_status"),
                dispatch_result=blocked,
            )
            return result_payload

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
            result_payload = {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": queued,
            }
            queued["execution_truth_status"] = resolve_dispatch_truth(
                dispatch_status=result_payload.get("dispatch_status"),
                dispatch_result=queued,
            )
            return result_payload

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
            result_payload = {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": gated,
            }
            gated["execution_truth_status"] = resolve_dispatch_truth(
                dispatch_status=result_payload.get("dispatch_status"),
                dispatch_result=gated,
            )
            return result_payload

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
            result_payload = {
                "dispatch_status": "accepted",
                "runtime_target": runtime_target_id,
                "dispatch_result": packaged,
            }
            packaged["execution_truth_status"] = resolve_dispatch_truth(
                dispatch_status=result_payload.get("dispatch_status"),
                dispatch_result=packaged,
            )
            return result_payload
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
        result_payload = {
            "dispatch_status": "blocked",
            "runtime_target": runtime_target_id,
            "dispatch_result": blocked,
        }
        blocked["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=blocked,
        )
        return result_payload
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
        result_payload = {
            "dispatch_status": "no_adapter",
            "runtime_target": runtime_target_id,
            "dispatch_result": no_adapter,
        }
        no_adapter["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=no_adapter,
        )
        return result_payload
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
        result_payload = {
            "dispatch_status": "accepted",
            "runtime_target": runtime_target_id,
            "dispatch_result": dispatch_result,
        }
        dispatch_result["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=dispatch_result,
        )
        return result_payload
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
        result_payload = {
            "dispatch_status": "error",
            "runtime_target": runtime_target_id,
            "dispatch_result": err,
        }
        err["execution_truth_status"] = resolve_dispatch_truth(
            dispatch_status=result_payload.get("dispatch_status"),
            dispatch_result=err,
        )
        return result_payload
