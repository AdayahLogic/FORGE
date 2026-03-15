import subprocess
from pathlib import Path
from datetime import datetime


ALLOWED_COMMANDS = [
    ["python", "--version"],
    ["pip", "list"],
]


def run_allowed_commands(project_path: str) -> list:
    results = []

    for cmd in ALLOWED_COMMANDS:
        try:
            process = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            results.append({
                "command": " ".join(cmd),
                "return_code": process.returncode,
                "stdout": process.stdout.strip(),
                "stderr": process.stderr.strip(),
            })

        except Exception as e:
            results.append({
                "command": " ".join(cmd),
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
            })

    return results


def write_terminal_report(project_path: str, project_name: str, results: list) -> str:
    base_path = Path(project_path)
    generated = base_path / "generated"
    generated.mkdir(exist_ok=True)

    report_path = generated / "terminal_report.txt"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Terminal Control Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Command Results:"
    ]

    for r in results:
        lines.append(f"- Command: {r['command']}")
        lines.append(f"  Return Code: {r['return_code']}")
        lines.append(f"  STDOUT: {r['stdout']}")
        lines.append(f"  STDERR: {r['stderr']}")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    return str(report_path)