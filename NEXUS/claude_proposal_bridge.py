"""
NEXUS Claude proposal bridge (Phase 4).

Translates normalized Claude proposed_actions into governed system objects.

Claude proposes. NEXUS decides.

This bridge converts Claude's structured proposals into sealed, review-pending
governed objects using existing NEXUS creation patterns. No action is executed
directly. All created objects require the existing approval/review lifecycle
before any activation.

Proposal → governed object mapping:
    create_followup_package  → sealed execution package + approval record
    require_human_review     → approval record
    route_to_codex           → candidate review journal record
    route_to_cursor_review   → candidate review journal record
    no_action_required       → clean no-op (logged with justification)

All translation is append-only, auditable, and wrapped in safe guards.
Failures are recorded as error_fallback outcomes and never propagate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


_VALID_PROPOSAL_ACTION_TYPES = frozenset({
    "route_to_codex",
    "route_to_cursor_review",
    "create_followup_package",
    "require_human_review",
    "no_action_required",
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_project_path(dispatch_plan: dict[str, Any]) -> str | None:
    """Extract project_path from dispatch_plan. Returns None if absent or empty."""
    path = str((dispatch_plan.get("project") or {}).get("project_path") or "").strip()
    return path or None


def _safe_project_name(dispatch_plan: dict[str, Any]) -> str:
    return str((dispatch_plan.get("project") or {}).get("project_name") or "").strip()


def _build_proposal_trace(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
    runtime_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a lightweight trace dict linking a governed object back to the
    originating Claude proposal and its source artifact.

    This trace is embedded into execution package metadata so the operator
    can always answer: which Claude proposal created this object?
    """
    artifact = runtime_artifact or {}
    return {
        "source_runtime": "claude",
        "bridge_phase": "phase_3_action_proposer",
        "proposal_index": proposal_index,
        "action_type": str(proposal.get("action_type") or ""),
        "target": str(proposal.get("target") or ""),
        "justification": str(proposal.get("justification") or ""),
        "required_approval": bool(proposal.get("required_approval", True)),
        "originating_artifact": {
            "artifact_type": str(artifact.get("artifact_type") or ""),
            "confidence_score": float(artifact.get("confidence_score") or 0.0),
            "risk_level": str(artifact.get("risk_level") or ""),
        },
    }


def _make_error_record(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
    error: str,
) -> dict[str, Any]:
    """Build a uniform error_fallback translation record."""
    return {
        "proposal_index": proposal_index,
        "action_type": str(proposal.get("action_type") or ""),
        "target": str(proposal.get("target") or ""),
        "justification": str(proposal.get("justification") or ""),
        "required_approval": bool(proposal.get("required_approval", True)),
        "outcome": "error_fallback",
        "approval_id": None,
        "package_id": None,
        "package_path": None,
        "review_id": None,
        "error": str(error),
        "source_runtime": "claude",
    }


# ---------------------------------------------------------------------------
# Per-proposal translators
# ---------------------------------------------------------------------------

