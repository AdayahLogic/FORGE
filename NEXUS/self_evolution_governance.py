"""
NEXUS self-evolution governance foundations.

Classifies proposed self-modifications, validates governed self-change
contracts, and resolves one shared release-gating outcome. This layer is
contract-only and does not execute modifications.
"""

from __future__ import annotations

import uuid
from typing import Any


SELF_EVOLUTION_GOVERNANCE_VERSION = "1.2"
SELF_CHANGE_REQUIRED_FIELDS = (
    "change_id",
    "target_files",
    "change_type",
    "risk_level",
    "reason",
    "expected_outcome",
    "validation_plan",
    "rollback_plan",
    "authority_trace",
    "governance_trace",
)
VALID_RISK_LEVELS = {"low_risk", "medium_risk", "high_risk"}
VALID_APPROVAL_REQUIREMENTS = {
    "low_risk": "optional",
    "medium_risk": "recommended",
    "high_risk": "mandatory",
}
VALIDATION_REQUIRED_CHECKS = ("tests", "build", "regressions")
VALID_GATE_OUTCOMES = {
    "allow_for_review",
    "blocked_missing_validation",
    "blocked_missing_approval",
    "blocked_protected_zone",
    "release_ready",
    "release_rejected",
    "rollback_required",
}
VALID_RELEASE_LANES = {"stable", "experimental"}
VALID_SANDBOX_STATUSES = {
    "sandbox_pending",
    "sandbox_running",
    "sandbox_passed",
    "sandbox_failed",
    "sandbox_rejected",
    "sandbox_not_required",
}
VALID_PROMOTION_STATUSES = {
    "promotion_pending",
    "promotion_blocked",
    "promotion_ready",
    "promoted_to_stable",
    "kept_experimental",
    "promotion_rejected",
}
VALID_COMPARATIVE_SCORING_STATUSES = {
    "scored",
    "insufficient_evidence",
    "regression_detected",
    "promote_ready",
    "keep_experimental",
    "confidence_too_weak",
}
VALID_CONFIDENCE_BANDS = {"weak", "moderate", "strong"}
VALID_PROMOTION_CONFIDENCE_OUTCOMES = {
    "promote_ready",
    "keep_experimental",
    "confidence_too_weak",
    "regression_detected",
    "insufficient_evidence",
}
VALID_RECOMMENDATIONS = {"promote", "hold_experimental", "reject", "rollback"}
CORE_COMPARISON_DIMENSIONS = ("tests", "build", "regressions", "governance", "authority")
PROTECTED_CORE_ZONES: dict[str, tuple[str, ...]] = {
    "nexus_orchestration_core": ("nexus/main.py", "nexus/router.py", "nexus/agent_router.py"),
    "governance_layer": ("nexus/governance_layer.py",),
    "authority_model": ("nexus/authority_model.py",),
    "project_autopilot": ("nexus/project_autopilot.py",),
    "runtime_dispatcher": ("nexus/runtime_dispatcher.py",),
    "execution_package_system": (
        "nexus/execution_package_",
        "nexus/execution_bridge.py",
        "nexus/runtime_execution.py",
    ),
}
LOW_RISK_HINTS = ("ui", "display", "summary", "dashboard", "log", "logs")
MEDIUM_RISK_HINTS = ("adapter", "adapters", "helper", "helpers", "non_core_logic", "support")
HIGH_RISK_HINTS = (
    "routing",
    "governance",
    "authority",
    "autopilot",
    "execution",
    "dispatcher",
    "orchestration",
    "self_modification",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_path(value: Any) -> str:
    return _normalize_text(value).replace("\\", "/").lower()


def _normalize_target_files(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = _normalize_text(item)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _normalize_plan(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        checks = value.get("checks")
        if isinstance(checks, str):
            checks = [checks]
        elif not isinstance(checks, list):
            checks = []
        return {
            **value,
            "checks": [str(item).strip().lower() for item in checks if str(item).strip()],
            "summary": _normalize_text(value.get("summary")),
        }
    summary = _normalize_text(value)
    return {"summary": summary, "checks": []}


def _normalize_comparison_dimensions(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = _normalize_text(item).lower()
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _normalize_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, raw_value in value.items():
        normalized_key = _normalize_text(key).lower()
        if not normalized_key:
            continue
        if isinstance(raw_value, str):
            out[normalized_key] = raw_value.strip().lower()
        elif isinstance(raw_value, (int, float, bool)):
            out[normalized_key] = raw_value
        else:
            out[normalized_key] = raw_value
    return out


def _contains_any(text: str, hints: tuple[str, ...] | list[str]) -> bool:
    lowered = _normalize_path(text)
    return any(hint in lowered for hint in hints)


def _normalize_approval_status(value: Any, *, approval_required: bool) -> str:
    status = _normalize_text(value).lower()
    if status in {"approved", "pending", "rejected", "denied", "optional", "not_required"}:
        return status
    return "pending" if approval_required else "optional"


def _normalize_check_status(value: Any) -> str:
    status = _normalize_text(value).lower()
    if status in {"passed", "failed", "pending", "not_applicable", "rejected"}:
        return status
    return "pending"


def _normalize_validation_outcome(value: Any) -> str:
    outcome = _normalize_text(value).lower()
    if outcome in {"passed", "failed", "pending", "rejected"}:
        return outcome
    return "pending"


def _normalize_release_lane(value: Any, *, default: str) -> str:
    lane = _normalize_text(value).lower()
    return lane if lane in VALID_RELEASE_LANES else default


def _normalize_sandbox_status(value: Any, *, default: str) -> str:
    status = _normalize_text(value).lower()
    aliases = {
        "pending": "sandbox_pending",
        "running": "sandbox_running",
        "passed": "sandbox_passed",
        "failed": "sandbox_failed",
        "rejected": "sandbox_rejected",
        "not_required": "sandbox_not_required",
    }
    status = aliases.get(status, status)
    return status if status in VALID_SANDBOX_STATUSES else default


def _normalize_promotion_status(value: Any, *, default: str) -> str:
    status = _normalize_text(value).lower()
    aliases = {
        "pending": "promotion_pending",
        "blocked": "promotion_blocked",
        "ready": "promotion_ready",
        "rejected": "promotion_rejected",
    }
    status = aliases.get(status, status)
    return status if status in VALID_PROMOTION_STATUSES else default


def _normalize_application_state(value: Any) -> str:
    state = _normalize_text(value).lower()
    if state in {"proposed", "attempted", "applied", "failed"}:
        return state
    return "proposed"


def _is_approval_present(status: str) -> bool:
    return status == "approved"


def detect_protected_core_zones(target_files: Any = None) -> list[str]:
    files = _normalize_target_files(target_files)
    matches: list[str] = []
    for file_path in files:
        lowered = _normalize_path(file_path)
        for zone_name, patterns in PROTECTED_CORE_ZONES.items():
            if zone_name in matches:
                continue
            if any(pattern in lowered for pattern in patterns):
                matches.append(zone_name)
    return matches


def classify_self_change(
    *,
    target_files: Any = None,
    change_type: Any = None,
) -> dict[str, Any]:
    files = _normalize_target_files(target_files)
    change_type_text = _normalize_text(change_type).lower()
    protected_zones = detect_protected_core_zones(files)

    if protected_zones:
        risk_level = "high_risk"
        reason = "Targets protected core zones."
    elif _contains_any(change_type_text, HIGH_RISK_HINTS) or any(_contains_any(path, HIGH_RISK_HINTS) for path in files):
        risk_level = "high_risk"
        reason = "Change touches governance-sensitive routing, authority, autopilot, or execution paths."
    elif _contains_any(change_type_text, MEDIUM_RISK_HINTS) or any(_contains_any(path, MEDIUM_RISK_HINTS) for path in files):
        risk_level = "medium_risk"
        reason = "Change affects non-core logic, adapters, or helpers."
    elif _contains_any(change_type_text, LOW_RISK_HINTS) or any(_contains_any(path, LOW_RISK_HINTS) for path in files):
        risk_level = "low_risk"
        reason = "Change is limited to UI, logging, display, or summaries."
    else:
        risk_level = "medium_risk"
        reason = "Change defaults to medium risk when classification is ambiguous."

    return {
        "risk_level": risk_level,
        "approval_requirement": VALID_APPROVAL_REQUIREMENTS[risk_level],
        "protected_zones": protected_zones,
        "classification_reason": reason,
        "explicit_approval_required": risk_level == "high_risk",
    }


def normalize_self_change_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
    raw = contract or {}
    normalized_target_files = _normalize_target_files(raw.get("target_files"))
    classification = classify_self_change(
        target_files=normalized_target_files,
        change_type=raw.get("change_type"),
    )
    validation_plan = _normalize_plan(raw.get("validation_plan"))
    rollback_plan = _normalize_plan(raw.get("rollback_plan"))
    risk_level = _normalize_text(raw.get("risk_level")).lower()
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = classification["risk_level"]
    approval_required = VALID_APPROVAL_REQUIREMENTS[risk_level] == "mandatory"

    tests_status = _normalize_check_status(raw.get("tests_status") or raw.get("test_status"))
    build_status = _normalize_check_status(raw.get("build_status"))
    regression_status = _normalize_check_status(raw.get("regression_status"))
    validation_outcome = _normalize_validation_outcome(raw.get("validation_outcome"))
    if validation_outcome == "pending" and tests_status == "passed" and build_status == "passed" and regression_status == "passed":
        validation_outcome = "passed"
    elif validation_outcome == "pending" and "failed" in {tests_status, build_status, regression_status}:
        validation_outcome = "failed"

    requested_release_lane = _normalize_release_lane(
        raw.get("release_lane") or raw.get("requested_release_lane"),
        default="experimental" if risk_level == "high_risk" or classification["protected_zones"] else "stable",
    )

    return {
        "governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
        "change_id": _normalize_text(raw.get("change_id")) or f"self-change-{uuid.uuid4().hex[:12]}",
        "target_files": normalized_target_files,
        "change_type": _normalize_text(raw.get("change_type")),
        "risk_level": risk_level,
        "reason": _normalize_text(raw.get("reason")),
        "expected_outcome": _normalize_text(raw.get("expected_outcome")),
        "validation_plan": validation_plan,
        "rollback_plan": rollback_plan,
        "authority_trace": dict(raw.get("authority_trace") or {}),
        "governance_trace": dict(raw.get("governance_trace") or {}),
        "classification": classification,
        "protected_zones": list(classification.get("protected_zones") or []),
        "approval_requirement": VALID_APPROVAL_REQUIREMENTS[risk_level],
        "approval_status": _normalize_approval_status(raw.get("approval_status"), approval_required=approval_required),
        "validation_outcome": validation_outcome,
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "release_lane": requested_release_lane,
        "stable_release_approved": bool(raw.get("stable_release_approved", False)),
        "application_state": _normalize_application_state(raw.get("application_state")),
        "sandbox_status": _normalize_sandbox_status(
            raw.get("sandbox_status"),
            default="sandbox_pending",
        ),
        "sandbox_result": _normalize_sandbox_status(
            raw.get("sandbox_result") or raw.get("sandbox_status"),
            default="sandbox_pending",
        ),
        "promotion_status": _normalize_promotion_status(
            raw.get("promotion_status"),
            default="promotion_pending",
        ),
        "promotion_reason": _normalize_text(raw.get("promotion_reason")),
        "baseline_reference": _normalize_text(raw.get("baseline_reference")),
        "candidate_reference": _normalize_text(raw.get("candidate_reference")) or _normalize_text(raw.get("change_id")),
        "baseline_evidence": _normalize_evidence(raw.get("baseline_evidence")),
        "candidate_evidence": _normalize_evidence(raw.get("candidate_evidence")),
        "comparison_dimensions": _normalize_comparison_dimensions(raw.get("comparison_dimensions")),
    }


def validate_self_change_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_self_change_contract(contract)
    missing_fields: list[str] = []
    for field in SELF_CHANGE_REQUIRED_FIELDS:
        value = normalized.get(field)
        if isinstance(value, dict):
            if not value:
                missing_fields.append(field)
        elif isinstance(value, list):
            if not value:
                missing_fields.append(field)
        elif not _normalize_text(value):
            missing_fields.append(field)

    validation_checks = set(str(item).strip().lower() for item in (normalized.get("validation_plan") or {}).get("checks", []))
    missing_validation_checks = [check for check in VALIDATION_REQUIRED_CHECKS if check not in validation_checks]
    rollback_summary = _normalize_text((normalized.get("rollback_plan") or {}).get("summary"))
    rollback_ready = bool(rollback_summary)
    checks_present = not missing_validation_checks

    contract_valid = not missing_fields and checks_present and rollback_ready
    reason_parts: list[str] = []
    if missing_fields:
        reason_parts.append(f"missing required fields: {', '.join(missing_fields)}")
    if missing_validation_checks:
        reason_parts.append(f"missing validation checks: {', '.join(missing_validation_checks)}")
    if not rollback_ready:
        reason_parts.append("rollback summary required")

    return {
        "contract_status": "valid" if contract_valid else "invalid",
        "missing_fields": missing_fields,
        "missing_validation_checks": missing_validation_checks,
        "rollback_ready": rollback_ready,
        "checks_present": checks_present,
        "validation_required": True,
        "reason": "; ".join(reason_parts) if reason_parts else "Self-change contract is valid.",
        "normalized_contract": normalized,
    }


def evaluate_self_change_governance(contract: dict[str, Any] | None) -> dict[str, Any]:
    validation = validate_self_change_contract(contract)
    normalized = validation["normalized_contract"]
    risk_level = str(normalized.get("risk_level") or "medium_risk")
    approval_requirement = VALID_APPROVAL_REQUIREMENTS.get(risk_level, "recommended")
    explicit_approval_required = approval_requirement == "mandatory"
    protected_zones = list(normalized.get("protected_zones") or [])

    if validation["contract_status"] != "valid":
        governance_status = "blocked"
        reason = str(validation.get("reason") or "Invalid self-change contract.")
    elif explicit_approval_required:
        governance_status = "approval_required"
        reason = "High-risk self-change requires explicit approval."
    elif approval_requirement == "recommended":
        governance_status = "review_required"
        reason = "Medium-risk self-change should receive approval before execution."
    else:
        governance_status = "approved"
        reason = "Low-risk self-change classified with optional approval."

    governance_trace = {
        **dict(normalized.get("governance_trace") or {}),
        "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
        "classification": dict(normalized.get("classification") or {}),
        "contract_validation": {
            "contract_status": validation.get("contract_status"),
            "missing_fields": list(validation.get("missing_fields") or []),
            "missing_validation_checks": list(validation.get("missing_validation_checks") or []),
            "rollback_ready": bool(validation.get("rollback_ready")),
        },
    }

    return {
        "self_change_status": governance_status,
        "governance_status": governance_status,
        "approval_required": explicit_approval_required,
        "approval_requirement": approval_requirement,
        "risk_level": risk_level,
        "protected_zones": protected_zones,
        "validation_required": True,
        "rollback_required": True,
        "contract_status": validation.get("contract_status"),
        "decision_reason": reason,
        "authority_trace": dict(normalized.get("authority_trace") or {}),
        "governance_trace": governance_trace,
        "normalized_contract": normalized,
    }


def evaluate_self_change_release_gate(contract: dict[str, Any] | None) -> dict[str, Any]:
    governance = evaluate_self_change_governance(contract)
    normalized = governance["normalized_contract"]
    validation = validate_self_change_contract(normalized)
    protected_zone_hit = bool(normalized.get("protected_zones"))
    risk_level = str(normalized.get("risk_level") or "medium_risk")
    approval_required = bool(governance.get("approval_required"))
    approval_status = str(normalized.get("approval_status") or "optional")
    validation_outcome = str(normalized.get("validation_outcome") or "pending")
    tests_status = str(normalized.get("tests_status") or "pending")
    build_status = str(normalized.get("build_status") or "pending")
    regression_status = str(normalized.get("regression_status") or "pending")
    application_state = str(normalized.get("application_state") or "proposed")

    release_lane = _normalize_release_lane(
        normalized.get("release_lane"),
        default="experimental" if protected_zone_hit or risk_level == "high_risk" else "stable",
    )
    if (protected_zone_hit or risk_level == "high_risk") and not bool(normalized.get("stable_release_approved")):
        release_lane = "experimental"

    checks_present = bool(validation.get("checks_present"))
    rollback_ready = bool(validation.get("rollback_ready"))
    validation_failure = validation_outcome in {"failed", "rejected"} or "failed" in {tests_status, build_status, regression_status}
    attempted_application = application_state in {"attempted", "applied", "failed"}

    reason = ""
    gate_outcome = "allow_for_review"
    status = "ok"
    rollback_required = False

    if attempted_application and (
        validation_failure or (protected_zone_hit and application_state == "failed")
    ):
        gate_outcome = "rollback_required"
        status = "rollback_required"
        rollback_required = True
        reason = "Attempted self-change failed validation, build, regression, or protected-zone safety checks."
    elif approval_status in {"rejected", "denied"}:
        gate_outcome = "release_rejected"
        status = "release_rejected"
        reason = "Self-change approval was rejected."
    elif validation.get("contract_status") != "valid" or not checks_present or not rollback_ready:
        gate_outcome = "blocked_missing_validation"
        status = "blocked"
        reason = str(validation.get("reason") or "Validation requirements are incomplete.")
    elif protected_zone_hit and approval_required and not _is_approval_present(approval_status):
        gate_outcome = "blocked_missing_approval"
        status = "blocked"
        reason = "Protected-zone self-change requires mandatory approval before advancing."
    elif protected_zone_hit and validation_outcome != "passed":
        gate_outcome = "blocked_protected_zone"
        status = "blocked"
        reason = "Protected-zone self-change cannot advance without a passed validation outcome."
    elif validation_failure:
        gate_outcome = "release_rejected"
        status = "release_rejected"
        reason = "Self-change validation, build, or regression verification failed."
    elif validation_outcome != "passed" or tests_status != "passed" or build_status != "passed" or regression_status != "passed":
        gate_outcome = "allow_for_review"
        status = "ok"
        reason = "Self-change remains held for review until validation completes."
    elif risk_level == "medium_risk" and approval_status != "approved":
        gate_outcome = "allow_for_review"
        status = "ok"
        reason = "Medium-risk self-change passed validation but remains review-lane pending approval."
    else:
        gate_outcome = "release_ready"
        status = "release_ready"
        reason = "Self-change satisfied approval, validation, and rollback requirements."

    if gate_outcome == "release_ready" and (protected_zone_hit or risk_level == "high_risk") and release_lane != "experimental":
        if bool(normalized.get("stable_release_approved")):
            release_lane = "stable"
        else:
            release_lane = "experimental"
    elif gate_outcome != "release_ready" and release_lane not in VALID_RELEASE_LANES:
        release_lane = "experimental"

    gate_trace = {
        **dict(governance.get("governance_trace") or {}),
        "release_gate": {
            "gate_outcome": gate_outcome,
            "release_lane": release_lane,
            "approval_status": approval_status,
            "validation_outcome": validation_outcome,
            "tests_status": tests_status,
            "build_status": build_status,
            "regression_status": regression_status,
            "rollback_ready": rollback_ready,
            "protected_zone_hit": protected_zone_hit,
        },
    }

    return {
        "status": status,
        "change_id": str(normalized.get("change_id") or ""),
        "risk_level": risk_level,
        "protected_zone_hit": protected_zone_hit,
        "protected_zones": list(normalized.get("protected_zones") or []),
        "validation_outcome": validation_outcome,
        "gate_outcome": gate_outcome,
        "release_lane": release_lane,
        "rollback_required": rollback_required,
        "approval_required": approval_required,
        "approval_requirement": str(governance.get("approval_requirement") or ""),
        "approval_status": approval_status,
        "contract_status": str(validation.get("contract_status") or ""),
        "tests_status": tests_status,
        "build_status": build_status,
        "regression_status": regression_status,
        "reason": reason,
        "authority_trace": dict(governance.get("authority_trace") or {}),
        "governance_trace": gate_trace,
        "normalized_contract": normalized,
    }


def evaluate_self_change_sandbox_promotion(contract: dict[str, Any] | None) -> dict[str, Any]:
    gate = evaluate_self_change_release_gate(contract)
    normalized = gate["normalized_contract"]
    risk_level = str(gate.get("risk_level") or "medium_risk")
    protected_zone_hit = bool(gate.get("protected_zone_hit"))
    sandbox_required = protected_zone_hit or risk_level == "high_risk"
    approval_required = bool(gate.get("approval_required"))
    approval_status = str(gate.get("approval_status") or "optional")
    requested_release_lane = _normalize_release_lane(
        normalized.get("release_lane"),
        default="experimental" if sandbox_required else "stable",
    )
    release_lane = _normalize_release_lane(
        gate.get("release_lane"),
        default="experimental" if sandbox_required else "stable",
    )
    raw_sandbox_status = _normalize_sandbox_status(
        normalized.get("sandbox_status"),
        default="sandbox_pending" if sandbox_required else "sandbox_not_required",
    )
    raw_sandbox_result = _normalize_sandbox_status(
        normalized.get("sandbox_result"),
        default=raw_sandbox_status,
    )

    if not sandbox_required:
        sandbox_status = "sandbox_not_required"
        sandbox_result = "sandbox_not_required"
    elif approval_status in {"rejected", "denied"}:
        sandbox_status = "sandbox_rejected"
        sandbox_result = "sandbox_rejected"
    elif bool(gate.get("rollback_required")) or raw_sandbox_status == "sandbox_failed" or raw_sandbox_result == "sandbox_failed":
        sandbox_status = "sandbox_failed"
        sandbox_result = "sandbox_failed"
    elif raw_sandbox_status == "sandbox_running" or raw_sandbox_result == "sandbox_running":
        sandbox_status = "sandbox_running"
        sandbox_result = "sandbox_running"
    elif raw_sandbox_status == "sandbox_passed" or raw_sandbox_result == "sandbox_passed":
        sandbox_status = "sandbox_passed"
        sandbox_result = "sandbox_passed"
    elif raw_sandbox_status == "sandbox_rejected" or raw_sandbox_result == "sandbox_rejected":
        sandbox_status = "sandbox_rejected"
        sandbox_result = "sandbox_rejected"
    else:
        sandbox_status = "sandbox_pending"
        sandbox_result = "sandbox_pending"

    promotion_status = "promotion_pending"
    promotion_reason = ""
    effective_release_lane = release_lane

    if approval_status in {"rejected", "denied"} or gate.get("gate_outcome") == "release_rejected":
        promotion_status = "promotion_rejected"
        promotion_reason = "Self-change cannot be promoted because approval or validation was rejected."
    elif bool(gate.get("rollback_required")) or sandbox_result == "sandbox_failed":
        promotion_status = "promotion_blocked"
        promotion_reason = "Self-change cannot be promoted because rollback or sandbox failure was triggered."
    elif gate.get("gate_outcome") != "release_ready":
        promotion_status = "promotion_pending"
        promotion_reason = "Self-change remains pending until release-gate requirements are satisfied."
    elif sandbox_required and sandbox_result in {"sandbox_pending", "sandbox_running"}:
        promotion_status = "promotion_pending"
        promotion_reason = "Sandbox-required self-change remains pending until sandbox evaluation completes successfully."
        effective_release_lane = "experimental"
    elif sandbox_required and sandbox_result == "sandbox_rejected":
        promotion_status = "promotion_rejected"
        promotion_reason = "Sandbox-required self-change was rejected before promotion."
        effective_release_lane = "experimental"
    elif sandbox_required and sandbox_result == "sandbox_passed":
        if release_lane == "stable":
            promotion_status = "promoted_to_stable"
            promotion_reason = "Sandbox-passed self-change satisfied promotion criteria and was promoted to stable."
            effective_release_lane = "stable"
        elif requested_release_lane == "stable":
            promotion_status = "promotion_ready"
            promotion_reason = "Sandbox-passed risky self-change is promotion-ready but remains experimental until explicit stable promotion approval is present."
            effective_release_lane = "experimental"
        else:
            promotion_status = "kept_experimental"
            promotion_reason = "Sandbox-passed self-change satisfied release gating but remains in the experimental lane."
            effective_release_lane = "experimental"
    elif release_lane == "stable":
        promotion_status = "promoted_to_stable"
        promotion_reason = "Validated self-change satisfied promotion criteria and was promoted to stable."
        effective_release_lane = "stable"
    else:
        promotion_status = "kept_experimental"
        promotion_reason = "Validated self-change satisfied release gating and remains in the experimental lane."
        effective_release_lane = "experimental"

    if approval_required and not _is_approval_present(approval_status) and promotion_status not in {"promotion_rejected", "promotion_blocked"}:
        promotion_status = "promotion_pending"
        promotion_reason = "Promotion remains pending until required approval is present."

    sandbox_trace = {
        "sandbox_required": sandbox_required,
        "sandbox_status": sandbox_status,
        "sandbox_result": sandbox_result,
        "promotion_status": promotion_status,
        "promotion_reason": promotion_reason,
        "effective_release_lane": effective_release_lane,
    }
    governance_trace = {
        **dict(gate.get("governance_trace") or {}),
        "sandbox_promotion": sandbox_trace,
    }
    status = sandbox_status if sandbox_required and sandbox_result in {"sandbox_pending", "sandbox_running"} else promotion_status

    return {
        "status": status,
        "change_id": str(gate.get("change_id") or ""),
        "risk_level": risk_level,
        "protected_zone_hit": protected_zone_hit,
        "protected_zones": list(gate.get("protected_zones") or []),
        "release_lane": effective_release_lane,
        "sandbox_required": sandbox_required,
        "sandbox_status": sandbox_status,
        "sandbox_result": sandbox_result,
        "promotion_status": promotion_status,
        "promotion_reason": promotion_reason,
        "rollback_required": bool(gate.get("rollback_required")),
        "approval_required": approval_required,
        "approval_requirement": str(gate.get("approval_requirement") or ""),
        "approval_status": approval_status,
        "validation_outcome": str(gate.get("validation_outcome") or "pending"),
        "gate_outcome": str(gate.get("gate_outcome") or "allow_for_review"),
        "contract_status": str(gate.get("contract_status") or ""),
        "tests_status": str(gate.get("tests_status") or "pending"),
        "build_status": str(gate.get("build_status") or "pending"),
        "regression_status": str(gate.get("regression_status") or "pending"),
        "reason": str(gate.get("reason") or ""),
        "authority_trace": dict(gate.get("authority_trace") or {}),
        "governance_trace": governance_trace,
        "normalized_contract": normalized,
    }


def _build_candidate_comparison_evidence(
    *,
    normalized: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, Any]:
    governance_status = "blocked" if str(promotion.get("contract_status") or "") != "valid" else "approved"
    authority_trace = dict(promotion.get("authority_trace") or {})
    authority_status = str(authority_trace.get("authority_status") or "authorized").strip().lower()
    base = {
        "tests_status": str(promotion.get("tests_status") or normalized.get("tests_status") or "pending").strip().lower(),
        "build_status": str(promotion.get("build_status") or normalized.get("build_status") or "pending").strip().lower(),
        "regression_status": str(promotion.get("regression_status") or normalized.get("regression_status") or "pending").strip().lower(),
        "governance_status": governance_status,
        "governance_compatible": governance_status != "blocked",
        "authority_status": authority_status,
        "authority_compatible": authority_status not in {"denied", "blocked"},
    }
    return {
        **base,
        **dict(normalized.get("candidate_evidence") or {}),
    }


def _extract_comparison_value(dimension: str, evidence: dict[str, Any]) -> Any:
    if dimension == "tests":
        return evidence.get("tests_status") or evidence.get("tests")
    if dimension == "build":
        return evidence.get("build_status") or evidence.get("build")
    if dimension == "regressions":
        return evidence.get("regression_status") or evidence.get("regressions")
    if dimension == "governance":
        if "governance_compatible" in evidence:
            return evidence.get("governance_compatible")
        return evidence.get("governance_status") or evidence.get("governance")
    if dimension == "authority":
        if "authority_compatible" in evidence:
            return evidence.get("authority_compatible")
        return evidence.get("authority_status") or evidence.get("authority")
    return evidence.get(dimension)


def _comparison_value_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else -1.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _normalize_text(value).lower()
    mapping = {
        "passed": 1.0,
        "approved": 1.0,
        "authorized": 1.0,
        "compatible": 1.0,
        "true": 1.0,
        "not_required": 0.0,
        "optional": 0.0,
        "recommended": 0.0,
        "pending": 0.0,
        "review_required": 0.0,
        "approval_required": 0.0,
        "proposed": 0.0,
        "experimental": 0.0,
        "failed": -1.0,
        "rejected": -1.0,
        "denied": -1.0,
        "blocked": -1.0,
        "rollback_required": -1.0,
        "incompatible": -1.0,
        "false": -1.0,
    }
    return mapping.get(text)


def _confidence_band(level: float) -> str:
    if level >= 0.75:
        return "strong"
    if level >= 0.45:
        return "moderate"
    return "weak"


def evaluate_self_change_comparative_scoring(contract: dict[str, Any] | None) -> dict[str, Any]:
    promotion = evaluate_self_change_sandbox_promotion(contract)
    normalized = promotion["normalized_contract"]
    baseline_reference = str(normalized.get("baseline_reference") or "")
    candidate_reference = str(normalized.get("candidate_reference") or normalized.get("change_id") or "")
    baseline_evidence = dict(normalized.get("baseline_evidence") or {})
    candidate_evidence = _build_candidate_comparison_evidence(normalized=normalized, promotion=promotion)
    requested_dimensions = list(normalized.get("comparison_dimensions") or [])

    dimensions: list[str] = []
    if requested_dimensions:
        for dimension in requested_dimensions:
            if dimension not in dimensions:
                dimensions.append(dimension)
    else:
        for dimension in CORE_COMPARISON_DIMENSIONS:
            if _extract_comparison_value(dimension, baseline_evidence) not in (None, ""):
                dimensions.append(dimension)
        for dimension in candidate_evidence.keys():
            if dimension not in dimensions and dimension not in CORE_COMPARISON_DIMENSIONS:
                if _extract_comparison_value(dimension, baseline_evidence) not in (None, ""):
                    dimensions.append(dimension)

    observed_improvement: dict[str, Any] = {}
    observed_regression: dict[str, Any] = {}
    used_dimensions: list[str] = []
    net_score = 0.0

    for dimension in dimensions:
        baseline_value = _extract_comparison_value(dimension, baseline_evidence)
        candidate_value = _extract_comparison_value(dimension, candidate_evidence)
        baseline_score = _comparison_value_score(baseline_value)
        candidate_score = _comparison_value_score(candidate_value)
        if baseline_score is None or candidate_score is None:
            continue
        delta = round(candidate_score - baseline_score, 3)
        used_dimensions.append(dimension)
        net_score += delta
        if delta > 0:
            observed_improvement[dimension] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": delta,
            }
        elif delta < 0:
            observed_regression[dimension] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": delta,
            }

    evidence_count = len(used_dimensions)
    improvement_count = len(observed_improvement)
    regression_count = len(observed_regression)
    missing_references = not baseline_reference or not candidate_reference

    if missing_references or evidence_count == 0:
        confidence_level = 0.0
        confidence_band = "weak"
        promotion_confidence = "insufficient_evidence"
        recommendation = "hold_experimental"
        status = "insufficient_evidence"
        reason = "Comparative scoring requires explicit baseline/candidate references and usable evidence across at least one shared dimension."
    else:
        confidence_level = min(1.0, max(0.0, (evidence_count / 5.0) * 0.7))
        if net_score > 0:
            confidence_level += 0.2
        elif net_score == 0:
            confidence_level += 0.05
        else:
            confidence_level -= 0.25
        if improvement_count >= 3:
            confidence_level += 0.1
        elif improvement_count == 0:
            confidence_level -= 0.05
        if str(promotion.get("promotion_status") or "") in {"promoted_to_stable", "promotion_ready"}:
            confidence_level += 0.1
        elif str(promotion.get("promotion_status") or "") in {"promotion_pending", "promotion_blocked", "promotion_rejected"}:
            confidence_level -= 0.1
        if regression_count:
            confidence_level -= 0.25
        confidence_level = round(min(1.0, max(0.0, confidence_level)), 3)
        confidence_band = _confidence_band(confidence_level)

        if bool(promotion.get("rollback_required")):
            promotion_confidence = "regression_detected"
            recommendation = "rollback"
            status = "regression_detected"
            reason = "Comparative scoring detected a rollback-required self-change state."
        elif regression_count or net_score < 0:
            promotion_confidence = "regression_detected"
            recommendation = "reject"
            status = "regression_detected"
            reason = "Candidate evidence regressed relative to the baseline."
        elif confidence_band == "weak":
            promotion_confidence = "confidence_too_weak"
            recommendation = "hold_experimental"
            status = "confidence_too_weak"
            reason = "Comparative evidence is too weak to support broader promotion."
        elif str(promotion.get("promotion_status") or "") in {"promotion_rejected"}:
            promotion_confidence = "keep_experimental"
            recommendation = "reject"
            status = "keep_experimental"
            reason = "Comparative scoring completed, but governed promotion was rejected by earlier controls."
        elif confidence_band == "strong" and net_score > 0 and str(promotion.get("promotion_status") or "") in {"promoted_to_stable", "promotion_ready"}:
            promotion_confidence = "promote_ready"
            recommendation = "promote"
            status = "promote_ready"
            reason = "Candidate outperformed the baseline with strong confidence and satisfies governed promotion prerequisites."
        else:
            promotion_confidence = "keep_experimental"
            recommendation = "hold_experimental"
            status = "keep_experimental"
            reason = "Candidate evidence is positive but not strong enough for broader promotion beyond the experimental lane."

    comparison_trace = {
        "baseline_reference": baseline_reference,
        "candidate_reference": candidate_reference,
        "comparison_dimensions": used_dimensions,
        "observed_improvement": observed_improvement,
        "observed_regression": observed_regression,
        "net_score": round(net_score, 3),
        "confidence_level": confidence_level,
        "confidence_band": confidence_band,
        "promotion_confidence": promotion_confidence,
        "recommendation": recommendation,
    }
    governance_trace = {
        **dict(promotion.get("governance_trace") or {}),
        "comparative_scoring": comparison_trace,
    }

    return {
        "status": status if status in VALID_COMPARATIVE_SCORING_STATUSES else "scored",
        "change_id": str(promotion.get("change_id") or ""),
        "baseline_reference": baseline_reference,
        "candidate_reference": candidate_reference,
        "comparison_dimensions": used_dimensions,
        "observed_improvement": observed_improvement,
        "observed_regression": observed_regression,
        "net_score": round(net_score, 3),
        "confidence_level": confidence_level,
        "confidence_band": confidence_band,
        "promotion_confidence": promotion_confidence,
        "recommendation": recommendation,
        "reason": reason,
        "authority_trace": dict(promotion.get("authority_trace") or {}),
        "governance_trace": governance_trace,
        "promotion_status": str(promotion.get("promotion_status") or ""),
        "promotion_reason": str(promotion.get("promotion_reason") or ""),
        "release_lane": str(promotion.get("release_lane") or "experimental"),
        "sandbox_required": bool(promotion.get("sandbox_required")),
        "sandbox_status": str(promotion.get("sandbox_status") or "sandbox_pending"),
        "sandbox_result": str(promotion.get("sandbox_result") or "sandbox_pending"),
        "rollback_required": bool(promotion.get("rollback_required")),
        "risk_level": str(promotion.get("risk_level") or "medium_risk"),
        "protected_zone_hit": bool(promotion.get("protected_zone_hit")),
        "protected_zones": list(promotion.get("protected_zones") or []),
        "gate_outcome": str(promotion.get("gate_outcome") or "allow_for_review"),
        "approval_required": bool(promotion.get("approval_required")),
        "approval_requirement": str(promotion.get("approval_requirement") or ""),
        "approval_status": str(promotion.get("approval_status") or "optional"),
        "validation_outcome": str(promotion.get("validation_outcome") or "pending"),
        "tests_status": str(promotion.get("tests_status") or "pending"),
        "build_status": str(promotion.get("build_status") or "pending"),
        "regression_status": str(promotion.get("regression_status") or "pending"),
        "contract_status": str(promotion.get("contract_status") or ""),
        "normalized_contract": normalized,
    }


def build_self_change_audit_record(
    *,
    contract: dict[str, Any] | None,
    outcome_status: Any = None,
    approved_by: Any = None,
    approval_status: Any = None,
    outcome_summary: Any = None,
    validation_status: Any = None,
    build_status: Any = None,
    regression_status: Any = None,
    stable_state_ref: Any = None,
    release_lane: Any = None,
) -> dict[str, Any]:
    source_contract = dict(contract or {})
    if approval_status not in (None, ""):
        source_contract["approval_status"] = approval_status
    if validation_status not in (None, ""):
        source_contract["validation_outcome"] = validation_status
    if build_status not in (None, ""):
        source_contract["build_status"] = build_status
    if regression_status not in (None, ""):
        source_contract["regression_status"] = regression_status
    if release_lane not in (None, ""):
        source_contract["release_lane"] = release_lane
    if outcome_status not in (None, ""):
        source_contract["application_state"] = "failed" if _normalize_text(outcome_status).lower() in {"failed", "rolled_back"} else "proposed"

    scored = evaluate_self_change_comparative_scoring(source_contract)
    normalized = scored["normalized_contract"]
    success = str(outcome_status or "").strip().lower() in ("succeeded", "success", "completed", "approved")
    return {
        "change_id": str(normalized.get("change_id") or ""),
        "recorded_at": str((normalized.get("governance_trace") or {}).get("recorded_at") or ""),
        "target_files": list(normalized.get("target_files") or []),
        "change_type": str(normalized.get("change_type") or ""),
        "risk_level": str(scored.get("risk_level") or "medium_risk"),
        "protected_zones": list(scored.get("protected_zones") or []),
        "protected_zone_hit": bool(scored.get("protected_zone_hit")),
        "reason": str(normalized.get("reason") or ""),
        "expected_outcome": str(normalized.get("expected_outcome") or ""),
        "validation_plan": dict(normalized.get("validation_plan") or {}),
        "rollback_plan": dict(normalized.get("rollback_plan") or {}),
        "approval_requirement": str(scored.get("approval_requirement") or ""),
        "approval_required": bool(scored.get("approval_required")),
        "approval_status": _normalize_text(approval_status) or str(scored.get("approval_status") or ""),
        "approved_by": _normalize_text(approved_by),
        "outcome_status": _normalize_text(outcome_status) or "proposed",
        "outcome_summary": _normalize_text(outcome_summary),
        "validation_status": str(scored.get("validation_outcome") or "pending"),
        "build_status": str(scored.get("build_status") or "pending"),
        "regression_status": str(scored.get("regression_status") or "pending"),
        "gate_outcome": str(scored.get("gate_outcome") or "allow_for_review"),
        "release_lane": str(scored.get("release_lane") or "experimental"),
        "sandbox_required": bool(scored.get("sandbox_required")),
        "sandbox_status": str(scored.get("sandbox_status") or "sandbox_pending"),
        "sandbox_result": str(scored.get("sandbox_result") or "sandbox_pending"),
        "promotion_status": str(scored.get("promotion_status") or "promotion_pending"),
        "promotion_reason": str(scored.get("promotion_reason") or ""),
        "baseline_reference": str(scored.get("baseline_reference") or ""),
        "candidate_reference": str(scored.get("candidate_reference") or ""),
        "comparison_dimensions": list(scored.get("comparison_dimensions") or []),
        "observed_improvement": dict(scored.get("observed_improvement") or {}),
        "observed_regression": dict(scored.get("observed_regression") or {}),
        "net_score": _normalize_float(scored.get("net_score")),
        "confidence_level": _normalize_float(scored.get("confidence_level")),
        "confidence_band": str(scored.get("confidence_band") or "weak"),
        "comparison_status": str(scored.get("status") or "scored"),
        "promotion_confidence": str(scored.get("promotion_confidence") or "insufficient_evidence"),
        "recommendation": str(scored.get("recommendation") or "hold_experimental"),
        "comparison_reason": str(scored.get("reason") or ""),
        "rollback_required": bool(scored.get("rollback_required")),
        "validation_reasons": [str(scored.get("reason") or "")] if _normalize_text(scored.get("reason")) else [],
        "stable_state_ref": _normalize_text(stable_state_ref),
        "success": bool(success),
        "authority_trace": dict(scored.get("authority_trace") or {}),
        "governance_trace": dict(scored.get("governance_trace") or {}),
        "contract_status": str(scored.get("contract_status") or ""),
    }


def evaluate_self_change_governance_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_governance(contract)
    except Exception as e:
        return {
            "self_change_status": "blocked",
            "governance_status": "blocked",
            "approval_required": True,
            "approval_requirement": "mandatory",
            "risk_level": "high_risk",
            "protected_zones": [],
            "validation_required": True,
            "rollback_required": True,
            "contract_status": "invalid",
            "decision_reason": f"Self-change governance evaluation failed: {e}",
            "authority_trace": {},
            "governance_trace": {"self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION},
            "normalized_contract": normalize_self_change_contract(contract),
        }


def evaluate_self_change_release_gate_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_release_gate(contract)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        return {
            "status": "blocked",
            "change_id": str(normalized.get("change_id") or ""),
            "risk_level": str(normalized.get("risk_level") or "high_risk"),
            "protected_zone_hit": bool(normalized.get("protected_zones")),
            "protected_zones": list(normalized.get("protected_zones") or []),
            "validation_outcome": "pending",
            "gate_outcome": "blocked_missing_validation",
            "release_lane": "experimental",
            "rollback_required": False,
            "approval_required": True,
            "approval_requirement": str(normalized.get("approval_requirement") or "mandatory"),
            "approval_status": str(normalized.get("approval_status") or "pending"),
            "contract_status": "invalid",
            "tests_status": str(normalized.get("tests_status") or "pending"),
            "build_status": str(normalized.get("build_status") or "pending"),
            "regression_status": str(normalized.get("regression_status") or "pending"),
            "reason": f"Self-change release gating failed: {e}",
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "release_gate_error": str(e),
            },
            "normalized_contract": normalized,
        }


def evaluate_self_change_sandbox_promotion_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_sandbox_promotion(contract)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        risk_level = str(normalized.get("risk_level") or "high_risk")
        protected_zone_hit = bool(normalized.get("protected_zones"))
        sandbox_required = protected_zone_hit or risk_level == "high_risk"
        sandbox_status = "sandbox_pending" if sandbox_required else "sandbox_not_required"
        sandbox_result = sandbox_status
        return {
            "status": sandbox_status if sandbox_required else "promotion_blocked",
            "change_id": str(normalized.get("change_id") or ""),
            "risk_level": risk_level,
            "protected_zone_hit": protected_zone_hit,
            "protected_zones": list(normalized.get("protected_zones") or []),
            "release_lane": "experimental" if sandbox_required else str(normalized.get("release_lane") or "stable"),
            "sandbox_required": sandbox_required,
            "sandbox_status": sandbox_status,
            "sandbox_result": sandbox_result,
            "promotion_status": "promotion_blocked",
            "promotion_reason": f"Self-change sandbox/promotion evaluation failed: {e}",
            "rollback_required": bool(normalized.get("application_state") in {"attempted", "failed"}),
            "approval_required": VALID_APPROVAL_REQUIREMENTS.get(risk_level, "recommended") == "mandatory",
            "approval_requirement": VALID_APPROVAL_REQUIREMENTS.get(risk_level, "recommended"),
            "approval_status": str(normalized.get("approval_status") or "pending"),
            "validation_outcome": str(normalized.get("validation_outcome") or "pending"),
            "gate_outcome": "blocked_missing_validation",
            "contract_status": "invalid",
            "tests_status": str(normalized.get("tests_status") or "pending"),
            "build_status": str(normalized.get("build_status") or "pending"),
            "regression_status": str(normalized.get("regression_status") or "pending"),
            "reason": f"Self-change sandbox/promotion evaluation failed: {e}",
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "sandbox_promotion_error": str(e),
            },
            "normalized_contract": normalized,
        }


def evaluate_self_change_comparative_scoring_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_comparative_scoring(contract)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        candidate_reference = str(normalized.get("candidate_reference") or normalized.get("change_id") or "")
        return {
            "status": "insufficient_evidence",
            "change_id": str(normalized.get("change_id") or ""),
            "baseline_reference": str(normalized.get("baseline_reference") or ""),
            "candidate_reference": candidate_reference,
            "comparison_dimensions": [],
            "observed_improvement": {},
            "observed_regression": {},
            "net_score": 0.0,
            "confidence_level": 0.0,
            "confidence_band": "weak",
            "promotion_confidence": "insufficient_evidence",
            "recommendation": "hold_experimental",
            "reason": f"Self-change comparative scoring failed: {e}",
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "comparative_scoring_error": str(e),
            },
            "promotion_status": str(normalized.get("promotion_status") or "promotion_pending"),
            "promotion_reason": str(normalized.get("promotion_reason") or ""),
            "release_lane": str(normalized.get("release_lane") or "experimental"),
            "sandbox_required": bool(normalized.get("protected_zones") or str(normalized.get("risk_level") or "") == "high_risk"),
            "sandbox_status": str(normalized.get("sandbox_status") or "sandbox_pending"),
            "sandbox_result": str(normalized.get("sandbox_result") or "sandbox_pending"),
            "rollback_required": bool(normalized.get("application_state") in {"attempted", "failed"}),
            "risk_level": str(normalized.get("risk_level") or "high_risk"),
            "protected_zone_hit": bool(normalized.get("protected_zones")),
            "protected_zones": list(normalized.get("protected_zones") or []),
            "gate_outcome": "blocked_missing_validation",
            "approval_required": VALID_APPROVAL_REQUIREMENTS.get(str(normalized.get("risk_level") or "medium_risk"), "recommended") == "mandatory",
            "approval_requirement": str(normalized.get("approval_requirement") or "recommended"),
            "approval_status": str(normalized.get("approval_status") or "pending"),
            "validation_outcome": str(normalized.get("validation_outcome") or "pending"),
            "tests_status": str(normalized.get("tests_status") or "pending"),
            "build_status": str(normalized.get("build_status") or "pending"),
            "regression_status": str(normalized.get("regression_status") or "pending"),
            "contract_status": "invalid",
            "normalized_contract": normalized,
        }
