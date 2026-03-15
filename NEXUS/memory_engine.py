from __future__ import annotations

from pathlib import Path
from typing import Optional

from .memory_models import ProjectMemory


def _safe_read_text(path: Path) -> Optional[str]:
    """
    Safely read a text file, returning None if the file is missing
    or cannot be read.
    """
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def load_project_memory(project_path: str, project_name: Optional[str] = None) -> ProjectMemory:
    """
    Load project-scoped memory for the active project only.

    This loader:
    - reads from the provided project_path only
    - tolerates missing files
    - returns a normalized ProjectMemory instance
    - never attempts to read from other workspaces
    """
    base = Path(project_path)

    docs = base / "docs"
    memory = base / "memory"
    tasks = base / "tasks"

    overview = _safe_read_text(docs / "project_overview.txt")
    # Existing convention: current_focus lives under memory/, not docs/.
    current_focus = _safe_read_text(memory / "current_focus.txt")
    # Existing convention: next_steps lives under tasks/, not docs/.
    next_steps = _safe_read_text(tasks / "next_steps.txt")
    architecture_notes = _safe_read_text(docs / "architecture_notes.txt")
    dev_notes = _safe_read_text(memory / "dev_notes.txt")

    filled_fields = [
        value
        for value in (
            overview,
            current_focus,
            next_steps,
            architecture_notes,
            dev_notes,
        )
        if value is not None
    ]

    if not filled_fields:
        status = "empty"
    elif len(filled_fields) < 3:
        status = "partial"
    else:
        status = "ok"

    return ProjectMemory(
        project_name=project_name,
        project_overview=overview,
        current_focus=current_focus,
        dev_notes=dev_notes,
        next_steps=next_steps,
        architecture_notes=architecture_notes,
        memory_status=status,
    )

