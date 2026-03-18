from __future__ import annotations

from typing import Any

from elite_layers.veritas_engine import build_veritas_engine_safe


def build_veritas_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    meta_engine_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    VERITAS summary: truth/contradiction/assumption audit visibility.

    Stable output shape:
    {
      "veritas_status": "...",
      "truth_reason": "...",
      "contradictions_detected": false,
      "assumption_review_required": false,
      "truth_confidence": "high" | "medium" | "low",
      "issues": []
      "source_signals": {
        "state_validator": null,
        "guardrails": null,
        "prism_recommendation": null,
        "aegis_decision": null
      }
    }
    """
    # Backward-compatible wrapper: delegate to the new consolidation engine.
    # meta_engine_summary is intentionally accepted for compatibility, but
    # VERITAS consolidation consumes state_validator + production_guardrails +
    # PRISM + AEGIS outcome.
    return build_veritas_engine_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        studio_driver_summary=studio_driver_summary,
        project_name=None,
    )

