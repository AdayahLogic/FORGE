"""
NEXUS run context / execution session.

Generates run_id and minimal session context for grouping workflow runs and
ledger entries. No database, no async; just enough structure to tag a run.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def create_run_context(
    project_name: str | None = None,
    user_input: str | None = None,
) -> dict[str, Any]:
    """
    Create a new workflow run context.

    Returns a dict with: run_id, project_name, user_input, started_at,
    ended_at (None), status ("running"), entry_count (None), error_summary (None).
    """
    now = datetime.now().isoformat()
    return {
        "run_id": uuid.uuid4().hex,
        "project_name": project_name,
        "user_input": (user_input or "")[:500],
        "started_at": now,
        "ended_at": None,
        "status": "running",
        "entry_count": None,
        "error_summary": None,
    }


def finalize_run_context(
    context: dict[str, Any],
    status: str = "completed",
    error_summary: str | None = None,
) -> dict[str, Any]:
    """
    Set ended_at and status on a run context. Returns the updated context.
    """
    context = dict(context)
    context["ended_at"] = datetime.now().isoformat()
    context["status"] = status
    if error_summary is not None:
        context["error_summary"] = error_summary[:500]
    return context
