"""
Nexus core path migration helper and reporting.

Detects legacy path aliases and produces migration summaries.
Does not perform physical renames.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.studio_config import STUDIO_ROOT, LEGACY_STUDIO_FOLDER_NAME
from core.path_alias_registry import (
    INTENDED_ROOT_NAME,
    LEGACY_ROOT_NAMES,
    LEGACY_PROJECT_PATH_SEGMENTS,
    PATH_ALIAS_REGISTRY,
)


def analyze_path(path: str | Path) -> dict[str, Any]:
    """
    Analyze a path for legacy aliases and return a migration summary.

    Returns: input_path, normalized_path, alias_detected, logical_name,
    migration_status, human_review_recommended.
    """
    try:
        raw = Path(path) if path else Path(".")
        normalized = raw.resolve()
        input_str = str(path) if path else ""
    except Exception:
        normalized = Path(str(path)) if path else Path(".")
        input_str = str(path) if path else ""

    norm_str = str(normalized)
    norm_lower = norm_str.lower().replace("\\", "/")
    alias_detected = False
    logical_name = INTENDED_ROOT_NAME
    migration_status = "no_alias"

    for legacy in LEGACY_ROOT_NAMES:
        if legacy.lower() in norm_lower:
            alias_detected = True
            logical_name = INTENDED_ROOT_NAME
            migration_status = "alias_only"
            break

    if not alias_detected and "projects" in norm_lower:
        for seg in LEGACY_PROJECT_PATH_SEGMENTS:
            if f"projects/{seg}" in norm_lower or f"projects\\{seg}" in norm_lower:
                alias_detected = True
                logical_name = "jarvis"
                migration_status = "physical_unchanged"
                break

    human = alias_detected and migration_status in ("alias_only", "physical_unchanged")

    return {
        "input_path": input_str,
        "normalized_path": norm_str,
        "alias_detected": alias_detected,
        "logical_name": logical_name,
        "migration_status": migration_status,
        "human_review_recommended": human,
    }


def build_path_migration_summary(
    project_path: str | None,
    active_project: str | None,
) -> dict[str, Any]:
    """
    Build a path migration summary for the active project.

    Inspects studio root, project path, and key subpaths; reports
    legacy aliases, root naming status, and recommended next steps.
    """
    from core.path_utils import normalize_display_data

    root = Path(STUDIO_ROOT).resolve()
    paths_to_check = [str(root)]
    if project_path:
        proj = Path(project_path).resolve()
        paths_to_check.extend([
            str(proj),
            str(proj / "generated"),
            str(proj / "state"),
        ])

    results = [analyze_path(p) for p in paths_to_check]
    alias_count = sum(1 for r in results if r.get("alias_detected"))

    root_naming_status = "legacy_in_use"
    if alias_count > 0:
        root_naming_status = "legacy_aliases_detected"
    else:
        root_naming_status = "no_legacy_detected"

    recommended_steps = []
    if alias_count > 0:
        recommended_steps.append("Review path_migration_report for paths containing legacy names.")
        recommended_steps.append("When ready, set FORGE_ROOT env to intended root path.")
        recommended_steps.append("Physical folder renames (e.g. AI_STUDIO->FORGE, nexus->jarvis) are deferred.")
    else:
        recommended_steps.append("No legacy path aliases detected in inspected paths.")

    summary = {
        "active_project": active_project,
        "intended_root_name": INTENDED_ROOT_NAME,
        "legacy_root_name": LEGACY_STUDIO_FOLDER_NAME,
        "root_naming_status": root_naming_status,
        "alias_count": alias_count,
        "inspected_path_count": len(results),
        "inspected_paths": results,
        "recommended_next_steps": recommended_steps,
        "human_review_recommended": alias_count > 0,
        "notes": "Path migration inspection completed.",
    }
    return normalize_display_data(summary)


def write_path_migration_report(
    project_path: str,
    project_name: str,
    summary: dict[str, Any],
) -> str:
    """Write path migration report to project generated/ folder."""
    from datetime import datetime

    base = Path(project_path)
    generated = base / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    report_file = generated / "path_migration_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Path Migration Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Root Naming:",
        f"- intended_root_name: {summary.get('intended_root_name')}",
        f"- legacy_root_name: {summary.get('legacy_root_name')}",
        f"- root_naming_status: {summary.get('root_naming_status')}",
        "",
        "Summary:",
        f"- alias_count: {summary.get('alias_count')}",
        f"- inspected_path_count: {summary.get('inspected_path_count')}",
        f"- human_review_recommended: {summary.get('human_review_recommended')}",
        f"- notes: {summary.get('notes')}",
        "",
        "Recommended Next Steps:",
    ]
    for step in summary.get("recommended_next_steps", []):
        lines.append(f"- {step}")
    lines.extend(["", "Inspected Paths:"])

    for item in summary.get("inspected_paths", []):
        lines.append(f"- path: {item.get('normalized_path', item.get('input_path', ''))}")
        lines.append(f"  alias_detected: {item.get('alias_detected')}  logical_name: {item.get('logical_name')}  migration_status: {item.get('migration_status')}")
        if item.get("human_review_recommended"):
            lines.append("  human_review_recommended: True")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)
