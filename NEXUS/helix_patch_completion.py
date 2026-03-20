"""
NEXUS HELIX patch completion assist (Phase 36).

Governed builder-assist layer: evaluates when a patch candidate is complete.
Does NOT fabricate search_text or replacement_text.
Completed fields ONLY populated when present in Builder patch payload.
"""

from __future__ import annotations

from typing import Any

VALID_COMPLETION_STATUS = ("not_completable", "partially_completable", "completed_patch_candidate")
VALID_COMPLETED_CANDIDATE_TYPE = ("diff_patch_candidate", "guided_followup_only", "advisory_only")


def evaluate_patch_completion(
    builder_result: dict[str, Any] | None,
    repair_metadata: dict[str, Any],
    patch_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Phase 36: Evaluate patch completion from Builder + Surgeon outputs.
    Does NOT fabricate patch content. completed_search_text and completed_replacement_text
    ONLY set when present in patch_payload (from Builder).
    """
    meta = repair_metadata or {}
    payload = patch_payload or {}
    impl_plan = (builder_result or {}).get("implementation_plan") or {}
    patch_req = impl_plan.get("patch_request") if isinstance(impl_plan, dict) else {}

    target_from_payload = payload.get("target_relative_path") or patch_req.get("target_relative_path") if isinstance(patch_req, dict) else None
    search_from_payload = payload.get("search_text") if payload else (patch_req.get("search_text") if isinstance(patch_req, dict) else None)
    replacement_from_payload = payload.get("replacement_text") if payload is not None else (patch_req.get("replacement_text") if isinstance(patch_req, dict) else None)

    has_target = bool(target_from_payload and str(target_from_payload).strip())
    has_search = bool(search_from_payload is not None and str(search_from_payload).strip())
    has_replacement = replacement_from_payload is not None

    target_files = meta.get("candidate_target_files") or meta.get("target_files_candidate") or []
    search_anchors = meta.get("candidate_search_anchors") or []
    replacement_intent = meta.get("candidate_replacement_intent") or ""
    conversion_status = (meta.get("conversion_status") or "not_convertible").strip().lower()
    refinement_status = (meta.get("refinement_status") or "not_refinable").strip().lower()

    completion_requirements_met: list[str] = []
    completion_requirements_missing: list[str] = []
    completion_evidence: list[str] = []

    if has_target:
        completion_requirements_met.append("target_file")
        completion_evidence.append("target_from_builder")
    elif target_files:
        completion_requirements_met.append("candidate_target_files")
        completion_evidence.append(f"candidate_targets={len(target_files)}")
    else:
        completion_requirements_missing.append("target_file")
    if has_search:
        completion_requirements_met.append("search_text")
        completion_evidence.append("search_from_builder")
    elif search_anchors or meta.get("target_hint"):
        completion_requirements_met.append("search_anchors_or_hint")
    else:
        completion_requirements_missing.append("search_text")
    if has_replacement:
        completion_requirements_met.append("replacement_text")
        completion_evidence.append("replacement_from_builder")
    elif replacement_intent or meta.get("suspected_root_causes"):
        completion_requirements_met.append("replacement_intent")
    else:
        completion_requirements_missing.append("replacement_text")

    if has_target and has_search and has_replacement:
        completion_status = "completed_patch_candidate"
        completion_reason = "Builder supplied full patch; completion complete."
        completion_confidence = "high"
        completed_candidate_type = "diff_patch_candidate"
        completed_target_file = str(target_from_payload or "").strip()
        completed_search_text = str(search_from_payload or "").strip()
        completed_replacement_text = str(replacement_from_payload or "")
        human_review_required = False
        requires_followup_before_approval = False
    elif conversion_status == "conditionally_convertible" and refinement_status == "partially_refined" and target_files:
        completion_status = "partially_completable"
        completion_reason = "Strong candidate; target and intent present. Human must provide search_text and replacement_text."
        completion_confidence = "medium"
        completed_candidate_type = "guided_followup_only"
        completed_target_file = target_files[0] if target_files else ""
        completed_search_text = ""
        completed_replacement_text = ""
        human_review_required = True
        requires_followup_before_approval = True
    elif target_files or replacement_intent:
        completion_status = "partially_completable"
        completion_reason = "Partial evidence; completion blocked by missing search/replace."
        completion_confidence = "low"
        completed_candidate_type = "guided_followup_only"
        completed_target_file = target_files[0] if target_files else ""
        completed_search_text = ""
        completed_replacement_text = ""
        human_review_required = True
        requires_followup_before_approval = True
    else:
        completion_status = "not_completable"
        completion_reason = "Insufficient evidence for completion; remain advisory."
        completion_confidence = "low"
        completed_candidate_type = "advisory_only"
        completed_target_file = ""
        completed_search_text = ""
        completed_replacement_text = ""
        human_review_required = True
        requires_followup_before_approval = True

    return {
        "completion_status": completion_status,
        "completion_reason": completion_reason[:300],
        "completion_requirements_met": completion_requirements_met[:10],
        "completion_requirements_missing": completion_requirements_missing[:10],
        "completion_confidence": completion_confidence,
        "completed_candidate_type": completed_candidate_type,
        "completed_target_file": completed_target_file[:500],
        "completed_search_text": completed_search_text[:2000],
        "completed_replacement_text": completed_replacement_text[:2000],
        "completion_evidence": completion_evidence[:5],
        "human_review_required": human_review_required,
        "requires_followup_before_approval": requires_followup_before_approval,
    }
