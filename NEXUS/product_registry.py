"""
NEXUS product registry (Phase 19).

Defines product manifest contract and per-project storage.
Product = structured packaging layer for deployable, inspectable units.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PRODUCT_MANIFEST_FILENAME = "product_manifest.json"


def get_product_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for product manifest; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_product_manifest_path(project_path: str | None) -> str | None:
    """Return path to project-scoped product manifest."""
    state_dir = get_product_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PRODUCT_MANIFEST_FILENAME)


def normalize_product_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize product manifest to contract shape.
    Ensures required fields exist with safe defaults.
    """
    m = manifest or {}
    return {
        "product_id": str(m.get("product_id") or ""),
        "project_name": str(m.get("project_name") or ""),
        "version": str(m.get("version") or "0.1.0"),
        "status": str(m.get("status") or "draft").strip().lower(),
        "created_at": str(m.get("created_at") or ""),
        "last_updated": str(m.get("last_updated") or ""),
        "entry_points": list(m.get("entry_points") or []),
        "capabilities": list(m.get("capabilities") or []),
        "required_tools": list(m.get("required_tools") or []),
        "required_runtime_targets": list(m.get("required_runtime_targets") or []),
        "execution_environment": str(m.get("execution_environment") or ""),
        "approval_requirements": dict(m.get("approval_requirements") or {}),
        "risk_profile": str(m.get("risk_profile") or "unknown"),
        "safety_summary": dict(m.get("safety_summary") or {}),
        "notes": str(m.get("notes") or ""),
    }


def read_product_manifest(project_path: str | None) -> dict[str, Any] | None:
    """Read product manifest from project state. Returns None if missing or invalid."""
    path = get_product_manifest_path(project_path)
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_product_manifest(data)
    except Exception:
        pass
    return None


def write_product_manifest(
    project_path: str | None,
    manifest: dict[str, Any],
) -> str | None:
    """
    Write product manifest to project state.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_product_manifest_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_product_manifest(manifest)
        normalized["last_updated"] = datetime.now().isoformat()
        if not normalized.get("created_at"):
            normalized["created_at"] = normalized["last_updated"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


def write_product_manifest_safe(
    project_path: str | None,
    manifest: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return write_product_manifest(project_path=project_path, manifest=manifest)
    except Exception:
        return None
