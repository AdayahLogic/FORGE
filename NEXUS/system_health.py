"""
NEXUS system health and safety monitor.

Evaluates current run state into healthy / warning / critical and produces
safety flags and alerts. No external services; read-only checks on paths
and session/policy summaries.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.execution_ledger import get_ledger_path


def evaluate_health(
    project_path: str | None = None,
    run_id: str | None = None,
    execution_session_summary: dict | None = None,
    execution_policy_summary: dict | None = None,
    notes: str | None = None,
    agent_routing_report_path: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate system health from current runtime data.

    Returns: overall_status (healthy | warning | critical), safety_flags (list),
    alerts (list), checks (dict), human_review_recommended (bool).
    """
    safety_flags: list[str] = []
    alerts: list[str] = []
    checks: dict[str, bool | str] = {}

    # Project path
    if not project_path or not str(project_path).strip():
        checks["project_path_exists"] = False
        safety_flags.append("missing_project_path")
        alerts.append("Project path is missing.")
    else:
        checks["project_path_exists"] = True
        root = Path(project_path).resolve()
        if not root.exists():
            checks["project_path_exists"] = False
            safety_flags.append("missing_project_path")
            alerts.append("Project path does not exist on disk.")
        else:
            state_dir = root / "state"
            if not state_dir.is_dir():
                checks["state_dir_exists"] = False
                safety_flags.append("missing_state_file")
                alerts.append("Project state directory is missing.")
            else:
                checks["state_dir_exists"] = True
                ledger_path_str = get_ledger_path(project_path)
                if ledger_path_str:
                    ledger_exists = Path(ledger_path_str).exists()
                    checks["ledger_exists"] = ledger_exists
                    if not ledger_exists:
                        safety_flags.append("missing_ledger")
                        alerts.append("Execution ledger file not found.")
                else:
                    checks["ledger_exists"] = False

    # Run/session
    if not run_id or not str(run_id).strip():
        checks["run_id_present"] = False
        safety_flags.append("no_run_context")
        alerts.append("No run_id; session context may be missing.")
    else:
        checks["run_id_present"] = True

    session = execution_session_summary or {}
    if not session:
        checks["session_summary_present"] = False
        if run_id:
            safety_flags.append("missing_session_summary")
            alerts.append("Execution session summary is empty.")
    else:
        checks["session_summary_present"] = True
        if session.get("status") == "failed":
            safety_flags.append("workflow_failed")
            alerts.append("Session status is failed.")
    if execution_policy_summary is None or (isinstance(execution_policy_summary, dict) and not execution_policy_summary):
        checks["policy_summary_present"] = False
    else:
        checks["policy_summary_present"] = True

    # Report path (optional; only flag when path is set but file missing)
    if agent_routing_report_path:
        p = Path(agent_routing_report_path)
        if not p.is_absolute() and project_path:
            p = Path(project_path).resolve() / agent_routing_report_path
        exists = p.exists() if p else False
        checks["agent_routing_report_exists"] = exists
        if not exists:
            safety_flags.append("report_generation_issue")
            alerts.append("Agent routing report path set but file not found.")
    else:
        checks["agent_routing_report_exists"] = None  # not required

    # Overall status
    if "missing_project_path" in safety_flags or "workflow_failed" in safety_flags:
        overall_status = "critical"
    elif safety_flags:
        overall_status = "warning"
    else:
        overall_status = "healthy"

    human_review_recommended = overall_status != "healthy"

    return {
        "overall_status": overall_status,
        "safety_flags": safety_flags,
        "alerts": alerts,
        "checks": checks,
        "human_review_recommended": human_review_recommended,
        "evaluated_at": datetime.now().isoformat(),
    }


def evaluate_system_health(
    project_path: str | None = None,
    run_id: str | None = None,
    run_status: str | None = None,
    execution_session_summary: dict | None = None,
    execution_policy_summary: dict | None = None,
    notes: str | None = None,
    agent_routing_report_path: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Public compatibility adapter for evaluate_health.
    Accepts run_status and maps it into execution_session_summary['status'] when needed.
    Extra kwargs are ignored so callers can pass optional args safely.
    """
    session = dict(execution_session_summary) if execution_session_summary else {}
    if run_status is not None and "status" not in session:
        session["status"] = run_status
    return evaluate_health(
        project_path=project_path,
        run_id=run_id,
        execution_session_summary=session if session else None,
        execution_policy_summary=execution_policy_summary,
        notes=notes,
        agent_routing_report_path=agent_routing_report_path,
    )


def write_system_health_report(
    project_path: str,
    project_name: str,
    summary: dict[str, Any],
) -> str:
    """Write a simple system health report to project generated/ folder. Returns report path."""
    base = Path(project_path)
    generated = base / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    report_file = generated / "system_health_report.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "System Health Report",
        f"Timestamp: {ts}",
        f"Project: {project_name}",
        "",
        f"Overall status: {summary.get('overall_status', 'unknown')}",
        f"Human review recommended: {summary.get('human_review_recommended')}",
        "",
        "Safety flags:",
    ]
    for f in summary.get("safety_flags", []):
        lines.append(f"  - {f}")
    lines.extend(["", "Alerts:"])
    for a in summary.get("alerts", []):
        lines.append(f"  - {a}")
    lines.extend(["", "Checks:"])
    for k, v in summary.get("checks", {}).items():
        lines.append(f"  - {k}: {v}")
    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)
