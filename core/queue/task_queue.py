from __future__ import annotations

from typing import List, Dict, Any, Optional

from .task_model import Task


class InMemoryTaskQueue:
    """
    Minimal in-memory task queue for Nexus orchestration.

    This queue is intentionally simple:
    - no persistence
    - no background workers
    - no async primitives
    """

    def __init__(self) -> None:
        self._tasks: List[Task] = []

    def add_task(self, task: Task) -> None:
        """Append a task to the queue."""
        self._tasks.append(task)

    def has_tasks(self) -> bool:
        """Return True if there are any tasks in the queue."""
        return bool(self._tasks)

    def size(self) -> int:
        """Return the current number of tasks in the queue."""
        return len(self._tasks)

    def get_next_task(self) -> Optional[Task]:
        """
        Retrieve and remove the next task to process.

        Tasks are returned in ascending priority order; tasks with the same
        priority are returned in insertion order.
        """
        if not self._tasks:
            return None

        # Find the index of the next task by (priority, insertion index).
        # Because we keep tasks in insertion order, min() with key=priority
        # preserves insertion ordering for ties.
        min_idx = min(range(len(self._tasks)), key=lambda i: self._tasks[i].priority)
        return self._tasks.pop(min_idx)

    def snapshot(self) -> List[Dict[str, Any]]:
        """
        Return a serializable snapshot of the queue contents.

        Each entry is a dict compatible with existing Nexus task_queue
        consumers (e.g., coder, tester, supervisor) while also exposing
        richer queue metadata.
        """
        return [task.to_snapshot_dict() for task in self._tasks]

