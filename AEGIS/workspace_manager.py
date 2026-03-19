from __future__ import annotations

from pathlib import Path
from typing import Any


def _to_path(v: Any) -> Path | None:
    if v is None:
        return None
    try:
        return Path(str(v)).resolve()
    except Exception:
        return None


def validate_workspace(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Restrict paths to project scope.

    Expected request keys (best-effort):
    - project_path: str
    - candidate_paths: list[str] (optional)
    """
    req = request or {}
    project_path = _to_path(req.get("project_path"))
    if not project_path:
        return {"ok": False, "reason": "project_path missing or invalid."}
    # Phase 13: stronger workspace control — project_path must exist and be a directory.
    if not project_path.exists():
        return {"ok": False, "reason": "project_path does not exist."}
    if not project_path.is_dir():
        return {"ok": False, "reason": "project_path is not a directory."}

    candidate_paths = req.get("candidate_paths") or []
    if not isinstance(candidate_paths, list) or not candidate_paths:
        # Nothing to restrict; allow.
        return {"ok": True, "reason": "No candidate_paths provided."}

    for cp in candidate_paths:
        p = _to_path(cp)
        if not p:
            return {"ok": False, "reason": f"Invalid candidate path: {cp}"}
        try:
            # Scope check: candidate must be within project_path directory.
            if project_path not in p.parents and p != project_path:
                return {"ok": False, "reason": f"Path outside project scope: {p}"}
        except Exception:
            return {"ok": False, "reason": f"Failed scope check for: {p}"}

    return {"ok": True, "reason": "Workspace path validation passed."}

