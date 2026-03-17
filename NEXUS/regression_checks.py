"""
NEXUS regression checks (planning/safety only).

Runs compact internal import/compatibility checks to validate that
self-improvement planning won't break core interfaces.
"""

from __future__ import annotations

from typing import Any


def run_regression_checks(
    *,
    project_name: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Stable shape:
    {
      regression_status,
      regression_reason,
      checks: {
        workflow_compile,
        command_surface,
        dashboard_summary,
        project_state_compatibility
      }
    }
    """
    checks = {
        "workflow_compile": False,
        "command_surface": False,
        "dashboard_summary": False,
        "project_state_compatibility": False,
    }
    reason_parts: list[str] = []

    # 1) workflow_compile: import-only (no execution)
    try:
        from NEXUS.workflow import build_workflow  # noqa: F401
        checks["workflow_compile"] = callable(build_workflow)
        if not checks["workflow_compile"]:
            reason_parts.append("build_workflow not callable.")
    except Exception as e:
        checks["workflow_compile"] = False
        reason_parts.append(f"workflow import failed: {e}")

    # 2) command_surface callable
    try:
        from NEXUS.command_surface import run_command  # noqa: F401
        checks["command_surface"] = callable(run_command)
    except Exception:
        checks["command_surface"] = False
        reason_parts.append("command_surface import failed.")

    # 3) dashboard summary build
    try:
        from NEXUS.registry_dashboard import build_registry_dashboard_summary

        dash = build_registry_dashboard_summary()
        checks["dashboard_summary"] = isinstance(dash, dict) and bool(dash.get("studio_name"))
    except Exception as e:
        checks["dashboard_summary"] = False
        reason_parts.append(f"dashboard build failed: {e}")

    # 4) project_state load compatibility
    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.project_state import load_project_state

        path = project_path
        if not path and project_name:
            key = str(project_name).strip().lower()
            if key in PROJECTS:
                path = PROJECTS[key].get("path")
        if not path:
            path = PROJECTS.get("jarvis", {}).get("path")

        if path:
            loaded = load_project_state(path)
            checks["project_state_compatibility"] = isinstance(loaded, dict) and "load_error" not in loaded
        else:
            checks["project_state_compatibility"] = False
            reason_parts.append("No project path available for compatibility check.")
    except Exception as e:
        checks["project_state_compatibility"] = False
        reason_parts.append(f"project_state load failed: {e}")

    any_false = any(not v for v in checks.values())
    if not any_false:
        return {
            "regression_status": "passed",
            "regression_reason": "All regression checks passed.",
            "checks": checks,
        }

    # If workflow/command_surface are broken, treat as blocked.
    critical_false = (not checks["workflow_compile"]) or (not checks["command_surface"])
    if critical_false:
        return {
            "regression_status": "blocked",
            "regression_reason": "Critical regression checks failed: " + "; ".join(reason_parts),
            "checks": checks,
        }

    return {
        "regression_status": "warning",
        "regression_reason": "Non-critical regression checks failed: " + "; ".join(reason_parts),
        "checks": checks,
    }


def run_regression_checks_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return run_regression_checks(**kwargs)
    except Exception:
        return {
            "regression_status": "error_fallback",
            "regression_reason": "Regression checks failed to run.",
            "checks": {
                "workflow_compile": False,
                "command_surface": False,
                "dashboard_summary": False,
                "project_state_compatibility": False,
            },
        }

