"""
NEXUS runtime target registry.

Models where work can run: local, cursor, codex, container/remote/cloud workers.
Read-only registry; no actual dispatching or implementation in this step.
"""

from __future__ import annotations

from typing import Any

DISPATCH_READY_REVIEW_TARGETS = {"windows_review_package"}
DISPATCH_UNAVAILABLE_TARGETS = {"openclaw", "openclaw_browser"}

RUNTIME_TARGET_REGISTRY: dict[str, dict[str, Any]] = {
    "local": {
        "canonical_name": "local",
        "display_name": "Local",
        "status": "active",
        "runtime_type": "local",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning"],
        "approval_level": "auto",
        "description": "Local process execution; default in-process runtime.",
    },
    "cursor": {
        "canonical_name": "cursor",
        "display_name": "Cursor",
        "status": "active",
        "runtime_type": "ide",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "approval_level": "human_review",
        "description": "Cursor IDE as execution target; agent and tool execution via Cursor.",
    },
    "codex": {
        "canonical_name": "codex",
        "display_name": "Codex",
        "status": "active",
        "runtime_type": "ide",
        "active_or_planned": "active",
        "capabilities": ["execute", "file_ops", "terminal", "planning", "agent_routing"],
        "approval_level": "human_review",
        "description": "Codex as execution target; agent and tool execution via Codex.",
    },
    "openclaw": {
        "canonical_name": "openclaw",
        "display_name": "OpenClaw",
        "status": "active",
        "runtime_type": "controlled_executor",
        "active_or_planned": "active",
        "capabilities": ["execute", "controlled_executor"],
        "approval_level": "human_review",
        "description": "Controlled executor target for reviewed package execution only.",
    },
    "openclaw_browser": {
        "canonical_name": "openclaw_browser",
        "display_name": "OpenClaw Browser",
        "status": "active",
        "runtime_type": "controlled_executor",
        "active_or_planned": "active",
        "capabilities": ["execute", "controlled_executor", "browser_automation"],
        "approval_level": "human_review",
        "description": "Governed browser executor target for bounded Playwright execution with evidence receipts.",
    },
    "windows_review_package": {
        "canonical_name": "windows_review_package",
        "display_name": "Windows Review Package",
        "status": "active",
        "runtime_type": "local_review",
        "active_or_planned": "active",
        "capabilities": ["review_package", "execution_planning", "approval_handoff"],
        "approval_level": "human_review",
        "description": "Windows-local review-only execution package target; produces sealed packages and stops before execution.",
    },
    "container_worker": {
        "canonical_name": "container_worker",
        "display_name": "Container Worker",
        "status": "planned",
        "runtime_type": "container",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "auto",
        "description": "Containerized worker for isolated execution (planned).",
    },
    "remote_worker": {
        "canonical_name": "remote_worker",
        "display_name": "Remote Worker",
        "status": "planned",
        "runtime_type": "remote",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "human_review",
        "description": "Remote worker node for distributed execution (planned).",
    },
    "cloud_worker": {
        "canonical_name": "cloud_worker",
        "display_name": "Cloud Worker",
        "status": "planned",
        "runtime_type": "cloud",
        "active_or_planned": "planned",
        "capabilities": ["execute", "terminal", "planning"],
        "approval_level": "human_review",
        "description": "Cloud-hosted worker for scalable execution (planned).",
    },
}


def get_runtime_target_entry(canonical_name: str | None) -> dict[str, Any]:
    """Return a normalized registry entry for a runtime target, or {} if unknown."""
    if not canonical_name:
        return {}
    return dict(RUNTIME_TARGET_REGISTRY.get((canonical_name or "").strip().lower()) or {})


def list_active_runtime_targets() -> list[str]:
    """Return canonical names of runtime targets marked active."""
    return sorted(
        name for name, meta in RUNTIME_TARGET_REGISTRY.items()
        if meta.get("active_or_planned") == "active"
    )


def list_planned_runtime_targets() -> list[str]:
    """Return canonical names of runtime targets marked planned."""
    return sorted(
        name for name, meta in RUNTIME_TARGET_REGISTRY.items()
        if meta.get("active_or_planned") == "planned"
    )


def get_target_capabilities(canonical_name: str | None) -> list[str]:
    """Return capabilities list for a runtime target, or [] if unknown."""
    entry = get_runtime_target_entry(canonical_name)
    return list(entry.get("capabilities", [])) if entry else []


def get_runtime_target_health(canonical_name: str | None) -> dict[str, Any]:
    """
    Return additive readiness/availability health for a runtime target.

    This is display and selector support only; it does not execute or dispatch.
    """
    target_id = str(canonical_name or "").strip().lower()
    entry = get_runtime_target_entry(target_id)
    if not entry:
        return {
            "canonical_name": target_id,
            "target_type": "unknown",
            "availability_status": "unknown",
            "readiness_status": "unknown_target",
            "dispatch_ready": False,
            "denial_reason": "unknown_target",
        }

    runtime_type = str(entry.get("runtime_type") or "unknown")
    active_or_planned = str(entry.get("active_or_planned") or entry.get("status") or "planned").strip().lower()
    availability_status = "available" if active_or_planned == "active" else "planned"
    readiness_status = "ready"
    dispatch_ready = True
    denial_reason = ""

    if target_id in DISPATCH_UNAVAILABLE_TARGETS:
        readiness_status = "executor_only"
        dispatch_ready = False
        denial_reason = "target_not_dispatch_ready"
    elif active_or_planned != "active":
        readiness_status = "planned_only"
        dispatch_ready = False
        denial_reason = "target_not_active"
    elif target_id in DISPATCH_READY_REVIEW_TARGETS:
        readiness_status = "review_only_ready"
    else:
        from NEXUS.runtimes import RUNTIME_ADAPTERS

        if target_id not in RUNTIME_ADAPTERS:
            readiness_status = "adapter_missing"
            dispatch_ready = False
            denial_reason = "dispatch_adapter_missing"

    return {
        "canonical_name": target_id,
        "target_type": runtime_type,
        "availability_status": availability_status,
        "readiness_status": readiness_status,
        "dispatch_ready": dispatch_ready,
        "denial_reason": denial_reason,
    }


def get_runtime_target_summary() -> dict[str, Any]:
    """Return a normalized summary of the runtime target registry."""
    active = list_active_runtime_targets()
    planned = list_planned_runtime_targets()
    targets = []
    for name in sorted(RUNTIME_TARGET_REGISTRY.keys()):
        entry = RUNTIME_TARGET_REGISTRY[name]
        health = get_runtime_target_health(name)
        targets.append({
            "canonical_name": entry.get("canonical_name", name),
            "display_name": entry.get("display_name", name),
            "status": entry.get("status"),
            "runtime_type": entry.get("runtime_type"),
            "active_or_planned": entry.get("active_or_planned"),
            "capabilities": list(entry.get("capabilities", [])),
            "approval_level": entry.get("approval_level"),
            "description": entry.get("description", ""),
            "availability_status": health.get("availability_status"),
            "readiness_status": health.get("readiness_status"),
            "dispatch_ready": bool(health.get("dispatch_ready")),
            "denial_reason": health.get("denial_reason"),
        })
    return {
        "active_count": len(active),
        "planned_count": len(planned),
        "active_names": active,
        "planned_names": planned,
        "dispatch_ready_count": sum(1 for item in targets if item.get("dispatch_ready")),
        "unavailable_count": sum(1 for item in targets if not item.get("dispatch_ready")),
        "targets": targets,
    }
