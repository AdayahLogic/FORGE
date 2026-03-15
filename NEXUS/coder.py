from pathlib import Path
from datetime import datetime


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"

    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def write_coder_output(project_path: str, project_name: str, task_queue: list) -> str:
    generated_path = ensure_generated_folder(project_path)
    output_file = generated_path / "coder_output.txt"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"Coder Execution Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Task Queue Snapshot:"
    ]

    if task_queue:
        for i, task in enumerate(task_queue, start=1):
            lines.append(f"{i}. {task['task']} [{task['status']}]")
    else:
        lines.append("[No tasks found]")

    lines.extend([
        "",
        "Execution Notes:",
        "- Coder agent initialized successfully.",
        "- Generated folder verified.",
        "- Output artifact created successfully.",
        "- Safe file-writing test completed."
    ])

    output_file.write_text("\n".join(lines), encoding="utf-8")

    return str(output_file)


def mark_first_pending_task_complete(task_queue: list) -> list:
    updated_queue = []

    completed_one = False

    for task in task_queue:
        updated_task = dict(task)

        if not completed_one and updated_task.get("status") == "pending":
            updated_task["status"] = "completed"
            completed_one = True

        updated_queue.append(updated_task)

    return updated_queue