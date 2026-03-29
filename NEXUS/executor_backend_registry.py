"""
Executor backend registry and readiness summary.

This registry is additive and read-only: it reports backend posture, health, and
approval/execution requirements without enabling unsafe behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from NEXUS.execution_receipt_registry import read_execution_receipt_journal_tail
from NEXUS.executor_backends import get_executor_backend_status
from NEXUS.runtime_target_registry import get_runtime_target_entry, get_runtime_target_health


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


EXECUTOR_BACKEND_REGISTRY: dict[str, dict[str, Any]] = {
    "local": {
        "backend_id": "local",
        "executor_target_id": "local",
        "executor_type": "local_runtime_adapter",
        "capabilities": ["execute", "file_ops", "terminal", "planning"],
        "action_classes_supported": ["internal_repo_ops", "local_validation", "simulation_dispatch"],
        "review_only": False,
        "execution_capable": True,
        "safe_execution_modes": ["safe_simulation", "manual_review"],
        "approval_requirements": {"requires_human_review": False, "requires_package_handoff": False},
        "dry_run_posture": "safe_simulation",
        "simulated_posture": "simulated_execution",
        "live_posture": "bounded_local_only",
        "operator_review_required": False,
    },
    "cursor": {
        "backend_id": "cursor",
        "executor_target_id": "cursor",
        "executor_type": "ide_bridge",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "action_classes_supported": ["repo_editing", "bridge_handoff", "simulation_dispatch"],
        "review_only": False,
        "execution_capable": True,
        "safe_execution_modes": ["manual_review", "bridge_handoff"],
        "approval_requirements": {"requires_human_review": True, "requires_package_handoff": True},
        "dry_run_posture": "bridge_simulation",
        "simulated_posture": "simulated_execution",
        "live_posture": "handoff_only",
        "operator_review_required": True,
    },
    "codex": {
        "backend_id": "codex",
        "executor_target_id": "codex",
        "executor_type": "ide_bridge",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "action_classes_supported": ["repo_editing", "bridge_handoff", "simulation_dispatch"],
        "review_only": False,
        "execution_capable": True,
        "safe_execution_modes": ["manual_review", "bridge_handoff"],
        "approval_requirements": {"requires_human_review": True, "requires_package_handoff": True},
        "dry_run_posture": "bridge_simulation",
        "simulated_posture": "simulated_execution",
        "live_posture": "handoff_only",
        "operator_review_required": True,
    },
    "openclaw": {
        "backend_id": "openclaw",
        "executor_target_id": "openclaw",
        "executor_type": "controlled_executor_backend",
        "capabilities": ["execute", "controlled_executor", "execution_receipt"],
        "action_classes_supported": ["controlled_runtime_execution", "package_execution"],
        "review_only": False,
        "execution_capable": True,
        "safe_execution_modes": ["reviewed_package_execution", "manual_review"],
        "approval_requirements": {"requires_human_review": True, "requires_package_handoff": True},
        "dry_run_posture": "reviewed_package_only",
        "simulated_posture": "manual_review",
        "live_posture": "controlled_executor",
        "operator_review_required": True,
    },
    "windows_review_package": {
        "backend_id": "windows_review_package",
        "executor_target_id": "windows_review_package",
        "executor_type": "review_package_handler",
        "capabilities": ["review_package", "approval_handoff", "execution_planning"],
        "action_classes_supported": ["review_packaging", "approval_queueing"],
        "review_only": True,
        "execution_capable": False,
        "safe_execution_modes": ["review_only", "manual_review"],
        "approval_requirements": {"requires_human_review": True, "requires_package_handoff": False},
        "dry_run_posture": "review_only",
        "simulated_posture": "queued_for_review",
        "live_posture": "not_applicable",
        "operator_review_required": True,
    },
    "container_worker": {
        "backend_id": "container_worker",
        "executor_target_id": "container_worker",
        "executor_type": "planned_container_executor",
        "capabilities": ["execute", "terminal", "planning"],
        "action_classes_supported": ["planned_isolated_execution"],
        "review_only": False,
        "execution_capable": False,
        "safe_execution_modes": ["planned_only"],
        "approval_requirements": {"requires_human_review": True, "requires_package_handoff": True},
        "dry_run_posture": "planned_only",
        "simulated_posture": "planned_only",
        "live_posture": "disabled",
        "operator_review_required": True,
    },
}


def _entry_for_target(target_id: str) -> dict[str, Any]:
    base = EXECUTOR_BACKEND_REGISTRY.get(target_id) or {}
    if base:
        return dict(base)
    entry = get_runtime_target_entry(target_id)
    if not entry:
        return {}
    return {
        "backend_id": target_id,
        "executor_target_id": target_id,
        "executor_type": str(entry.get("runtime_type") or "runtime_target"),
        "capabilities": [str(x) for x in list(entry.get("capabilities") or []) if str(x).strip()],
        "action_classes_supported": ["runtime_target_dispatch"],
        "review_only": False,
        "execution_capable": bool("execute" in list(entry.get("capabilities") or [])),
        "safe_execution_modes": ["manual_review"],
        "approval_requirements": {
            "requires_human_review": str(entry.get("approval_level") or "").strip().lower() == "human_review",
            "requires_package_handoff": True,
        },
        "dry_run_posture": "safe_simulation",
        "simulated_posture": "simulated_execution",
        "live_posture": "unknown",
        "operator_review_required": True,
    }


def _readiness_from_target_health(target_health: dict[str, Any], *, review_only: bool, execution_capable: bool) -> tuple[str, dict[str, Any]]:
    readiness_status = _text(target_health.get("readiness_status")).lower() or "unknown"
    dispatch_ready = bool(target_health.get("dispatch_ready"))
    if review_only:
        return ("review_only_ready" if dispatch_ready else "review_only_degraded", {"dispatch_ready": dispatch_ready})
    if not execution_capable:
        return ("planned_only", {"dispatch_ready": dispatch_ready})
    if readiness_status in {"ready"} and dispatch_ready:
        return ("ready", {"dispatch_ready": True})
    if readiness_status in {"executor_only"}:
        return ("handoff_only", {"dispatch_ready": False})
    if readiness_status in {"planned_only"}:
        return ("planned_only", {"dispatch_ready": False})
    return ("degraded", {"dispatch_ready": dispatch_ready})


def build_executor_backend_status(
    *,
    backend_id: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    target_id = _text(backend_id).lower()
    if not target_id:
        return {
            "backend_status": "error",
            "reason": "backend_id is required.",
            "backend": {},
        }
    base = _entry_for_target(target_id)
    if not base:
        return {
            "backend_status": "error",
            "reason": "Unknown executor backend.",
            "backend": {"backend_id": target_id},
        }
    target_health = get_runtime_target_health(base.get("executor_target_id") or target_id)
    runtime_entry = get_runtime_target_entry(base.get("executor_target_id") or target_id)
    review_only = bool(base.get("review_only"))
    execution_capable = bool(base.get("execution_capable"))
    readiness_state, readiness_meta = _readiness_from_target_health(
        target_health,
        review_only=review_only,
        execution_capable=execution_capable,
    )

    backend_health = {}
    if target_id == "openclaw":
        backend_health = get_executor_backend_status("openclaw")
        adapter_status = _text(backend_health.get("adapter_status")).lower() or "inactive"
        if adapter_status == "active" and readiness_state in {"ready", "handoff_only"}:
            readiness_state = "ready"
        elif adapter_status in {"inactive", "error"}:
            readiness_state = "degraded"

    last_success_at = ""
    last_failure_at = ""
    if project_path:
        rows = read_execution_receipt_journal_tail(project_path=project_path, n=200)
        for row in reversed(rows):
            if _text(row.get("executor_target_id")).lower() != target_id and _text(row.get("executor_backend_id")).lower() != target_id:
                continue
            status = _text(row.get("execution_status")).lower()
            finished_at = _text(row.get("execution_finished_at") or row.get("recorded_at"))
            if not last_success_at and status in {"succeeded", "completed"}:
                last_success_at = finished_at
            if not last_failure_at and status in {"failed", "blocked", "rolled_back"}:
                last_failure_at = finished_at
            if last_success_at and last_failure_at:
                break

    backend = {
        **base,
        "runtime_type": _text(runtime_entry.get("runtime_type") or target_health.get("target_type") or "unknown"),
        "readiness_state": readiness_state,
        "last_known_health": {
            "availability_status": _text(target_health.get("availability_status")) or "unknown",
            "readiness_status": _text(target_health.get("readiness_status")) or "unknown",
            "denial_reason": _text(target_health.get("denial_reason")),
            **readiness_meta,
            "adapter_status": _text(backend_health.get("adapter_status") or ""),
        },
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "safe_to_execute": readiness_state == "ready" and not review_only and execution_capable,
        "recorded_at": _now_iso(),
    }
    return {"backend_status": "ok", "reason": "Executor backend status resolved.", "backend": backend}


def build_executor_backend_registry_summary(*, project_path: str | None = None) -> dict[str, Any]:
    backend_ids = sorted(set(EXECUTOR_BACKEND_REGISTRY.keys()))
    backends: list[dict[str, Any]] = []
    for backend_id in backend_ids:
        status = build_executor_backend_status(backend_id=backend_id, project_path=project_path)
        backends.append(dict(status.get("backend") or {"backend_id": backend_id}))
    ready_count = sum(1 for row in backends if bool(row.get("safe_to_execute")))
    review_only_count = sum(1 for row in backends if bool(row.get("review_only")))
    degraded_count = sum(1 for row in backends if _text(row.get("readiness_state")) in {"degraded", "planned_only", "review_only_degraded"})
    return {
        "backend_registry_status": "ok",
        "backend_count": len(backends),
        "ready_count": ready_count,
        "review_only_count": review_only_count,
        "degraded_count": degraded_count,
        "backends": backends,
    }

