from pathlib import Path
from datetime import datetime


def ensure_src_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    src_path = base_path / "src"
    src_path.mkdir(parents=True, exist_ok=True)
    return src_path


def build_generated_module_text(project_name: str, architect_plan: dict | None, task_queue: list) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    objective = "No objective available"
    if architect_plan:
        objective = architect_plan.get("objective", objective)

    task_lines = []
    for task in task_queue:
        task_lines.append(f"# - {task.get('task')} [{task.get('status')}]")

    if not task_lines:
        task_lines.append("# - No tasks available")

    return f'''"""
AI Generated Module
Project: {project_name}
Generated: {timestamp}

Objective:
{objective}
"""

PROJECT_NAME = "{project_name}"
PROJECT_OBJECTIVE = """{objective}"""


def get_project_summary() -> dict:
    """
    Returns a structured summary for the current AI-generated implementation slice.
    """
    return {{
        "project": PROJECT_NAME,
        "objective": PROJECT_OBJECTIVE,
        "status": "generated",
        "task_count": {len(task_queue)}
    }}


def print_project_summary() -> None:
    summary = get_project_summary()
    print("Project:", summary["project"])
    print("Objective:", summary["objective"])
    print("Status:", summary["status"])
    print("Task Count:", summary["task_count"])


# Task Snapshot
{chr(10).join(task_lines)}
'''
    

def write_controlled_implementation_file(
    project_path: str,
    project_name: str,
    architect_plan: dict | None,
    task_queue: list
) -> str:
    src_path = ensure_src_folder(project_path)
    output_file = src_path / "ai_generated_module.py"

    module_text = build_generated_module_text(
        project_name=project_name,
        architect_plan=architect_plan,
        task_queue=task_queue
    )

    output_file.write_text(module_text, encoding="utf-8")
    return str(output_file)