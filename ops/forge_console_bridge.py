"""
Forge Console bridge.

Additive read-mostly adapter between the Forge Console Next routes and the
existing Forge command/state surfaces. The browser never reads Forge state
directly; routes call this bridge and the bridge reads only from existing
command outputs plus persisted project/package state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from NEXUS.command_surface import run_command
from NEXUS.console_attachment_registry import (
    build_attachment_review_context_safe,
    build_intake_workspace,
    list_console_attachments_safe,
    ingest_console_attachment_safe,
    preview_intake_request_safe,
)
from NEXUS.execution_package_registry import (
    list_execution_package_journal_entries,
    read_execution_package,
)
from NEXUS.project_state import load_project_state
from NEXUS.registry import PROJECTS


ALLOWED_CONTROL_ACTIONS = {
    "complete_review": {
        "confirmation_phrase": "CONFIRM COMPLETE REVIEW",
        "requires_project": True,
    },
    "complete_approval": {
        "confirmation_phrase": "CONFIRM COMPLETE APPROVAL",
        "requires_project": True,
    },
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _result(status: str, payload: dict[str, Any], message: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "payload": payload,
    }


def _resolve_project(project_key: str | None) -> tuple[str | None, dict[str, Any] | None]:
    key = str(project_key or "").strip().lower()
    if not key:
        return None, None
    if key not in PROJECTS:
        return key, None
    return key, PROJECTS[key]


def _project_rows_from_dashboard(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dispatch_by_project = dashboard.get("dispatch_status_by_project") or {}
    governance_by_project = dashboard.get("governance_status_by_project") or {}
    enforcement_by_project = dashboard.get("enforcement_status_by_project") or {}
    lifecycle_by_project = dashboard.get("project_lifecycle_by_project") or {}
    queue_by_project = dashboard.get("queue_status_by_project") or {}
    review_summary = dashboard.get("execution_package_review_summary") or {}
    latest_package_id = review_summary.get("latest_package_id_by_project") or {}
    latest_package_path = review_summary.get("latest_package_path_by_project") or {}
    latest_eval = (dashboard.get("execution_package_evaluation_summary") or {}).get("latest_evaluation_status_by_project") or {}
    latest_analysis = (dashboard.get("execution_package_local_analysis_summary") or {}).get("latest_analysis_status_by_project") or {}
    health_by_project = dashboard.get("execution_status_by_project") or {}
    for key in sorted(PROJECTS.keys()):
        meta = PROJECTS.get(key) or {}
        rows.append(
            {
                "project_key": key,
                "project_name": meta.get("name") or key,
                "description": meta.get("description") or "",
                "workspace_type": meta.get("workspace_type") or "",
                "dispatch_status": dispatch_by_project.get(key) or "none",
                "governance_status": governance_by_project.get(key) or "none",
                "enforcement_status": enforcement_by_project.get(key) or "none",
                "lifecycle_status": lifecycle_by_project.get(key) or "none",
                "queue_status": queue_by_project.get(key) or "none",
                "current_package_id": latest_package_id.get(key) or "",
                "current_package_path": latest_package_path.get(key) or "",
                "latest_evaluation_status": latest_eval.get(key) or "pending",
                "latest_local_analysis_status": latest_analysis.get(key) or "pending",
                "executor_health": health_by_project.get(key) or "unknown",
            }
        )
    return rows


def _executor_health_summary(dashboard: dict[str, Any]) -> dict[str, Any]:
    exec_env = dashboard.get("execution_environment_summary") or {}
    runtime_infra = dashboard.get("runtime_infrastructure_summary") or {}
    execution_summary = dashboard.get("execution_package_execution_summary") or {}
    return {
        "execution_environment_status": exec_env.get("execution_environment_status") or "unknown",
        "environment_reason": exec_env.get("reason") or "",
        "runtime_infrastructure_status": runtime_infra.get("runtime_infrastructure_status") or runtime_infra.get("status") or "unknown",
        "runtime_reason": runtime_infra.get("reason") or runtime_infra.get("summary_reason") or "",
        "integrity_verified_count_total": execution_summary.get("integrity_verified_count_total", 0),
        "integrity_issues_count_total": execution_summary.get("integrity_issues_count_total", 0),
        "blocked_execution_count_total": execution_summary.get("blocked_count_total", 0),
    }


def _pretty_label(value: str) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    if not text:
        return "Untitled"
    return " ".join(part.capitalize() for part in text.split())


def _client_status_from_state(project_state: dict[str, Any], package: dict[str, Any]) -> str:
    release_status = str(package.get("release_status") or "").strip().lower()
    decision_status = str(package.get("decision_status") or "").strip().lower()
    review_status = str(package.get("review_status") or "").strip().lower()
    execution_status = str(package.get("execution_status") or "").strip().lower()
    lifecycle_status = str(project_state.get("project_lifecycle_status") or "").strip().lower()
    if release_status == "released" or decision_status == "approved":
        return "approved"
    if review_status in {"ready_for_review", "review_pending", "pending", "reviewed"}:
        return "ready_for_review"
    if execution_status in {"succeeded", "completed"}:
        return "complete"
    if package or lifecycle_status in {"active", "queued", "running"}:
        return "in_progress"
    return "pending"


def _client_progress_percent(client_status: str) -> int:
    mapping = {
        "pending": 15,
        "in_progress": 52,
        "complete": 78,
        "ready_for_review": 88,
        "approved": 100,
    }
    return mapping.get(client_status, 0)


def _client_phase_label(client_status: str) -> str:
    mapping = {
        "pending": "Project Intake",
        "in_progress": "Build In Progress",
        "complete": "Internal Review",
        "ready_for_review": "Ready for Review",
        "approved": "Approved Delivery",
    }
    return mapping.get(client_status, "Project Intake")


def _client_progress_label(client_status: str) -> str:
    mapping = {
        "pending": "Planning underway",
        "in_progress": "Work in progress",
        "complete": "Implementation complete",
        "ready_for_review": "Ready for review",
        "approved": "Approved to share",
    }
    return mapping.get(client_status, "Status unavailable")


def _client_safe_summary(
    *,
    client_status: str,
    package: dict[str, Any],
    deliverable_count: int,
) -> str:
    if client_status == "approved":
        return f"{deliverable_count} approved deliverable(s) are ready to share."
    if client_status == "ready_for_review":
        return "Current work has cleared internal build activity and is ready for stakeholder review."
    if client_status == "complete":
        return "Implementation work is complete and moving through the final review steps."
    if client_status == "in_progress":
        return "Project work is actively progressing within the current milestone."
    return "Project intake is active and milestone planning is underway."


def _deliverable_status_from_package(package: dict[str, Any]) -> str:
    client_status = _client_status_from_state({}, package)
    if client_status == "approved":
        return "approved"
    if client_status == "ready_for_review":
        return "ready_for_review"
    if client_status == "complete":
        return "complete"
    if package:
        return "in_progress"
    return "pending"


def _build_client_deliverables(package: dict[str, Any]) -> list[dict[str, Any]]:
    titles: list[str] = []
    for item in list(package.get("expected_outputs") or []):
        label = _pretty_label(str(item))
        if label not in titles:
            titles.append(label)
    for item in list(package.get("runtime_artifacts") or []):
        if not isinstance(item, dict):
            continue
        label = _pretty_label(str(item.get("artifact_type") or "artifact"))
        if label not in titles:
            titles.append(label)
    if not titles:
        titles.append("Project Summary")
    status = _deliverable_status_from_package(package)
    approved_at = str(package.get("created_at") or "") if status == "approved" else ""
    safe_to_share = status == "approved"
    summary_text = (
        "Approved for client visibility."
        if safe_to_share
        else "Tracked within the current governed delivery milestone."
    )
    return [
        {
            "deliverable_id": f"deliverable-{index}",
            "title": title,
            "status": status,
            "summary": summary_text,
            "safe_to_share": safe_to_share,
            "approved_at": approved_at,
        }
        for index, title in enumerate(titles, start=1)
    ]


def _build_client_milestones(client_status: str) -> list[dict[str, Any]]:
    def milestone_status(name: str) -> str:
        order = ["pending", "in_progress", "complete", "ready_for_review", "approved"]
        rank = order.index(client_status) if client_status in order else 0
        if name == "intake":
            return "complete" if rank >= 1 else "in_progress"
        if name == "build":
            if rank >= 2:
                return "complete"
            if rank >= 1:
                return "in_progress"
            return "pending"
        if name == "review":
            if rank >= 4:
                return "complete"
            if rank >= 3:
                return "ready_for_review"
            return "pending"
        if rank >= 4:
            return "complete"
        if rank >= 3:
            return "in_progress"
        return "pending"

    return [
        {
            "milestone_id": "intake",
            "title": "Scope Confirmed",
            "status": milestone_status("intake"),
            "summary": "Project scope and requested outcomes are established.",
            "target_label": "Intake milestone",
        },
        {
            "milestone_id": "build",
            "title": "Work In Progress",
            "status": milestone_status("build"),
            "summary": "The current implementation milestone is underway.",
            "target_label": "Active build milestone",
        },
        {
            "milestone_id": "review",
            "title": "Ready For Review",
            "status": milestone_status("review"),
            "summary": "Review-ready materials are being assembled for stakeholder visibility.",
            "target_label": "Review milestone",
        },
        {
            "milestone_id": "delivery",
            "title": "Approved Delivery",
            "status": milestone_status("delivery"),
            "summary": "Approved deliverables are prepared for safe external sharing.",
            "target_label": "Delivery milestone",
        },
    ]


def _attachment_marked_shareable(record: dict[str, Any]) -> bool:
    purpose = str(record.get("purpose") or "").strip().lower()
    return bool(record.get("shareable")) or bool(record.get("safe_to_share")) or purpose in {"shareable", "safe_to_share"}


def _build_client_attachments(project_path: str) -> list[dict[str, Any]]:
    attachments = list_console_attachments_safe(project_path)
    safe_rows: list[dict[str, Any]] = []
    for record in attachments:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "").strip().lower() != "classified":
            continue
        if not _attachment_marked_shareable(record):
            continue
        safe_rows.append(
            {
                "attachment_id": str(record.get("attachment_id") or ""),
                "file_name": str(record.get("file_name") or "attachment"),
                "purpose": str(record.get("purpose") or ""),
                "status": "safe_to_share",
                "summary": str(record.get("extracted_summary") or "Approved attachment available for client review."),
                "uploaded_at": str(record.get("uploaded_at") or ""),
            }
        )
    return safe_rows[:12]


def _build_client_timeline(
    *,
    project_name: str,
    package: dict[str, Any],
    client_status: str,
) -> list[dict[str, Any]]:
    occurred_at = str(package.get("created_at") or "")
    events = [
        {
            "event_id": "timeline-intake",
            "label": "Project Started",
            "status": "complete" if client_status != "pending" else "in_progress",
            "summary": f"{project_name} is active in the Forge delivery workflow.",
            "occurred_at": occurred_at,
        }
    ]
    if client_status in {"in_progress", "complete", "ready_for_review", "approved"}:
        events.append(
            {
                "event_id": "timeline-build",
                "label": "Current Workstream",
                "status": "complete" if client_status in {"complete", "ready_for_review", "approved"} else "in_progress",
                "summary": "Current milestone work is progressing through the governed build workflow.",
                "occurred_at": occurred_at,
            }
        )
    if client_status in {"ready_for_review", "approved"}:
        events.append(
            {
                "event_id": "timeline-review",
                "label": "Review Ready",
                "status": "approved" if client_status == "approved" else "ready_for_review",
                "summary": "Deliverables have reached the review-ready stage for safe stakeholder visibility.",
                "occurred_at": occurred_at,
            }
        )
    if client_status == "approved":
        events.append(
            {
                "event_id": "timeline-delivery",
                "label": "Approved Deliverables Shared",
                "status": "approved",
                "summary": "Approved project outputs are now safe to share externally.",
                "occurred_at": occurred_at,
            }
        )
    return events


def _read_current_package(project_path: str, project_state: dict[str, Any]) -> dict[str, Any]:
    package_id = str(project_state.get("execution_package_id") or "")
    if not package_id:
        return {}
    return read_execution_package(project_path, package_id) or {}


def _build_client_project_row(
    *,
    project_key: str,
    project: dict[str, Any],
    project_state: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    deliverables = _build_client_deliverables(package)
    client_status = _client_status_from_state(project_state, package)
    return {
        "project_key": project_key,
        "project_name": str(project.get("name") or project_key),
        "description": str(project.get("description") or ""),
        "client_status": client_status,
        "current_phase": _client_phase_label(client_status),
        "progress_percent": _client_progress_percent(client_status),
        "progress_label": _client_progress_label(client_status),
        "safe_summary": _client_safe_summary(
            client_status=client_status,
            package=package,
            deliverable_count=len(deliverables),
        ),
    }


def _build_client_project_snapshot(
    *,
    project_key: str,
    project: dict[str, Any],
    project_state: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    row = _build_client_project_row(
        project_key=project_key,
        project=project,
        project_state=project_state,
        package=package,
    )
    return {
        "project_key": row["project_key"],
        "project_name": row["project_name"],
        "description": row["description"],
        "client_status": row["client_status"],
        "current_phase": row["current_phase"],
        "progress_percent": row["progress_percent"],
        "progress_label": row["progress_label"],
        "safe_summary": row["safe_summary"],
        "milestones": _build_client_milestones(str(row["client_status"])),
        "deliverables": _build_client_deliverables(package),
        "approved_attachments": _build_client_attachments(str(project.get("path") or "")),
        "timeline": _build_client_timeline(
            project_name=str(row["project_name"]),
            package=package,
            client_status=str(row["client_status"]),
        ),
    }


def build_client_view_snapshot(project_key: str | None = None) -> dict[str, Any]:
    selected_key = str(project_key or "").strip().lower()
    if selected_key and selected_key not in PROJECTS:
        return _result(
            "error",
            {
                "generated_at": "",
                "surface_mode": "client_safe",
                "selected_project_key": selected_key,
                "projects": [],
                "project": None,
            },
            "Unknown project.",
        )
    project_rows: list[dict[str, Any]] = []
    selected_project_snapshot = None
    generated_at = ""
    for key in sorted(PROJECTS.keys()):
        project = PROJECTS.get(key) or {}
        project_path = str(project.get("path") or "")
        project_state = load_project_state(project_path)
        package = _read_current_package(project_path, project_state)
        row = _build_client_project_row(
            project_key=key,
            project=project,
            project_state=project_state,
            package=package,
        )
        project_rows.append(row)
        if not generated_at:
            generated_at = str(package.get("created_at") or "")
        if key == selected_key:
            selected_project_snapshot = _build_client_project_snapshot(
                project_key=key,
                project=project,
                project_state=project_state,
                package=package,
            )
    if not selected_key and project_rows:
        selected_key = str(project_rows[0].get("project_key") or "")
        project = PROJECTS.get(selected_key) or {}
        project_path = str(project.get("path") or "")
        project_state = load_project_state(project_path)
        package = _read_current_package(project_path, project_state)
        selected_project_snapshot = _build_client_project_snapshot(
            project_key=selected_key,
            project=project,
            project_state=project_state,
            package=package,
        )
    return _result(
        "ok",
        {
            "generated_at": generated_at,
            "surface_mode": "client_safe",
            "selected_project_key": selected_key,
            "projects": project_rows,
            "project": selected_project_snapshot,
        },
        "",
    )


def build_studio_snapshot() -> dict[str, Any]:
    dashboard_res = run_command("dashboard_summary")
    dashboard = dashboard_res.get("payload") or {}
    approval_res = run_command("pending_approvals")
    approval = approval_res.get("payload") or {}
    lifecycle_res = run_command("approval_lifecycle_status")
    lifecycle = lifecycle_res.get("payload") or {}
    review_summary = dashboard.get("execution_package_review_summary") or {}
    decision_summary = dashboard.get("execution_package_decision_summary") or {}
    eligibility_summary = dashboard.get("execution_package_eligibility_summary") or {}
    release_summary = dashboard.get("execution_package_release_summary") or {}
    handoff_summary = dashboard.get("execution_package_handoff_summary") or {}
    execution_summary = dashboard.get("execution_package_execution_summary") or {}
    evaluation_summary = dashboard.get("execution_package_evaluation_summary") or {}
    local_analysis_summary = dashboard.get("execution_package_local_analysis_summary") or {}
    project_rows = _project_rows_from_dashboard(dashboard)
    package_counts = {
        "review_pending": review_summary.get("pending_count_total", 0),
        "decision_pending": decision_summary.get("pending_count_total", 0),
        "eligibility_pending": eligibility_summary.get("pending_count_total", 0),
        "release_pending": release_summary.get("pending_count_total", 0),
        "handoff_pending": handoff_summary.get("pending_count_total", 0),
        "execution_pending": execution_summary.get("pending_count_total", 0),
        "execution_blocked": execution_summary.get("blocked_count_total", 0),
        "execution_failed": execution_summary.get("failed_count_total", 0),
        "execution_succeeded": execution_summary.get("succeeded_count_total", 0),
    }
    return {
        "generated_at": dashboard.get("summary_generated_at") or "",
        "studio_name": dashboard.get("studio_name") or "FORGE",
        "overview": {
            "studio_health": (dashboard.get("release_readiness_summary") or {}).get("release_readiness_status") or "unknown",
            "aegis_posture": dashboard.get("aegis_summary") or {},
            "queue_counts": {
                "queued_projects": len(dashboard.get("queued_projects") or []),
                "review_required_projects": len(review_summary.get("review_required_projects") or []),
                "approval_pending_total": approval.get("pending_count_total", 0),
                "reapproval_required_total": lifecycle.get("reapproval_required_count", 0),
            },
            "package_counts": package_counts,
            "evaluation_counts": {
                "pending": evaluation_summary.get("pending_count_total", 0),
                "completed": evaluation_summary.get("completed_count_total", 0),
                "blocked": evaluation_summary.get("blocked_count_total", 0),
                "error": evaluation_summary.get("error_count_total", 0),
                "bands": {
                    "execution_quality": evaluation_summary.get("execution_quality_band_count_total") or {},
                    "integrity": evaluation_summary.get("integrity_band_count_total") or {},
                    "rollback_quality": evaluation_summary.get("rollback_quality_band_count_total") or {},
                    "failure_risk": evaluation_summary.get("failure_risk_band_count_total") or {},
                },
            },
            "local_analysis_counts": {
                "pending": local_analysis_summary.get("pending_count_total", 0),
                "completed": local_analysis_summary.get("completed_count_total", 0),
                "blocked": local_analysis_summary.get("blocked_count_total", 0),
                "error": local_analysis_summary.get("error_count_total", 0),
                "confidence_bands": local_analysis_summary.get("confidence_band_count_total") or {},
                "next_actions": local_analysis_summary.get("suggested_next_action_count_total") or {},
            },
            "project_count": (dashboard.get("project_summary") or {}).get("total", 0) or len(project_rows),
            "executor_health": _executor_health_summary(dashboard),
        },
        "projects": project_rows,
        "approval_center": {
            "approval_summary": approval,
            "approval_lifecycle": lifecycle,
            "allowed_actions": sorted(ALLOWED_CONTROL_ACTIONS.keys()),
            "surface_mode": "read_only",
        },
        "raw": {
            "dashboard_summary": dashboard,
        },
    }


def _normalize_package_queue(project_key: str, project_path: str) -> dict[str, Any]:
    queue_res = run_command("execution_package_queue", project_path=project_path, project_name=project_key, n=50)
    queue_payload = queue_res.get("payload") or {}
    return {
        "project_key": project_key,
        "project_path": project_path,
        "count": queue_payload.get("count", 0),
        "pending_count": queue_payload.get("pending_count", 0),
        "packages": queue_payload.get("packages") or [],
    }


def build_project_snapshot(project_key: str) -> dict[str, Any]:
    key, project = _resolve_project(project_key)
    if not project:
        return _result("error", {"project_key": key, "error": "Unknown project."}, "Unknown project.")
    project_path = str(project.get("path") or "")
    project_state = load_project_state(project_path)
    project_summary = (run_command("project_summary", project_path=project_path, project_name=key).get("payload") or {})
    latest_session = (run_command("latest_session", project_path=project_path, project_name=key).get("payload") or {})
    health = (run_command("health", project_path=project_path, project_name=key).get("payload") or {})
    package_queue = _normalize_package_queue(key, project_path)
    approvals = (run_command("pending_approvals", project_path=project_path, project_name=key).get("payload") or {})
    intake_workspace = build_intake_workspace(project_key=key, project_path=project_path)
    current_package_id = str(project_state.get("execution_package_id") or "")
    current_package = None
    if current_package_id:
        current_package = (
            run_command(
                "execution_package_details",
                project_path=project_path,
                project_name=key,
                execution_package_id=current_package_id,
            ).get("payload")
            or {}
        )
    return _result(
        "ok",
        {
            "project_key": key,
            "project_name": project.get("name") or key,
            "project_path": project_path,
            "project_meta": project,
            "project_summary": project_summary,
            "project_state": project_state,
            "latest_session": latest_session,
            "system_health": health,
            "package_queue": package_queue,
            "current_package": current_package,
            "approval_summary": approvals,
            "intake_workspace": intake_workspace,
            "degraded_sources": [
                source
                for source, value in (
                    ("project_state", project_state),
                    ("project_summary", project_summary),
                    ("latest_session", latest_session),
                    ("system_health", health),
                )
                if isinstance(value, dict) and value.get("error")
            ],
        },
        "",
    )


def build_intake_preview(
    *,
    request_kind: str,
    project_key: str,
    objective: str,
    project_context: str,
    constraints_json: str,
    requested_artifacts_json: str,
    linked_attachment_ids_json: str,
    autonomy_mode: str,
) -> dict[str, Any]:
    key, project = _resolve_project(project_key)
    if not project:
        return _result("error", {"project_key": key, "error": "Unknown project."}, "Unknown project.")
    project_path = str(project.get("path") or "")
    try:
        constraints = json.loads(constraints_json or "[]")
        requested_artifacts = json.loads(requested_artifacts_json or "[]")
        linked_attachment_ids = json.loads(linked_attachment_ids_json or "[]")
    except json.JSONDecodeError as exc:
        return _result(
            "error",
            {"project_key": key, "error": f"Invalid preview payload: {exc}"},
            "Invalid preview payload.",
        )
    payload = preview_intake_request_safe(
        request_kind=request_kind,
        project_key=key,
        project_path=project_path,
        objective=objective,
        project_context=project_context,
        constraints=constraints if isinstance(constraints, (dict, list)) else {},
        requested_artifacts=requested_artifacts if isinstance(requested_artifacts, (dict, list)) else {},
        linked_attachment_ids=linked_attachment_ids if isinstance(linked_attachment_ids, list) else [],
        autonomy_mode=autonomy_mode,
    )
    return _result("ok", payload, "")


def upload_attachment(
    *,
    project_key: str,
    file_path: str,
    file_name: str,
    file_type: str,
    source: str,
    purpose: str,
    package_id: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    key, project = _resolve_project(project_key)
    if not project:
        return _result("error", {"project_key": key, "error": "Unknown project."}, "Unknown project.")
    project_path = str(project.get("path") or "")
    result = ingest_console_attachment_safe(
        project_path=project_path,
        project_id=key,
        file_path=file_path,
        file_name=file_name,
        file_type=file_type,
        source=source,
        purpose=purpose,
        package_id=package_id or None,
        request_id=request_id or None,
    )
    return _result(
        "ok" if result.get("status") == "ok" else "error",
        result,
        str(result.get("reason") or ""),
    )


def _find_package_project(package_id: str, project_key: str | None = None) -> tuple[str | None, str | None]:
    if project_key:
        key, project = _resolve_project(project_key)
        if project:
            return key, str(project.get("path") or "")
    for key in sorted(PROJECTS.keys()):
        path = str((PROJECTS.get(key) or {}).get("path") or "")
        if not path:
            continue
        if read_execution_package(path, package_id):
            return key, path
    return None, None


def build_package_snapshot(package_id: str, project_key: str | None = None) -> dict[str, Any]:
    key, project_path = _find_package_project(package_id, project_key=project_key)
    if not key or not project_path:
        return _result(
            "error",
            {"package_id": package_id, "project_key": project_key or "", "error": "Execution package not found."},
            "Execution package not found.",
        )
    detail = (
        run_command(
            "execution_package_details",
            project_path=project_path,
            project_name=key,
            execution_package_id=package_id,
        ).get("payload")
        or {}
    )
    evaluation = (
        run_command(
            "execution_package_evaluation_status",
            project_path=project_path,
            project_name=key,
            execution_package_id=package_id,
        ).get("payload")
        or {}
    )
    local_analysis = (
        run_command(
            "execution_package_local_analysis_status",
            project_path=project_path,
            project_name=key,
            execution_package_id=package_id,
        ).get("payload")
        or {}
    )
    package = read_execution_package(project_path, package_id) or {}
    related_attachments = build_attachment_review_context_safe(
        project_path=project_path,
        package_id=package_id,
        request_id=str(package.get("request_id") or ""),
    )
    journal_rows = list_execution_package_journal_entries(project_path, n=50)
    timeline = []
    for row in journal_rows:
        if row.get("package_id") != package_id:
            continue
        timeline.append(
            {
                "created_at": row.get("created_at") or "",
                "review_status": row.get("review_status") or "",
                "decision_status": row.get("decision_status") or "",
                "eligibility_status": row.get("eligibility_status") or "",
                "release_status": row.get("release_status") or "",
                "handoff_status": row.get("handoff_status") or "",
                "execution_status": row.get("execution_status") or "",
                "evaluation_status": row.get("evaluation_status") or "",
                "local_analysis_status": row.get("local_analysis_status") or "",
            }
        )
    return _result(
        "ok",
        {
            "package_id": package_id,
            "project_key": key,
            "project_path": project_path,
            "review_header": detail.get("review_header") or {},
            "sections": detail.get("sections") or {},
            "evaluation": evaluation.get("evaluation") or {},
            "local_analysis": local_analysis.get("local_analysis") or {},
            "package_json": package,
            "timeline": timeline,
            "review_center": _build_review_center_snapshot(
                package_id=package_id,
                package=package,
                detail=detail,
                evaluation=evaluation.get("evaluation") or {},
                local_analysis=local_analysis.get("local_analysis") or {},
                related_attachments=related_attachments,
            ),
        },
        "",
    )


def _summarize_patch_context(package: dict[str, Any]) -> dict[str, Any]:
    cursor_artifacts = [
        item for item in list(package.get("cursor_bridge_artifacts") or []) if isinstance(item, dict)
    ]
    latest_cursor = cursor_artifacts[-1] if cursor_artifacts else {}
    candidate_paths = [str(item) for item in list(package.get("candidate_paths") or []) if str(item).strip()]
    return {
        "patch_summary": str(latest_cursor.get("patch_summary") or latest_cursor.get("artifact_summary") or ""),
        "changed_files": [str(item) for item in list(latest_cursor.get("changed_files") or []) if str(item).strip()],
        "candidate_paths": candidate_paths[:12],
        "requested_outputs": [str(item) for item in list(package.get("expected_outputs") or []) if str(item).strip()],
    }


def _summarize_returned_artifacts(package: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = []
    runtime_artifacts = [item for item in list(package.get("runtime_artifacts") or []) if isinstance(item, dict)]
    for item in runtime_artifacts[:12]:
        artifacts.append(
            {
                "artifact_type": str(item.get("artifact_type") or "artifact"),
                "summary": str(
                    item.get("artifact_summary")
                    or item.get("patch_summary")
                    or item.get("log_ref")
                    or item.get("artifact")
                    or ""
                ),
                "status": str(item.get("status") or package.get("execution_status") or "recorded"),
                "source": str(item.get("source_runtime") or item.get("actor") or "package"),
            }
        )
    return artifacts


def _summarize_test_results(
    package: dict[str, Any],
    evaluation: dict[str, Any],
    local_analysis: dict[str, Any],
) -> dict[str, Any]:
    execution_receipt = dict(package.get("execution_receipt") or {})
    evaluation_summary = dict(evaluation.get("evaluation_summary") or {})
    local_summary = dict(local_analysis.get("local_analysis_summary") or {})
    return {
        "execution_result_status": str(execution_receipt.get("result_status") or package.get("execution_status") or "pending"),
        "exit_code": execution_receipt.get("exit_code"),
        "log_ref": str(execution_receipt.get("log_ref") or ""),
        "integrity_status": str((package.get("integrity_verification") or {}).get("integrity_status") or "unknown"),
        "evaluation_quality_band": str(evaluation_summary.get("execution_quality_band") or ""),
        "suggested_next_action": str(local_summary.get("suggested_next_action") or ""),
    }


def _build_review_center_snapshot(
    *,
    package_id: str,
    package: dict[str, Any],
    detail: dict[str, Any],
    evaluation: dict[str, Any],
    local_analysis: dict[str, Any],
    related_attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    review_header = dict(detail.get("review_header") or {})
    sections = dict(detail.get("sections") or {})
    return {
        "package_id": package_id,
        "approval_ready_context": {
            "review_status": str(review_header.get("review_status") or package.get("review_status") or "pending"),
            "sealed": bool(review_header.get("sealed")),
            "seal_reason": str(review_header.get("seal_reason") or ""),
            "approval_id_refs": [str(item) for item in list(review_header.get("approval_id_refs") or []) if str(item).strip()],
            "requires_human_approval": bool(review_header.get("requires_human_approval")),
            "decision_status": str(review_header.get("decision_status") or package.get("decision_status") or "pending"),
            "release_status": str(review_header.get("release_status") or package.get("release_status") or "pending"),
            "review_checklist": [str(item) for item in list((sections.get("safety") or {}).get("review_checklist") or []) if str(item).strip()],
        },
        "returned_artifacts": _summarize_returned_artifacts(package),
        "patch_context": _summarize_patch_context(package),
        "test_results": _summarize_test_results(package, evaluation, local_analysis),
        "evaluation_summary": dict(evaluation.get("evaluation_summary") or {}),
        "local_analysis_summary": dict(local_analysis.get("local_analysis_summary") or {}),
        "related_attachments": related_attachments,
    }


def execute_control_action(
    *,
    action: str,
    project_key: str | None,
    confirmed: bool,
    confirmation_text: str,
) -> dict[str, Any]:
    normalized_action = str(action or "").strip().lower()
    policy = ALLOWED_CONTROL_ACTIONS.get(normalized_action)
    if not policy:
        return _result(
            "error",
            {
                "action": normalized_action,
                "allowed_actions": sorted(ALLOWED_CONTROL_ACTIONS.keys()),
                "error": "Action not allowed.",
            },
            "Action not allowed.",
        )
    if not confirmed:
        return _result(
            "error",
            {
                "action": normalized_action,
                "error": "Confirmation required.",
                "required_confirmation_phrase": policy["confirmation_phrase"],
            },
            "Confirmation required.",
        )
    if str(confirmation_text or "").strip() != policy["confirmation_phrase"]:
        return _result(
            "error",
            {
                "action": normalized_action,
                "error": "Confirmation phrase mismatch.",
                "required_confirmation_phrase": policy["confirmation_phrase"],
            },
            "Confirmation phrase mismatch.",
        )
    key, project = _resolve_project(project_key)
    if policy.get("requires_project") and not project:
        return _result(
            "error",
            {
                "action": normalized_action,
                "project_key": key,
                "error": "Known project required.",
            },
            "Known project required.",
        )
    result = run_command(normalized_action, project_path=str(project.get("path") or ""), project_name=key)
    return _result(
        "ok" if result.get("status") == "ok" else "error",
        {
            "action": normalized_action,
            "project_key": key,
            "result": result,
            "surface_mode": "supervised_control",
        },
        result.get("summary") or "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Forge Console bridge")
    parser.add_argument(
        "mode",
        choices=["overview", "project", "package", "control", "intake_preview", "upload_attachment", "client_view"],
    )
    parser.add_argument("--project-key", default="")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--action", default="")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--confirmation-text", default="")
    parser.add_argument("--file-path", default="")
    parser.add_argument("--file-name", default="")
    parser.add_argument("--file-type", default="")
    parser.add_argument("--source", default="console_upload")
    parser.add_argument("--purpose", default="supporting_context")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--request-kind", default="update_request")
    parser.add_argument("--objective", default="")
    parser.add_argument("--project-context", default="")
    parser.add_argument("--constraints-json", default="[]")
    parser.add_argument("--requested-artifacts-json", default="[]")
    parser.add_argument("--linked-attachment-ids-json", default="[]")
    parser.add_argument("--autonomy-mode", default="supervised_build")
    args = parser.parse_args()

    if args.mode == "overview":
        out = _result("ok", build_studio_snapshot())
    elif args.mode == "project":
        out = build_project_snapshot(args.project_key)
    elif args.mode == "package":
        out = build_package_snapshot(args.package_id, project_key=args.project_key or None)
    elif args.mode == "intake_preview":
        out = build_intake_preview(
            request_kind=args.request_kind,
            project_key=args.project_key,
            objective=args.objective,
            project_context=args.project_context,
            constraints_json=args.constraints_json,
            requested_artifacts_json=args.requested_artifacts_json,
            linked_attachment_ids_json=args.linked_attachment_ids_json,
            autonomy_mode=args.autonomy_mode,
        )
    elif args.mode == "upload_attachment":
        out = upload_attachment(
            project_key=args.project_key,
            file_path=args.file_path,
            file_name=args.file_name,
            file_type=args.file_type,
            source=args.source,
            purpose=args.purpose,
            package_id=args.package_id,
            request_id=args.request_id,
        )
    elif args.mode == "client_view":
        out = build_client_view_snapshot(args.project_key or None)
    else:
        out = execute_control_action(
            action=args.action,
            project_key=args.project_key or None,
            confirmed=bool(args.confirmed),
            confirmation_text=args.confirmation_text,
        )
    sys.stdout.write(json.dumps(out, ensure_ascii=False, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
