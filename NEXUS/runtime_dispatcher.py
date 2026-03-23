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
    build_runtime_execution_error,
    build_runtime_execution_skipped,
    build_runtime_execution_result,
)


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
        )
        package_id = package.get("package_id")
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
            runtime=runtime_target_id or "local",
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
            "runtime_target": runtime_target_id or "local",
            "dispatch_result": blocked,
        }

    if not dispatch_plan or not dispatch_plan.get("ready_for_dispatch", False):
        skipped = build_runtime_execution_skipped(
            runtime=runtime_target_id or "local",
            message="Dispatch skipped: dispatch plan not ready.",
            reason="not_ready",
        )
        skipped["authority_trace"] = nexus_trace
        return {
            "dispatch_status": "skipped",
            "runtime_target": runtime_target_id,
            "dispatch_result": skipped,
        }

    if not runtime_target_id:
        runtime_target_id = "local"

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
        return {
            "dispatch_status": "error",
            "runtime_target": runtime_target_id,
            "dispatch_result": err,
        }
