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


def build_intake_workspace(
    *,
    project_key: str,
    project_path: str,
) -> dict[str, Any]:
    project_state = load_project_state(project_path)
    attachments = list_console_attachments_safe(project_path)
    autonomy_mode = str(project_state.get("autonomy_mode") or "supervised_build")
    allowed_actions = [str(item) for item in list(project_state.get("allowed_actions") or []) if str(item).strip()]
    return {
        "project_key": project_key,
        "project_path": project_path,
        "draft_seed": {
            "request_kind": "update_request",
            "objective": "",
            "constraints": [],
            "requested_artifacts": ["implementation_summary", "test_report", "diff_review"],
            "autonomy_mode": autonomy_mode,
            "linked_attachment_ids": [],
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
            project_key=project_key,
            project_path=project_path,
            objective="",
            constraints=[],
            requested_artifacts=["implementation_summary", "test_report", "diff_review"],
            linked_attachment_ids=[],
            autonomy_mode=autonomy_mode,
        ),
    }


def preview_intake_request(
    *,
    project_key: str,
    project_path: str,
    objective: str,
    constraints: list[str],
    requested_artifacts: list[str],
    linked_attachment_ids: list[str],
    autonomy_mode: str,
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
    readiness = "needs_input"
    if objective_value and not warnings:
        readiness = "ready_for_governed_request"
    elif objective_value:
        readiness = "ready_with_attachment_limits"
    request_id = f"preview-{uuid.uuid4().hex[:8]}"
    return {
        "request_id": request_id,
        "request_kind": "preview_only",
        "objective": objective_value,
        "constraints": [str(item).strip() for item in constraints if str(item).strip()],
        "requested_artifacts": [str(item).strip() for item in requested_artifacts if str(item).strip()],
        "autonomy_mode": str(autonomy_mode or "supervised_build"),
        "linked_attachments": linked,
        "readiness": readiness,
        "warnings": warnings,
        "package_preview": {
            "creation_mode": "preview_only",
            "package_creation_allowed": False,
            "governance_required": True,
            "routing_authority": "NEXUS",
            "execution_authority": "package_governance_only",
            "attachment_input_count": len(linked),
            "attachment_preview_count": allowed_link_count,
            "summary": "Console can preview governed request creation, but package creation remains a backend-governed action.",
        },
    }


def preview_intake_request_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return preview_intake_request(**kwargs)
    except Exception as exc:
        return {
            "request_id": "",
            "request_kind": "preview_only",
            "objective": "",
            "constraints": [],
            "requested_artifacts": [],
            "autonomy_mode": str(kwargs.get("autonomy_mode") or "supervised_build"),
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
