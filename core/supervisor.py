from pathlib import Path
from datetime import datetime


def build_supervisor_decision(active_project: str | None, previous_run_state: dict, task_queue: list) -> dict:
    completed = 0
    pending = 0

    for task in task_queue:
        if task.get("status") == "completed":
            completed += 1
        elif task.get("status") == "pending":
            pending += 1

    if pending > 0:
        recommended_action = "continue_development_cycle"
        proceed = True
        reason = "There are still pending tasks in the current project queue."
    else:
        recommended_action = "review_or_expand_scope"
        proceed = True
        reason = "No pending tasks remain; project is ready for review or next-scope planning."

    previous_saved_at = previous_run_state.get("saved_at", "none")
    previous_notes = previous_run_state.get("notes", "none")

    return {
        "active_project": active_project,
        "completed_tasks": completed,
        "pending_tasks": pending,
        "previous_saved_at": previous_saved_at,
        "previous_notes": previous_notes,
        "recommended_action": recommended_action,
        "proceed_with_cycle": proceed,
        "reason": reason,
    }


def write_supervisor_report(project_path: str, decision: dict) -> str:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)

    report_file = generated_path / "supervisor_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Supervisor Report",
        f"Timestamp: {timestamp}",
        f"Project: {decision.get('active_project')}",
        "",
        "Decision Summary:",
        f"- completed_tasks: {decision.get('completed_tasks')}",
        f"- pending_tasks: {decision.get('pending_tasks')}",
        f"- previous_saved_at: {decision.get('previous_saved_at')}",
        f"- previous_notes: {decision.get('previous_notes')}",
        f"- recommended_action: {decision.get('recommended_action')}",
        f"- proceed_with_cycle: {decision.get('proceed_with_cycle')}",
        "",
        "Reason:",
        decision.get("reason", "No reason provided."),
    ]

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)