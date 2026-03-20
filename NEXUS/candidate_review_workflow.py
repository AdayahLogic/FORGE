"""
NEXUS candidate review workflow (Phase 37).

Governed review readiness evaluation for patch candidates and strong draft artifacts.
Deterministic rules; no hidden mutation. Review records are first-class governed artifacts.
"""

from __future__ import annotations

from typing import Any

VALID_REVIEW_STATUS = (
    "not_ready_for_review",
    "ready_for_review",
    "reviewed",
    "changes_requested",
    "approved_for_approval",
    "error_fallback",
)
VALID_REVIEW_READINESS = ("low", "medium", "high")


def evaluate_candidate_review_readiness(proposal: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 37: Evaluate review readiness from patch proposal.
    Deterministic; considers proposal_maturity, executable_candidate, completion_status,
    missing_information_flags, requires_followup_before_approval.
    Does NOT bypass approval. approved_for_approval means ready to submit to approval flow.
    """
    p = proposal or {}
    proposal_maturity = str(p.get("proposal_maturity") or "").strip().lower()
    executable_candidate = bool(p.get("executable_candidate", False))
    completion_status = str(p.get("completion_status") or "").strip().lower()
    missing_flags = list(p.get("missing_information_flags") or [])[:10]
    requires_followup = bool(p.get("requires_followup_before_approval", True))
    proposal_readiness = str(p.get("proposal_readiness") or "").strip().lower()
    change_type = str(p.get("change_type") or "").strip().lower()

    requirements_met: list[str] = []
    requirements_missing: list[str] = []

    if executable_candidate:
        requirements_met.append("executable_candidate")
    else:
        requirements_missing.append("executable_candidate")
    if completion_status == "completed_patch_candidate":
        requirements_met.append("completion_complete")
    elif completion_status == "partially_completable":
        requirements_met.append("completion_partial")
    else:
        requirements_missing.append("completion_complete")
    if not requires_followup:
        requirements_met.append("no_followup_required")
    else:
        requirements_missing.append("no_followup_required")
    if not missing_flags:
        requirements_met.append("no_missing_info")
    else:
        requirements_missing.append("missing_info")
    if proposal_readiness == "fully_ready":
        requirements_met.append("proposal_fully_ready")
    elif proposal_readiness == "draft_followup":
        requirements_met.append("proposal_draft_followup")
    else:
        requirements_missing.append("proposal_ready")

    if executable_candidate and completion_status == "completed_patch_candidate" and not requires_followup and not missing_flags:
        review_readiness = "high"
        review_status = "ready_for_review"
        review_reason = "Executable patch candidate; complete; no missing info. Ready for human review."
        approval_progression_ready = True
    elif (
        proposal_maturity in ("strong_candidate", "executable")
        or (completion_status == "partially_completable" and proposal_readiness == "draft_followup")
    ):
        review_readiness = "medium"
        review_status = "ready_for_review"
        review_reason = "Strong or partial candidate; review recommended. Some followup may be needed."
        approval_progression_ready = not requires_followup and executable_candidate
    elif proposal_maturity == "guided_followup" or change_type == "guided_patch_followup":
        review_readiness = "low"
        review_status = "ready_for_review"
        review_reason = "Draft followup candidate; review for guidance. Significant followup likely."
        approval_progression_ready = False
    elif proposal_maturity == "advisory" or change_type == "advisory_only":
        review_readiness = "low"
        review_status = "not_ready_for_review"
        review_reason = "Advisory only; not a patch candidate. Review not applicable."
        approval_progression_ready = False
    else:
        review_readiness = "low"
        review_status = "not_ready_for_review"
        review_reason = "Insufficient maturity for review. Complete candidate first."
        approval_progression_ready = False

    return {
        "review_status": review_status,
        "review_reason": review_reason[:300],
        "review_readiness": review_readiness,
        "review_requirements_met": requirements_met[:10],
        "review_requirements_missing": requirements_missing[:10],
        "human_review_required": review_status == "ready_for_review",
        "approval_progression_ready": approval_progression_ready,
        "next_step_recommendation": _next_step(review_status, approval_progression_ready, requires_followup),
    }


def _next_step(review_status: str, approval_progression_ready: bool, requires_followup: bool) -> str:
    """Deterministic next-step recommendation."""
    if review_status == "not_ready_for_review":
        return "Complete candidate (target, search, replacement) before review."
    if review_status == "ready_for_review":
        if approval_progression_ready:
            return "Review candidate; if acceptable, submit to approval flow."
        if requires_followup:
            return "Review candidate; provide followup (search/replace) before approval."
        return "Review candidate; assess readiness for approval."
    return "Proceed per review outcome."
