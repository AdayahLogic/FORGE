from pathlib import Path
from datetime import datetime

from NEXUS.path_utils import (
    get_project_display_name,
    normalize_display_data,
    sanitize_identifier,
)
from NEXUS.execution_policy import evaluate as execution_policy_evaluate
from NEXUS.execution_ledger import append_entry as ledger_append


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def read_text_file(target_file: Path) -> str:
    if not target_file.exists() or not target_file.is_file():
        raise FileNotFoundError(f"File not found: {target_file}")
    return target_file.read_text(encoding="utf-8", errors="ignore")


def append_controlled_update(
    project_path: str,
    project_name: str | None,
    architect_plan: dict | None,
    target_relative_path: str = "src/ai_generated_module.py"
) -> dict:
    base_path = Path(project_path)
    target_file = (base_path / target_relative_path).resolve()
    base_resolved = base_path.resolve()

    if not str(target_file).startswith(str(base_resolved)):
        raise ValueError("Blocked path traversal outside project directory.")

    original_text = read_text_file(target_file)

    objective = "No objective available"
    if architect_plan:
        objective = architect_plan.get("objective", objective)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_display_name = get_project_display_name(project_name)
    function_suffix = sanitize_identifier(project_name or project_display_name)
    function_name = f"get_latest_{function_suffix}_update"

    update_block = f"""

# --- Controlled {project_display_name} Update ---
# Timestamp: {timestamp}
# Objective Snapshot: {objective}

def {function_name}() -> dict:
    return {{
        "updated_at": "{timestamp}",
        "project": "{project_display_name}",
        "objective": "{objective}",
        "status": "controlled_update_applied"
    }}
"""

    new_text = original_text.rstrip() + "\n" + update_block.strip() + "\n"
    target_file.write_text(new_text, encoding="utf-8")

    execution_policy_decision = execution_policy_evaluate(
        "file_modification",
        "file_modification",
        action_type="file_append",
        target_path=target_relative_path,
    )
    summary = {
        "target_path": str(target_file),
        "bytes_before": len(original_text.encode("utf-8")),
        "bytes_after": len(new_text.encode("utf-8")),
        "lines_added_estimate": len(update_block.splitlines()),
        "update_preview": update_block[:600],
        "update_function_name": function_name,
        "update_project_name": project_display_name,
        "execution_policy_decision": execution_policy_decision,
    }

    return normalize_display_data(summary)


def write_file_modification_report(
    project_path: str,
    project_name: str,
    summary: dict,
    *,
    run_id: str | None = None,
) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "file_modification_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = normalize_display_data(summary)

    lines = [
        "File Modification Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Modification Summary:",
        f"- target_path: {summary.get('target_path')}",
        f"- bytes_before: {summary.get('bytes_before')}",
        f"- bytes_after: {summary.get('bytes_after')}",
        f"- lines_added_estimate: {summary.get('lines_added_estimate')}",
        f"- update_function_name: {summary.get('update_function_name')}",
        f"- update_project_name: {summary.get('update_project_name')}",
        "",
        "Update Preview:",
        summary.get("update_preview", "[none]"),
    ]
    ep = summary.get("execution_policy_decision") or {}
    if ep:
        lines.extend([
            "",
            "Execution policy:",
            f"- status: {ep.get('status')}",
            f"- allowed: {ep.get('allowed')}",
            f"- review_required: {ep.get('review_required')}",
        ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    try:
        ledger_append(
            project_path,
            "file_modification",
            "completed",
            f"File modification report written for {project_name}.",
            project_name=project_name,
            tool_name="file_modification",
            payload={"target_path": summary.get("target_path"), "bytes_after": summary.get("bytes_after")},
            run_id=run_id,
        )
    except Exception:
        pass
    return str(report_file)