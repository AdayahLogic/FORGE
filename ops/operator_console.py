"""
Lightweight operator console for NEXUS.

Since Streamlit may not be installed in all environments, this module provides
two entrypoints:
  - Streamlit app (used only if streamlit is available)
  - Text console fallback

The console reuses command/dashboard/state helpers and does not duplicate
kernel logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    # Ensure `import NEXUS` works when running `python ops/operator_console.py`.
    sys.path.insert(0, str(_REPO_ROOT))


def _try_get_streamlit():
    try:
        import streamlit as st  # type: ignore

        return st
    except Exception:
        return None


def _text_console(snapshot: dict[str, Any]) -> None:
    studio_coord = snapshot.get("studio_coordination_summary") or {}
    driver = snapshot.get("studio_driver_summary") or {}
    registered_projects = snapshot.get("registered_projects") or snapshot.get("projects_table") or []
    scaffolded_unregistered_projects = snapshot.get("scaffolded_unregistered_projects") or []
    log_tail = snapshot.get("log_tail_records") or []

    print("\n=== Studio Overview ===")
    print("Coordination:", studio_coord.get("coordination_status"))
    print("Priority project:", studio_coord.get("priority_project"))
    print("Driver:", driver.get("driver_status"), "action:", driver.get("driver_action"))

    print("\n=== Projects Overview ===")
    for row in registered_projects:
        line = (
            f"- {row.get('project')}: lifecycle={row.get('lifecycle_status')}, "
            f"queue={row.get('queue_status')}, recovery={row.get('recovery_status')}, "
            f"scheduler={row.get('scheduler_status')}, autonomy={row.get('autonomy_status')}, "
            f"launch={row.get('launch_status')}, deploy_preflight={row.get('deployment_preflight_status')}"
        )
        if row.get("priority_project"):
            line = "[PRIORITY] " + line
        print(line)

    if scaffolded_unregistered_projects:
        print("\n=== Scaffolded But Unregistered Projects (under projects/) ===")
        for row in scaffolded_unregistered_projects:
            missing = row.get("scaffold_missing") or []
            sf = row.get("state_file_exists")
            state_note = "state_ok" if sf else "no_state_file"
            missing_note = f"missing={','.join(missing)}" if missing else "scaffolds_ok"
            print(f"- {row.get('project')}: {state_note}; {missing_note} (NOT in registry)")

    print("\n=== PRISM v1 ===")
    try:
        from NEXUS.command_surface import run_command as _run_command

        priority_project = studio_coord.get("priority_project") or driver.get("target_project") or "jarvis"
        prism = _run_command("prism_status", project_name=str(priority_project))
        payload = prism.get("payload") or {}
        scores = payload.get("scores") or {}
        friction = payload.get("audience_friction_points") or []

        print("Recommendation:", payload.get("recommendation"))
        print("Success estimate:", scores.get("success_estimate"))
        print("Strongest audience segment:", payload.get("strongest_audience_segment"))
        print("Strongest launch angle:", payload.get("strongest_launch_angle"))
        print("Audience friction points:", "; ".join([str(x) for x in friction[:6]]) if friction else "(none)")
    except Exception:
        print("(PRISM unavailable)")

    print("\n=== Action Panel (available commands) ===")
    print("complete_review, complete_approval")
    print("launch_next_cycle, autonomous_cycle")
    print("launch_studio_cycle, autonomous_studio_cycle")
    print("runtime_route, model_route, deployment_preflight")
    print("project_onboard")
    print("self_improvement_backlog, improve_system")
    print("change_gate, regression_check")

    print("\n=== Elite Layers ===")
    print("titan_status, leviathan_status, helios_status")
    print("veritas_status, sentinel_status, elite_systems_snapshot")

    print("\n=== PRISM Actions ===")
    print("prism_evaluate, prism_status")

    print("\n=== Log Tail (forge_operations.jsonl) ===")
    if not log_tail:
        print("(no log tail available)")
    else:
        for rec in log_tail[-5:]:
            if isinstance(rec, dict):
                print(json.dumps(rec, ensure_ascii=False)[:700])
            else:
                print(str(rec)[:700])


def run_operator_console() -> None:
    """
    Text console entrypoint.
    For UI actions, run via CLI args:
      python ops/operator_console.py --action <cmd> --project <name>
    """
    st = _try_get_streamlit()
    if st is not None:
        _run_streamlit(st)
        return

    from NEXUS.command_surface import run_command

    action = None
    project = None
    tail = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--action" and i + 1 < len(args):
            action = args[i + 1].strip().lower()
            i += 2
            continue
        if args[i] == "--project" and i + 1 < len(args):
            project = args[i + 1].strip().lower()
            i += 2
            continue
        if args[i] == "--tail" and i + 1 < len(args):
            try:
                tail = int(args[i + 1])
            except Exception:
                tail = None
            i += 2
            continue
        i += 1

    if action:
        payload = run_command(action, project_name=project, tail=tail)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    snapshot = run_command("operator_snapshot", tail=tail)
    _text_console(snapshot.get("payload") or {})


def _run_streamlit(st: Any) -> None:
    """
    Streamlit operator console. Uses command_surface for actions.
    """
    from NEXUS.command_surface import run_command

    st.set_page_config(page_title="NEXUS Operator Console", layout="wide")
    tail = st.sidebar.number_input("Log tail count", min_value=1, max_value=50, value=10, step=1)

    st.sidebar.markdown(
        "### Elite Layers (Phase 6)\n"
        "- TITAN: `titan_status`\n"
        "- LEVIATHAN: `leviathan_status`\n"
        "- HELIOS: `helios_status`\n"
        "- VERITAS: `veritas_status`\n"
        "- SENTINEL: `sentinel_status`\n"
        "- Snapshot: `elite_systems_snapshot`"
    )

    st.sidebar.markdown(
        "### PRISM v1 (Phase 7)\n"
        "- Evaluate: `prism_evaluate`\n"
        "- Status: `prism_status`"
    )

    action = st.sidebar.selectbox(
        "Action",
        [
            "operator_snapshot_only",
            "complete_review",
            "complete_approval",
            "project_onboard",
            "self_improvement_backlog",
            "improve_system",
            "change_gate",
            "regression_check",
            # Elite capability layers (Phase 6)
            "titan_status",
            "leviathan_status",
            "helios_status",
            "veritas_status",
            "sentinel_status",
            "elite_systems_snapshot",
            # PRISM v1 (Phase 7)
            "prism_evaluate",
            "prism_status",
            "runtime_route",
            "model_route",
            "deployment_preflight",
            "launch_next_cycle",
            "autonomous_cycle",
            "launch_studio_cycle",
            "autonomous_studio_cycle",
        ],
    )

    project = st.sidebar.text_input("Project (for project-scoped actions)", value="jarvis")

    if action == "operator_snapshot_only":
        snapshot = run_command("operator_snapshot", tail=int(tail))
        st.json(snapshot.get("payload") or {})
        return

    studio_scoped_actions = {"autonomous_studio_cycle", "launch_studio_cycle"}
    if action in studio_scoped_actions:
        result = run_command(action)
    else:
        result = run_command(action, project_name=project)

    st.subheader("Action Result")
    st.json(result)


if __name__ == "__main__":
    run_operator_console()

