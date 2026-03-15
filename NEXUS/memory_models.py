from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProjectMemory(BaseModel):
    """
    Normalized, project-scoped memory snapshot for Nexus.

    This model is intentionally minimal and based on the fields
    that exist in current Jarvis/Nexus docs and memory files.
    """

    project_name: Optional[str] = Field(
        default=None,
        description="Logical name of the active project (e.g. 'jarvis').",
    )
    project_overview: Optional[str] = Field(
        default=None,
        description="High-level project description and purpose.",
    )
    current_focus: Optional[str] = Field(
        default=None,
        description="Current short-term focus for this project.",
    )
    dev_notes: Optional[str] = Field(
        default=None,
        description="Recent developer notes or cycle logs for this project.",
    )
    next_steps: Optional[str] = Field(
        default=None,
        description="Planned next steps or roadmap items.",
    )
    architecture_notes: Optional[str] = Field(
        default=None,
        description="Architecture or design notes, if available.",
    )
    memory_status: str = Field(
        default="empty",
        description="High-level status for the memory load (e.g. 'empty', 'partial', 'ok').",
    )

