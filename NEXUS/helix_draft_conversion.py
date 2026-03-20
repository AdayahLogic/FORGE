"""
NEXUS HELIX draft-to-patch conversion (Phase 35).

Conservative conversion evaluation: determines when a draft artifact
qualifies as convertible. Does NOT fabricate patch content.
Executable candidate only when full patch payload exists.
"""

from __future__ import annotations

from typing import Any

VALID_CONVERSION_STATUS = ("not_convertible", "conditionally_convertible", "converted_to_patch_candidate")
VALID_CANDIDATE_PATCH_TYPE = ("diff_patch_candidate", "guided_patch_followup", "advisory_only")
VALID_CONVERSION_CONFIDENCE = ("low", "medium", "high")
VALID_PROPOSAL_MATURITY = ("advisory", "guided_followup", "strong_candidate", "executable")


def evaluate_draft_conversion(
    repair_metadata: dict[str, Any],
    has_patch_payload: bool,
    patch_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Phase 35: Evaluate whether a draft artifact is convertible to a patch candidate.
    Conservative: executable_candidate only when full search/replace exists.
    Does NOT fabricate patch content.
    """
    meta = repair_metadata or {}
    payload = patch_payload or {}

    target_files = meta.get("candidate_target_files") or meta.get("target_files_candidate") or []
    search_anchors = meta.get("candidate_search_anchors") or []
    replacement_intent = meta.get("candidate_replacement_intent") or ""
    refinement_status = (meta.get("refinement_status") or "not_refinable").strip().lower()
    draft_quality = (meta.get("draft_candidate_quality") or "low").strip().lower()
    change_scope = (meta.get("candidate_change_scope") or "unknown").strip().lower()
    missing_flags = meta.get("missing_information_flags") or []
    has_search_text = bool(payload.get("search_text") and str(payload.get("search_text", "")).strip())
    has_replacement_text = payload.get("replacement_text") is not None

    conversion_requirements_met: list[str] = []
    conversion_requirements_missing: list[str] = []
    conversion_evidence: list[str] = []

    if target_files:
        conversion_requirements_met.append("candidate_target_files")
        conversion_evidence.append(f"target_files={len(target_files)}")
    else:
        conversion_requirements_missing.append("candidate_target_files")
    if search_anchors or meta.get("target_hint"):
        conversion_requirements_met.append("search_anchors_or_hint")
    else:
        conversion_requirements_missing.append("search_anchors")
    if replacement_intent or meta.get("suspected_root_causes"):
        conversion_requirements_met.append("replacement_intent_or_causes")
    else:
        conversion_requirements_missing.append("replacement_intent")
    if has_search_text:
        conversion_requirements_met.append("search_text")
    else:
        conversion_requirements_missing.append("search_text")
    if has_replacement_text:
        conversion_requirements_met.append("replacement_text")
    else:
        conversion_requirements_missing.append("replacement_text")

    critical_missing = any(
        "search_text" in f or "replacement" in f or "patch_request" in f
        for f in missing_flags
    ) if missing_flags else False

    if has_patch_payload and has_search_text and has_replacement_text:
        conversion_status = "converted_to_patch_candidate"
        conversion_reason = "Full patch payload present; ready for governed proposal."
        candidate_patch_type = "diff_patch_candidate"
        executable_candidate = True
        human_verification_required = False
        conversion_confidence = "high"
        proposal_maturity = "executable"
        ready_for_human_patch_review = True
        ready_for_governed_patch_validation = True
    elif refinement_status == "partially_refined" and draft_quality in ("medium", "high") and target_files and not critical_missing and change_scope in ("single_file", "multi_file"):
        conversion_status = "conditionally_convertible"
        conversion_reason = "Strong draft evidence; human can convert to patch. Search/replace still required."
        candidate_patch_type = "guided_patch_followup"
        executable_candidate = False
        human_verification_required = True
        conversion_confidence = "medium" if draft_quality == "medium" else "high"
        proposal_maturity = "strong_candidate"
        ready_for_human_patch_review = True
        ready_for_governed_patch_validation = False
    elif refinement_status == "partially_refined" or (target_files and replacement_intent):
        conversion_status = "conditionally_convertible"
        conversion_reason = "Partial evidence; human review may enable conversion."
        candidate_patch_type = "guided_patch_followup"
        executable_candidate = False
        human_verification_required = True
        conversion_confidence = "low"
        proposal_maturity = "guided_followup"
        ready_for_human_patch_review = True
        ready_for_governed_patch_validation = False
    else:
        conversion_status = "not_convertible"
        conversion_reason = "Insufficient evidence for conversion; remain advisory."
        candidate_patch_type = "advisory_only"
        executable_candidate = False
        human_verification_required = True
        conversion_confidence = "low"
        proposal_maturity = "advisory"
        ready_for_human_patch_review = False
        ready_for_governed_patch_validation = False

    return {
        "conversion_status": conversion_status,
        "conversion_reason": conversion_reason[:300],
        "conversion_requirements_met": conversion_requirements_met[:10],
        "conversion_requirements_missing": conversion_requirements_missing[:10],
        "candidate_patch_type": candidate_patch_type,
        "executable_candidate": executable_candidate,
        "human_verification_required": human_verification_required,
        "conversion_confidence": conversion_confidence,
        "conversion_evidence": conversion_evidence[:5],
        "proposal_maturity": proposal_maturity,
        "ready_for_human_patch_review": ready_for_human_patch_review,
        "ready_for_governed_patch_validation": ready_for_governed_patch_validation,
    }