def _translate_create_followup_package(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
    dispatch_plan: dict[str, Any],
    aegis_res: dict[str, Any] | None,
    authority_trace: dict[str, Any] | None,
    runtime_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Create a sealed execution package + approval record for a
    create_followup_package proposal.

    The package is always sealed, review_status="pending",
    requires_human_approval=True. No execution is triggered.
    """
    try:
        from NEXUS.approval_builder import build_approval_record
        from NEXUS.approval_registry import append_approval_record_safe
        from NEXUS.execution_package_builder import build_execution_package_safe
        from NEXUS.execution_package_registry import write_execution_package_safe

        project_path = _safe_project_path(dispatch_plan)
        justification = str(
            proposal.get("justification") or "Claude proposed follow-up package."
        ).strip()

        # Build and persist the approval record first so the package can reference it.
        approval_record = build_approval_record(
            dispatch_plan=dispatch_plan,
            aegis_result=aegis_res,
            approval_type="claude_proposal",
            reason=justification or "Claude proposed follow-up package requiring human approval.",
        )
        append_approval_record_safe(project_path=project_path, record=approval_record)
        approval_id = str(approval_record.get("approval_id") or "")

        # Enrich the authority trace with the proposal trace so the package
        # carries a full audit link back to the originating Claude proposal.
        proposal_trace = _build_proposal_trace(
            proposal=proposal,
            proposal_index=proposal_index,
            runtime_artifact=runtime_artifact,
        )
        enriched_authority_trace: dict[str, Any] = {
            **(authority_trace or {}),
            "claude_proposal_trace": proposal_trace,
        }

        # Build the sealed review-only execution package.
        package = build_execution_package_safe(
            dispatch_plan=dispatch_plan,
            aegis_result=aegis_res,
            approval_record=approval_record,
            approval_id=approval_id,
            package_reason=justification,
            authority_trace=enriched_authority_trace,
        )
        package_id = str(package.get("package_id") or "")
        package_path = write_execution_package_safe(
            project_path=project_path,
            package=package,
        )

        return {
            "proposal_index": proposal_index,
            "action_type": "create_followup_package",
            "target": str(proposal.get("target") or ""),
            "justification": justification,
            "required_approval": bool(proposal.get("required_approval", True)),
            "outcome": "followup_package_created",
            "approval_id": approval_id or None,
            "package_id": package_id or None,
            "package_path": str(package_path or "") or None,
            "review_id": None,
            "error": None,
            "source_runtime": "claude",
        }
    except Exception as e:
        return _make_error_record(
            proposal=proposal,
            proposal_index=proposal_index,
            error=str(e),
        )


def _translate_require_human_review(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
    dispatch_plan: dict[str, Any],
    aegis_res: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Create an approval record for a require_human_review proposal.

    The record is appended to approval_journal.jsonl. No package is created;
    the approval record alone creates the correct review gate.
    """
    try:
        from NEXUS.approval_builder import build_approval_record
        from NEXUS.approval_registry import append_approval_record_safe

        project_path = _safe_project_path(dispatch_plan)
        justification = str(
            proposal.get("justification") or "Claude requested human review."
        ).strip()

        approval_record = build_approval_record(
            dispatch_plan=dispatch_plan,
            aegis_result=aegis_res,
            approval_type="claude_proposal",
            reason=justification or "Claude requested human review.",
        )
        append_approval_record_safe(project_path=project_path, record=approval_record)
        approval_id = str(approval_record.get("approval_id") or "")

        return {
            "proposal_index": proposal_index,
            "action_type": "require_human_review",
            "target": str(proposal.get("target") or ""),
            "justification": justification,
            "required_approval": bool(proposal.get("required_approval", True)),
            "outcome": "approval_record_created",
            "approval_id": approval_id or None,
            "package_id": None,
            "package_path": None,
            "review_id": None,
            "error": None,
            "source_runtime": "claude",
        }
    except Exception as e:
        return _make_error_record(
            proposal=proposal,
            proposal_index=proposal_index,
            error=str(e),
        )


def _translate_route_proposal(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
    dispatch_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a candidate review journal record for a route_to_codex or
    route_to_cursor_review proposal.

    The record surfaces into the candidate review workflow with
    human_review_required=True. No approval record is created (none needed
    for a routing candidate); operator reviews before any routing occurs.
    """
    action_type = str(proposal.get("action_type") or "").strip().lower()
    try:
        from NEXUS.candidate_review_registry import append_candidate_review_record_safe

        project_path = _safe_project_path(dispatch_plan)
        project_name = _safe_project_name(dispatch_plan)
        justification = str(
            proposal.get("justification") or f"Claude proposed {action_type}."
        ).strip()
        review_id = uuid.uuid4().hex[:16]

        review_record: dict[str, Any] = {
            "review_id": review_id,
            "patch_id": "",           # no patch at proposal stage
            "project_name": project_name,
            "review_status": "ready_for_review",
            "review_reason": justification,
            "review_readiness": "medium",
            "review_requirements_met": [],
            "review_requirements_missing": ["operator_approval"],
            "reviewer_notes": "",
            "review_outcome": "",
            "followup_actions": [
                {
                    "action": action_type,
                    "target": str(proposal.get("target") or ""),
                }
            ],
            "human_review_required": True,
            "approval_progression_ready": False,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            # Extra trace fields — stored in journal, truncated safely by registry.
            "source_runtime": "claude",
            "proposal_index": proposal_index,
        }
        append_candidate_review_record_safe(project_path=project_path, record=review_record)

        return {
            "proposal_index": proposal_index,
            "action_type": action_type,
            "target": str(proposal.get("target") or ""),
            "justification": justification,
            "required_approval": bool(proposal.get("required_approval", True)),
            "outcome": "review_candidate_created",
            "approval_id": None,
            "package_id": None,
            "package_path": None,
            "review_id": review_id,
            "error": None,
            "source_runtime": "claude",
        }
    except Exception as e:
        return _make_error_record(
            proposal=proposal,
            proposal_index=proposal_index,
            error=str(e),
        )


def _translate_no_action(
    *,
    proposal: dict[str, Any],
    proposal_index: int,
) -> dict[str, Any]:
    """
    Record a clean no-op for no_action_required proposals.

    No governed objects are created; the justification is preserved in the
    translation record for auditability.
    """
    return {
        "proposal_index": proposal_index,
        "action_type": "no_action_required",
        "target": str(proposal.get("target") or ""),
        "justification": str(
            proposal.get("justification") or "Claude determined no action required."
        ),
        "required_approval": bool(proposal.get("required_approval", False)),
        "outcome": "no_action",
        "approval_id": None,
        "package_id": None,
        "package_path": None,
        "review_id": None,
        "error": None,
        "source_runtime": "claude",
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def translate_claude_proposals(
    *,
    proposed_actions: list[dict[str, Any]],
    dispatch_plan: dict[str, Any],
    aegis_res: dict[str, Any] | None = None,
    authority_trace: dict[str, Any] | None = None,
    runtime_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Translate a list of normalized Claude proposed_actions into governed
    system objects.

    Returns a translation_summary dict suitable for attaching to dispatch_result.
    Callers should use translate_claude_proposals_safe() instead — it wraps
    this function and guarantees no exception propagates.

    Proposal → governed object mapping:
        create_followup_package  → execution package + approval record
        require_human_review     → approval record
        route_to_codex           → candidate review record
        route_to_cursor_review   → candidate review record
        no_action_required       → no-op (logged)
        unknown/invalid          → normalised to require_human_review

    Schema of returned dict:
        translation_count     int
        source_runtime        "claude"
        translations          list[TranslationRecord]
        followup_package_ids  list[str]
        approval_ids          list[str]
        review_candidate_ids  list[str]

    Each TranslationRecord:
        proposal_index    int
        action_type       str
        target            str
        justification     str
        required_approval bool
        outcome           "followup_package_created" | "approval_record_created"
                          | "review_candidate_created" | "no_action" | "error_fallback"
        approval_id       str | None
        package_id        str | None
        package_path      str | None
        review_id         str | None
        error             str | None
        source_runtime    "claude"
    """
    translations: list[dict[str, Any]] = []
    followup_package_ids: list[str] = []
    approval_ids: list[str] = []
    review_candidate_ids: list[str] = []

    for i, proposal in enumerate(proposed_actions or []):
        if not isinstance(proposal, dict):
            continue

        action_type = str(proposal.get("action_type") or "").strip().lower()
        if action_type not in _VALID_PROPOSAL_ACTION_TYPES:
            # Normalise unknown types to the safe default, preserving all other fields.
            proposal = {**proposal, "action_type": "require_human_review"}
            action_type = "require_human_review"

        if action_type == "create_followup_package":
            record = _translate_create_followup_package(
                proposal=proposal,
                proposal_index=i,
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
                authority_trace=authority_trace,
                runtime_artifact=runtime_artifact,
            )
            if record.get("package_id"):
                followup_package_ids.append(record["package_id"])
            if record.get("approval_id"):
                approval_ids.append(record["approval_id"])

        elif action_type == "require_human_review":
            record = _translate_require_human_review(
                proposal=proposal,
                proposal_index=i,
                dispatch_plan=dispatch_plan,
                aegis_res=aegis_res,
            )
            if record.get("approval_id"):
                approval_ids.append(record["approval_id"])

        elif action_type in ("route_to_codex", "route_to_cursor_review"):
            record = _translate_route_proposal(
                proposal=proposal,
                proposal_index=i,
                dispatch_plan=dispatch_plan,
            )
            if record.get("review_id"):
                review_candidate_ids.append(record["review_id"])

        elif action_type == "no_action_required":
            record = _translate_no_action(proposal=proposal, proposal_index=i)

        else:
            # Unreachable after normalisation above — defensive fallback.
            record = _make_error_record(
                proposal=proposal,
                proposal_index=i,
                error=f"Unhandled action_type after normalisation: {action_type!r}",
            )

        translations.append(record)

    return {
        "translation_count": len(translations),
        "source_runtime": "claude",
        "translations": translations,
        "followup_package_ids": followup_package_ids,
        "approval_ids": approval_ids,
        "review_candidate_ids": review_candidate_ids,
    }


def translate_claude_proposals_safe(
    *,
    proposed_actions: list[dict[str, Any]],
    dispatch_plan: dict[str, Any],
    aegis_res: dict[str, Any] | None = None,
    authority_trace: dict[str, Any] | None = None,
    runtime_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Safe wrapper around translate_claude_proposals.

    Never raises. Returns an error_fallback summary if the translation
    function itself throws an unexpected exception. Per-proposal exceptions
    are already caught inside translate_claude_proposals and recorded as
    error_fallback outcomes; this wrapper guards against top-level failures
    (e.g., import errors, unexpected state) so the dispatch flow is
    never interrupted.
    """
    try:
        return translate_claude_proposals(
            proposed_actions=proposed_actions,
            dispatch_plan=dispatch_plan,
            aegis_res=aegis_res,
            authority_trace=authority_trace,
            runtime_artifact=runtime_artifact,
        )
    except Exception as e:
        return {
            "translation_count": 0,
            "source_runtime": "claude",
            "translations": [],
            "followup_package_ids": [],
            "approval_ids": [],
            "review_candidate_ids": [],
            "outcome": "error_fallback",
            "error": str(e),
        }
