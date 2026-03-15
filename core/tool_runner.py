from pathlib import Path
from datetime import datetime

from core.path_utils import to_studio_relative_path


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def ensure_memory_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    memory_path = base_path / "memory"
    memory_path.mkdir(parents=True, exist_ok=True)
    return memory_path


def read_project_summary(project_path: str) -> dict:
    base_path = Path(project_path)
    docs_file = base_path / "docs" / "project_overview.txt"
    memory_file = base_path / "memory" / "current_focus.txt"
    tasks_file = base_path / "tasks" / "next_steps.txt"

    def safe_read(path: Path) -> str:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")[:1000].strip()
        return "[missing]"

    return {
        "project_overview": safe_read(docs_file),
        "current_focus": safe_read(memory_file),
        "next_steps": safe_read(tasks_file),
    }


def append_dev_note(project_path: str, note_text: str) -> dict:
    memory_path = ensure_memory_folder(project_path)
    notes_file = memory_path / "dev_notes.txt"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = f"[{timestamp}] {note_text}\n"

    with notes_file.open("a", encoding="utf-8") as f:
        f.write(block)

    return {
        "target_path": str(notes_file),
        "note_written": block.strip(),
    }


def list_src_files(project_path: str) -> dict:
    base_path = Path(project_path)
    src_path = base_path / "src"

    if not src_path.exists() or not src_path.is_dir():
        return {
            "src_exists": False,
            "files": [],
        }

    files = []
    for path in sorted(src_path.rglob("*")):
        if path.is_file():
            files.append(str(path.relative_to(base_path)))

    return {
        "src_exists": True,
        "files": files,
    }


def run_tool_sequence(project_path: str, project_name: str, architect_plan: dict | None) -> dict:
    objective = "No objective available"
    if architect_plan:
        objective = architect_plan.get("objective", objective)

    summary_result = read_project_summary(project_path)
    src_result = list_src_files(project_path)
    note_result = append_dev_note(
        project_path,
        f"{project_name}: tool execution cycle recorded. Objective snapshot: {objective}"
    )

    return {
        "tools_run": [
            "read_project_summary",
            "list_src_files",
            "append_dev_note",
        ],
        "project_summary": summary_result,
        "src_listing": src_result,
        "dev_note_result": note_result,
    }


def write_tool_execution_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "tool_execution_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Tool Execution Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Tools Run:",
    ]

    for tool_name in summary.get("tools_run", []):
        lines.append(f"- {tool_name}")

    project_summary = summary.get("project_summary", {})
    lines.extend([
        "",
        "Project Summary Snapshot:",
        f"- project_overview: {project_summary.get('project_overview', '[none]')}",
        f"- current_focus: {project_summary.get('current_focus', '[none]')}",
        f"- next_steps: {project_summary.get('next_steps', '[none]')}",
    ])

    src_listing = summary.get("src_listing", {})
    lines.extend([
        "",
        "Source Listing:",
        f"- src_exists: {src_listing.get('src_exists')}",
    ])
    for item in src_listing.get("files", []):
        lines.append(f"- {item}")

    dev_note = summary.get("dev_note_result", {})
    lines.extend([
        "",
        "Dev Note Result:",
        f"- target_path: {to_studio_relative_path(dev_note.get('target_path', '[none]'))}",
        f"- note_written: {dev_note.get('note_written', '[none]')}",
    ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)