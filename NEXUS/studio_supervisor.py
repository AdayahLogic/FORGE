from pathlib import Path
from datetime import datetime
from NEXUS.registry import PROJECTS
from NEXUS.project_state import load_project_state


def count_task_statuses(task_queue: list) -> tuple[int, int]:
    completed = 0
    pending = 0

    for task in task_queue:
        if task.get("status") == "completed":
            completed += 1
        elif task.get("status") == "pending":
            pending += 1

    return completed, pending


def summarize_all_projects() -> list[dict]:
    summaries = []

    for project_key, project_data in PROJECTS.items():
        project_name = project_data.get("name", project_key)
        project_path = project_data.get("path", "")
        workspace_type = project_data.get("workspace_type", "internal")

        state = load_project_state(project_path)

        if state:
            task_queue = state.get("task_queue", [])
            completed, pending = count_task_statuses(task_queue)

            recommended_action = (
                "continue_development_cycle" if pending > 0 else "review_or_expand_scope"
            )

            summaries.append({
                "project_key": project_key,
                "project_name": project_name,
                "project_path": project_path,
                "workspace_type": workspace_type,
                "has_state": True,
                "saved_at": state.get("saved_at", "unknown"),
                "completed_tasks": completed,
                "pending_tasks": pending,
                "recommended_action": recommended_action,
                "latest_notes": state.get("notes", "none"),
            })
        else:
            summaries.append({
                "project_key": project_key,
                "project_name": project_name,
                "project_path": project_path,
                "workspace_type": workspace_type,
                "has_state": False,
                "saved_at": "none",
                "completed_tasks": 0,
                "pending_tasks": 0,
                "recommended_action": "initialize_project_cycle",
                "latest_notes": "No saved state found.",
            })

    return summaries


def choose_priority_project(summary: list[dict]) -> str:
    # Priority rule:
    # 1. highest pending task count
    # 2. otherwise first project needing initialization
    # 3. otherwise first project in list
    if not summary:
        return "none"

    with_pending = [p for p in summary if p.get("pending_tasks", 0) > 0]
    if with_pending:
        with_pending.sort(key=lambda x: x.get("pending_tasks", 0), reverse=True)
        return with_pending[0]["project_name"]

    uninitialized = [p for p in summary if not p.get("has_state")]
    if uninitialized:
        return uninitialized[0]["project_name"]

    return summary[0]["project_name"]


def write_studio_supervisor_report(summary: list[dict], logs_dir: str = "logs") -> str:
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    report_file = logs_path / "studio_supervisor_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    priority_project = choose_priority_project(summary)

    lines = [
        "Studio Supervisor Report",
        f"Timestamp: {timestamp}",
        "",
        f"Priority Project: {priority_project}",
        "",
        "Project Summary:",
    ]

    for item in summary:
        lines.extend([
            f"- Project: {item['project_name']} ({item['project_key']})",
            f"  Path: {item['project_path']}",
            f"  Workspace Type: {item['workspace_type']}",
            f"  Has State: {item['has_state']}",
            f"  Saved At: {item['saved_at']}",
            f"  Completed Tasks: {item['completed_tasks']}",
            f"  Pending Tasks: {item['pending_tasks']}",
            f"  Recommended Action: {item['recommended_action']}",
            f"  Latest Notes: {item['latest_notes']}",
            "",
        ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)