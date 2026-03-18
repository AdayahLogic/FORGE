from __future__ import annotations

from typing import Any

from elite_layers.helios_engine import build_helios_expanded_summary_safe


def build_helios_summary_safe(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    live_regression: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    HELIOS summary: self-improvement planning / gating layer.

    Stable output shape:
    {
      "helios_status": "...",
      "selected_improvement": null,
      "improvement_category": null,
      "improvement_reason": "...",
      "execution_gated": true
    }
    """
    # Phase 11: expanded HELIOS logic including a structured change proposal.
    # Backward compatible: existing keys remain, but extra keys are added.
    return build_helios_expanded_summary_safe(
        dashboard_summary=dashboard_summary,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
        project_name=project_name,
        live_regression=live_regression,
        **kwargs,
    )

