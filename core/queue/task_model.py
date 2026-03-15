from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class Task(BaseModel):
    """
    Core orchestration task model for Nexus.

    This is intentionally small and focused on the minimal fields
    needed for safe in-memory queueing and reporting.
    """

    id: str = Field(..., description="Stable identifier for the task within a run.")
    type: str = Field(..., description="High-level task type, e.g. 'implementation_step'.")
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary structured payload for the task.",
    )
    priority: int = Field(
        default=0,
        description="Lower numbers indicate higher priority; ties preserve insertion order.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Execution status of the task within the current run.",
    )

    def to_snapshot_dict(self) -> Dict[str, Any]:
        """
        Produce a snapshot compatible with existing Nexus task_queue usage.

        Existing agents expect at least:
        - task: human-readable description
        - status: 'pending' | 'completed' | ...
        """
        description: Optional[str] = None

        # Prefer a dedicated description if present.
        if isinstance(self.payload.get("description"), str):
            description = self.payload["description"]
        # Fallback to a generic string form if needed.
        if not description:
            description = f"{self.type}: {self.id}"

        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "priority": self.priority,
            "status": self.status.value,
            # Backwards-compatible fields used by existing reporters.
            "task": description,
        }

