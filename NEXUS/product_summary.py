"""
NEXUS product summary layer (Phase 19).

Builds product visibility for dashboard and command surface.
Read-only; no packaging or deployment.
"""

from __future__ import annotations

from typing import Any

from NEXUS.product_builder import build_product_manifest_safe
from NEXUS.product_registry import read_product_manifest
from NEXUS.registry import PROJECTS


def build_product_summary(
    *,
    use_cached: bool = True,
) -> dict[str, Any]:
    """
    Build product summary across all projects.

    Returns:
        product_status: str
        draft_count: int
        ready_count: int
        restricted_count: int
        products_by_project: dict[str, dict]
        safety_indicators: dict
        reason: str
    """
    draft_count = 0
    ready_count = 0
    restricted_count = 0
    products_by_project: dict[str, dict[str, Any]] = {}
    safety_issues: list[str] = []

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        manifest = read_product_manifest(project_path=path) if use_cached else None
        if not manifest:
            manifest = build_product_manifest_safe(
                project_name=proj.get("name") or proj_key,
                project_path=path,
                project_key=proj_key,
            )
        products_by_project[proj_key] = manifest
        status = str(manifest.get("status") or "draft").strip().lower()
        if status == "ready":
            ready_count += 1
        elif status == "restricted":
            restricted_count += 1
            safety = manifest.get("safety_summary") or {}
            issues = safety.get("critical_issues") or []
            safety_issues.extend(issues)
        else:
            draft_count += 1

    total = draft_count + ready_count + restricted_count

    # Forward-compatibility: expose linkage presence (Phase 29: patch, helix too).
    learning_linkage_present = False
    approval_linkage_present = False
    autonomy_linkage_present = False
    patch_linkage_present = False
    helix_linkage_present = False
    for _proj, m in products_by_project.items():
        if m.get("learning_insight_refs"):
            learning_linkage_present = True
        if m.get("approval_refs") or m.get("approval_id_refs"):
            approval_linkage_present = True
        if m.get("autonomy_refs") or m.get("autonomy_id_refs"):
            autonomy_linkage_present = True
        if m.get("patch_id_refs"):
            patch_linkage_present = True
        if m.get("helix_id_refs"):
            helix_linkage_present = True

    if ready_count > 0 and restricted_count == 0:
        product_status = "ready"
        reason = f"{ready_count} product(s) ready; {draft_count} draft."
    elif restricted_count > 0:
        product_status = "restricted"
        reason = f"{restricted_count} restricted; {draft_count} draft; {ready_count} ready."
    elif draft_count > 0:
        product_status = "draft"
        reason = f"{draft_count} product(s) in draft."
    else:
        product_status = "unknown"
        reason = "No products evaluated."

    return {
        "product_status": product_status,
        "draft_count": draft_count,
        "ready_count": ready_count,
        "restricted_count": restricted_count,
        "total_count": total,
        "products_by_project": products_by_project,
        "safety_indicators": {
            "safety_issues": list(set(safety_issues)),
            "restricted_count": restricted_count,
        },
        "learning_linkage_present": learning_linkage_present,
        "approval_linkage_present": approval_linkage_present,
        "autonomy_linkage_present": autonomy_linkage_present,
        "patch_linkage_present": patch_linkage_present,
        "helix_linkage_present": helix_linkage_present,
        "reason": reason,
    }


def build_product_summary_safe(
    *,
    use_cached: bool = True,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_product_summary(use_cached=use_cached)
    except Exception:
        return {
            "product_status": "error_fallback",
            "draft_count": 0,
            "ready_count": 0,
            "restricted_count": 0,
            "total_count": 0,
            "products_by_project": {},
            "safety_indicators": {"safety_issues": [], "restricted_count": 0},
            "learning_linkage_present": False,
            "approval_linkage_present": False,
            "autonomy_linkage_present": False,
            "patch_linkage_present": False,
            "helix_linkage_present": False,
            "reason": "Product summary evaluation failed.",
        }
