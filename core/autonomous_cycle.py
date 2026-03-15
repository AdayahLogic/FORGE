from pathlib import Path
from datetime import datetime


def build_autonomous_cycle_summary(
    supervisor_decision: dict,
    max_cycles: int = 3
) -> dict:
    pending_tasks = supervisor_decision.get("pending_tasks", 0)
    recommended_action = supervisor_decision.get("recommended_action", "unknown")
    proceed = supervisor_decision.get("proceed_with_cycle", False)

    if not proceed:
        cycles_run = 0
        stopped_reason = "Supervisor decided not to proceed."
    else:
        # Safe simulation for now:
        # run up to 3 internal cycles, but never more than pending task count
        cycles_run = min(max_cycles, max(1, pending_tasks))
        if pending_tasks > max_cycles:
            stopped_reason = f"Stopped at safe max cycle limit ({max_cycles})."
        else:
            stopped_reason = "Stopped because pending work was within the safe simulated cycle window."

    return {
        "recommended_action": recommended_action,
        "proceed_with_cycle": proceed,
        "pending_tasks_at_start": pending_tasks,
        "max_cycles_allowed": max_cycles,
        "cycles_run": cycles_run,
        "stopped_reason": stopped_reason,
    }


def write_autonomous_cycle_report(project_path: str, project_name: str, summary: dict) -> str:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)

    report_file = generated_path / "autonomous_cycle_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Autonomous Cycle Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Cycle Summary:",
        f"- recommended_action: {summary.get('recommended_action')}",
        f"- proceed_with_cycle: {summary.get('proceed_with_cycle')}",
        f"- pending_tasks_at_start: {summary.get('pending_tasks_at_start')}",
        f"- max_cycles_allowed: {summary.get('max_cycles_allowed')}",
        f"- cycles_run: {summary.get('cycles_run')}",
        "",
        "Stopped Reason:",
        summary.get("stopped_reason", "No reason provided."),
    ]

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)