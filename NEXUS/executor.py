import subprocess
import platform
from pathlib import Path
from datetime import datetime


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_safe_commands(project_path: str) -> list[list[str]]:
    """
    Returns a small list of read-only / inspection-only commands.
    These commands should not modify files.
    """
    system_name = platform.system().lower()

    if project_path.startswith("\\\\wsl$"):
        return [
            ["wsl", "bash", "-lc", f'cd "{convert_wsl_unc_to_linux_path(project_path)}" && pwd'],
            ["wsl", "bash", "-lc", f'cd "{convert_wsl_unc_to_linux_path(project_path)}" && ls'],
            ["wsl", "bash", "-lc", f'cd "{convert_wsl_unc_to_linux_path(project_path)}" && python3 --version'],
        ]

    if "windows" in system_name:
        absolute_path = str(Path(project_path).resolve())
        
        return [
            ["python", "-c", "import os; print(os.getcwd())"],
            ["python", "-c", f"import os; print(os.listdir(r'{absolute_path}'))"],
            ["python", "-c", "import sys; print(sys.version)"],
        ]


def convert_wsl_unc_to_linux_path(unc_path: str) -> str:
    """
    Converts:
    \\wsl$\\Ubuntu-22.04\\home\\adayahlogic\\blofin-bot
    to:
    /home/adayahlogic/blofin-bot
    """
    parts = unc_path.split("\\")
    cleaned = [p for p in parts if p]
    if len(cleaned) >= 3 and cleaned[0].lower() == "wsl$":
        linux_parts = cleaned[2:]
        return "/" + "/".join(linux_parts)
    return unc_path


def run_safe_commands(project_path: str) -> list[dict]:
    commands = build_safe_commands(project_path)
    results = []

    for cmd in commands:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                shell=False
            )
            results.append({
                "command": " ".join(cmd),
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            })
        except Exception as e:
            results.append({
                "command": " ".join(cmd),
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            })

    return results


def write_execution_report(project_path: str, project_name: str, results: list[dict]) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "execution_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Execution Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Command Results:",
    ]

    for item in results:
        lines.extend([
            f"- Command: {item['command']}",
            f"  Return Code: {item['returncode']}",
            f"  STDOUT: {item['stdout'] or '[empty]'}",
            f"  STDERR: {item['stderr'] or '[empty]'}",
            "",
        ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)