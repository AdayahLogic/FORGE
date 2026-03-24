"""
NEXUS self-evolution governance foundations.

Classifies proposed self-modifications, validates governed self-change
contracts, and resolves one shared release-gating outcome. This layer is
contract-only and does not execute modifications.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
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
VALID_MONITORING_STATUSES = {
    "pending_monitoring",
    "actively_monitored",
    "monitoring_passed",
    "monitoring_failed",
}
VALID_ROLLBACK_TRIGGER_OUTCOMES = {
    "no_action",
    "monitor_more",
    "rollback_recommended",
    "rollback_required",
}
VALID_STABLE_STATUSES = {
    "provisionally_stable",
    "stable_confirmed",
    "stable_degraded",
    "rollback_pending",
}
VALID_ROLLBACK_EXECUTION_STATUSES = {
    "rollback_pending",
    "rollback_approved",
    "rollback_blocked",
    "rollback_executing",
    "rollback_completed",
    "rollback_failed",
}
VALID_ROLLBACK_SCOPES = {
    "file_only",
    "component_only",
    "project_only",
    "protected_core_limited",
}
VALID_BLAST_RADIUS_LEVELS = {"low", "medium", "high"}
DEFAULT_ROLLBACK_SEQUENCE = ["validate", "approve", "execute", "verify"]
VALID_MUTATION_CONTROL_STATUSES = {
    "budget_available",
    "budget_exhausted",
    "mutation_rate_too_high",
    "cool_down_required",
    "protected_zone_throttled",
    "change_attempt_blocked",
}
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


def _normalize_monitoring_status(value: Any, *, default: str) -> str:
    status = _normalize_text(value).lower()
    return status if status in VALID_MONITORING_STATUSES else default


def _normalize_rollback_trigger_outcome(value: Any, *, default: str) -> str:
    outcome = _normalize_text(value).lower()
    return outcome if outcome in VALID_ROLLBACK_TRIGGER_OUTCOMES else default


def _normalize_stable_status(value: Any, *, default: str) -> str:
    status = _normalize_text(value).lower()
    return status if status in VALID_STABLE_STATUSES else default


def _normalize_rollback_scope(value: Any, *, default: str) -> str:
    scope = _normalize_text(value).lower()
    return scope if scope in VALID_ROLLBACK_SCOPES else default


def _normalize_blast_radius_level(value: Any, *, default: str) -> str:
    level = _normalize_text(value).lower()
    return level if level in VALID_BLAST_RADIUS_LEVELS else default


def _normalize_string_list(value: Any, *, limit: int = 50, lower: bool = False) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        normalized = _normalize_text(item)
        if lower:
            normalized = normalized.lower()
        if normalized and normalized not in out:
            out.append(normalized)
    return out[:limit]


def _normalize_rollback_sequence(value: Any) -> list[str]:
    sequence = _normalize_string_list(value, limit=10, lower=True)
    normalized: list[str] = []
    for step in sequence or DEFAULT_ROLLBACK_SEQUENCE:
        if step in {"validate", "approve", "execute", "verify"} and step not in normalized:
            normalized.append(step)
    return normalized or list(DEFAULT_ROLLBACK_SEQUENCE)


def _infer_rollback_scope(
    *,
    raw_scope: Any,
    target_files: list[str],
    target_components: list[str],
    protected_zones: list[str],
) -> str:
    explicit = _normalize_rollback_scope(raw_scope, default="")
    if explicit:
        return explicit
    if protected_zones:
        return "protected_core_limited"
    if target_components and not target_files:
        return "component_only"
    if len(target_files) > 1:
        return "project_only"
    return "file_only"


def _infer_blast_radius_level(
    *,
    raw_level: Any,
    rollback_scope: str,
    protected_zones: list[str],
    target_files: list[str],
    target_components: list[str],
) -> str:
    explicit = _normalize_blast_radius_level(raw_level, default="")
    if explicit:
        return explicit
    if protected_zones or rollback_scope == "protected_core_limited":
        return "high"
    if rollback_scope == "project_only" or len(target_components) > 1 or len(target_files) > 5:
        return "medium"
    return "low"


def _determine_rollback_approval_requirement(
    *,
    blast_radius_level: str,
    rollback_scope: str,
    protected_zones: list[str],
) -> bool:
    if protected_zones or rollback_scope == "protected_core_limited":
        return True
    return blast_radius_level in {"medium", "high"}


def _extract_project_roots(target_files: list[str]) -> list[str]:
    roots: list[str] = []
    for path in target_files:
        normalized = _normalize_path(path)
        if not normalized:
            continue
        parts = [part for part in normalized.split("/") if part]
        if len(parts) >= 2:
            root = "/".join(parts[:2])
        elif parts:
            root = parts[0]
        else:
            continue
        if root not in roots:
            roots.append(root)
    return roots


def _resolve_component_targets(components: list[str]) -> list[str]:
    resolved: list[str] = []
    component_set = {component.lower() for component in components if component}
    for zone_name, patterns in PROTECTED_CORE_ZONES.items():
        normalized_zone_name = zone_name.lower()
        if normalized_zone_name in component_set:
            for pattern in patterns:
                normalized = _normalize_text(pattern)
                if normalized and normalized not in resolved:
                    resolved.append(normalized)
    return resolved


def _is_path_within_scope(
    path: str,
    *,
    rollback_scope: str,
    allowed_files: list[str],
    allowed_components: list[str],
    protected_zones: list[str],
    project_roots: list[str],
) -> bool:
    normalized_path = _normalize_path(path)
    if not normalized_path:
        return False
    allowed_file_paths = {_normalize_path(item) for item in allowed_files if _normalize_text(item)}
    component_patterns = {_normalize_path(item) for item in _resolve_component_targets(allowed_components)}
    protected_patterns = {
        _normalize_path(pattern)
        for zone_name, patterns in PROTECTED_CORE_ZONES.items()
        if zone_name in protected_zones
        for pattern in patterns
    }

    if rollback_scope == "file_only":
        return normalized_path in allowed_file_paths
    if rollback_scope == "component_only":
        return any(pattern and pattern in normalized_path for pattern in component_patterns)
    if rollback_scope == "project_only":
        return any(root and normalized_path.startswith(root) for root in project_roots)
    if rollback_scope == "protected_core_limited":
        return any(pattern and pattern in normalized_path for pattern in protected_patterns)
    return False


def _normalize_follow_up_validation_required(value: Any, *, blast_radius_level: str, approval_required: bool) -> bool:
    if value is None:
        return approval_required or blast_radius_level in {"medium", "high"}
    return bool(value)


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _resolve_budget_window(value: Any) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    if isinstance(value, dict):
        start = _parse_datetime(value.get("window_start"))
        end = _parse_datetime(value.get("window_end"))
        current_window_id = _normalize_text(value.get("current_window_id"))
        if start and end and end >= start:
            return {
                "current_window_id": current_window_id or start.strftime("window-%Y%m%d"),
                "window_start": _iso_utc(start),
                "window_end": _iso_utc(end),
            }
    anchor = now
    start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return {
        "current_window_id": start.strftime("window-%Y%m%d"),
        "window_start": _iso_utc(start),
        "window_end": _iso_utc(end),
    }


def _derive_budget_window(raw: dict[str, Any]) -> dict[str, str]:
    explicit = _resolve_budget_window(raw.get("budgeting_window"))
    if explicit:
        return explicit
    return _resolve_budget_window(None)


def _budget_limit_for_change(*, risk_level: str, protected_zone_hit: bool) -> int:
    base = {"low_risk": 5, "medium_risk": 3, "high_risk": 2}.get(risk_level, 3)
    if protected_zone_hit:
        return min(base, 1 if risk_level == "high_risk" else 2)
    return base


def _failure_limit_for_change(*, risk_level: str, protected_zone_hit: bool) -> int:
    if protected_zone_hit or risk_level == "high_risk":
        return 1
    return 2 if risk_level == "medium_risk" else 3


def _rollback_limit_for_change(*, risk_level: str, protected_zone_hit: bool) -> int:
    if protected_zone_hit:
        return 1
    return 1 if risk_level in {"medium_risk", "high_risk"} else 2


def _protected_zone_attempt_limit(*, risk_level: str) -> int:
    return 1 if risk_level == "high_risk" else 2


def _entry_within_budget_window(entry: dict[str, Any], budgeting_window: dict[str, str]) -> bool:
    recorded_at = _parse_datetime(entry.get("recorded_at"))
    if recorded_at is None:
        recorded_at = _parse_datetime((entry.get("governance_trace") or {}).get("recorded_at"))
    start = _parse_datetime(budgeting_window.get("window_start"))
    end = _parse_datetime(budgeting_window.get("window_end"))
    if recorded_at is None or start is None or end is None:
        return False
    return start <= recorded_at < end


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
    rollback_target_files = _normalize_target_files(raw.get("rollback_target_files") or raw.get("target_files"))
    rollback_target_components = _normalize_string_list(raw.get("rollback_target_components"), limit=20, lower=True)
    protected_zones = list(classification.get("protected_zones") or [])
    rollback_scope = _infer_rollback_scope(
        raw_scope=raw.get("rollback_scope"),
        target_files=rollback_target_files,
        target_components=rollback_target_components,
        protected_zones=protected_zones,
    )
    blast_radius_level = _infer_blast_radius_level(
        raw_level=raw.get("blast_radius_level"),
        rollback_scope=rollback_scope,
        protected_zones=protected_zones,
        target_files=rollback_target_files,
        target_components=rollback_target_components,
    )
    rollback_approval_required = _determine_rollback_approval_requirement(
        blast_radius_level=blast_radius_level,
        rollback_scope=rollback_scope,
        protected_zones=protected_zones,
    )
    rollback_status = _normalize_text(raw.get("rollback_status")).lower()
    if rollback_status not in VALID_ROLLBACK_EXECUTION_STATUSES:
        rollback_status = "rollback_pending"
    rollback_sequence = _normalize_rollback_sequence(raw.get("rollback_sequence"))
    budgeting_window = _derive_budget_window(raw)
    mutation_rate_status = _normalize_text(raw.get("mutation_rate_status")).lower() or "within_budget"
    control_outcome = _normalize_text(raw.get("control_outcome")).lower() or "budget_available"
    if control_outcome not in VALID_MUTATION_CONTROL_STATUSES:
        control_outcome = "budget_available"

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
        "protected_zones": protected_zones,
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
        "promoted_at": _normalize_text(raw.get("promoted_at")),
        "monitoring_window": _normalize_text(raw.get("monitoring_window")) or "observation_window",
        "observation_count": max(0, int(raw.get("observation_count") or 0)),
        "health_signals": _normalize_evidence(raw.get("health_signals")),
        "monitoring_status": _normalize_monitoring_status(
            raw.get("monitoring_status"),
            default="pending_monitoring",
        ),
        "rollback_trigger_outcome": _normalize_rollback_trigger_outcome(
            raw.get("rollback_trigger_outcome"),
            default="monitor_more",
        ),
        "stable_status": _normalize_stable_status(
            raw.get("stable_status"),
            default="provisionally_stable",
        ),
        "rollback_id": _normalize_text(raw.get("rollback_id")),
        "rollback_scope": rollback_scope,
        "rollback_target_files": rollback_target_files,
        "rollback_target_components": rollback_target_components,
        "blast_radius_level": blast_radius_level,
        "rollback_status": rollback_status,
        "rollback_result": _normalize_text(raw.get("rollback_result")),
        "rollback_execution_eligible": bool(raw.get("rollback_execution_eligible", False)),
        "rollback_reason": _normalize_text(raw.get("rollback_reason")),
        "rollback_approval_required": rollback_approval_required,
        "rollback_sequence": rollback_sequence,
        "rollback_sequence_completed": _normalize_string_list(raw.get("rollback_sequence_completed"), limit=10, lower=True),
        "rollback_follow_up_validation_required": _normalize_follow_up_validation_required(
            raw.get("rollback_follow_up_validation_required"),
            blast_radius_level=blast_radius_level,
            approval_required=rollback_approval_required,
        ),
        "rollback_validation_status": _normalize_text(raw.get("rollback_validation_status")).lower() or "pending",
        "budgeting_window": budgeting_window,
        "attempted_changes_in_window": max(0, int(raw.get("attempted_changes_in_window") or 0)),
        "successful_changes_in_window": max(0, int(raw.get("successful_changes_in_window") or 0)),
        "failed_changes_in_window": max(0, int(raw.get("failed_changes_in_window") or 0)),
        "rollbacks_in_window": max(0, int(raw.get("rollbacks_in_window") or 0)),
        "protected_zone_changes_in_window": max(0, int(raw.get("protected_zone_changes_in_window") or 0)),
        "mutation_rate_status": mutation_rate_status,
        "budget_remaining": int(raw.get("budget_remaining") or 0),
        "cool_down_required": bool(raw.get("cool_down_required")),
        "control_outcome": control_outcome,
        "budget_reason": _normalize_text(raw.get("budget_reason")),
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


def evaluate_self_change_post_promotion_monitoring(contract: dict[str, Any] | None) -> dict[str, Any]:
    scored = evaluate_self_change_comparative_scoring(contract)
    normalized = scored["normalized_contract"]
    promoted_at = str(normalized.get("promoted_at") or "")
    monitoring_window = str(normalized.get("monitoring_window") or "observation_window")
    observation_count = max(0, int(normalized.get("observation_count") or 0))
    base_health_signals = dict(normalized.get("health_signals") or {})
    protected_zone_hit = bool(scored.get("protected_zone_hit"))

    health_signals = {
        "tests_healthy": str(scored.get("tests_status") or "pending") == "passed",
        "build_healthy": str(scored.get("build_status") or "pending") == "passed",
        "regressions_healthy": str(scored.get("regression_status") or "pending") == "passed",
        "protected_zone_healthy": not protected_zone_hit or not bool(base_health_signals.get("protected_zone_degraded")),
        "comparative_health": str(scored.get("promotion_confidence") or "") not in {"regression_detected", "confidence_too_weak"},
        "comparison_degraded": bool(base_health_signals.get("comparison_degraded")),
        **base_health_signals,
    }
    regression_detected = bool(
        scored.get("rollback_required")
        or base_health_signals.get("regression_detected")
        or base_health_signals.get("comparison_degraded")
        or not bool(health_signals.get("regressions_healthy"))
    )
    build_degraded = not bool(health_signals.get("build_healthy"))
    tests_degraded = not bool(health_signals.get("tests_healthy"))
    protected_zone_degraded = protected_zone_hit and not bool(health_signals.get("protected_zone_healthy"))
    monitoring_failure = regression_detected or build_degraded or tests_degraded or protected_zone_degraded
    promoted = bool(promoted_at) or str(scored.get("promotion_status") or "") == "promoted_to_stable"

    if not promoted:
        monitoring_status = "pending_monitoring"
        status = "pending_monitoring"
        rollback_trigger_outcome = "monitor_more"
        stable_status = "provisionally_stable"
        rollback_triggered = False
        rollback_reason = "Post-promotion monitoring is pending until the self-change reaches a promoted state."
    elif monitoring_failure:
        monitoring_status = "monitoring_failed"
        rollback_trigger_outcome = "rollback_required" if protected_zone_degraded or regression_detected or build_degraded else "rollback_recommended"
        rollback_triggered = rollback_trigger_outcome in {"rollback_recommended", "rollback_required"}
        stable_status = "rollback_pending" if rollback_trigger_outcome == "rollback_required" else "stable_degraded"
        status = rollback_trigger_outcome
        if protected_zone_degraded:
            rollback_reason = "Protected-zone post-promotion monitoring detected degraded behavior."
        elif regression_detected:
            rollback_reason = "Post-promotion monitoring detected regression after promotion."
        elif build_degraded:
            rollback_reason = "Post-promotion monitoring detected build degradation after promotion."
        else:
            rollback_reason = "Post-promotion monitoring detected degraded health signals."
    elif observation_count <= 0:
        monitoring_status = "pending_monitoring"
        status = "pending_monitoring"
        rollback_trigger_outcome = "monitor_more"
        rollback_triggered = False
        stable_status = "provisionally_stable"
        rollback_reason = "Promoted self-change is awaiting initial post-promotion observations."
    elif observation_count < 3:
        monitoring_status = "actively_monitored"
        status = "actively_monitored"
        rollback_trigger_outcome = "monitor_more"
        rollback_triggered = False
        stable_status = "provisionally_stable"
        rollback_reason = "Promoted self-change remains under post-promotion monitoring."
    else:
        monitoring_status = "monitoring_passed"
        status = "no_action"
        rollback_trigger_outcome = "no_action"
        rollback_triggered = False
        stable_status = "stable_confirmed"
        rollback_reason = "Promoted self-change remained healthy throughout the monitoring window."

    monitoring_trace = {
        "promoted_at": promoted_at,
        "monitoring_window": monitoring_window,
        "monitoring_status": monitoring_status,
        "observation_count": observation_count,
        "health_signals": health_signals,
        "regression_detected": regression_detected,
        "rollback_triggered": rollback_triggered,
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "rollback_reason": rollback_reason,
        "stable_status": stable_status,
    }
    governance_trace = {
        **dict(scored.get("governance_trace") or {}),
        "post_promotion_monitoring": monitoring_trace,
    }

    return {
        "status": status,
        "change_id": str(scored.get("change_id") or ""),
        "promoted_at": promoted_at,
        "monitoring_window": monitoring_window,
        "monitoring_status": monitoring_status,
        "observation_count": observation_count,
        "health_signals": health_signals,
        "regression_detected": regression_detected,
        "rollback_triggered": rollback_triggered,
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "rollback_reason": rollback_reason,
        "stable_status": stable_status,
        "authority_trace": dict(scored.get("authority_trace") or {}),
        "governance_trace": governance_trace,
        "baseline_reference": str(scored.get("baseline_reference") or ""),
        "candidate_reference": str(scored.get("candidate_reference") or ""),
        "comparison_dimensions": list(scored.get("comparison_dimensions") or []),
        "observed_improvement": dict(scored.get("observed_improvement") or {}),
        "observed_regression": dict(scored.get("observed_regression") or {}),
        "net_score": _normalize_float(scored.get("net_score")),
        "confidence_level": _normalize_float(scored.get("confidence_level")),
        "confidence_band": str(scored.get("confidence_band") or "weak"),
        "comparison_status": str(scored.get("status") or "insufficient_evidence"),
        "promotion_confidence": str(scored.get("promotion_confidence") or "insufficient_evidence"),
        "recommendation": str(scored.get("recommendation") or "hold_experimental"),
        "reason": str(scored.get("reason") or ""),
        "promotion_status": str(scored.get("promotion_status") or ""),
        "promotion_reason": str(scored.get("promotion_reason") or ""),
        "release_lane": str(scored.get("release_lane") or "experimental"),
        "sandbox_required": bool(scored.get("sandbox_required")),
        "sandbox_status": str(scored.get("sandbox_status") or "sandbox_pending"),
        "sandbox_result": str(scored.get("sandbox_result") or "sandbox_pending"),
        "rollback_required": bool(scored.get("rollback_required")) or rollback_trigger_outcome == "rollback_required",
        "risk_level": str(scored.get("risk_level") or "medium_risk"),
        "protected_zone_hit": protected_zone_hit,
        "protected_zones": list(scored.get("protected_zones") or []),
        "gate_outcome": str(scored.get("gate_outcome") or "allow_for_review"),
        "approval_required": bool(scored.get("approval_required")),
        "approval_requirement": str(scored.get("approval_requirement") or ""),
        "approval_status": str(scored.get("approval_status") or "optional"),
        "validation_outcome": str(scored.get("validation_outcome") or "pending"),
        "tests_status": str(scored.get("tests_status") or "pending"),
        "build_status": str(scored.get("build_status") or "pending"),
        "regression_status": str(scored.get("regression_status") or "pending"),
        "contract_status": str(scored.get("contract_status") or ""),
        "normalized_contract": normalized,
    }


def evaluate_self_change_rollback_execution(contract: dict[str, Any] | None) -> dict[str, Any]:
    monitored = evaluate_self_change_post_promotion_monitoring(contract)
    normalized = monitored["normalized_contract"]
    rollback_id = str(normalized.get("rollback_id") or f"rollback-{uuid.uuid4().hex[:12]}")
    rollback_scope = str(normalized.get("rollback_scope") or "file_only")
    rollback_target_files = list(normalized.get("rollback_target_files") or [])
    rollback_target_components = list(normalized.get("rollback_target_components") or [])
    protected_zones = list(monitored.get("protected_zones") or [])
    blast_radius_level = str(normalized.get("blast_radius_level") or "low")
    rollback_reason = str(normalized.get("rollback_reason") or monitored.get("rollback_reason") or "")
    approval_status = str(normalized.get("approval_status") or monitored.get("approval_status") or "optional").lower()
    rollback_approval_required = bool(normalized.get("rollback_approval_required"))
    rollback_sequence = list(normalized.get("rollback_sequence") or DEFAULT_ROLLBACK_SEQUENCE)
    project_roots = _extract_project_roots(rollback_target_files)

    rollback_trigger_outcome = str(monitored.get("rollback_trigger_outcome") or "monitor_more")
    rollback_required = bool(monitored.get("rollback_required"))
    governance_trace = {
        **dict(monitored.get("governance_trace") or {}),
    }
    authority_trace = dict(monitored.get("authority_trace") or {})

    if rollback_trigger_outcome not in {"rollback_recommended", "rollback_required"} and not rollback_required:
        status = "rollback_blocked"
        rollback_result = "Rollback execution is not eligible because no governed rollback trigger is active."
        sequence_completed = ["validate"]
        rollback_execution_eligible = False
    else:
        rollback_execution_eligible = True
        status = "rollback_pending"
        rollback_result = "Rollback execution remains pending governed validation."
        sequence_completed = ["validate"]

    scope_expansion_detected = False
    scope_expansion_details: list[str] = []
    for candidate in rollback_target_files:
        if not _is_path_within_scope(
            candidate,
            rollback_scope=rollback_scope,
            allowed_files=rollback_target_files,
            allowed_components=rollback_target_components,
            protected_zones=protected_zones,
            project_roots=project_roots,
        ):
            scope_expansion_detected = True
            scope_expansion_details.append(candidate)

    if rollback_scope == "component_only" and not rollback_target_components:
        scope_expansion_detected = True
        scope_expansion_details.append("missing rollback_target_components")
    if rollback_scope == "file_only" and len(rollback_target_files) != 1:
        scope_expansion_detected = True
        scope_expansion_details.append("file_only scope requires exactly one rollback target file")
    if rollback_scope == "protected_core_limited" and not protected_zones:
        scope_expansion_detected = True
        scope_expansion_details.append("missing protected_zones")

    if scope_expansion_detected:
        status = "rollback_blocked"
        rollback_result = "Rollback scope expansion was denied."
        rollback_execution_eligible = False
        rollback_reason = rollback_reason or "Rollback attempted to exceed its declared governed scope."

    approval_satisfied = approval_status in {"approved", "optional", "not_required"}
    if rollback_approval_required and approval_status != "approved":
        status = "rollback_blocked"
        rollback_result = "Rollback approval is required before execution can proceed."
        rollback_execution_eligible = rollback_execution_eligible and not scope_expansion_detected
    elif rollback_execution_eligible and not scope_expansion_detected:
        if blast_radius_level == "low":
            status = "rollback_approved"
            rollback_result = "Rollback is eligible for governed execution within its bounded scope."
            sequence_completed = ["validate", "approve"]
        elif approval_satisfied:
            status = "rollback_approved"
            rollback_result = "Rollback received required approval and is ready for governed execution."
            sequence_completed = ["validate", "approve"]

    rollback_validation_status = str(normalized.get("rollback_validation_status") or "pending").lower()
    if rollback_execution_eligible and not scope_expansion_detected and (
        (blast_radius_level == "low" and not rollback_approval_required) or approval_status == "approved"
    ):
        status = "rollback_completed"
        rollback_result = "Rollback completed within its governed scope."
        sequence_completed = list(rollback_sequence)
        rollback_validation_status = "required" if bool(normalized.get("rollback_follow_up_validation_required")) else "not_required"
    elif rollback_execution_eligible and status == "rollback_approved":
        status = "rollback_approved"

    if status == "rollback_completed":
        governance_trace["rollback_execution"] = {
            "rollback_id": rollback_id,
            "rollback_scope": rollback_scope,
            "rollback_target_files": rollback_target_files,
            "rollback_target_components": rollback_target_components,
            "blast_radius_level": blast_radius_level,
            "rollback_trigger_outcome": rollback_trigger_outcome,
            "rollback_follow_up_validation_required": bool(normalized.get("rollback_follow_up_validation_required")),
            "rollback_validation_status": rollback_validation_status,
            "rollback_sequence": rollback_sequence,
            "rollback_sequence_completed": sequence_completed,
            "scope_expansion_detected": False,
        }
    else:
        governance_trace["rollback_execution"] = {
            "rollback_id": rollback_id,
            "rollback_scope": rollback_scope,
            "rollback_target_files": rollback_target_files,
            "rollback_target_components": rollback_target_components,
            "blast_radius_level": blast_radius_level,
            "rollback_trigger_outcome": rollback_trigger_outcome,
            "rollback_follow_up_validation_required": bool(normalized.get("rollback_follow_up_validation_required")),
            "rollback_validation_status": rollback_validation_status,
            "rollback_sequence": rollback_sequence,
            "rollback_sequence_completed": sequence_completed,
            "scope_expansion_detected": scope_expansion_detected,
            "scope_expansion_details": scope_expansion_details,
        }

    return {
        "status": status,
        "change_id": str(monitored.get("change_id") or ""),
        "rollback_id": rollback_id,
        "rollback_scope": rollback_scope,
        "rollback_target_files": rollback_target_files,
        "rollback_target_components": rollback_target_components,
        "blast_radius_level": blast_radius_level,
        "rollback_status": status,
        "rollback_reason": rollback_reason,
        "rollback_approval_required": rollback_approval_required,
        "rollback_sequence": rollback_sequence,
        "rollback_result": rollback_result,
        "rollback_execution_eligible": rollback_execution_eligible,
        "rollback_follow_up_validation_required": bool(normalized.get("rollback_follow_up_validation_required")),
        "rollback_validation_status": rollback_validation_status,
        "rollback_triggered": bool(monitored.get("rollback_triggered")),
        "rollback_trigger_outcome": rollback_trigger_outcome,
        "approval_status": approval_status,
        "protected_zone_hit": bool(monitored.get("protected_zone_hit")),
        "protected_zones": protected_zones,
        "authority_trace": authority_trace,
        "governance_trace": governance_trace,
        "normalized_contract": normalized,
    }


def evaluate_self_change_mutation_budget(
    contract: dict[str, Any] | None,
    recent_audit_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    governed = evaluate_self_change_governance(contract)
    normalized = governed["normalized_contract"]
    budgeting_window = dict(normalized.get("budgeting_window") or _derive_budget_window(normalized))
    risk_level = str(normalized.get("risk_level") or "medium_risk")
    protected_zone_hit = bool(normalized.get("protected_zones"))
    entries = [dict(entry) for entry in (recent_audit_entries or []) if isinstance(entry, dict)]
    window_entries = [entry for entry in entries if _entry_within_budget_window(entry, budgeting_window)]

    attempted_changes_in_window = len(window_entries) + 1
    successful_changes_in_window = sum(1 for entry in window_entries if bool(entry.get("success")))
    failed_changes_in_window = sum(
        1
        for entry in window_entries
        if str(entry.get("outcome_status") or "").strip().lower() in {"failed", "reverted", "blocked", "error"}
    )
    rollbacks_in_window = sum(
        1
        for entry in window_entries
        if bool(entry.get("rollback_required"))
        or str(entry.get("rollback_status") or "").strip().lower() in {"rollback_completed", "rollback_failed"}
        or str(entry.get("rollback_trigger_outcome") or "").strip().lower() in {"rollback_recommended", "rollback_required"}
    )
    protected_zone_changes_in_window = sum(1 for entry in window_entries if bool(entry.get("protected_zone_hit")))
    if protected_zone_hit:
        protected_zone_changes_in_window += 1

    budget_limit = _budget_limit_for_change(risk_level=risk_level, protected_zone_hit=protected_zone_hit)
    failure_limit = _failure_limit_for_change(risk_level=risk_level, protected_zone_hit=protected_zone_hit)
    rollback_limit = _rollback_limit_for_change(risk_level=risk_level, protected_zone_hit=protected_zone_hit)
    protected_limit = _protected_zone_attempt_limit(risk_level=risk_level)
    observed_failures = failed_changes_in_window + (
        1 if str(normalized.get("application_state") or "").lower() == "failed" else 0
    )
    observed_rollbacks = rollbacks_in_window + (
        1 if str(normalized.get("rollback_status") or "").lower() in {"rollback_completed", "rollback_failed"} else 0
    )

    status = "budget_available"
    mutation_rate_status = "within_budget"
    cool_down_required = False
    reason = "Self-change mutation budget is available for the current window."

    if protected_zone_hit and protected_zone_changes_in_window > protected_limit:
        status = "protected_zone_throttled"
        mutation_rate_status = "protected_zone_pressure"
        cool_down_required = True
        reason = "Protected-core mutation frequency exceeded the governed window limit."
    elif observed_failures >= failure_limit or observed_rollbacks >= rollback_limit:
        status = "cool_down_required"
        mutation_rate_status = "cool_down"
        cool_down_required = True
        reason = "Recent failures or rollbacks require a cool-down before more self-change attempts."
    elif attempted_changes_in_window > budget_limit + 1:
        status = "change_attempt_blocked"
        mutation_rate_status = "blocked"
        cool_down_required = True
        reason = "Mutation pressure is too high for another self-change attempt in the current window."
    elif attempted_changes_in_window > budget_limit:
        status = "budget_exhausted"
        mutation_rate_status = "budget_exhausted"
        reason = "The self-change budget for the current window has been exhausted."
    elif attempted_changes_in_window == budget_limit and (
        protected_zone_hit or failed_changes_in_window > 0 or rollbacks_in_window > 0 or risk_level == "high_risk"
    ):
        status = "mutation_rate_too_high"
        mutation_rate_status = "high"
        cool_down_required = protected_zone_hit or risk_level == "high_risk"
        reason = "Mutation pressure reached a governed high-water mark for this window."
    elif attempted_changes_in_window >= max(1, budget_limit - 1):
        mutation_rate_status = "elevated"
        reason = "Self-change remains within budget but is approaching the governed mutation limit."

    budget_remaining = max(0, budget_limit - attempted_changes_in_window)
    control_outcome = status
    governance_trace = {
        **dict(governed.get("governance_trace") or {}),
        "change_budgeting": {
            "budgeting_window": budgeting_window,
            "budget_limit": budget_limit,
            "failure_limit": failure_limit,
            "rollback_limit": rollback_limit,
            "protected_zone_limit": protected_limit,
            "attempted_changes_in_window": attempted_changes_in_window,
            "successful_changes_in_window": successful_changes_in_window,
            "failed_changes_in_window": failed_changes_in_window,
            "rollbacks_in_window": rollbacks_in_window,
            "protected_zone_changes_in_window": protected_zone_changes_in_window,
            "mutation_rate_status": mutation_rate_status,
            "budget_remaining": budget_remaining,
            "cool_down_required": cool_down_required,
            "control_outcome": control_outcome,
        },
    }

    return {
        "status": status,
        "change_id": str(normalized.get("change_id") or ""),
        "risk_level": risk_level,
        "protected_zone_hit": protected_zone_hit,
        "budgeting_window": budgeting_window,
        "attempted_changes_in_window": attempted_changes_in_window,
        "successful_changes_in_window": successful_changes_in_window,
        "failed_changes_in_window": failed_changes_in_window,
        "rollbacks_in_window": rollbacks_in_window,
        "protected_zone_changes_in_window": protected_zone_changes_in_window,
        "mutation_rate_status": mutation_rate_status,
        "budget_remaining": budget_remaining,
        "cool_down_required": cool_down_required,
        "control_outcome": control_outcome,
        "reason": reason,
        "authority_trace": dict(governed.get("authority_trace") or {}),
        "governance_trace": governance_trace,
        "normalized_contract": normalized,
    }


def build_self_change_audit_record(
    *,
    contract: dict[str, Any] | None,
    recent_audit_entries: list[dict[str, Any]] | None = None,
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

    monitored = evaluate_self_change_post_promotion_monitoring(source_contract)
    rollback_execution = evaluate_self_change_rollback_execution(source_contract)
    mutation_budget = evaluate_self_change_mutation_budget(source_contract, recent_audit_entries=recent_audit_entries)
    normalized = monitored["normalized_contract"]
    success = str(outcome_status or "").strip().lower() in ("succeeded", "success", "completed", "approved")
    return {
        "change_id": str(normalized.get("change_id") or ""),
        "recorded_at": str((normalized.get("governance_trace") or {}).get("recorded_at") or ""),
        "target_files": list(normalized.get("target_files") or []),
        "change_type": str(normalized.get("change_type") or ""),
        "risk_level": str(monitored.get("risk_level") or "medium_risk"),
        "protected_zones": list(monitored.get("protected_zones") or []),
        "protected_zone_hit": bool(monitored.get("protected_zone_hit")),
        "reason": str(normalized.get("reason") or ""),
        "expected_outcome": str(normalized.get("expected_outcome") or ""),
        "validation_plan": dict(normalized.get("validation_plan") or {}),
        "rollback_plan": dict(normalized.get("rollback_plan") or {}),
        "approval_requirement": str(monitored.get("approval_requirement") or ""),
        "approval_required": bool(monitored.get("approval_required")),
        "approval_status": _normalize_text(approval_status) or str(monitored.get("approval_status") or ""),
        "approved_by": _normalize_text(approved_by),
        "outcome_status": _normalize_text(outcome_status) or "proposed",
        "outcome_summary": _normalize_text(outcome_summary),
        "validation_status": str(monitored.get("validation_outcome") or "pending"),
        "build_status": str(monitored.get("build_status") or "pending"),
        "regression_status": str(monitored.get("regression_status") or "pending"),
        "gate_outcome": str(monitored.get("gate_outcome") or "allow_for_review"),
        "release_lane": str(monitored.get("release_lane") or "experimental"),
        "sandbox_required": bool(monitored.get("sandbox_required")),
        "sandbox_status": str(monitored.get("sandbox_status") or "sandbox_pending"),
        "sandbox_result": str(monitored.get("sandbox_result") or "sandbox_pending"),
        "promotion_status": str(monitored.get("promotion_status") or "promotion_pending"),
        "promotion_reason": str(monitored.get("promotion_reason") or ""),
        "baseline_reference": str(monitored.get("baseline_reference") or ""),
        "candidate_reference": str(monitored.get("candidate_reference") or ""),
        "comparison_dimensions": list(monitored.get("comparison_dimensions") or []),
        "observed_improvement": dict(monitored.get("observed_improvement") or {}),
        "observed_regression": dict(monitored.get("observed_regression") or {}),
        "net_score": _normalize_float(monitored.get("net_score")),
        "confidence_level": _normalize_float(monitored.get("confidence_level")),
        "confidence_band": str(monitored.get("confidence_band") or "weak"),
        "comparison_status": str(monitored.get("comparison_status") or "scored"),
        "promotion_confidence": str(monitored.get("promotion_confidence") or "insufficient_evidence"),
        "recommendation": str(monitored.get("recommendation") or "hold_experimental"),
        "comparison_reason": str(monitored.get("reason") or ""),
        "promoted_at": str(monitored.get("promoted_at") or ""),
        "monitoring_window": str(monitored.get("monitoring_window") or "observation_window"),
        "monitoring_status": str(monitored.get("monitoring_status") or "pending_monitoring"),
        "observation_count": max(0, int(monitored.get("observation_count") or 0)),
        "health_signals": dict(monitored.get("health_signals") or {}),
        "regression_detected": bool(monitored.get("regression_detected")),
        "rollback_triggered": bool(monitored.get("rollback_triggered")),
        "rollback_trigger_outcome": str(monitored.get("rollback_trigger_outcome") or "monitor_more"),
        "rollback_reason": str(monitored.get("rollback_reason") or ""),
        "stable_status": str(monitored.get("stable_status") or "provisionally_stable"),
        "rollback_required": bool(monitored.get("rollback_required")),
        "rollback_id": str(rollback_execution.get("rollback_id") or normalized.get("rollback_id") or ""),
        "rollback_scope": str(rollback_execution.get("rollback_scope") or normalized.get("rollback_scope") or "file_only"),
        "rollback_target_files": list(rollback_execution.get("rollback_target_files") or normalized.get("rollback_target_files") or []),
        "rollback_target_components": list(
            rollback_execution.get("rollback_target_components") or normalized.get("rollback_target_components") or []
        ),
        "blast_radius_level": str(rollback_execution.get("blast_radius_level") or normalized.get("blast_radius_level") or "low"),
        "rollback_status": str(rollback_execution.get("rollback_status") or "rollback_pending"),
        "rollback_result": str(rollback_execution.get("rollback_result") or ""),
        "rollback_execution_eligible": bool(rollback_execution.get("rollback_execution_eligible")),
        "rollback_approval_required": bool(rollback_execution.get("rollback_approval_required")),
        "rollback_sequence": list(rollback_execution.get("rollback_sequence") or normalized.get("rollback_sequence") or []),
        "rollback_follow_up_validation_required": bool(
            rollback_execution.get("rollback_follow_up_validation_required")
            or normalized.get("rollback_follow_up_validation_required")
        ),
        "rollback_validation_status": str(
            rollback_execution.get("rollback_validation_status") or normalized.get("rollback_validation_status") or "pending"
        ),
        "budgeting_window": dict(mutation_budget.get("budgeting_window") or normalized.get("budgeting_window") or {}),
        "attempted_changes_in_window": int(mutation_budget.get("attempted_changes_in_window") or 0),
        "successful_changes_in_window": int(mutation_budget.get("successful_changes_in_window") or 0),
        "failed_changes_in_window": int(mutation_budget.get("failed_changes_in_window") or 0),
        "rollbacks_in_window": int(mutation_budget.get("rollbacks_in_window") or 0),
        "protected_zone_changes_in_window": int(mutation_budget.get("protected_zone_changes_in_window") or 0),
        "mutation_rate_status": str(mutation_budget.get("mutation_rate_status") or normalized.get("mutation_rate_status") or "within_budget"),
        "budget_remaining": int(mutation_budget.get("budget_remaining") or 0),
        "cool_down_required": bool(mutation_budget.get("cool_down_required")),
        "control_outcome": str(mutation_budget.get("control_outcome") or normalized.get("control_outcome") or "budget_available"),
        "budget_reason": str(mutation_budget.get("reason") or normalized.get("budget_reason") or ""),
        "validation_reasons": [str(monitored.get("reason") or "")] if _normalize_text(monitored.get("reason")) else [],
        "stable_state_ref": _normalize_text(stable_state_ref),
        "success": bool(success),
        "authority_trace": dict(rollback_execution.get("authority_trace") or monitored.get("authority_trace") or {}),
        "governance_trace": {
            **dict(rollback_execution.get("governance_trace") or monitored.get("governance_trace") or {}),
            **({"change_budgeting": dict((mutation_budget.get("governance_trace") or {}).get("change_budgeting") or {})} if mutation_budget.get("governance_trace") else {}),
        },
        "contract_status": str(monitored.get("contract_status") or ""),
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


def evaluate_self_change_post_promotion_monitoring_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_post_promotion_monitoring(contract)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        return {
            "status": "pending_monitoring",
            "change_id": str(normalized.get("change_id") or ""),
            "promoted_at": str(normalized.get("promoted_at") or ""),
            "monitoring_window": str(normalized.get("monitoring_window") or "observation_window"),
            "monitoring_status": "pending_monitoring",
            "observation_count": 0,
            "health_signals": {},
            "regression_detected": False,
            "rollback_triggered": False,
            "rollback_trigger_outcome": "monitor_more",
            "rollback_reason": f"Self-change post-promotion monitoring failed: {e}",
            "stable_status": "provisionally_stable",
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "post_promotion_monitoring_error": str(e),
            },
            "baseline_reference": str(normalized.get("baseline_reference") or ""),
            "candidate_reference": str(normalized.get("candidate_reference") or normalized.get("change_id") or ""),
            "comparison_dimensions": list(normalized.get("comparison_dimensions") or []),
            "observed_improvement": {},
            "observed_regression": {},
            "net_score": 0.0,
            "confidence_level": 0.0,
            "confidence_band": "weak",
            "comparison_status": "insufficient_evidence",
            "promotion_confidence": "insufficient_evidence",
            "recommendation": "hold_experimental",
            "reason": f"Self-change post-promotion monitoring failed: {e}",
            "promotion_status": str(normalized.get("promotion_status") or "promotion_pending"),
            "promotion_reason": str(normalized.get("promotion_reason") or ""),
            "release_lane": str(normalized.get("release_lane") or "experimental"),
            "sandbox_required": bool(normalized.get("protected_zones") or str(normalized.get("risk_level") or "") == "high_risk"),
            "sandbox_status": str(normalized.get("sandbox_status") or "sandbox_pending"),
            "sandbox_result": str(normalized.get("sandbox_result") or "sandbox_pending"),
            "rollback_required": False,
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


def evaluate_self_change_rollback_execution_safe(contract: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return evaluate_self_change_rollback_execution(contract)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        rollback_id = str(normalized.get("rollback_id") or "")
        return {
            "status": "rollback_failed",
            "change_id": str(normalized.get("change_id") or ""),
            "rollback_id": rollback_id,
            "rollback_scope": str(normalized.get("rollback_scope") or "file_only"),
            "rollback_target_files": list(normalized.get("rollback_target_files") or []),
            "rollback_target_components": list(normalized.get("rollback_target_components") or []),
            "blast_radius_level": str(normalized.get("blast_radius_level") or "high"),
            "rollback_status": "rollback_failed",
            "rollback_reason": str(normalized.get("rollback_reason") or f"Rollback execution failed: {e}"),
            "rollback_approval_required": bool(normalized.get("rollback_approval_required", True)),
            "rollback_sequence": list(normalized.get("rollback_sequence") or DEFAULT_ROLLBACK_SEQUENCE),
            "rollback_result": f"Rollback execution failed: {e}",
            "rollback_execution_eligible": False,
            "rollback_follow_up_validation_required": bool(normalized.get("rollback_follow_up_validation_required")),
            "rollback_validation_status": str(normalized.get("rollback_validation_status") or "pending"),
            "rollback_triggered": False,
            "rollback_trigger_outcome": str(normalized.get("rollback_trigger_outcome") or "monitor_more"),
            "approval_status": str(normalized.get("approval_status") or "pending"),
            "protected_zone_hit": bool(normalized.get("protected_zones")),
            "protected_zones": list(normalized.get("protected_zones") or []),
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "rollback_execution_error": str(e),
            },
            "normalized_contract": normalized,
        }


def evaluate_self_change_mutation_budget_safe(
    contract: dict[str, Any] | None,
    recent_audit_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        return evaluate_self_change_mutation_budget(contract, recent_audit_entries=recent_audit_entries)
    except Exception as e:
        normalized = normalize_self_change_contract(contract)
        budgeting_window = dict(normalized.get("budgeting_window") or _derive_budget_window(normalized))
        return {
            "status": "change_attempt_blocked",
            "change_id": str(normalized.get("change_id") or ""),
            "risk_level": str(normalized.get("risk_level") or "high_risk"),
            "protected_zone_hit": bool(normalized.get("protected_zones")),
            "budgeting_window": budgeting_window,
            "attempted_changes_in_window": 0,
            "successful_changes_in_window": 0,
            "failed_changes_in_window": 0,
            "rollbacks_in_window": 0,
            "protected_zone_changes_in_window": 0,
            "mutation_rate_status": "blocked",
            "budget_remaining": 0,
            "cool_down_required": True,
            "control_outcome": "change_attempt_blocked",
            "reason": f"Self-change mutation budgeting failed: {e}",
            "authority_trace": dict(normalized.get("authority_trace") or {}),
            "governance_trace": {
                **dict(normalized.get("governance_trace") or {}),
                "self_evolution_governance_version": SELF_EVOLUTION_GOVERNANCE_VERSION,
                "change_budgeting_error": str(e),
            },
            "normalized_contract": normalized,
        }
