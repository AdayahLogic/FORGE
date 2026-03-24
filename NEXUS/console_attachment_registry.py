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


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    return {
        "project_key": project_key,
        "project_path": project_path,
        "draft_seed": {
            "request_kind": "update_request",
            "objective": "",
            "project_context": "",
            "constraints": _flatten_constraint_sections(structured_constraints),
            "structured_constraints": structured_constraints,
            "requested_artifacts": _flatten_requested_artifacts(requested_artifacts),
            "requested_artifacts_draft": requested_artifacts,
            "autonomy_mode": autonomy_mode,
            "linked_attachment_ids": [],
            "lead_intake_profile": lead_intake_profile,
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
            request_kind="update_request",
            project_key=project_key,
            project_path=project_path,
            objective="",
            project_context="",
            constraints=structured_constraints,
            requested_artifacts=requested_artifacts,
            linked_attachment_ids=[],
            autonomy_mode=autonomy_mode,
            lead_intake_profile=lead_intake_profile,
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
) -> dict[str, Any]:
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
    return {
        "request_id": request_id,
        "request_kind": str(request_kind or "update_request"),
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
        "package_preview": {
            "creation_mode": "lead_preview_only" if mode == "revenue_lead" else "preview_only",
            "package_creation_allowed": False,
            "governance_required": True,
            "routing_authority": "NEXUS",
            "execution_authority": "package_governance_only",
            "attachment_input_count": len(linked),
            "attachment_preview_count": allowed_link_count,
            "summary": (
                "Console can preview governed revenue lead intake intent, but package creation, routing, and execution remain backend-governed actions."
                if mode == "revenue_lead"
                else "Console can preview governed request intent, but package creation, routing, and execution remain backend-governed actions."
            ),
        },
    }


def preview_intake_request_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return preview_intake_request(**kwargs)
    except Exception as exc:
        return {
            "request_id": "",
            "request_kind": str(kwargs.get("request_kind") or "update_request"),
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
            "package_preview": {
                "creation_mode": "preview_only",
                "package_creation_allowed": False,
                "governance_required": True,
                "routing_authority": "NEXUS",
                "execution_authority": "package_governance_only",
                "attachment_input_count": 0,
                "attachment_preview_count": 0,
                "summary": "Preview unavailable.",
            },
        }
