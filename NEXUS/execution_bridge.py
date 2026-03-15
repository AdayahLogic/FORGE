from pathlib import Path
from datetime import datetime

from NEXUS.execution_targets import EXECUTION_TARGETS, DEFAULT_EXECUTION_TARGET
from NEXUS.path_utils import normalize_display_data


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def _build_cursor_prompt(
    active_project: str | None,
    runtime_node: str | None,
    task_queue: list,
    architect_plan: dict | None,
) -> str:
    objective = ""
    if architect_plan and isinstance(architect_plan, dict):
        objective = architect_plan.get("objective", "")

    pending_tasks = []
    for task in task_queue:
        if task.get("status") == "pending":
            pending_tasks.append(task.get("task"))

    top_task = pending_tasks[0] if pending_tasks else "Review current plan and continue safely."

    allowed_files = [
        "core/",
        "tests/",
        "docs/",
    ]

    return f"""Task: Implement the next safe development slice for project '{active_project}'.

Target runtime agent:
{runtime_node}

Objective:
{objective}

Primary pending task:
{top_task}

Rules:
- make narrow, minimal changes
- do not redesign architecture
- do not delete working modules
- keep changes backward compatible
- prefer small modular files
- stop and explain before making broad changes

Suggested allowed areas:
{chr(10).join(f"- {item}" for item in allowed_files)}

Expected output:
- summary of files changed
- summary of logic added
- suggested tests to run
"""


def _build_codex_prompt(
    active_project: str | None,
    runtime_node: str | None,
    task_queue: list,
    architect_plan: dict | None,
) -> str:
    objective = ""
    if architect_plan and isinstance(architect_plan, dict):
        objective = architect_plan.get("objective", "")

    pending_tasks = []
    for task in task_queue:
        if task.get("status") == "pending":
            pending_tasks.append(task.get("task"))

    top_task = pending_tasks[0] if pending_tasks else "Generate a safe modular code draft."

    return f"""Generate code support for project '{active_project}'.

Runtime agent:
{runtime_node}

Objective:
{objective}

Focus task:
{top_task}

Requirements:
- generate modular code only
- do not redesign architecture
- prefer small isolated functions/classes
- keep code easy to integrate into an existing repository
- include safe defaults and clear naming
- avoid touching unrelated systems
"""


def _build_human_review_checklist(summary: dict) -> list[str]:
    runtime_node = summary.get("runtime_node", "unknown")
    return [
        f"Confirm the requested runtime node '{runtime_node}' makes sense for this task.",
        "Confirm the task scope is narrow and does not redesign the system.",
        "Confirm only expected files will be modified.",
        "Run tests before accepting major changes.",
        "Review diffs before commit or deployment.",
    ]


def build_execution_bridge_packet(
    active_project: str | None,
    architect_plan: dict | None,
    task_queue: list,
    agent_routing_summary: dict | None,
) -> dict:
    routing = agent_routing_summary or {}
    runtime_node = routing.get("runtime_node", "unknown")

    target = EXECUTION_TARGETS.get(runtime_node, DEFAULT_EXECUTION_TARGET)

    packet = {
        "active_project": active_project,
        "runtime_node": runtime_node,
        "primary_tool": target.get("primary_tool"),
        "secondary_tool": target.get("secondary_tool"),
        "human_review_required": target.get("human_review_required", True),
        "purpose": target.get("purpose"),
        "cursor_usage": target.get("cursor_usage"),
        "codex_usage": target.get("codex_usage"),
        "cursor_prompt": _build_cursor_prompt(
            active_project=active_project,
            runtime_node=runtime_node,
            task_queue=task_queue,
            architect_plan=architect_plan,
        ),
        "codex_prompt": _build_codex_prompt(
            active_project=active_project,
            runtime_node=runtime_node,
            task_queue=task_queue,
            architect_plan=architect_plan,
        ),
        "human_review_checklist": _build_human_review_checklist(routing),
        "handoff_status": "execution_packet_ready",
    }

    return normalize_display_data(packet)


def write_execution_bridge_report(project_path: str, project_name: str, packet: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "execution_bridge_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Execution Bridge Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Execution Target:",
        f"- runtime_node: {packet.get('runtime_node')}",
        f"- primary_tool: {packet.get('primary_tool')}",
        f"- secondary_tool: {packet.get('secondary_tool')}",
        f"- human_review_required: {packet.get('human_review_required')}",
        f"- purpose: {packet.get('purpose')}",
        "",
        "Cursor Usage:",
        packet.get("cursor_usage", "[none]"),
        "",
        "Codex Usage:",
        packet.get("codex_usage", "[none]"),
        "",
        "Human Review Checklist:",
    ]

    for item in packet.get("human_review_checklist", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Cursor Prompt:",
        packet.get("cursor_prompt", "[none]"),
        "",
        "Codex Prompt:",
        packet.get("codex_prompt", "[none]"),
    ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)