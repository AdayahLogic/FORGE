"""
NEXUS project onboarding scaffolding.

Creates isolated project folder structure under projects/<name> and writes a
minimal state/project_state.json if missing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.studio_config import PROJECTS_DIR


def _minimal_project_state(project_name: str) -> dict[str, Any]:
    """
    Minimal persisted shape. Callers should tolerate missing fields, but
    validator/logging guardrails may expect these basics.
    """
    return {
        "saved_at": datetime.now().isoformat(),
        "active_project": project_name,
        "notes": "",
        "task_queue": [],
        "task_queue_snapshot": [],
        "review_queue_entry": {},
        "recovery_status": "none",
        "recovery_result": {},
        "scheduler_status": "none",
        "scheduler_result": {},
        "reexecution_status": "none",
        "reexecution_result": {},
        "launch_status": "none",
        "launch_result": {},
        "autonomy_status": "none",
        "autonomy_result": {},
        "autonomy_mode": "supervised_build",
        "autonomy_mode_status": "active",
        "autonomy_mode_reason": "Default safe autonomy mode.",
        "allowed_actions": ["prepare_package", "recommend_next_step", "bounded_low_risk_step"],
        "blocked_actions": ["unbounded_loop", "policy_self_modification", "mode_self_escalation"],
        "escalation_threshold": "low",
        "approval_required_actions": ["decision", "release", "handoff", "execute", "project_switch"],
        "project_routing_status": "idle",
        "project_routing_result": {},
        "guardrail_status": "passed",
        "guardrail_result": {
            "guardrail_status": "passed",
            "guardrail_reason": "Guardrails passed.",
            "launch_allowed": True,
            "recursion_blocked": False,
            "state_repair_recommended": False,
        },
        "runtime_router_result": {},
        "model_router_result": {},
        "deployment_preflight_result": {},
        "last_run_summary": {},
        "last_launch_summary": {},
        "last_recovery_summary": {},
        "last_completion_summary": {},
    }


def create_project_scaffold(
    project_name: str,
    *,
    base_path: str | None = None,
) -> dict[str, Any]:
    """
    Create projects/<project_name> with standard subfolders and a minimal state file.
    """
    try:
        proj = (project_name or "").strip()
        if not proj:
            return {
                "onboarding_status": "error_fallback",
                "project_name": project_name,
                "project_path": None,
                "created_paths": [],
                "reason": "project_name required.",
            }

        root = Path(base_path).resolve() if base_path else PROJECTS_DIR
        project_dir = (root / proj).resolve()
        created_paths: list[str] = []

        if project_dir.exists():
            return {
                "onboarding_status": "already_exists",
                "project_name": proj,
                "project_path": str(project_dir),
                "created_paths": [],
                "reason": "Project directory already exists.",
            }

        # Create root + required subfolders
        project_dir.mkdir(parents=True, exist_ok=True)
        created_paths.append(str(project_dir))

        subfolders = ["docs", "memory", "tasks", "generated", "state", "src"]
        for sub in subfolders:
            p = project_dir / sub
            p.mkdir(parents=True, exist_ok=True)
            created_paths.append(str(p))

        state_file = project_dir / "state" / "project_state.json"
        if not state_file.exists():
            state_file.write_text(json.dumps(_minimal_project_state(proj), indent=2), encoding="utf-8")
            created_paths.append(str(state_file))

        return {
            "onboarding_status": "created",
            "project_name": proj,
            "project_path": str(project_dir),
            "created_paths": created_paths,
            "reason": "Project scaffold created.",
        }
    except Exception as e:
        return {
            "onboarding_status": "error_fallback",
            "project_name": project_name,
            "project_path": None,
            "created_paths": [],
            "reason": str(e),
        }


def create_project_scaffold_safe(project_name: str, *, base_path: str | None = None) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return create_project_scaffold(project_name, base_path=base_path)
    except Exception as e:
        return {
            "onboarding_status": "error_fallback",
            "project_name": project_name,
            "project_path": None,
            "created_paths": [],
            "reason": str(e),
        }

