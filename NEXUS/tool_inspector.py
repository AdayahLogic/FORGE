"""
Nexus core tool inspector.

Produces summaries and reports from the tool registry for the active project
and optional agent context. Does not change execution behavior.
"""

from __future__ import annotations

from typing import Any

from pathlib import Path
from datetime import datetime

from NEXUS.tool_registry import (
    TOOL_REGISTRY,
    list_active_tools,
    list_planned_tools,
    get_tools_for_agent,
    normalize_tool_metadata,
)
from NEXUS.path_utils import normalize_display_data


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_tool_summary(
    active_project: str | None,
    active_agent: str | None = None,
) -> dict:
    """
    Build a summary of the tool registry for the active project/agent context.

    Returns active tools, planned tools, tools allowed for the given agent,
    category counts, and human review notes.
    """
    active_tools = list_active_tools()
    planned_tools = list_planned_tools()
    tools_allowed_for_agent = get_tools_for_agent(active_agent) if active_agent else []

    category_counts: dict[str, int] = {}
    sensitivity_counts: dict[str, int] = {}
    human_review_tools: list[str] = []
    active_tool_details: list[dict[str, Any]] = []
    planned_tool_details: list[dict[str, Any]] = []

    for _name, meta in TOOL_REGISTRY.items():
        cat = meta.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        sensitivity = meta.get("sensitivity") or "unknown"
        sensitivity_counts[sensitivity] = sensitivity_counts.get(sensitivity, 0) + 1
        if meta.get("human_review_recommended"):
            human_review_tools.append(_name)

    for t in active_tools:
        active_tool_details.append(normalize_tool_metadata(t))
    for t in planned_tools:
        planned_tool_details.append(normalize_tool_metadata(t))

    summary = {
        "active_project": active_project,
        "active_agent": active_agent,
        "active_tool_count": len(active_tools),
        "planned_tool_count": len(planned_tools),
        "active_tools": active_tools,
        "planned_tools": planned_tools,
        "active_tool_details": active_tool_details,
        "planned_tool_details": planned_tool_details,
        "tools_allowed_for_agent": tools_allowed_for_agent,
        "category_counts": category_counts,
        "sensitivity_counts": sensitivity_counts,
        "human_review_recommended_tools": sorted(human_review_tools),
        "human_review_recommended": True,
        "notes": "Tool registry inspected successfully.",
    }

    return normalize_display_data(summary)


def write_tool_registry_report(
    project_path: str,
    project_name: str,
    summary: dict,
) -> str:
    """Write a tool registry report to the project generated folder."""
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "tool_registry_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Tool Registry Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Registry Summary:",
        f"- active_project: {summary.get('active_project')}",
        f"- active_agent: {summary.get('active_agent')}",
        f"- active_tool_count: {summary.get('active_tool_count')}",
        f"- planned_tool_count: {summary.get('planned_tool_count')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        f"- notes: {summary.get('notes')}",
        "",
        "Active Tools:",
    ]
    for item in summary.get("active_tools", []):
        lines.append(f"- {item}")

    lines.extend(["", "Planned Tools:"])
    for item in summary.get("planned_tools", []):
        lines.append(f"- {item}")

    lines.extend(["", "Tools Allowed for Agent:"])
    for item in summary.get("tools_allowed_for_agent", []):
        lines.append(f"- {item}")

    lines.extend(["", "Category Counts:"])
    for key, value in summary.get("category_counts", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "Human Review Recommended Tools:"])
    for item in summary.get("human_review_recommended_tools", []):
        lines.append(f"- {item}")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)
