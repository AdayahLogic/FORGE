from __future__ import annotations

from typing import Any


def build_prism_recommendation(
    *,
    prism_status: str,
    success_estimate: int,
    clarity: int,
    novelty: int,
    audience_friction_points: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Decide go / revise / hold deterministically with explainable thresholds.

    Returns:
    {
      "recommendation": "go" | "revise" | "hold",
      "recommendation_reason": "..."
    }
    """
    audience_friction_points = audience_friction_points or []

    # If not enough inputs, we always hold (evaluation-only).
    if prism_status != "evaluated":
        return {
            "recommendation": "hold",
            "recommendation_reason": f"prism_status={prism_status}; inputs are insufficient to recommend a build.",
        }

    # Friction-based penalty.
    friction_penalty = max(0, len(audience_friction_points) - 2) * 4

    adjusted_success = success_estimate - friction_penalty

    if adjusted_success >= 72 and clarity >= 60 and novelty >= 40:
        return {
            "recommendation": "go",
            "recommendation_reason": (
                f"Adjusted success={adjusted_success} with clarity={clarity} and novelty={novelty}; "
                f"friction_points={len(audience_friction_points)}."
            ),
        }

    if adjusted_success >= 55 and clarity >= 45:
        return {
            "recommendation": "revise",
            "recommendation_reason": (
                f"Adjusted success={adjusted_success}; clarity={clarity}. Recommend revision to reduce friction and improve clarity."
            ),
        }

    return {
        "recommendation": "hold",
        "recommendation_reason": (
            f"Adjusted success={adjusted_success} not high enough for go; clarity={clarity}, novelty={novelty}. Recommend holding."
        ),
    }


def build_prism_recommendation_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_prism_recommendation(**kwargs)
    except Exception:
        return {
            "recommendation": "hold",
            "recommendation_reason": "Recommendation builder failed; defaulting to hold.",
        }

