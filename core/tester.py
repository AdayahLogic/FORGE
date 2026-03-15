from pathlib import Path
from datetime import datetime

from core.path_utils import to_studio_relative_path


def write_test_report(
    project_path: str,
    coder_output_path: str | None,
    task_queue: list,
    implementation_file_path: str | None = None
) -> str:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)

    report_file = generated_path / "test_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    coder_file_exists = False
    if coder_output_path:
        coder_file_exists = Path(coder_output_path).exists()

    implementation_file_exists = False
    if implementation_file_path:
        implementation_file_exists = Path(implementation_file_path).exists()

    completed_tasks = 0
    pending_tasks = 0

    for task in task_queue:
        if task.get("status") == "completed":
            completed_tasks += 1
        elif task.get("status") == "pending":
            pending_tasks += 1

    status = "PASS" if coder_file_exists and implementation_file_exists else "FAIL"

    lines = [
        "Tester Validation Report",
        f"Timestamp: {timestamp}",
        f"Validation Status: {status}",
        "",
        "Artifact Checks:",
        f"- coder_output_path: {to_studio_relative_path(coder_output_path)}",
        f"- coder_output_exists: {coder_file_exists}",
        f"- implementation_file_path: {to_studio_relative_path(implementation_file_path)}",
        f"- implementation_file_exists: {implementation_file_exists}",
        "",
        "Task Queue Checks:",
        f"- completed_tasks: {completed_tasks}",
        f"- pending_tasks: {pending_tasks}",
        "",
        "Tester Notes:",
    ]

    if coder_file_exists:
        lines.append("- Coder artifact exists and is readable by path check.")
    else:
        lines.append("- Coder artifact is missing.")

    if implementation_file_exists:
        lines.append("- Implementation file exists and was created successfully.")
    else:
        lines.append("- Implementation file is missing.")

    if completed_tasks > 0:
        lines.append("- At least one task was completed by coder execution.")
    else:
        lines.append("- No completed tasks detected.")

    if pending_tasks > 0:
        lines.append("- Remaining tasks are still pending, which is expected at this stage.")
    else:
        lines.append("- No pending tasks remain.")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)