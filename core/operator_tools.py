import json
import subprocess
from pathlib import Path
from datetime import datetime


SAFE_COMMANDS = {
    "python --version": ["python", "--version"],
    "git status": ["git", "status"],
}


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def get_operator_log_file(project_path: str) -> Path:
    generated_path = ensure_generated_folder(project_path)
    return generated_path / "operator_actions.jsonl"


def log_operator_action(project_path: str, action_type: str, payload: dict) -> str:
    log_file = get_operator_log_file(project_path)

    record = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "payload": payload,
    }

    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return str(log_file)


def list_directory(project_path: str, relative_path: str = ".") -> dict:
    base_path = Path(project_path).resolve()
    target_path = (base_path / relative_path).resolve()

    if not str(target_path).startswith(str(base_path)):
        raise ValueError("Blocked path traversal outside project directory.")

    if not target_path.exists() or not target_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {target_path}")

    entries = sorted([p.name for p in target_path.iterdir()])
    return {
        "target_path": str(target_path),
        "entries": entries,
    }


def read_text_file(project_path: str, relative_file_path: str, max_chars: int = 4000) -> dict:
    base_path = Path(project_path).resolve()
    target_file = (base_path / relative_file_path).resolve()

    if not str(target_file).startswith(str(base_path)):
        raise ValueError("Blocked path traversal outside project directory.")

    if not target_file.exists() or not target_file.is_file():
        raise FileNotFoundError(f"File not found: {target_file}")

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    return {
        "target_path": str(target_file),
        "content": text[:max_chars],
    }


def write_text_file(project_path: str, relative_file_path: str, content: str) -> dict:
    base_path = Path(project_path).resolve()
    target_file = (base_path / relative_file_path).resolve()

    if not str(target_file).startswith(str(base_path)):
        raise ValueError("Blocked path traversal outside project directory.")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")

    return {
        "target_path": str(target_file),
        "bytes_written": len(content.encode("utf-8")),
    }


def run_safe_command(project_path: str, command_name: str) -> dict:
    if command_name not in SAFE_COMMANDS:
        raise ValueError(f"Command not allowed: {command_name}")

    command = SAFE_COMMANDS[command_name]

    completed = subprocess.run(
        command,
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=20,
        shell=False
    )

    return {
        "command_name": command_name,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }