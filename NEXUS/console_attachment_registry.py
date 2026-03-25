"""
Governed Forge Console attachment registry.

Attachments are project-scoped artifacts for intake and review surfaces.
They are never treated as execution, routing, approval, or governance authority.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from NEXUS.autonomy_modes import get_mode_policy, normalize_autonomy_mode
from NEXUS.budget_controls import (
    evaluate_budget_controls,
    resolve_budget_caps,
    summarize_journal_estimated_costs,
)
from NEXUS.execution_package_registry import list_execution_package_journal_entries
from NEXUS.model_routing_policy import resolve_model_routing_policy_safe
from NEXUS.operator_quick_actions import build_intake_preview_quick_actions
from NEXUS.path_utils import to_studio_relative_path
from NEXUS.project_state import ensure_state_folder, load_project_state


MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".csv",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".html",
    ".xml",
}
DOCUMENT_EXTENSIONS = {".pdf"}
QUARANTINE_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".ps1",
    ".msi",
    ".com",
    ".scr",
    ".jar",
    ".sh",
}

DEFAULT_REQUESTED_ARTIFACTS = [
    "implementation_plan",
    "code_artifacts",
    "tests",
    "review_package",
    "summary_report",
]
REQUESTED_ARTIFACT_LABELS = {
    "implementation_plan": "Implementation Plan",
    "code_artifacts": "Code Artifacts",
    "tests": "Tests",
    "review_package": "Review Package",
    "summary_report": "Summary / Report",
    "implementation_summary": "Implementation Summary",
    "test_report": "Test Report",
    "diff_review": "Diff Review",
    "approved_summary": "Approved Summary",
}
REQUIRED_CONSTRAINT_SECTIONS = (
    "scope_boundaries",
    "output_expectations",
    "review_expectations",
)
REQUIRED_LEAD_INTAKE_FIELDS = (
    "contact_name",
    "contact_email",
    "company_name",
    "problem_summary",
)
LEAD_QUALIFICATION_REQUIRED_FIELDS = (
    "budget_band",
    "urgency",
    "problem_clarity",
    "decision_readiness",
)
DEFAULT_LEAD_QUALIFICATION = {
    "budget_band": "",
    "urgency": "",
    "problem_clarity": "",
    "decision_readiness": "",
    "fit_notes": "",
}
HIGH_TOUCH_COMPLEXITY_TERMS = (
    "multi-team",
    "multi team",
    "compliance",
    "regulated",
    "legacy",
    "migration",
    "critical",
    "security",
    "integration",
    "enterprise",
)
HIGH_RISK_ROUTING_TERMS = (
    "security",
    "regulated",
    "compliance",
    "critical",
    "high_risk",
    "legal",
    "privacy",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _build_cost_tracking(*, cost_source: str, estimated_tokens: int, model: str) -> dict[str, Any]:
    tokens = max(0, int(estimated_tokens or 0))
    estimated_cost = round((tokens / 1000.0) * 0.004, 6)
    return {
        "cost_estimate": estimated_cost,
        "cost_unit": "usd_estimated",
        "cost_source": str(cost_source or "composed_operation"),
        "cost_breakdown": {
            "model": str(model or "forge_preview_cost_estimator"),
            "estimated_tokens": tokens,
            "estimated_cost": estimated_cost,
        },
    }


def _estimate_preview_cost(
    *,
    request_kind: str,
    objective: str,
    project_context: str,
    constraints: list[str],
    requested_artifacts: list[str],
    linked_attachment_count: int,
    warnings_count: int,
    lead_profile: dict[str, str],
) -> dict[str, Any]:
    text_len = (
        len(str(objective or ""))
        + len(str(project_context or ""))
        + sum(len(str(item or "")) for item in constraints)
        + sum(len(str(item or "")) for item in requested_artifacts)
        + sum(len(str(value or "")) for value in lead_profile.values())
    )
    base_tokens = 140 + int(text_len / 4)
    base_tokens += linked_attachment_count * 45
    base_tokens += warnings_count * 20
    if str(request_kind or "").strip().lower() == "lead_intake":
        base_tokens += 90
    return _build_cost_tracking(
        cost_source="model_execution",
        estimated_tokens=base_tokens,
        model="forge_intake_preview_estimator",
    )


def _attachment_root(project_path: str) -> Path:
    root = ensure_state_folder(project_path) / "console_attachments"
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    return root


def _metadata_path(project_path: str) -> Path:
    return _attachment_root(project_path) / "attachments.json"


def _raw_storage_path(project_path: str, attachment_id: str, file_name: str) -> Path:
    safe_name = Path(file_name or "attachment.bin").name
    return _attachment_root(project_path) / "raw" / f"{attachment_id}_{safe_name}"


def _load_records(project_path: str) -> list[dict[str, Any]]:
    path = _metadata_path(project_path)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _save_records(project_path: str, records: list[dict[str, Any]]) -> None:
    _metadata_path(project_path).write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_summary(file_path: Path, extension: str) -> str:
    if extension in DOCUMENT_EXTENSIONS:
        return "Binary document stored for governed review. Text extraction is deferred in phase 1."
    if extension not in TEXT_EXTENSIONS:
        return ""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "Text attachment uploaded with no extractable preview content."
    summary = " ".join(lines[:4]).strip()
    return summary[:280]


def _classify_attachment(
    *,
    file_name: str,
    file_type: str,
    file_size: int,
) -> tuple[str, str, list[str], str]:
    extension = Path(file_name).suffix.lower()
    file_type_lower = str(file_type or "").strip().lower()
    if file_size > MAX_ATTACHMENT_BYTES:
        return (
            "denied",
            "size_limit_exceeded",
            [],
            "Attachment denied because it exceeded the governed console size limit.",
        )
    if extension in QUARANTINE_EXTENSIONS:
        return (
            "quarantined",
            "high_risk_executable",
            ["console_review"],
            "Attachment quarantined because executable or script formats cannot be trusted for intake.",
        )
    if extension in TEXT_EXTENSIONS or extension in DOCUMENT_EXTENSIONS:
        return (
            "classified",
            "supported_review_artifact",
            ["console_review", "request_preview"],
            "Attachment classified for console review and request preview only.",
        )
    if file_type_lower.startswith("text/"):
        return (
            "classified",
            "supported_text_artifact",
            ["console_review", "request_preview"],
            "Attachment classified from text media type for console review and request preview only.",
        )
    return (
        "quarantined",
        "unsupported_format",
        ["console_review"],
        "Attachment quarantined because the format is unsupported for downstream use in phase 1.",
    )


def ingest_console_attachment(
    *,
    project_path: str,
    project_id: str,
    file_path: str,
    file_name: str,
    file_type: str,
    source: str,
    purpose: str,
    package_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    raw_path = Path(file_path)
    if not raw_path.exists():
        return {
            "status": "error",
            "reason": "Attachment source file not found.",
            "attachment": {},
        }

    attachment_id = f"att-{uuid.uuid4().hex[:12]}"
    file_size = raw_path.stat().st_size
    status, classification, allowed_consumers, reason = _classify_attachment(
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
    )
    storage_path = ""
    if status in {"classified", "quarantined"}:
        destination = _raw_storage_path(project_path, attachment_id, file_name)
        shutil.copy2(raw_path, destination)
        storage_path = str(destination)

    extracted_summary = _read_summary(raw_path, Path(file_name).suffix.lower()) if status == "classified" else ""
    record = {
        "attachment_id": attachment_id,
        "project_id": project_id,
        "package_id": str(package_id or ""),
        "request_id": str(request_id or ""),
        "linked_context": {
            "project_id": project_id,
            "package_id": str(package_id or ""),
            "request_id": str(request_id or ""),
        },
        "file_name": Path(file_name or raw_path.name).name,
        "file_type": str(file_type or "application/octet-stream"),
        "file_size_bytes": file_size,
        "source": str(source or "console_upload"),
        "purpose": str(purpose or "supporting_context"),
        "uploaded_at": _now(),
        "trust_level": "untrusted",
        "allowed_consumers": allowed_consumers,
        "extracted_summary": extracted_summary,
        "status": status,
        "classification": classification,
        "status_reason": reason,
        "raw_storage_path": to_studio_relative_path(storage_path) or storage_path,
        "governance_trace": {
            "origin": "forge_console",
            "surface": "project_intake_panel",
            "classification_reason": reason,
            "classifier_version": "phase1",
            "routing_authority": "nexus_only",
            "execution_authority": "package_governance_only",
            "notes": [
                "Attachment is read-only by default.",
                "Attachment cannot trigger execution or routing.",
                "Extracted summary is separate from raw file storage.",
            ],
        },
    }
    records = _load_records(project_path)
    records.append(record)
    records.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    _save_records(project_path, records)
    return {
        "status": "ok" if status != "denied" else "error",
        "reason": reason,
        "attachment": record,
    }


def ingest_console_attachment_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return ingest_console_attachment(**kwargs)
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"Attachment ingestion failed: {exc}",
            "attachment": {},
        }


def list_console_attachments(project_path: str) -> list[dict[str, Any]]:
    return _load_records(project_path)


def list_console_attachments_safe(project_path: str) -> list[dict[str, Any]]:
    try:
        return list_console_attachments(project_path)
    except Exception:
        return []


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _empty_constraint_sections() -> dict[str, list[str]]:
    return {
        "scope_boundaries": [],
        "risk_notes": [],
        "runtime_preferences": [],
        "output_expectations": [],
        "review_expectations": [],
    }


def _empty_lead_intake_profile() -> dict[str, str]:
    return {
        "contact_name": "",
        "contact_email": "",
        "company_name": "",
        "contact_channel": "",
        "lead_source": "",
        "problem_summary": "",
        "requested_outcome": "",
        "budget_context": "",
        "urgency_context": "",
    }


def _normalize_lead_intake_profile(value: Any) -> dict[str, str]:
    normalized = _empty_lead_intake_profile()
    if not isinstance(value, dict):
        return normalized
    for key in normalized:
        normalized[key] = str(value.get(key) or "").strip()
    return normalized


def _lead_intake_missing_fields(value: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_LEAD_INTAKE_FIELDS:
        if not str(value.get(key) or "").strip():
            missing.append(f"lead_{key}")
    return missing


def _normalize_constraint_sections(value: Any) -> dict[str, list[str]]:
    normalized = _empty_constraint_sections()
    if isinstance(value, dict):
        for key in normalized:
            normalized[key] = _clean_text_list(value.get(key))
        return normalized
    flat_constraints = _clean_text_list(value)
    if flat_constraints:
        normalized["scope_boundaries"] = flat_constraints
    return normalized


def _flatten_constraint_sections(value: dict[str, list[str]]) -> list[str]:
    ordered_keys = [
        ("scope_boundaries", "Scope"),
        ("risk_notes", "Risk"),
        ("runtime_preferences", "Runtime"),
        ("output_expectations", "Output"),
        ("review_expectations", "Review"),
    ]
    flattened: list[str] = []
    for key, label in ordered_keys:
        for item in value.get(key) or []:
            text = str(item or "").strip()
            if text:
                flattened.append(f"{label}: {text}")
    return flattened


def _normalize_requested_artifacts(value: Any) -> dict[str, list[str]]:
    normalized = {
        "selected": [],
        "custom": [],
    }
    if isinstance(value, dict):
        normalized["selected"] = _clean_text_list(value.get("selected"))
        normalized["custom"] = _clean_text_list(value.get("custom"))
        return normalized
    normalized["selected"] = _clean_text_list(value)
    return normalized


def _artifact_label(artifact_id: str) -> str:
    key = str(artifact_id or "").strip()
    if not key:
        return ""
    return REQUESTED_ARTIFACT_LABELS.get(key, key.replace("_", " ").title())


def _requested_artifact_details(value: dict[str, list[str]]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for item in value.get("selected") or []:
        details.append(
            {
                "artifact_id": item,
                "label": _artifact_label(item),
                "source": "catalog",
            }
        )
    for item in value.get("custom") or []:
        details.append(
            {
                "artifact_id": item,
                "label": item,
                "source": "custom",
            }
        )
    return details


def _flatten_requested_artifacts(value: dict[str, list[str]]) -> list[str]:
    return [item["artifact_id"] for item in _requested_artifact_details(value)]


def _autonomy_mode_detail(mode: Any) -> dict[str, str]:
    normalized = normalize_autonomy_mode(mode)
    policy = get_mode_policy(normalized)
    posture_map = {
        "supervised_build": "Operator review at key progression points.",
        "assisted_autopilot": "Forge may continue within bounded guardrails and escalates when governance or risk requires it.",
        "low_risk_autonomous_development": "Forge may continue only through explicitly low-risk development loops and stops on ambiguity or elevated risk.",
    }
    return {
        "mode": normalized,
        "label": normalized.replace("_", " "),
        "summary": str(policy.get("autonomy_mode_reason") or ""),
        "operator_posture": posture_map.get(normalized, "Governed operator oversight remains required."),
    }


def _normalize_request_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"update_request", "create_request", "lead_intake"}:
        return normalized
    return "update_request"


def _default_lead_qualification() -> dict[str, str]:
    return dict(DEFAULT_LEAD_QUALIFICATION)


def _normalize_lead_qualification(value: Any) -> dict[str, str]:
    normalized = _default_lead_qualification()
    if not isinstance(value, dict):
        return normalized
    for key in normalized:
        normalized[key] = str(value.get(key) or "").strip().lower()
    return normalized


def _score_budget_band(value: str) -> int:
    mapping = {
        "none": 0,
        "unknown": 0,
        "very_low": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "enterprise": 4,
    }
    return mapping.get(str(value or "").strip().lower(), 0)


def _score_urgency(value: str) -> int:
    mapping = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }
    return mapping.get(str(value or "").strip().lower(), 0)


def _score_problem_clarity(value: str) -> int:
    mapping = {
        "unclear": 0,
        "partial": 1,
        "clear": 2,
        "very_clear": 3,
    }
    return mapping.get(str(value or "").strip().lower(), 0)


def _score_decision_readiness(value: str) -> int:
    mapping = {
        "exploring": 0,
        "evaluating": 1,
        "ready": 2,
        "committed": 3,
    }
    return mapping.get(str(value or "").strip().lower(), 0)


def _build_lead_qualification_summary(value: Any) -> dict[str, Any]:
    signals = _normalize_lead_qualification(value)
    missing_fields = [field for field in LEAD_QUALIFICATION_REQUIRED_FIELDS if not signals.get(field)]
    if missing_fields:
        return {
            "qualification_status": "needs_more_info",
            "qualification_signals": {
                "budget_band": signals["budget_band"],
                "urgency": signals["urgency"],
                "problem_clarity": signals["problem_clarity"],
                "decision_readiness": signals["decision_readiness"],
            },
            "missing_qualification_fields": missing_fields,
            "lead_readiness_level": "incomplete",
            "qualification_reasoning_summary": (
                "Lead qualification is incomplete. Populate budget band, urgency, "
                "problem clarity, and decision readiness to assess lead readiness."
            ),
        }

    budget_score = _score_budget_band(signals["budget_band"])
    urgency_score = _score_urgency(signals["urgency"])
    clarity_score = _score_problem_clarity(signals["problem_clarity"])
    decision_score = _score_decision_readiness(signals["decision_readiness"])
    total = budget_score + urgency_score + clarity_score + decision_score

    if urgency_score >= 2 and decision_score >= 2 and clarity_score >= 2 and budget_score >= 1:
        status = "high_priority"
        readiness = "expedite"
    elif decision_score <= 0 or clarity_score <= 0 or total <= 3:
        status = "underqualified"
        readiness = "low"
    else:
        status = "qualified"
        readiness = "ready"

    return {
        "qualification_status": status,
        "qualification_signals": {
            "budget_band": signals["budget_band"],
            "urgency": signals["urgency"],
            "problem_clarity": signals["problem_clarity"],
            "decision_readiness": signals["decision_readiness"],
        },
        "missing_qualification_fields": [],
        "lead_readiness_level": readiness,
        "qualification_reasoning_summary": (
            f"Lead qualification assessed as {status}. "
            f"Signals: budget={signals['budget_band']}, urgency={signals['urgency']}, "
            f"clarity={signals['problem_clarity']}, decision readiness={signals['decision_readiness']}."
        ),
    }


def _contains_any_term(*, text: str, terms: tuple[str, ...]) -> bool:
    haystack = str(text or "").strip().lower()
    if not haystack:
        return False
    return any(term in haystack for term in terms)


def _estimate_offer_complexity_band(
    *,
    lead_profile: dict[str, str],
    qualification_signals: dict[str, str],
) -> str:
    budget = str(qualification_signals.get("budget_band") or "").strip().lower()
    urgency = str(qualification_signals.get("urgency") or "").strip().lower()
    clarity = str(qualification_signals.get("problem_clarity") or "").strip().lower()
    decision = str(qualification_signals.get("decision_readiness") or "").strip().lower()
    profile_text = " ".join(
        [
            str(lead_profile.get("problem_summary") or ""),
            str(lead_profile.get("requested_outcome") or ""),
            str(lead_profile.get("budget_context") or ""),
            str(lead_profile.get("urgency_context") or ""),
        ]
    )
    if budget == "enterprise" or urgency == "critical":
        return "high"
    if _contains_any_term(text=profile_text, terms=HIGH_TOUCH_COMPLEXITY_TERMS):
        return "high"
    if budget == "high" and urgency in {"high", "critical"}:
        return "medium_high"
    if clarity in {"clear", "very_clear"} and decision in {"ready", "committed"}:
        return "medium"
    return "low_to_medium"


def _pricing_direction_from_budget(budget_band: str) -> str:
    budget = str(budget_band or "").strip().lower()
    mapping = {
        "enterprise": "enterprise_retainer_direction",
        "high": "premium_project_direction",
        "medium": "standard_project_direction",
        "low": "discovery_first_direction",
        "very_low": "discovery_first_direction",
        "none": "discovery_first_direction",
        "unknown": "qualification_required",
    }
    return mapping.get(budget, "qualification_required")


def _build_revenue_offer_summary(
    *,
    lead_profile: dict[str, str],
    qualification: dict[str, str],
    qualification_summary: dict[str, Any],
) -> dict[str, Any]:
    qualification_status = str(qualification_summary.get("qualification_status") or "").strip().lower()
    qualification_signals = dict(qualification_summary.get("qualification_signals") or {})
    missing_qualification_fields = [
        str(item) for item in list(qualification_summary.get("missing_qualification_fields") or []) if str(item).strip()
    ]
    intake_missing = _lead_intake_missing_fields(lead_profile)
    complexity_band = _estimate_offer_complexity_band(
        lead_profile=lead_profile,
        qualification_signals={
            "budget_band": str(qualification_signals.get("budget_band") or ""),
            "urgency": str(qualification_signals.get("urgency") or ""),
            "problem_clarity": str(qualification_signals.get("problem_clarity") or ""),
            "decision_readiness": str(qualification_signals.get("decision_readiness") or ""),
        },
    )
    pricing_direction = _pricing_direction_from_budget(str(qualification_signals.get("budget_band") or ""))
    notes: list[str] = [
        "Preview-only revenue framing. This does not create packages, route work, or trigger execution.",
    ]
    if intake_missing:
        notes.append("Lead profile still has required missing fields before a governed offer can be trusted.")
    if missing_qualification_fields:
        notes.append("Qualification inputs are incomplete; fill required qualification fields for stronger offer confidence.")

    if missing_qualification_fields:
        return {
            "offer_status": "no_offer_yet",
            "recommended_service_type": "intake_qualification",
            "recommended_package_tier": "undetermined",
            "estimated_complexity_band": "undetermined",
            "pricing_direction": "qualification_required",
            "offer_reasoning_summary": (
                "Offer generation is deferred because qualification is not yet usable. "
                "Complete required qualification fields first."
            ),
            "offer_constraints_or_notes": notes,
        }

    fit_notes = str(qualification.get("fit_notes") or "")
    complexity_text = " ".join(
        [
            str(lead_profile.get("problem_summary") or ""),
            str(lead_profile.get("requested_outcome") or ""),
            fit_notes,
        ]
    )
    high_touch = (
        qualification_status == "high_priority"
        and complexity_band in {"high", "medium_high"}
    ) or _contains_any_term(text=complexity_text, terms=HIGH_TOUCH_COMPLEXITY_TERMS)
    if high_touch:
        notes.append("Recommend human-led scope review before pricing commitments due to complexity or risk.")
        return {
            "offer_status": "high_touch_review_recommended",
            "recommended_service_type": "advisory_plus_delivery",
            "recommended_package_tier": "enterprise",
            "estimated_complexity_band": complexity_band,
            "pricing_direction": pricing_direction,
            "offer_reasoning_summary": (
                "Signals suggest elevated complexity or risk. Route this lead through high-touch review to "
                "shape final scope and pricing direction."
            ),
            "offer_constraints_or_notes": notes,
        }

    if qualification_status == "underqualified":
        notes.append("Use a scoped discovery conversation before proposing a larger implementation package.")
        return {
            "offer_status": "offer_needs_more_info",
            "recommended_service_type": "discovery_workshop",
            "recommended_package_tier": "starter",
            "estimated_complexity_band": complexity_band,
            "pricing_direction": pricing_direction,
            "offer_reasoning_summary": (
                "Lead signals are present but underqualified for a confident implementation offer. "
                "Recommend discovery-first framing and collect additional fit details."
            ),
            "offer_constraints_or_notes": notes,
        }

    tier = "growth" if complexity_band in {"low_to_medium", "medium"} else "scale"
    service_type = "rapid_delivery_sprint" if qualification_status == "high_priority" else "governed_implementation"
    return {
        "offer_status": "offer_ready",
        "recommended_service_type": service_type,
        "recommended_package_tier": tier,
        "estimated_complexity_band": complexity_band,
        "pricing_direction": pricing_direction,
        "offer_reasoning_summary": (
            "Lead intake and qualification are sufficient for preview-safe offer framing. "
            "Recommended service and tier reflect current readiness and complexity signals."
        ),
        "offer_constraints_or_notes": notes,
    }


def _response_tone_for_offer(*, offer_status: str, urgency: str) -> str:
    normalized_offer_status = str(offer_status or "").strip().lower()
    normalized_urgency = str(urgency or "").strip().lower()
    if normalized_offer_status == "high_touch_review_recommended":
        return "consultative"
    if normalized_urgency in {"low", "medium"}:
        return "friendly"
    return "professional"


def _build_revenue_response_summary(
    *,
    lead_profile: dict[str, str],
    qualification_summary: dict[str, Any],
    offer_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    qualification_status = str(qualification_summary.get("qualification_status") or "").strip().lower()
    offer = dict(offer_summary or {})
    offer_status = str(offer.get("offer_status") or "").strip().lower()
    contact_name = str(lead_profile.get("contact_name") or "").strip()
    company_name = str(lead_profile.get("company_name") or "").strip()
    problem_summary = str(lead_profile.get("problem_summary") or "").strip()
    requested_outcome = str(lead_profile.get("requested_outcome") or "").strip()
    missing_lead_fields = _lead_intake_missing_fields(lead_profile)
    urgency = str((qualification_summary.get("qualification_signals") or {}).get("urgency") or "")
    tone = _response_tone_for_offer(offer_status=offer_status, urgency=urgency)
    constraints = [
        "Draft response only. This is not sent externally.",
        "No execution, routing, or package creation is triggered by this draft.",
    ]
    if missing_lead_fields:
        constraints.append("Lead profile still has missing required fields.")

    if qualification_status == "needs_more_info" or not offer_status or offer_status == "no_offer_yet":
        return {
            "response_status": "no_response",
            "response_tone": tone,
            "response_message": "",
            "response_summary": (
                "Response drafting is deferred until qualification and offer framing are ready."
            ),
            "response_constraints": constraints,
        }

    if missing_lead_fields or offer_status == "offer_needs_more_info":
        missing_bits = []
        if missing_lead_fields:
            missing_bits.append("lead profile details")
        if offer_status == "offer_needs_more_info":
            missing_bits.append("offer inputs")
        missing_label = " and ".join(missing_bits) if missing_bits else "key details"
        return {
            "response_status": "needs_more_info",
            "response_tone": tone,
            "response_message": (
                f"Thanks for sharing this context{f', {contact_name}' if contact_name else ''}. "
                "We understand the core challenge and are preparing a tailored recommendation. "
                f"Before we finalize a formal response, we need a bit more clarity on {missing_label}. "
                "Once those details are confirmed, we can provide a more precise next-step proposal."
            ),
            "response_summary": (
                "A draft response exists, but additional information is needed before it is fully ready."
            ),
            "response_constraints": constraints,
        }

    if offer_status == "high_touch_review_recommended":
        constraints.append("High-touch review is recommended before any external commitments.")
        return {
            "response_status": "high_touch_required",
            "response_tone": tone,
            "response_message": (
                f"Thank you{f' {contact_name}' if contact_name else ''} for outlining your goals"
                f"{f' at {company_name}' if company_name else ''}. "
                "Based on the complexity and risk signals in your request, our recommended next step is a high-touch "
                "scoping review so we can align on boundaries, priorities, and delivery posture. "
                "After that review, we can share a refined implementation direction and commercial framing."
            ),
            "response_summary": (
                "Complexity is elevated, so the draft response recommends high-touch review before final offer messaging."
            ),
            "response_constraints": constraints,
        }

    recommended_service_type = str(offer.get("recommended_service_type") or "governed_implementation")
    recommended_tier = str(offer.get("recommended_package_tier") or "growth")
    pricing_direction = str(offer.get("pricing_direction") or "standard_project_direction")
    response_body = (
        f"Thank you{f' {contact_name}' if contact_name else ''} for sharing your request"
        f"{f' for {company_name}' if company_name else ''}. "
        f"We understand the core problem: {problem_summary or 'you need a governed implementation path that reduces delivery risk'}. "
        f"Based on your intake and qualification signals, our current draft direction is a {recommended_service_type} approach "
        f"with a {recommended_tier} package tier and {pricing_direction} pricing posture. "
        f"{requested_outcome + '. ' if requested_outcome else ''}"
        "If this direction aligns, the next step is a scoped planning review to confirm priorities, constraints, and implementation sequencing."
    )
    return {
        "response_status": "response_ready",
        "response_tone": tone,
        "response_message": response_body.strip(),
        "response_summary": (
            "Draft response is ready and aligned to intake, qualification, and offer framing."
        ),
        "response_constraints": constraints,
    }


def _project_type_from_offer(offer: dict[str, Any]) -> str:
    service_type = str(offer.get("recommended_service_type") or "").strip().lower()
    if service_type in {"advisory_plus_delivery", "discovery_workshop"}:
        return "advisory"
    if service_type == "rapid_delivery_sprint":
        return "delivery_sprint"
    return "governed_implementation"


def _sanitize_project_name(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "Revenue Lead Project Candidate"
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in {" ", "-", "_"}).strip()
    if not cleaned:
        return "Revenue Lead Project Candidate"
    return cleaned[:80]


def _build_revenue_conversion_summary(
    *,
    lead_profile: dict[str, str],
    qualification_summary: dict[str, Any],
    offer_summary: dict[str, Any] | None,
    response_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    qualification_status = str(qualification_summary.get("qualification_status") or "").strip().lower()
    offer = dict(offer_summary or {})
    response = dict(response_summary or {})
    offer_status = str(offer.get("offer_status") or "").strip().lower()
    response_status = str(response.get("response_status") or "").strip().lower()
    contact_company = str(lead_profile.get("company_name") or "").strip()
    problem_summary = str(lead_profile.get("problem_summary") or "").strip()
    requested_outcome = str(lead_profile.get("requested_outcome") or "").strip()
    project_type = _project_type_from_offer(offer)
    proposed_name = _sanitize_project_name(f"{contact_company or 'Lead'} - {project_type} candidate")
    constraints = [
        "Conversion output is governed preview data only.",
        "No execution package is created by conversion preview.",
        "No routing or runtime execution is triggered from this output.",
    ]
    notes: list[str] = []

    if qualification_status == "needs_more_info" or offer_status in {"", "no_offer_yet"} or response_status in {"", "no_response"}:
        notes.append("Upstream readiness is incomplete across qualification, offer, or response.")
        return {
            "conversion_status": "conversion_not_ready",
            "proposed_project_type": "undetermined",
            "proposed_project_name": "",
            "proposed_scope_summary": "",
            "proposed_constraints": constraints,
            "conversion_reasoning_summary": (
                "Lead cannot be converted yet because qualification, offer framing, or response drafting is incomplete."
            ),
            "conversion_notes": notes,
        }

    if offer_status == "high_touch_review_recommended" or response_status == "high_touch_required":
        notes.append("High-touch conversion review is required before project creation can be requested.")
        return {
            "conversion_status": "high_touch_conversion_required",
            "proposed_project_type": project_type,
            "proposed_project_name": proposed_name,
            "proposed_scope_summary": (
                f"High-touch candidate for {contact_company or 'lead organization'} focused on: "
                f"{problem_summary or 'governed transformation planning'}."
            ),
            "proposed_constraints": constraints,
            "conversion_reasoning_summary": (
                "Lead signals indicate complexity/risk. Conversion should remain in governed high-touch review."
            ),
            "conversion_notes": notes,
        }

    missing_lead_fields = _lead_intake_missing_fields(lead_profile)
    if offer_status == "offer_needs_more_info" or response_status == "needs_more_info" or missing_lead_fields:
        notes.append("Conversion candidate exists but key details require operator review.")
        if missing_lead_fields:
            notes.append("Missing lead fields: " + ", ".join(missing_lead_fields))
        return {
            "conversion_status": "conversion_needs_review",
            "proposed_project_type": project_type,
            "proposed_project_name": proposed_name,
            "proposed_scope_summary": (
                f"Candidate project for {contact_company or 'lead'} around {problem_summary or 'governed implementation needs'}."
            ),
            "proposed_constraints": constraints,
            "conversion_reasoning_summary": (
                "Readiness is partial. A governed operator review is required before submitting project-creation intent."
            ),
            "conversion_notes": notes,
        }

    scope_summary = (
        f"Proposed governed project candidate for {contact_company or 'lead'} to address "
        f"{problem_summary or 'the stated operational challenge'}. "
        f"{requested_outcome + '. ' if requested_outcome else ''}"
        "Candidate remains non-executing until explicit governed project-creation approval."
    ).strip()
    return {
        "conversion_status": "conversion_ready",
        "proposed_project_type": project_type,
        "proposed_project_name": proposed_name,
        "proposed_scope_summary": scope_summary,
        "proposed_constraints": constraints,
        "conversion_reasoning_summary": (
            "Lead, qualification, offer, and response inputs are aligned enough to produce a governed project candidate."
        ),
        "conversion_notes": notes,
    }


def _derive_task_complexity(
    *,
    objective: str,
    project_context: str,
    flat_constraints: list[str],
    requested_artifacts: list[str],
    mode: str,
    offer_summary: dict[str, Any] | None,
    conversion_summary: dict[str, Any] | None,
) -> str:
    if mode == "revenue_lead":
        offer_status = str((offer_summary or {}).get("offer_status") or "").strip().lower()
        conversion_status = str((conversion_summary or {}).get("conversion_status") or "").strip().lower()
        if offer_status == "high_touch_review_recommended" or conversion_status == "high_touch_conversion_required":
            return "high"
    content_len = (
        len(str(objective or ""))
        + len(str(project_context or ""))
        + sum(len(str(item or "")) for item in flat_constraints)
        + sum(len(str(item or "")) for item in requested_artifacts)
    )
    if content_len >= 1100 or len(requested_artifacts) >= 6 or len(flat_constraints) >= 10:
        return "high"
    if content_len <= 260 and len(requested_artifacts) <= 2 and len(flat_constraints) <= 4:
        return "low"
    return "medium"


def _derive_task_risk(
    *,
    structured_constraints: dict[str, list[str]],
    lead_profile: dict[str, str],
    mode: str,
    offer_summary: dict[str, Any] | None,
) -> str:
    risk_text = " ".join(
        list(structured_constraints.get("risk_notes") or [])
        + [
            str(lead_profile.get("problem_summary") or ""),
            str(lead_profile.get("requested_outcome") or ""),
        ]
    ).strip().lower()
    if mode == "revenue_lead" and str((offer_summary or {}).get("offer_status") or "").strip().lower() == "high_touch_review_recommended":
        return "governance_sensitive"
    if any(term in risk_text for term in HIGH_RISK_ROUTING_TERMS):
        return "high"
    return "medium"


def _derive_cost_sensitivity(
    *,
    qualification_summary: dict[str, Any],
    lead_profile: dict[str, str],
) -> str:
    budget_band = str(((qualification_summary.get("qualification_signals") or {}).get("budget_band")) or "").strip().lower()
    if budget_band in {"none", "unknown", "very_low", "low"}:
        return "high"
    if budget_band in {"high", "enterprise"}:
        return "low"
    context = str(lead_profile.get("budget_context") or "").strip().lower()
    if any(term in context for term in ("limited", "tight", "constrained", "reduced")):
        return "high"
    return "medium"


def _derive_budget_status(project_path: str) -> str:
    state = load_project_state(project_path) if str(project_path or "").strip() else {}
    if not isinstance(state, dict):
        return "within_cap"
    if bool(state.get("kill_switch_active")):
        return "kill_switch_active"
    explicit = str(
        state.get("budget_status")
        or state.get("budget_posture")
        or state.get("budget_cap_status")
        or ""
    ).strip().lower()
    if explicit in {"within_cap", "approaching_cap", "cap_exceeded", "kill_switch_active"}:
        return explicit
    if bool(state.get("budget_cap_exceeded")):
        return "cap_exceeded"
    if bool(state.get("budget_cap_approaching")):
        return "approaching_cap"
    return "within_cap"


def _resolve_default_request_kind(project_state: dict[str, Any]) -> str:
    intake_mode = str(project_state.get("intake_mode") or "").strip().lower()
    if intake_mode == "lead_intake":
        return "lead_intake"
    return _normalize_request_kind(project_state.get("request_kind") or "update_request")


def _composition_status(
    *,
    objective: str,
    project_context: str,
    structured_constraints: dict[str, list[str]],
    requested_artifacts: dict[str, list[str]],
    warnings: list[str],
) -> dict[str, Any]:
    missing_fields: list[str] = []
    if not str(objective or "").strip():
        missing_fields.append("objective")
    if not str(project_context or "").strip():
        missing_fields.append("project_context")
    if not _flatten_requested_artifacts(requested_artifacts):
        missing_fields.append("requested_artifacts")
    for key in REQUIRED_CONSTRAINT_SECTIONS:
        if not structured_constraints.get(key):
            missing_fields.append(key)
    return {
        "is_complete": not missing_fields and not warnings,
        "missing_fields": missing_fields,
        "warning_count": len(warnings),
        "stale_preview": False,
    }


def build_attachment_review_context(
    *,
    project_path: str,
    package_id: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    attachments = list_console_attachments_safe(project_path)
    normalized: list[dict[str, Any]] = []
    package_key = str(package_id or "")
    request_key = str(request_id or "")
    for item in attachments:
        if not isinstance(item, dict):
            continue
        item_package_id = str(item.get("package_id") or "")
        item_request_id = str(item.get("request_id") or "")
        if package_key and item_package_id == package_key:
            review_relevance = "package_linked"
        elif request_key and item_request_id == request_key:
            review_relevance = "request_linked"
        else:
            review_relevance = "project_scoped"
        normalized.append(
            {
                **item,
                "review_relevance": review_relevance,
                "review_ready": "console_review" in list(item.get("allowed_consumers") or []),
                "status_reason": str(
                    item.get("status_reason")
                    or ((item.get("governance_trace") or {}).get("classification_reason"))
                    or ""
                ),
            }
        )
    return normalized[:20]


def build_attachment_review_context_safe(**kwargs: Any) -> list[dict[str, Any]]:
    try:
        return build_attachment_review_context(**kwargs)
    except Exception:
        return []


def build_intake_workspace(
    *,
    project_key: str,
    project_path: str,
) -> dict[str, Any]:
    project_state = load_project_state(project_path)
    attachments = list_console_attachments_safe(project_path)
    autonomy_mode = normalize_autonomy_mode(project_state.get("autonomy_mode") or "supervised_build")
    allowed_actions = [str(item) for item in list(project_state.get("allowed_actions") or []) if str(item).strip()]
    structured_constraints = _empty_constraint_sections()
    requested_artifacts = {
        "selected": list(DEFAULT_REQUESTED_ARTIFACTS),
        "custom": [],
    }
    lead_intake_profile = _empty_lead_intake_profile()
    request_kind = _resolve_default_request_kind(project_state)
    return {
        "project_key": project_key,
        "project_path": project_path,
        "draft_seed": {
            "request_kind": request_kind,
            "objective": "",
            "project_context": "",
            "constraints": _flatten_constraint_sections(structured_constraints),
            "structured_constraints": structured_constraints,
            "requested_artifacts": _flatten_requested_artifacts(requested_artifacts),
            "requested_artifacts_draft": requested_artifacts,
            "autonomy_mode": autonomy_mode,
            "linked_attachment_ids": [],
            "lead_intake_profile": lead_intake_profile,
            "lead_qualification": _default_lead_qualification(),
        },
        "attachments": attachments[:20],
        "governance_notes": {
            "routing_authority": "NEXUS",
            "execution_authority": "package_governance_only",
            "request_status": "preview_only",
            "allowed_actions": allowed_actions[:12],
            "blocked_use_cases": [
                "attachment_as_governance_authority",
                "attachment_triggered_execution",
                "frontend_routing_decision",
            ],
        },
        "preview": preview_intake_request_safe(
            request_kind=request_kind,
            project_key=project_key,
            project_path=project_path,
            objective="",
            project_context="",
            constraints=structured_constraints,
            requested_artifacts=requested_artifacts,
            linked_attachment_ids=[],
            autonomy_mode=autonomy_mode,
            lead_intake_profile=lead_intake_profile,
            qualification=_default_lead_qualification(),
        ),
    }


def preview_intake_request(
    *,
    request_kind: str,
    project_key: str,
    project_path: str,
    objective: str,
    project_context: str,
    constraints: Any,
    requested_artifacts: Any,
    linked_attachment_ids: list[str],
    autonomy_mode: str,
    lead_intake_profile: Any = None,
    qualification: Any = None,
) -> dict[str, Any]:
    project_state = load_project_state(project_path)
    attachments = list_console_attachments_safe(project_path)
    attachments_by_id = {
        str(item.get("attachment_id") or ""): item
        for item in attachments
        if isinstance(item, dict)
    }
    linked = []
    warnings: list[str] = []
    allowed_link_count = 0
    structured_constraints = _normalize_constraint_sections(constraints)
    requested_artifact_state = _normalize_requested_artifacts(requested_artifacts)
    lead_profile = _normalize_lead_intake_profile(lead_intake_profile)
    mode = "revenue_lead" if str(request_kind or "").strip().lower() == "lead_intake" else "development"
    for attachment_id in linked_attachment_ids:
        record = attachments_by_id.get(str(attachment_id or ""))
        if not record:
            warnings.append(f"Linked attachment {attachment_id} was not found.")
            continue
        consumer_list = [str(item) for item in list(record.get("allowed_consumers") or [])]
        allowed_for_preview = "request_preview" in consumer_list and str(record.get("status") or "") == "classified"
        if allowed_for_preview:
            allowed_link_count += 1
        else:
            warnings.append(
                f"Attachment {record.get('attachment_id')} is {record.get('status')} and cannot inform request preview."
            )
        linked.append(
            {
                "attachment_id": record.get("attachment_id") or "",
                "file_name": record.get("file_name") or "",
                "status": record.get("status") or "unknown",
                "classification": record.get("classification") or "unknown",
                "allowed_for_request_preview": allowed_for_preview,
                "extracted_summary": record.get("extracted_summary") or "",
            }
        )

    objective_value = str(objective or "").strip()
    project_context_value = str(project_context or "").strip()
    flat_constraints = _flatten_constraint_sections(structured_constraints)
    flat_requested_artifacts = _flatten_requested_artifacts(requested_artifact_state)
    if mode == "revenue_lead":
        missing_fields = _lead_intake_missing_fields(lead_profile)
        composition_status = {
            "is_complete": not missing_fields and not warnings,
            "missing_fields": missing_fields,
            "warning_count": len(warnings),
            "stale_preview": False,
        }
    else:
        composition_status = _composition_status(
            objective=objective_value,
            project_context=project_context_value,
            structured_constraints=structured_constraints,
            requested_artifacts=requested_artifact_state,
            warnings=warnings,
        )
    readiness = "needs_input"
    if composition_status["is_complete"]:
        readiness = "ready_for_governed_request"
    elif mode != "revenue_lead" and objective_value and flat_requested_artifacts and warnings:
        readiness = "ready_with_attachment_limits"
    elif mode == "revenue_lead":
        warnings.append(
            "Lead intake is incomplete. Add contact name, contact email, company name, and problem summary before revenue intake can be marked ready."
        )
    elif objective_value:
        warnings.append(
            "Request composition is incomplete. Add project context, scope/output/review constraints, and requested artifacts before launch preview can be considered ready."
        )
    request_id = f"preview-{uuid.uuid4().hex[:8]}"
    normalized_request_kind = _normalize_request_kind(request_kind)
    qualification_summary = _build_lead_qualification_summary(qualification)
    offer_summary = (
        _build_revenue_offer_summary(
            lead_profile=lead_profile,
            qualification=_normalize_lead_qualification(qualification),
            qualification_summary=qualification_summary,
        )
        if normalized_request_kind == "lead_intake"
        else None
    )
    response_summary = (
        _build_revenue_response_summary(
            lead_profile=lead_profile,
            qualification_summary=qualification_summary,
            offer_summary=offer_summary,
        )
        if normalized_request_kind == "lead_intake"
        else None
    )
    conversion_summary = (
        _build_revenue_conversion_summary(
            lead_profile=lead_profile,
            qualification_summary=qualification_summary,
            offer_summary=offer_summary,
            response_summary=response_summary,
        )
        if normalized_request_kind == "lead_intake"
        else None
    )
    cost_tracking = _estimate_preview_cost(
        request_kind=normalized_request_kind,
        objective=objective_value,
        project_context=project_context_value,
        constraints=flat_constraints,
        requested_artifacts=flat_requested_artifacts,
        linked_attachment_count=len(linked),
        warnings_count=len(warnings),
        lead_profile=lead_profile,
    )
    journal_rows = list_execution_package_journal_entries(project_path, n=50)
    run_id = str(project_state.get("run_id") or "")
    estimated_totals = summarize_journal_estimated_costs(journal_rows, run_id=run_id)
    operation_cost = float(cost_tracking.get("cost_estimate") or 0.0)
    project_cost = float(estimated_totals.get("project_estimated_cost_total") or 0.0) + operation_cost
    session_cost = float(estimated_totals.get("session_estimated_cost_total") or 0.0) + operation_cost
    budget_caps = resolve_budget_caps(project_state)
    budget_control = evaluate_budget_controls(
        budget_caps=budget_caps,
        current_operation_cost=operation_cost,
        current_project_cost=project_cost,
        current_session_cost=session_cost,
    )
    task_type = "preview"
    if normalized_request_kind == "lead_intake" and str((offer_summary or {}).get("offer_status") or "").strip().lower() == "high_touch_review_recommended":
        task_type = "governance_sensitive_evaluation"
    policy_budget_status = str(budget_control.get("budget_status") or "within_budget").strip().lower()
    if policy_budget_status == "kill_switch_triggered":
        policy_budget_status = "kill_switch_active"
    model_routing_policy = resolve_model_routing_policy_safe(
        task_type=task_type,
        task_complexity=_derive_task_complexity(
            objective=objective_value,
            project_context=project_context_value,
            flat_constraints=flat_constraints,
            requested_artifacts=flat_requested_artifacts,
            mode=mode,
            offer_summary=offer_summary,
            conversion_summary=conversion_summary,
        ),
        task_risk_level=_derive_task_risk(
            structured_constraints=structured_constraints,
            lead_profile=lead_profile,
            mode=mode,
            offer_summary=offer_summary,
        ),
        cost_sensitivity=_derive_cost_sensitivity(
            qualification_summary=qualification_summary,
            lead_profile=lead_profile,
        ),
        budget_status=policy_budget_status,
        is_routine_task=(mode != "revenue_lead" and len(flat_constraints) <= 4 and len(flat_requested_artifacts) <= 2),
        is_high_impact_task=(mode == "revenue_lead" and str((qualification_summary.get("qualification_status") or "")).strip().lower() == "high_priority"),
        authority_trace={
            "routing_authority": "NEXUS",
            "surface": "console_intake_preview",
            "project_key": str(project_key or ""),
            "budget_scope": str(budget_control.get("budget_scope") or "operation"),
        },
        governance_trace={
            "request_kind": normalized_request_kind,
            "preview_only": True,
            "execution_authority": "package_governance_only",
            "budget_policy_reason": str(budget_control.get("budget_reason") or ""),
        },
    )
    preview_payload = {
        "request_id": request_id,
        "request_kind": normalized_request_kind,
        "objective": objective_value,
        "project_context": project_context_value,
        "constraints": flat_constraints,
        "structured_constraints": structured_constraints,
        "requested_artifacts": flat_requested_artifacts,
        "requested_artifact_details": _requested_artifact_details(requested_artifact_state),
        "autonomy_mode": normalize_autonomy_mode(autonomy_mode),
        "autonomy_mode_detail": _autonomy_mode_detail(autonomy_mode),
        "intake_mode": mode,
        "lead_intake_profile": lead_profile,
        "composition_status": {
            **composition_status,
            "warning_count": len(warnings),
        },
        "linked_attachments": linked,
        "readiness": readiness,
        "warnings": warnings,
        "qualification_summary": (
            qualification_summary
            if normalized_request_kind == "lead_intake"
            else None
        ),
        "offer_summary": offer_summary,
        "response_summary": response_summary,
        "conversion_summary": conversion_summary,
        "cost_tracking": cost_tracking,
        "budget_caps": budget_control.get("budget_caps") or budget_caps,
        "budget_control": budget_control,
        "budget_status": str(budget_control.get("budget_status") or "within_budget"),
        "budget_scope": str(budget_control.get("budget_scope") or "operation"),
        "budget_cap": float(budget_control.get("budget_cap") or 0.0),
        "current_estimated_cost": float(budget_control.get("current_estimated_cost") or 0.0),
        "remaining_estimated_budget": float(budget_control.get("remaining_estimated_budget") or 0.0),
        "kill_switch_active": bool(budget_control.get("kill_switch_active")),
        "budget_reason": str(budget_control.get("budget_reason") or ""),
        "model_routing_policy": model_routing_policy,
        "package_preview": {
            "creation_mode": "lead_preview_only" if mode == "revenue_lead" else "preview_only",
            "package_creation_allowed": False,
            "governance_required": True,
            "routing_authority": "NEXUS",
            "execution_authority": "package_governance_only",
            "routing_status": str(model_routing_policy.get("routing_status") or ""),
            "budget_aware_routing_note": str(model_routing_policy.get("budget_aware_note") or ""),
            "attachment_input_count": len(linked),
            "attachment_preview_count": allowed_link_count,
            "summary": (
                "Console can preview governed revenue lead intake intent, but package creation, routing, and execution remain backend-governed actions."
                if mode == "revenue_lead"
                else "Console can preview governed request intent, but package creation, routing, and execution remain backend-governed actions."
            ),
        },
    }
    preview_payload["quick_actions"] = build_intake_preview_quick_actions(preview_payload)
    return preview_payload


def preview_intake_request_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return preview_intake_request(**kwargs)
    except Exception as exc:
        fallback_payload = {
            "request_id": "",
            "request_kind": _normalize_request_kind(kwargs.get("request_kind") or "update_request"),
            "objective": "",
            "project_context": "",
            "constraints": [],
            "structured_constraints": _empty_constraint_sections(),
            "requested_artifacts": [],
            "requested_artifact_details": [],
            "autonomy_mode": str(kwargs.get("autonomy_mode") or "supervised_build"),
            "autonomy_mode_detail": _autonomy_mode_detail(kwargs.get("autonomy_mode") or "supervised_build"),
            "intake_mode": "revenue_lead" if str(kwargs.get("request_kind") or "").strip().lower() == "lead_intake" else "development",
            "lead_intake_profile": _normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
            "composition_status": {
                "is_complete": False,
                "missing_fields": ["preview_error"],
                "warning_count": 1,
                "stale_preview": False,
            },
            "linked_attachments": [],
            "readiness": "error",
            "warnings": [f"Preview failed: {exc}"],
            "qualification_summary": (
                _build_lead_qualification_summary(kwargs.get("qualification"))
                if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                else None
            ),
            "offer_summary": (
                _build_revenue_offer_summary(
                    lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                    qualification=_normalize_lead_qualification(kwargs.get("qualification")),
                    qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                )
                if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                else None
            ),
            "response_summary": (
                _build_revenue_response_summary(
                    lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                    qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                    offer_summary=(
                        _build_revenue_offer_summary(
                            lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                            qualification=_normalize_lead_qualification(kwargs.get("qualification")),
                            qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                        )
                        if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                        else None
                    ),
                )
                if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                else None
            ),
            "conversion_summary": (
                _build_revenue_conversion_summary(
                    lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                    qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                    offer_summary=(
                        _build_revenue_offer_summary(
                            lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                            qualification=_normalize_lead_qualification(kwargs.get("qualification")),
                            qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                        )
                        if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                        else None
                    ),
                    response_summary=(
                        _build_revenue_response_summary(
                            lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                            qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                            offer_summary=(
                                _build_revenue_offer_summary(
                                    lead_profile=_normalize_lead_intake_profile(kwargs.get("lead_intake_profile")),
                                    qualification=_normalize_lead_qualification(kwargs.get("qualification")),
                                    qualification_summary=_build_lead_qualification_summary(kwargs.get("qualification")),
                                )
                                if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                                else None
                            ),
                        )
                        if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                        else None
                    ),
                )
                if _normalize_request_kind(kwargs.get("request_kind")) == "lead_intake"
                else None
            ),
            "cost_tracking": _build_cost_tracking(
                cost_source="composed_operation",
                estimated_tokens=80,
                model="forge_intake_preview_estimator",
            ),
            "budget_caps": resolve_budget_caps({}),
            "budget_control": evaluate_budget_controls(
                budget_caps=resolve_budget_caps({}),
                current_operation_cost=0.0,
                current_project_cost=0.0,
                current_session_cost=0.0,
            ),
            "budget_status": "within_budget",
            "budget_scope": "operation",
            "budget_cap": 0.0,
            "current_estimated_cost": 0.0,
            "remaining_estimated_budget": 0.0,
            "kill_switch_active": False,
            "budget_reason": "Preview failed before budget evaluation could run.",
            "model_routing_policy": resolve_model_routing_policy_safe(
                task_type="preview",
                task_complexity="medium",
                task_risk_level="medium",
                cost_sensitivity="medium",
                budget_status="within_cap",
                authority_trace={
                    "routing_authority": "NEXUS",
                    "surface": "console_intake_preview",
                },
                governance_trace={
                    "preview_only": True,
                    "execution_authority": "package_governance_only",
                },
            ),
            "package_preview": {
                "creation_mode": "preview_only",
                "package_creation_allowed": False,
                "governance_required": True,
                "routing_authority": "NEXUS",
                "execution_authority": "package_governance_only",
                "routing_status": "deferred_for_review",
                "budget_aware_routing_note": "",
                "attachment_input_count": 0,
                "attachment_preview_count": 0,
                "summary": "Preview unavailable.",
            },
        }
        fallback_payload["quick_actions"] = build_intake_preview_quick_actions(fallback_payload)
        return fallback_payload
