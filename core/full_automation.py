from pathlib import Path
from datetime import datetime


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_full_automation_summary(
    computer_use_summary: dict | None,
    terminal_summary: dict | None,
    browser_research_summary: dict | None,
    tool_execution_summary: dict | None,
    file_modification_summary: dict | None,
    diff_patch_summary: dict | None,
) -> dict:
    computer_use_summary = computer_use_summary or {}
    terminal_summary = terminal_summary or {}
    browser_research_summary = browser_research_summary or {}
    tool_execution_summary = tool_execution_summary or {}
    file_modification_summary = file_modification_summary or {}
    diff_patch_summary = diff_patch_summary or {}

    actions = []

    if computer_use_summary:
        actions.append("computer_use")
    if terminal_summary:
        actions.append("terminal")
    if browser_research_summary:
        actions.append("browser_research")
    if tool_execution_summary:
        actions.append("tool_execution")
    if file_modification_summary:
        actions.append("file_modification")
    if diff_patch_summary:
        actions.append("diff_patch")

    return {
        "automation_layers_run": actions,
        "computer_use_launched": computer_use_summary.get("launched_count", 0),
        "terminal_commands_run": terminal_summary.get("commands_run", 0),
        "browser_urls_launched": browser_research_summary.get("urls_launched", 0),
        "tool_groups_run": len(tool_execution_summary.get("tools_run", [])),
        "file_modification_applied": bool(file_modification_summary.get("target_path")),
        "diff_patch_status": diff_patch_summary.get("status", "not_run"),
        "diff_patch_applied": bool(diff_patch_summary.get("patch_applied", False)),
        "status": "full_automation_sequence_completed",
    }


def write_full_automation_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "full_automation_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Full Automation Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Automation Summary:",
        f"- automation_layers_run: {summary.get('automation_layers_run')}",
        f"- computer_use_launched: {summary.get('computer_use_launched')}",
        f"- terminal_commands_run: {summary.get('terminal_commands_run')}",
        f"- browser_urls_launched: {summary.get('browser_urls_launched')}",
        f"- tool_groups_run: {summary.get('tool_groups_run')}",
        f"- file_modification_applied: {summary.get('file_modification_applied')}",
        f"- diff_patch_status: {summary.get('diff_patch_status')}",
        f"- diff_patch_applied: {summary.get('diff_patch_applied')}",
        f"- status: {summary.get('status')}",
    ]

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)