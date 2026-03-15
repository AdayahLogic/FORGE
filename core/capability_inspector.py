from pathlib import Path
from datetime import datetime

from core.capability_registry import (
    CAPABILITY_REGISTRY,
    list_active_capabilities,
    list_planned_capabilities,
    get_capabilities_for_product,
)
from core.path_utils import normalize_display_data


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_capability_summary(active_project: str | None) -> dict:
    active_capabilities = list_active_capabilities()
    planned_capabilities = list_planned_capabilities()
    project_capabilities = get_capabilities_for_product(active_project)

    reusable_active = sorted([
        name for name, metadata in CAPABILITY_REGISTRY.items()
        if metadata.get("status") == "active" and metadata.get("reusable", False)
    ])

    layer_counts = {}
    category_counts = {}
    engine_usage_counts = {}

    for _, metadata in CAPABILITY_REGISTRY.items():
        layer = metadata.get("layer", "unknown")
        category = metadata.get("category", "unknown")
        engine = metadata.get("engine", "unknown")

        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        engine_usage_counts[engine] = engine_usage_counts.get(engine, 0) + 1

    summary = {
        "active_project": active_project,
        "active_capability_count": len(active_capabilities),
        "planned_capability_count": len(planned_capabilities),
        "active_capabilities": active_capabilities,
        "planned_capabilities": planned_capabilities,
        "project_capabilities": project_capabilities,
        "reusable_active_capabilities": reusable_active,
        "layer_counts": layer_counts,
        "category_counts": category_counts,
        "engine_usage_counts": engine_usage_counts,
        "human_review_recommended": True,
        "notes": "Capability registry inspected successfully.",
    }

    return normalize_display_data(summary)


def write_capability_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "capability_registry_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Capability Registry Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Registry Summary:",
        f"- active_project: {summary.get('active_project')}",
        f"- active_capability_count: {summary.get('active_capability_count')}",
        f"- planned_capability_count: {summary.get('planned_capability_count')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        f"- notes: {summary.get('notes')}",
        "",
        "Project Capabilities:",
    ]

    for item in summary.get("project_capabilities", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Active Capabilities:",
    ])
    for item in summary.get("active_capabilities", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Planned Capabilities:",
    ])
    for item in summary.get("planned_capabilities", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Reusable Active Capabilities:",
    ])
    for item in summary.get("reusable_active_capabilities", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Layer Counts:",
    ])
    for key, value in summary.get("layer_counts", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "Category Counts:",
    ])
    for key, value in summary.get("category_counts", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "Engine Usage Counts:",
    ])
    for key, value in summary.get("engine_usage_counts", {}).items():
        lines.append(f"- {key}: {value}")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)