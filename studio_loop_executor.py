from __future__ import annotations

from typing import Any


def execute_selected_path(
    *,
    selected_path: str,
    selected_project: str | None,
    dashboard_summary: dict[str, Any] | None = None,
    helios_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    portfolio_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute exactly one bounded follow-through action for the selected path.

    Supported paths:
      - helios_proposal_review
      - project_cycle
      - genesis_generation
    """
    from NEXUS.registry import PROJECTS
    from NEXUS.project_state import load_project_state

    dash = dashboard_summary or {}
    coord = (dash.get("studio_coordination_summary") or {}) if isinstance(dash.get("studio_coordination_summary"), dict) else {}
    studio_driver = studio_driver_summary or (dash.get("studio_driver_summary") or {}) if isinstance(dash.get("studio_driver_summary"), dict) else {}
    studio_helios = helios_summary or (dash.get("helios_summary") or {}) if isinstance(dash.get("helios_summary"), dict) else {}
    port = portfolio_summary or (dash.get("portfolio_summary") or {}) if isinstance(dash.get("portfolio_summary"), dict) else {}

    proj = selected_project or coord.get("priority_project") or port.get("priority_project") or "jarvis"
    proj_key = str(proj).strip().lower() if proj else "jarvis"

    driver_action = str((studio_driver or {}).get("driver_action") or "").strip().lower()
    execution_permitted = bool((studio_driver or {}).get("execution_permitted", False))

    if selected_path == "helios_proposal_review":
        proposal = studio_helios.get("change_proposal") if isinstance(studio_helios, dict) else {}
        executed_result_summary = {
            "proposal_id": (proposal or {}).get("proposal_id"),
            "target_area": (proposal or {}).get("target_area"),
            "change_type": (proposal or {}).get("change_type"),
            "scope_level": (proposal or {}).get("scope_level"),
            "risk_level": (proposal or {}).get("risk_level"),
            "requires_review": (proposal or {}).get("requires_review"),
            "requires_regression_check": (proposal or {}).get("requires_regression_check"),
            "recommended_path": (proposal or {}).get("recommended_path"),
            "blocked_by_count": len((proposal or {}).get("blocked_by") or []),
        }
        return {
            "executed_command": "helios_proposal_review",
            "execution_started": False,
            "executed_result_summary": executed_result_summary,
        }

    if selected_path == "project_cycle":
        # Explicit permission check (fail-closed).
        driver_allows_cycle = execution_permitted and driver_action in ("run_priority_project", "resume_priority_project")
        if not driver_allows_cycle:
            return {
                "executed_command": None,
                "execution_started": False,
                "executed_result_summary": {
                    "gated": True,
                    "driver_action": driver_action,
                    "execution_permitted": execution_permitted,
                },
            }

        proj_path = (PROJECTS.get(proj_key) or {}).get("path") if proj_key else None
        if not proj_path:
            return {
                "executed_command": None,
                "execution_started": False,
                "executed_result_summary": {"error": "project_path_missing", "project_key": proj_key},
            }

        loaded = load_project_state(proj_path)
        if loaded.get("load_error"):
            return {
                "executed_command": None,
                "execution_started": False,
                "executed_result_summary": {"error": loaded.get("load_error") or "load_error"},
            }

        from NEXUS.autonomous_launcher import launch_project_cycle

        launch_result = launch_project_cycle(
            project_path=proj_path,
            project_name=proj_key,
            project_state=loaded,
        )
        return {
            "executed_command": "project_cycle",
            "execution_started": bool(launch_result.get("execution_started", False)),
            "executed_result_summary": {
                "launch_status": launch_result.get("launch_status"),
                "launch_action": launch_result.get("launch_action"),
                "launch_reason": launch_result.get("launch_reason"),
                "target_project": launch_result.get("target_project"),
                "bounded_execution": bool(launch_result.get("bounded_execution", True)),
            },
        }

    if selected_path == "genesis_generation":
        from elite_layers.genesis_engine import build_genesis_engine_safe

        proj_path = (PROJECTS.get(proj_key) or {}).get("path") if proj_key else None
        if not proj_path:
            return {
                "executed_command": None,
                "execution_started": False,
                "executed_result_summary": {"error": "project_path_missing", "project_key": proj_key},
            }

        loaded = load_project_state(proj_path)
        if loaded.get("load_error"):
            return {
                "executed_command": None,
                "execution_started": False,
                "executed_result_summary": {"error": loaded.get("load_error") or "load_error"},
            }

        # Single evaluation step: rank candidates (also covers generation when needed).
        genesis_res = build_genesis_engine_safe(
            genesis_mode="rank",
            project_state=loaded,
            project_name=proj_key,
            n_ideas=4,
            ideas=[],
        )
        ranking = genesis_res.get("ranking") or []
        top = ranking[0] if ranking and isinstance(ranking[0], dict) else {}

        return {
            "executed_command": "genesis_rank",
            "execution_started": False,
            "executed_result_summary": {
                "genesis_status": genesis_res.get("genesis_status"),
                "ranking_confidence": genesis_res.get("ranking_confidence"),
                "top_total_score": top.get("total_score"),
                "ranking_len": len(ranking) if isinstance(ranking, list) else None,
            },
        }

    return {
        "executed_command": None,
        "execution_started": False,
        "executed_result_summary": {"error": "unknown_selected_path", "selected_path": selected_path},
    }


def execute_selected_path_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return execute_selected_path(**kwargs)
    except Exception as e:
        return {
            "executed_command": None,
            "execution_started": False,
            "executed_result_summary": {"error": f"studio_loop_executor_failed: {e}"},
        }

