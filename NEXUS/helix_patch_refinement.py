"""
NEXUS HELIX patch draft refinement (Phase 34).

Pure refinement logic: merges Builder + Surgeon outputs into a stronger
patch draft candidate artifact. Advisory only; no execution.
"""

from __future__ import annotations

from typing import Any

VALID_REFINEMENT_STATUS = ("not_refinable", "partially_refined", "draft_ready")
VALID_DRAFT_CANDIDATE_QUALITY = ("low", "medium", "high")


def refine_patch_draft(
    builder_result: dict[str, Any] | None,
    repair_metadata: dict[str, Any],
    has_patch_payload: bool,
) -> dict[str, Any]:
    """
    Phase 34: Merge Builder + Surgeon outputs into a refinement artifact.
    Pure function; no side effects. Advisory only.
    """
    meta = repair_metadata or {}
    impl_plan = (builder_result or {}).get("implementation_plan") or {}
    impl_steps = impl_plan.get("implementation_steps") or []
    patch_req = impl_plan.get("patch_request") if isinstance(impl_plan, dict) else {}

    target_files = meta.get("candidate_target_files") or meta.get("target_files_candidate") or []
    search_anchors = meta.get("candidate_search_anchors") or []
    replacement_intent = meta.get("candidate_replacement_intent") or ""
    suspected_causes = meta.get("suspected_root_causes") or []
    validation_recs = meta.get("validation_recommendations") or []
    missing_flags = meta.get("missing_information_flags") or []
    draftability = (meta.get("patch_draftability") or "low").strip().lower()

    refinement_inputs_present: list[str] = []
    refinement_inputs_missing: list[str] = []
    if target_files:
        refinement_inputs_present.append("candidate_target_files")
    else:
        refinement_inputs_missing.append("candidate_target_files")
    if search_anchors or meta.get("target_hint"):
        refinement_inputs_present.append("search_anchors_or_hint")
    else:
        refinement_inputs_missing.append("search_anchors")
    if replacement_intent or suspected_causes:
        refinement_inputs_present.append("replacement_intent_or_causes")
    else:
        refinement_inputs_missing.append("replacement_intent")
    if impl_steps:
        refinement_inputs_present.append("implementation_steps")
    if isinstance(patch_req, dict) and patch_req.get("target_relative_path"):
        refinement_inputs_present.append("builder_patch_target")
    if isinstance(patch_req, dict) and patch_req.get("search_text"):
        refinement_inputs_present.append("builder_search_text")
    else:
        refinement_inputs_missing.append("search_text")
    if isinstance(patch_req, dict) and patch_req.get("replacement_text") is not None:
        refinement_inputs_present.append("builder_replacement_text")
    else:
        refinement_inputs_missing.append("replacement_text")

    if has_patch_payload:
        refinement_status = "draft_ready"
        refinement_reason = "Builder supplied full patch; refinement complete."
        draft_candidate_quality = "high"
        requires_human_reconstruction = False
        candidate_change_scope = "single_file" if len(target_files) <= 1 else "multi_file"
        candidate_validation_steps = list(validation_recs)[:5]
        candidate_followup_actions = ["Submit through approval flow for apply."]
    elif draftability == "medium" and target_files and suspected_causes:
        refinement_status = "partially_refined"
        refinement_reason = "Builder+Surgeon merged; target and causes identified; search/replace still missing."
        draft_candidate_quality = "medium"
        requires_human_reconstruction = True
        candidate_change_scope = "single_file" if len(target_files) == 1 else ("multi_file" if len(target_files) > 1 else "unknown")
        candidate_validation_steps = list(validation_recs)[:5]
        if not candidate_validation_steps:
            candidate_validation_steps = ["Re-run regression checks after manual fix.", "Verify target file and search anchor."]
        candidate_followup_actions = [
            "Locate search anchor in candidate target file(s).",
            "Draft replacement from replacement_intent and suspected causes.",
            "Validate via regression checks before proposing patch.",
        ]
    else:
        refinement_status = "not_refinable"
        refinement_reason = "Insufficient Builder+Surgeon evidence for refinement."
        draft_candidate_quality = "low"
        requires_human_reconstruction = True
        candidate_change_scope = "unknown"
        candidate_validation_steps = ["Gather target file and root cause before refinement."]
        candidate_followup_actions = [
            "Review repair_reason and target_hint.",
            "Re-run Architect with narrower scope if needed.",
        ]

    return {
        "refinement_status": refinement_status,
        "refinement_reason": refinement_reason[:300],
        "refinement_inputs_present": refinement_inputs_present[:10],
        "refinement_inputs_missing": refinement_inputs_missing[:10],
        "draft_candidate_quality": draft_candidate_quality,
        "candidate_target_files": target_files[:10],
        "candidate_search_anchors": search_anchors[:5],
        "candidate_replacement_intent": replacement_intent[:300],
        "candidate_change_scope": candidate_change_scope,
        "candidate_validation_steps": candidate_validation_steps[:5],
        "candidate_followup_actions": candidate_followup_actions[:5],
        "requires_human_reconstruction": requires_human_reconstruction,
    }
