from pathlib import Path
from datetime import datetime

from NEXUS.agent_registry import (
    RUNTIME_AGENT_REGISTRY,
    FUTURE_AGENT_REGISTRY,
    get_runtime_routable_agents,
    resolve_agent_alias,
)
from NEXUS.agent_identity_registry import get_agent_display_name
from NEXUS.agent_policy_registry import get_policy_summary_for_agent
from NEXUS.execution_ledger import append_entry as ledger_append
from NEXUS.path_utils import normalize_display_data


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_agent_route(architect_plan: dict | None, active_project: str | None) -> dict:
    requested_next_agent = None
    if architect_plan and isinstance(architect_plan, dict):
        requested_next_agent = architect_plan.get("next_agent")

    resolved_agent = resolve_agent_alias(requested_next_agent)
    routable_agents = get_runtime_routable_agents()

    route_status = "fallback"
    route_reason = "No requested next_agent was provided."
    runtime_node = "coder"
    is_future_agent = False
    mapped_runtime_agent = None

    if resolved_agent in RUNTIME_AGENT_REGISTRY:
        agent_meta = RUNTIME_AGENT_REGISTRY[resolved_agent]
        if agent_meta.get("routable", False):
            route_status = "direct_runtime_route"
            route_reason = f"Resolved next_agent '{resolved_agent}' to active runtime agent."
            runtime_node = agent_meta.get("runtime_node", resolved_agent)
        else:
            route_status = "non_routable_runtime_agent"
            route_reason = (
                f"Resolved next_agent '{resolved_agent}' to a runtime agent that is not directly routable. "
                "Falling back to coder."
            )
            runtime_node = "coder"

    elif resolved_agent in FUTURE_AGENT_REGISTRY:
        is_future_agent = True
        future_meta = FUTURE_AGENT_REGISTRY[resolved_agent]
        mapped_runtime_agent = future_meta.get("mapped_runtime_agent")

        if mapped_runtime_agent in RUNTIME_AGENT_REGISTRY and \
           RUNTIME_AGENT_REGISTRY[mapped_runtime_agent].get("routable", False):
            route_status = "future_agent_mapped"
            route_reason = (
                f"Requested next_agent '{resolved_agent}' is a planned future role. "
                f"Temporarily mapped to runtime agent '{mapped_runtime_agent}'."
            )
            runtime_node = RUNTIME_AGENT_REGISTRY[mapped_runtime_agent].get("runtime_node", mapped_runtime_agent)
        else:
            route_status = "future_agent_unimplemented"
            route_reason = (
                f"Requested next_agent '{resolved_agent}' is a future agent not yet implemented. "
                "Falling back to coder."
            )
            runtime_node = "coder"

    elif requested_next_agent:
        route_status = "unknown_agent_fallback"
        route_reason = (
            f"Requested next_agent '{requested_next_agent}' is unknown to the registry. "
            "Falling back to coder."
        )
        runtime_node = "coder"

    runtime_node_display_name = get_agent_display_name(runtime_node) or runtime_node
    runtime_node_policy_summary = get_policy_summary_for_agent(runtime_node)

    summary = {
        "active_project": active_project,
        "requested_next_agent": requested_next_agent,
        "resolved_agent_name": resolved_agent,
        "runtime_node": runtime_node,
        "runtime_node_display_name": runtime_node_display_name,
        "runtime_node_policy_summary": runtime_node_policy_summary,
        "route_status": route_status,
        "route_reason": route_reason,
        "available_runtime_agents": routable_agents,
        "is_future_agent": is_future_agent,
        "mapped_runtime_agent": mapped_runtime_agent,
        "human_review_recommended": route_status not in {"direct_runtime_route"},
    }

    return normalize_display_data(summary)


def write_agent_router_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "agent_router_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Agent Router Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Routing Summary:",
        f"- requested_next_agent: {summary.get('requested_next_agent')}",
        f"- resolved_agent_name: {summary.get('resolved_agent_name')}",
        f"- runtime_node: {summary.get('runtime_node')}",
        f"- runtime_node_display_name: {summary.get('runtime_node_display_name', summary.get('runtime_node'))}",
        f"- route_status: {summary.get('route_status')}",
        f"- route_reason: {summary.get('route_reason')}",
        f"- is_future_agent: {summary.get('is_future_agent')}",
        f"- mapped_runtime_agent: {summary.get('mapped_runtime_agent')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        "",
        "Policy (runtime_node):",
    ]
    policy = summary.get("runtime_node_policy_summary") or {}
    lines.append(f"- policy_status: {policy.get('policy_status')}")
    lines.append(f"- blocked_count: {policy.get('blocked_count', 0)}")
    lines.append(f"- review_required_count: {policy.get('review_required_count', 0)}")
    lines.extend([
        "",
        "Available Runtime Agents:",
    ])

    for item in summary.get("available_runtime_agents", []):
        lines.append(f"- {item}")

    report_file.write_text("\n".join(lines), encoding="utf-8")

    try:
        ledger_append(
            project_path,
            "agent_routing",
            summary.get("route_status") or "unknown",
            summary.get("route_reason") or "Agent routing completed.",
            project_name=project_name,
            agent_name=summary.get("runtime_node"),
            payload={"runtime_node": summary.get("runtime_node"), "route_status": summary.get("route_status")},
        )
    except Exception:
        pass
    return str(report_file)