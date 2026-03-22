"""
NEXUS runtime target selection layer.

Chooses a runtime target from agent_name, tool_name, action_type, task_type,
and optional sensitivity/review context. Returns a normalized selection decision.
No actual dispatch; selection logic only.
"""

from __future__ import annotations

from typing import Any

from NEXUS.runtime_target_registry import (
    RUNTIME_TARGET_REGISTRY,
    list_active_runtime_targets,
)


DEFAULT_FALLBACK_TARGET = "local"


def _is_planned(canonical_name: str) -> bool:
    entry = RUNTIME_TARGET_REGISTRY.get((canonical_name or "").strip().lower())
    return (entry or {}).get("active_or_planned") == "planned"


def _resolve_to_active(target: str) -> str:
    """If target is planned, return safe active fallback; else return target."""
    if not _is_planned(target):
        return target
    active = list_active_runtime_targets()
    return active[0] if active else DEFAULT_FALLBACK_TARGET


def _approval_implies_review(canonical_name: str) -> bool:
    entry = RUNTIME_TARGET_REGISTRY.get((canonical_name or "").strip().lower())
    return (entry or {}).get("approval_level") == "human_review"


def select_runtime_target(
    agent_name: str | None = None,
    tool_name: str | None = None,
    action_type: str | None = None,
    task_type: str | None = None,
    sensitivity: str | None = None,
    review_context: str | None = None,
) -> dict[str, Any]:
    """
    Select a runtime target from the given inputs.

    Returns: selected_target, fallback_target, selection_status, review_required,
    reason, inputs_considered.

    Safe defaults: planning/general → local; repo-aware code editing → cursor;
    code generation/refactor drafting → codex; isolated (planned) → fallback local;
    unknown → local.
    """
    inputs_considered: dict[str, Any] = {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "action_type": action_type,
        "task_type": task_type,
        "sensitivity": sensitivity,
        "review_context": review_context,
    }
    agent = (agent_name or "").strip().lower()
    tool = (tool_name or "").strip().lower()
    action = (action_type or "").strip().lower()
    task = (task_type or "").strip().lower()

    ideal: str = DEFAULT_FALLBACK_TARGET
    reason = "Default: local."

    # Repo-aware code editing → cursor
    if tool in ("file_modification", "diff_patch") or action in ("edit_file", "patch", "apply_patch"):
        ideal = "cursor"
        reason = "Repo-aware code editing; target cursor."
    # Code generation / refactor drafting → codex (coder agent, non-file tool or generic)
    elif agent in ("coder",) and tool not in ("file_modification", "diff_patch"):
        ideal = "codex"
        reason = "Code generation/refactor drafting; target codex."
    # Coder with file tools already handled as cursor
    # Planning / general workflow → local
    elif agent in ("architect", "planner") or task in ("planning", "plan") or action in ("plan", "planning"):
        ideal = "local"
        reason = "Planning or general workflow; target local."
    elif task in ("review_package", "execution_package") or action in ("review_package", "package_for_review"):
        ideal = "windows_review_package"
        reason = "Review-only execution package requested; target windows_review_package."
    # Isolated execution (planned targets) → container_worker ideal, then fallback
    elif task in ("isolated", "container") or action in ("isolated", "container"):
        ideal = "container_worker"
        reason = "Isolated execution requested; container_worker is planned, will use active fallback."
    # Tester, docs, executor, workspace, operator, supervisor → local (or cursor if file-heavy; keep simple)
    elif agent in ("tester", "docs", "executor", "workspace", "operator", "supervisor"):
        ideal = "local"
        reason = f"Agent '{agent}' default to local."
    # Unknown
    else:
        reason = "Unknown case; default local."

    # If ideal is planned, use active fallback as selected_target and record ideal as fallback_target
    fallback_target = ideal
    selected_target = _resolve_to_active(ideal)
    if _is_planned(ideal):
        selection_status = "fallback_planned"
        reason += " Ideal target is planned; using active fallback."
        fallback_target = ideal
    else:
        selection_status = "selected"
        fallback_target = DEFAULT_FALLBACK_TARGET

    review_required = _approval_implies_review(selected_target)
    if review_context or (sensitivity and str(sensitivity).strip().lower() in ("high", "review")):
        review_required = True

    return {
        "selected_target": selected_target,
        "fallback_target": fallback_target,
        "selection_status": selection_status,
        "review_required": review_required,
        "reason": reason.strip(),
        "inputs_considered": inputs_considered,
    }


def get_selection_defaults_summary() -> dict[str, Any]:
    """Return a short summary of selection defaults/mappings for dashboard or docs."""
    return {
        "default_fallback": DEFAULT_FALLBACK_TARGET,
        "mappings": [
            {"inputs": "planning, general workflow", "target": "local"},
            {"inputs": "repo-aware code editing (file_modification, diff_patch)", "target": "cursor"},
            {"inputs": "code generation / refactor drafting (coder)", "target": "codex"},
            {"inputs": "review-only execution package", "target": "windows_review_package"},
            {"inputs": "isolated execution", "target": "container_worker (planned; fallback local)"},
            {"inputs": "unknown", "target": "local"},
        ],
    }
