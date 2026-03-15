from pathlib import Path
from datetime import datetime

from core.engine_registry import (
    ENGINE_REGISTRY,
    list_active_engines,
    list_planned_engines,
    get_engines_for_product,
)
from core.path_utils import normalize_display_data


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def build_engine_summary(active_project: str | None) -> dict:
    active_engines = list_active_engines()
    planned_engines = list_planned_engines()
    product_engines = get_engines_for_product(active_project)

    reusable_active = sorted([
        name for name, metadata in ENGINE_REGISTRY.items()
        if metadata.get("status") == "active" and metadata.get("reusable", False)
    ])

    layer_counts = {}
    category_counts = {}

    for _, metadata in ENGINE_REGISTRY.items():
        layer = metadata.get("layer", "unknown")
        category = metadata.get("category", "unknown")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1

    summary = {
        "active_project": active_project,
        "active_engine_count": len(active_engines),
        "planned_engine_count": len(planned_engines),
        "active_engines": active_engines,
        "planned_engines": planned_engines,
        "project_engines": product_engines,
        "reusable_active_engines": reusable_active,
        "layer_counts": layer_counts,
        "category_counts": category_counts,
        "human_review_recommended": True,
        "notes": "Engine registry inspected successfully.",
    }

    return normalize_display_data(summary)


def write_engine_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "engine_registry_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Engine Registry Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Registry Summary:",
        f"- active_project: {summary.get('active_project')}",
        f"- active_engine_count: {summary.get('active_engine_count')}",
        f"- planned_engine_count: {summary.get('planned_engine_count')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        f"- notes: {summary.get('notes')}",
        "",
        "Project Engines:",
    ]

    for item in summary.get("project_engines", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Active Engines:",
    ])
    for item in summary.get("active_engines", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Planned Engines:",
    ])
    for item in summary.get("planned_engines", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "Reusable Active Engines:",
    ])
    for item in summary.get("reusable_active_engines", []):
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

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)