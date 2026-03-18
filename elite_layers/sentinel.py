from __future__ import annotations

from typing import Any

from elite_layers.sentinel_engine import build_sentinel_engine_safe


def build_sentinel_summary_safe(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    meta_engine_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    SENTINEL summary: unified threat/risk posture layer.

    Stable output shape:
    {
      "sentinel_status": "...",
      "threat_reason": "...",
      "high_risk_detected": false,
      "review_required": false,
      "risk_level": "low" | "medium" | "high" | "unknown",
      "active_warnings": [],
      "source_signals": {
        "safety_engine": null,
        "security_engine": null,
        "compliance_engine": null,
        "risk_engine": null,
        "aegis_decision": null,
        "deployment_preflight": null
      }
    }
    """
    # Backward-compatible wrapper: delegate to the new consolidation engine.
    # meta_engine_summary is consumed as-is by SENTINEL consolidation.
    return build_sentinel_engine_safe(
        states_by_project=states_by_project,
        studio_coordination_summary=studio_coordination_summary,
        meta_engine_summary=meta_engine_summary,
    )

