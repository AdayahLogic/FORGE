from pathlib import Path
from datetime import datetime

from NEXUS.path_utils import to_studio_relative_path


def write_docs_update(
    project_path: str,
    project_name: str,
    architect_plan: dict | None,
    task_queue: list,
    coder_output_path: str | None,
    test_report_path: str | None,
) -> str:

    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)

    docs_file = generated_path / "docs_update.txt"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    completed = 0
    pending = 0

    for task in task_queue:
        if task.get("status") == "completed":
            completed += 1
        elif task.get("status") == "pending":
            pending += 1

    lines = [
        "AI Studio Documentation Update",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Execution Summary:",
        f"- coder_output_path: {to_studio_relative_path(coder_output_path)}",
        f"- test_report_path: {to_studio_relative_path(test_report_path)}",
        "",
        "Task Status:",
        f"- completed_tasks: {completed}",
        f"- pending_tasks: {pending}",
        "",
        "Architect Objective:",
    ]

    if architect_plan:
        lines.append(architect_plan.get("objective", "No objective provided"))
    else:
        lines.append("No objective provided")

    lines.extend([
        "",
        "Remaining Tasks:",
    ])

    for task in task_queue:
        if task.get("status") == "pending":
            lines.append(f"- {task['task']}")

    lines.extend([
        "",
        "Completed Tasks:",
    ])

    for task in task_queue:
        if task.get("status") == "completed":
            lines.append(f"- {task['task']}")

    lines.extend([
        "",
        "Documentation Notes:",
        "- This report was generated automatically by the AI Studio docs agent.",
        "- It summarizes the latest planning and execution cycle.",
        "- Future iterations may include commit summaries, code diffs, and changelog entries."
    ])

    docs_file.write_text("\n".join(lines), encoding="utf-8")

    return str(docs_file)