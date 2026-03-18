from __future__ import annotations

from typing import Any

from elite_layers.genesis_engine import build_genesis_engine_safe


def build_genesis_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    n_ideas: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    GENESIS summary: lightweight evaluation-only idea ranking.

    Stable output shape (matches GENESIS OUTPUT):
      {
        "genesis_status": "...",
        "ideas": [...],
        "ranking": [...]
      }
    """
    try:
        states = states_by_project or {}
        coord = studio_coordination_summary or {}
        prj = (project_name or coord.get("priority_project") or "").strip()
        if not prj and states:
            prj = sorted(states.keys())[0]
        if not prj:
            return {"genesis_status": "idle", "ideas": [], "ranking": []}

        state = states.get(prj) or {}
        if not isinstance(state, dict):
            return {"genesis_status": "idle", "ideas": [], "ranking": []}

        return build_genesis_engine_safe(
            genesis_mode="rank",
            project_state=state,
            project_name=prj,
            n_ideas=n_ideas,
        )
    except Exception:
        return {"genesis_status": "error_fallback", "ideas": [], "ranking": []}

