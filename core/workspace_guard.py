"""
Nexus core workspace boundary guard.

Classifies paths into workspace layers and returns a normalized summary
with write_policy and owner_scope. Does not perform path migration or
modify the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.studio_config import STUDIO_ROOT
from core.workspace_layers import LAYER_REGISTRY


def classify_path(path: str | Path, studio_root: str | Path | None = None) -> dict[str, Any]:
    """
    Classify a path into a workspace layer and return a normalized summary.

    Returns: input_path, normalized_path, layer, write_policy, owner_scope,
    human_review_recommended (True when write_policy is restricted or review_required).
    """
    root = Path(studio_root or STUDIO_ROOT).resolve()
    try:
        raw = Path(path) if path else Path(".")
        normalized = raw.resolve()
    except Exception:
        normalized = Path(path) if path else Path(".")
    input_str = str(path) if path else ""

    try:
        relative = normalized.relative_to(root)
        parts = relative.parts
    except (ValueError, TypeError):
        return _summary(
            input_str=input_str,
            normalized_path=str(normalized),
            layer="unknown",
            root=root,
        )

    if not parts:
        return _summary(
            input_str=input_str,
            normalized_path=str(normalized),
            layer="core",
            root=root,
        )

    first = parts[0].lower()
    if first == "core":
        return _summary(input_str, str(normalized), "core", root)
    if first == "shared":
        return _summary(input_str, str(normalized), "shared", root)
    if first == "docs":
        return _summary(input_str, str(normalized), "docs", root)
    if first == "projects":
        if len(parts) >= 3:
            second = parts[2].lower()
            if second == "generated":
                return _summary(input_str, str(normalized), "generated", root)
            if second == "state":
                return _summary(input_str, str(normalized), "state", root)
            if second == "docs":
                return _summary(input_str, str(normalized), "docs", root, owner_scope="project")
            if second == "memory":
                return _summary(input_str, str(normalized), "memory", root)
            if second == "tasks":
                return _summary(input_str, str(normalized), "tasks", root)
        return _summary(input_str, str(normalized), "projects", root)

    return _summary(input_str, str(normalized), "unknown", root)


def _summary(
    input_str: str,
    normalized_path: str,
    layer: str,
    root: Path,
    owner_scope: str | None = None,
) -> dict[str, Any]:
    meta = LAYER_REGISTRY.get(layer, LAYER_REGISTRY["unknown"])
    write_policy = meta.get("write_policy", "restricted")
    scope = owner_scope or meta.get("owner_scope", "nexus")
    human = write_policy in ("restricted", "review_required")
    return {
        "input_path": input_str,
        "normalized_path": normalized_path,
        "layer": layer,
        "write_policy": write_policy,
        "owner_scope": scope,
        "human_review_recommended": human,
    }


def inspect_project_paths(project_path: str | None, studio_root: str | Path | None = None) -> list[dict[str, Any]]:
    """
    Inspect key paths for the active project and classify each.

    Includes: core/, project path, project/generated, project/state,
    project/docs, project/memory, project/tasks. Returns a list of
    classification summaries.
    """
    root = Path(studio_root or STUDIO_ROOT).resolve()
    results: list[dict[str, Any]] = []

    core_dir = root / "core"
    results.append(classify_path(core_dir, studio_root))

    if project_path:
        proj = Path(project_path).resolve()
        results.append(classify_path(proj, studio_root))
        results.append(classify_path(proj / "generated", studio_root))
        results.append(classify_path(proj / "state", studio_root))
        results.append(classify_path(proj / "docs", studio_root))
        results.append(classify_path(proj / "memory", studio_root))
        results.append(classify_path(proj / "tasks", studio_root))

    shared_dir = root / "shared"
    results.append(classify_path(shared_dir, studio_root))

    docs_dir = root / "docs"
    results.append(classify_path(docs_dir, studio_root))

    return results


def build_workspace_boundary_summary(
    project_path: str | None,
    active_project: str | None,
    studio_root: str | Path | None = None,
) -> dict[str, Any]:
    """
    Build a workspace boundary summary for the active project.

    Inspects core, project path, generated, state, docs, memory, tasks, shared, docs.
    Returns inspected_paths, layer counts, policies, human_review_recommended.
    """
    from core.path_utils import normalize_display_data

    inspected = inspect_project_paths(project_path, studio_root)
    layer_counts: dict[str, int] = {}
    for item in inspected:
        layer = item.get("layer", "unknown")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    human = any(item.get("human_review_recommended") for item in inspected)

    summary = {
        "active_project": active_project,
        "project_path": str(Path(project_path).resolve()) if project_path else None,
        "inspected_path_count": len(inspected),
        "inspected_paths": inspected,
        "layer_counts": layer_counts,
        "human_review_recommended": human,
        "notes": "Workspace boundary inspection completed.",
    }
    return normalize_display_data(summary)


def write_workspace_boundary_report(
    project_path: str,
    project_name: str,
    summary: dict[str, Any],
) -> str:
    """Write workspace boundary report to project generated/ folder."""
    from datetime import datetime

    base = Path(project_path)
    generated = base / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    report_file = generated / "workspace_boundary_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Workspace Boundary Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Summary:",
        f"- active_project: {summary.get('active_project')}",
        f"- inspected_path_count: {summary.get('inspected_path_count')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        f"- notes: {summary.get('notes')}",
        "",
        "Layer Counts:",
    ]
    for k, v in summary.get("layer_counts", {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "Inspected Paths:"])

    for item in summary.get("inspected_paths", []):
        lines.append(f"- path: {item.get('normalized_path', item.get('input_path', ''))}")
        lines.append(f"  layer: {item.get('layer')}  write_policy: {item.get('write_policy')}  owner_scope: {item.get('owner_scope')}")
        if item.get("human_review_recommended"):
            lines.append("  human_review_recommended: True")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)
