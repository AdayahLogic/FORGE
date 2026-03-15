import os
import subprocess
import platform
import webbrowser
from pathlib import Path
from datetime import datetime

from NEXUS.path_utils import to_studio_relative_path


SAFE_URLS = [
    "https://platform.openai.com",
    "https://github.com",
]


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def open_project_folder(project_path: str) -> dict:
    system_name = platform.system().lower()
    resolved = str(Path(project_path).resolve())

    if "windows" in system_name:
        os.startfile(resolved)
    elif "darwin" in system_name:
        subprocess.run(["open", resolved], check=False)
    else:
        subprocess.run(["xdg-open", resolved], check=False)

    return {
        "action": "open_project_folder",
        "target": resolved,
        "status": "launched",
    }


def open_file_if_exists(file_path: str | None) -> dict:
    if not file_path:
        return {
            "action": "open_file",
            "target": None,
            "status": "skipped",
            "reason": "No file path provided.",
        }

    path_obj = Path(file_path)

    if not path_obj.exists():
        return {
            "action": "open_file",
            "target": str(path_obj),
            "status": "skipped",
            "reason": "File does not exist.",
        }

    system_name = platform.system().lower()
    resolved = str(path_obj.resolve())

    if "windows" in system_name:
        os.startfile(resolved)
    elif "darwin" in system_name:
        subprocess.run(["open", resolved], check=False)
    else:
        subprocess.run(["xdg-open", resolved], check=False)

    return {
        "action": "open_file",
        "target": resolved,
        "status": "launched",
    }


def open_safe_url(url: str) -> dict:
    if url not in SAFE_URLS:
        return {
            "action": "open_url",
            "target": url,
            "status": "blocked",
            "reason": "URL not in allowlist.",
        }

    webbrowser.open(url)
    return {
        "action": "open_url",
        "target": url,
        "status": "launched",
    }


def build_computer_use_summary(
    project_path: str,
    docs_output_path: str | None,
    workspace_report_path: str | None,
    open_project: bool = True,
    open_docs: bool = False,
    open_workspace_report: bool = False,
    open_url: str | None = None,
) -> dict:
    actions = []

    if open_project:
        try:
            actions.append(open_project_folder(project_path))
        except Exception as e:
            actions.append({
                "action": "open_project_folder",
                "target": project_path,
                "status": "error",
                "reason": str(e),
            })

    if open_docs:
        try:
            actions.append(open_file_if_exists(docs_output_path))
        except Exception as e:
            actions.append({
                "action": "open_file",
                "target": docs_output_path,
                "status": "error",
                "reason": str(e),
            })

    if open_workspace_report:
        try:
            actions.append(open_file_if_exists(workspace_report_path))
        except Exception as e:
            actions.append({
                "action": "open_file",
                "target": workspace_report_path,
                "status": "error",
                "reason": str(e),
            })

    if open_url:
        try:
            actions.append(open_safe_url(open_url))
        except Exception as e:
            actions.append({
                "action": "open_url",
                "target": open_url,
                "status": "error",
                "reason": str(e),
            })

    launched = len([a for a in actions if a.get("status") == "launched"])
    blocked = len([a for a in actions if a.get("status") == "blocked"])
    skipped = len([a for a in actions if a.get("status") == "skipped"])
    errored = len([a for a in actions if a.get("status") == "error"])

    return {
        "actions": actions,
        "launched_count": launched,
        "blocked_count": blocked,
        "skipped_count": skipped,
        "error_count": errored,
    }


def write_computer_use_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "computer_use_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Computer Use Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Summary:",
        f"- launched_count: {summary.get('launched_count')}",
        f"- blocked_count: {summary.get('blocked_count')}",
        f"- skipped_count: {summary.get('skipped_count')}",
        f"- error_count: {summary.get('error_count')}",
        "",
        "Actions:",
    ]

    for action in summary.get("actions", []):
        lines.extend([
            f"- action: {action.get('action')}",
            f"  target: {to_studio_relative_path(action.get('target'))}",
            f"  status: {action.get('status')}",
            f"  reason: {action.get('reason', '[none]')}",
            "",
        ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)