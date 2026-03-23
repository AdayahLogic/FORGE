"""
Explicit HELIX input/output contracts and execution-package bridge helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


HELIX_CONTRACT_VERSION = "1.0"
HELIX_INPUT_SCHEMA_VERSION = "1.0"
HELIX_OUTPUT_SCHEMA_VERSION = "1.0"
HELIX_REQUIRED_INPUT_FIELDS = {
    "project_name": str,
    "run_id": str,
    "task": str,
    "project_state": dict,
    "loaded_context": dict,
    "prior_evaluations": list,
}
HELIX_REQUIRED_OUTPUT_FIELDS = {
    "task_summary": str,
    "plans": dict,
    "code_generation": dict,
    "validation": dict,
    "risk_flags": list,
    "pipeline_status": str,
    "stop_reason": str,
    "requires_surgeon": bool,
}


def _trim_text(value: Any, limit: int = 500) -> str:
    return str(value or "")[:limit]


def _extract_target_files(stage_results: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for result in stage_results or []:
        if not isinstance(result, dict):
            continue
        impl_plan = result.get("implementation_plan") or {}
        patch_request = impl_plan.get("patch_request") if isinstance(impl_plan, dict) else None
        if isinstance(patch_request, dict):
            target = str(patch_request.get("target_relative_path") or "").strip()
            if target and target not in out:
                out.append(target)
        repair_metadata = result.get("repair_metadata") or {}
        if isinstance(repair_metadata, dict):
            for item in repair_metadata.get("candidate_target_files") or repair_metadata.get("target_files_candidate") or []:
                normalized = str(item or "").strip()
                if normalized and normalized not in out:
                    out.append(normalized)
    return out[:20]


def build_helix_input_contract(
    *,
    project_state: dict[str, Any] | None,
    requested_outcome: str,
    loaded_context: dict[str, Any] | None = None,
    prior_evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = project_state or {}
    context = loaded_context or {}
    evaluations = [dict(item) for item in (prior_evaluations or []) if isinstance(item, dict)][:10]
    return {
        "project_name": str(state.get("active_project") or state.get("project_name") or ""),
        "run_id": str(state.get("run_id") or ""),
        "task": _trim_text(requested_outcome, 1000),
        "project_state": {
            "governance_status": str(state.get("governance_status") or ""),
            "enforcement_status": str(state.get("enforcement_status") or ""),
            "recovery_status": str(state.get("recovery_status") or ""),
            "autonomy_mode": str(state.get("autonomy_mode") or ""),
        },
        "loaded_context": {
            "memory_status": str(context.get("memory_status") or ""),
            "current_focus": _trim_text(context.get("current_focus") or "", 300),
            "next_steps": list(context.get("next_steps") or [])[:5] if isinstance(context.get("next_steps"), list) else _trim_text(context.get("next_steps") or "", 300),
        },
        "prior_evaluations": evaluations,
    }


def build_helix_output_contract(
    *,
    requested_outcome: str,
    stage_results: list[dict[str, Any]] | None,
    pipeline_status: str,
    stop_reason: str,
    requires_surgeon: bool,
) -> dict[str, Any]:
    results = [dict(item) for item in (stage_results or []) if isinstance(item, dict)]
    builder = next((item for item in results if item.get("stage") == "builder"), {})
    inspector = next((item for item in results if item.get("stage") == "inspector"), {})
    critic = next((item for item in results if item.get("stage") == "critic"), {})
    surgeon = next((item for item in results if item.get("stage") == "surgeon"), {})
    implementation_plan = builder.get("implementation_plan") or {}
    critique_evaluation = critic.get("critique_evaluation") or {}
    validation_result = inspector.get("validation_result") or {}
    repair_metadata = surgeon.get("repair_metadata") or {}

    risk_flags: list[str] = []
    if requires_surgeon:
        risk_flags.append("repair_recommended")
    severity = str(critique_evaluation.get("severity") or repair_metadata.get("severity") or "").strip().lower()
    if severity:
        risk_flags.append(f"severity:{severity}")
    if str(validation_result.get("regression_status") or "").strip().lower() not in ("", "passed"):
        risk_flags.append("validation_regression_issue")

    return {
        "task_summary": _trim_text(requested_outcome, 500),
        "plans": {
            "implementation_steps": list(implementation_plan.get("implementation_steps") or [])[:20],
            "assumptions": list(implementation_plan.get("assumptions") or [])[:10],
            "next_agent": str(implementation_plan.get("next_agent") or ""),
        },
        "code_generation": {
            "patch_request_present": isinstance(implementation_plan.get("patch_request"), dict),
            "target_files": _extract_target_files(results),
        },
        "validation": {
            "regression_status": str(validation_result.get("regression_status") or ""),
            "regression_reason": _trim_text(validation_result.get("regression_reason") or "", 300),
        },
        "risk_flags": risk_flags[:10],
        "pipeline_status": str(pipeline_status or ""),
        "stop_reason": str(stop_reason or ""),
        "requires_surgeon": bool(requires_surgeon),
    }


def build_helix_contract_envelope(
    *,
    input_contract: dict[str, Any],
    output_contract: dict[str, Any],
    package_id_refs: list[str] | None = None,
    authority_trace: dict[str, Any] | None = None,
    trace_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_refs = [str(item) for item in (package_id_refs or []) if str(item).strip()][:10]
    authority = dict(authority_trace or {})
    trace = dict(trace_metadata or {})
    if "trace_generated_at" not in trace:
        trace["trace_generated_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "contract_version": HELIX_CONTRACT_VERSION,
        "input_schema_version": HELIX_INPUT_SCHEMA_VERSION,
        "output_schema_version": HELIX_OUTPUT_SCHEMA_VERSION,
        "input_contract": dict(input_contract or {}),
        "output_contract": dict(output_contract or {}),
        "package_enforcement": {
            "required": True,
            "package_status": "packaged" if package_refs else "pending_package",
            "package_id_refs": package_refs,
            "binding_path": "review_sealed_package_flow",
            "review_required": True,
            "sealed_package_required": True,
        },
        "authority_trace": authority,
        "trace_metadata": trace,
    }


def validate_helix_contract_envelope(contract: dict[str, Any] | None) -> dict[str, Any]:
    data = contract or {}
    input_contract = data.get("input_contract") if isinstance(data.get("input_contract"), dict) else {}
    output_contract = data.get("output_contract") if isinstance(data.get("output_contract"), dict) else {}
    missing: list[str] = []
    type_errors: list[str] = []
    validation_errors: list[str] = []
    package_enforcement = data.get("package_enforcement") if isinstance(data.get("package_enforcement"), dict) else {}
    authority_trace = data.get("authority_trace") if isinstance(data.get("authority_trace"), dict) else {}
    trace_metadata = data.get("trace_metadata") if isinstance(data.get("trace_metadata"), dict) else {}

    if str(data.get("contract_version") or "") != HELIX_CONTRACT_VERSION:
        validation_errors.append(f"contract_version must be '{HELIX_CONTRACT_VERSION}'")
    if str(data.get("input_schema_version") or "") != HELIX_INPUT_SCHEMA_VERSION:
        validation_errors.append(f"input_schema_version must be '{HELIX_INPUT_SCHEMA_VERSION}'")
    if str(data.get("output_schema_version") or "") != HELIX_OUTPUT_SCHEMA_VERSION:
        validation_errors.append(f"output_schema_version must be '{HELIX_OUTPUT_SCHEMA_VERSION}'")

    for field, expected_type in HELIX_REQUIRED_INPUT_FIELDS.items():
        if field not in input_contract:
            missing.append(f"input_contract.{field}")
            continue
        if not isinstance(input_contract.get(field), expected_type):
            type_errors.append(f"input_contract.{field} must be {expected_type.__name__}")
    for field, expected_type in HELIX_REQUIRED_OUTPUT_FIELDS.items():
        if field not in output_contract:
            missing.append(f"output_contract.{field}")
            continue
        if not isinstance(output_contract.get(field), expected_type):
            type_errors.append(f"output_contract.{field} must be {expected_type.__name__}")

    if not str(input_contract.get("task") or "").strip():
        validation_errors.append("input_contract.task must be non-empty")
    plans = output_contract.get("plans") if isinstance(output_contract.get("plans"), dict) else {}
    code_generation = output_contract.get("code_generation") if isinstance(output_contract.get("code_generation"), dict) else {}
    validation = output_contract.get("validation") if isinstance(output_contract.get("validation"), dict) else {}
    if "implementation_steps" not in plans:
        missing.append("output_contract.plans.implementation_steps")
    elif not isinstance(plans.get("implementation_steps"), list):
        type_errors.append("output_contract.plans.implementation_steps must be list")
    if "patch_request_present" not in code_generation:
        missing.append("output_contract.code_generation.patch_request_present")
    elif not isinstance(code_generation.get("patch_request_present"), bool):
        type_errors.append("output_contract.code_generation.patch_request_present must be bool")
    if "target_files" not in code_generation:
        missing.append("output_contract.code_generation.target_files")
    elif not isinstance(code_generation.get("target_files"), list):
        type_errors.append("output_contract.code_generation.target_files must be list")
    if "regression_status" not in validation:
        missing.append("output_contract.validation.regression_status")
    elif not isinstance(validation.get("regression_status"), str):
        type_errors.append("output_contract.validation.regression_status must be str")

    if package_enforcement.get("required") is not True:
        validation_errors.append("package_enforcement.required must be true")
    if str(package_enforcement.get("binding_path") or "") != "review_sealed_package_flow":
        validation_errors.append("package_enforcement.binding_path must be 'review_sealed_package_flow'")
    if not str(trace_metadata.get("project_name") or "").strip():
        validation_errors.append("trace_metadata.project_name is required")
    if not str(trace_metadata.get("trace_id") or "").strip():
        validation_errors.append("trace_metadata.trace_id is required")
    if not str(authority_trace.get("component_name") or "").strip():
        validation_errors.append("authority_trace.component_name is required")
    if not str(authority_trace.get("authority_status") or "").strip():
        validation_errors.append("authority_trace.authority_status is required")

    issues = missing + type_errors + validation_errors
    contract_status = "valid" if not issues else "invalid"
    package_binding_status = "validated_for_review_package" if contract_status == "valid" else "validation_failed"
    return {
        "contract_status": contract_status,
        "missing_fields": missing,
        "type_errors": type_errors,
        "validation_errors": validation_errors,
        "validation_path": "package_binding_allowed" if contract_status == "valid" else "blocked_before_package_binding",
        "package_binding_status": package_binding_status,
        "packaging_required": bool(((data.get("package_enforcement") or {}).get("required"))),
        "authority_trace_present": bool(authority_trace),
        "trace_metadata_present": bool(trace_metadata),
        "issue_count": len(issues),
    }


def build_helix_review_dispatch_plan(
    *,
    project_path: str,
    project_name: str,
    requested_outcome: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    output_contract = (contract or {}).get("output_contract") or {}
    code_generation = output_contract.get("code_generation") or {}
    target_files = [str(item) for item in (code_generation.get("target_files") or []) if str(item).strip()][:20]
    return {
        "dispatch_version": "helix_contract_bridge_v1",
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": True,
        "timestamps": {"planned_at": ""},
        "project": {
            "project_name": str(project_name or ""),
            "project_path": str(project_path or ""),
        },
        "routing": {
            "runtime_node": "helix",
            "agent_name": "helix",
            "tool_name": "execution_package_builder",
            "selection_status": "selected",
            "selection_reason": "HELIX contract output routed into review-only execution package.",
        },
        "execution": {
            "runtime_target_id": "windows_review_package",
            "requires_human_approval": True,
        },
        "request": {
            "request_type": "helix_contract_review",
            "task_type": "helix_generation",
            "summary": _trim_text(requested_outcome, 500),
            "priority": "high",
        },
        "artifacts": {
            "target_files": target_files,
            "expected_outputs": ["helix_contract_review", "execution_package"],
        },
    }
