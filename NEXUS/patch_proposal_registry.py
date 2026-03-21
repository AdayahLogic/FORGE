"""
NEXUS patch proposal registry (Phase 23).

Governed patch proposal storage. Proposals are first-class artifacts;
application is approval-gated and uses existing diff_patch infrastructure.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from NEXUS.ref_utils import normalize_ref_list

PATCH_PROPOSAL_JOURNAL_FILENAME = "patch_proposal_journal.jsonl"
PATCH_PROPOSAL_RESOLUTION_FILENAME = "patch_proposal_resolution.jsonl"

# Allowed source values
PATCH_SOURCES = ("helix_builder", "surgeon", "manual", "architect", "unknown")
# Allowed status values
PATCH_STATUSES = (
    "proposed",
    "approval_required",
    "approved_pending_apply",
    "rejected",
    "blocked",
    "applied",
    "error_fallback",
)
# Allowed change_type values (Phase 33: guided_patch_followup for draft-followup artifacts)
CHANGE_TYPES = ("diff_patch", "safe_patch", "advisory_only", "guided_patch_followup")


def get_patch_proposal_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for patch proposal journal."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_patch_proposal_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped patch proposal journal."""
    state_dir = get_patch_proposal_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PATCH_PROPOSAL_JOURNAL_FILENAME)


def normalize_patch_proposal(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize patch proposal to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    source = str(r.get("source") or "unknown").strip().lower()
    if source not in PATCH_SOURCES:
        source = "unknown"
    status = str(r.get("status") or "proposed").strip().lower()
    if status not in PATCH_STATUSES:
        status = "proposed"
    change_type = str(r.get("change_type") or "diff_patch").strip().lower()
    if change_type not in CHANGE_TYPES:
        change_type = "diff_patch"

    now = datetime.now().isoformat()
    patch_payload = r.get("patch_payload")
    if not isinstance(patch_payload, dict):
        patch_payload = {}

    out: dict[str, Any] = {
        "patch_id": str(r.get("patch_id") or uuid.uuid4().hex[:16]),
        "project_name": str(r.get("project_name") or ""),
        "run_id": str(r.get("run_id") or ""),
        "source": source,
        "status": status,
        "summary": str(r.get("summary") or "")[:500],
        "target_files": list(r.get("target_files") or [])[:20],
        "change_type": change_type,
        "risk_level": str(r.get("risk_level") or "medium").strip().lower()[:20],
        "requires_approval": bool(r.get("requires_approval", True)),
        "approval_id_refs": normalize_ref_list(r.get("approval_id_refs")),
        "product_id_refs": normalize_ref_list(r.get("product_id_refs")),
        "autonomy_id_refs": normalize_ref_list(r.get("autonomy_id_refs")),
        "helix_id_refs": normalize_ref_list(r.get("helix_id_refs")),
        "rationale": str(r.get("rationale") or "")[:1000],
        "patch_payload": patch_payload,
        "created_at": str(r.get("created_at") or now),
        "updated_at": str(r.get("updated_at") or now),
    }
    # Phase 33: proposal readiness and draft quality
    proposal_readiness = str(r.get("proposal_readiness") or "").strip().lower()
    if proposal_readiness not in ("fully_ready", "draft_followup", "advisory_only"):
        proposal_readiness = "fully_ready" if change_type == "diff_patch" and patch_payload.get("search_text") else "advisory_only"
    out["proposal_readiness"] = proposal_readiness
    proposal_completeness = str(r.get("proposal_completeness") or "").strip().lower()
    if proposal_completeness not in ("complete", "partial", "advisory"):
        proposal_completeness = "complete" if proposal_readiness == "fully_ready" else ("partial" if proposal_readiness == "draft_followup" else "advisory")
    out["proposal_completeness"] = proposal_completeness
    out["draft_source"] = str(r.get("draft_source") or source)[:50]
    out["missing_information_flags"] = list(r.get("missing_information_flags") or [])[:10]
    out["requires_followup_before_apply"] = bool(r.get("requires_followup_before_apply", proposal_readiness != "fully_ready"))
    # Phase 34: refinement fields (from patch_payload or top-level)
    pp = out.get("patch_payload") or {}
    out["refinement_status"] = str(r.get("refinement_status") or pp.get("refinement_status") or "not_refinable").strip().lower()
    if out["refinement_status"] not in ("not_refinable", "partially_refined", "draft_ready"):
        out["refinement_status"] = "not_refinable"
    out["draft_candidate_quality"] = str(r.get("draft_candidate_quality") or pp.get("draft_candidate_quality") or "low").strip().lower()
    if out["draft_candidate_quality"] not in ("low", "medium", "high"):
        out["draft_candidate_quality"] = "low"
    out["candidate_change_scope"] = str(r.get("candidate_change_scope") or pp.get("candidate_change_scope") or "unknown").strip().lower()
    rhr = r.get("requires_human_reconstruction")
    if rhr is None:
        rhr = pp.get("requires_human_reconstruction")
    if rhr is None:
        rhr = proposal_readiness != "fully_ready"
    out["requires_human_reconstruction"] = bool(rhr)
    # Phase 35: conversion and maturity fields
    conversion_status = str(r.get("conversion_status") or pp.get("conversion_status") or "").strip().lower()
    if conversion_status not in ("not_convertible", "conditionally_convertible", "converted_to_patch_candidate"):
        conversion_status = "converted_to_patch_candidate" if (change_type == "diff_patch" and patch_payload.get("search_text")) else "conditionally_convertible"
    out["conversion_status"] = conversion_status
    out["conversion_reason"] = str(r.get("conversion_reason") or "")[:300]
    out["conversion_requirements_met"] = list(r.get("conversion_requirements_met") or [])[:10]
    out["conversion_requirements_missing"] = list(r.get("conversion_requirements_missing") or [])[:10]
    out["executable_candidate"] = bool(r.get("executable_candidate") if "executable_candidate" in r else (change_type == "diff_patch" and bool(patch_payload.get("search_text"))))
    proposal_maturity = str(r.get("proposal_maturity") or pp.get("proposal_maturity") or "").strip().lower()
    if proposal_maturity not in ("advisory", "guided_followup", "strong_candidate", "executable"):
        proposal_maturity = "executable" if out["executable_candidate"] else ("strong_candidate" if conversion_status == "conditionally_convertible" and out.get("refinement_status") == "partially_refined" else "guided_followup")
    out["proposal_maturity"] = proposal_maturity
    out["conversion_confidence"] = str(r.get("conversion_confidence") or "low").strip().lower()
    if out["conversion_confidence"] not in ("low", "medium", "high"):
        out["conversion_confidence"] = "high" if out["executable_candidate"] else "low"
    out["ready_for_human_patch_review"] = bool(r.get("ready_for_human_patch_review", True))
    out["ready_for_governed_patch_validation"] = bool(r.get("ready_for_governed_patch_validation", out["executable_candidate"]))
    # Phase 36: completion fields
    completion_status = str(r.get("completion_status") or pp.get("completion_status") or "").strip().lower()
    if completion_status not in ("not_completable", "partially_completable", "completed_patch_candidate"):
        completion_status = "completed_patch_candidate" if out["executable_candidate"] else "partially_completable"
    out["completion_status"] = completion_status
    out["completion_reason"] = str(r.get("completion_reason") or "")[:300]
    out["completion_requirements_met"] = list(r.get("completion_requirements_met") or [])[:10]
    out["completion_requirements_missing"] = list(r.get("completion_requirements_missing") or [])[:10]
    out["completion_confidence"] = str(r.get("completion_confidence") or "low").strip().lower()
    if out["completion_confidence"] not in ("low", "medium", "high"):
        out["completion_confidence"] = "high" if out["executable_candidate"] else "low"
    out["completed_candidate_type"] = str(r.get("completed_candidate_type") or pp.get("completed_candidate_type") or "advisory_only").strip().lower()
    if out["completed_candidate_type"] not in ("diff_patch_candidate", "guided_followup_only", "advisory_only"):
        out["completed_candidate_type"] = "diff_patch_candidate" if out["executable_candidate"] else "guided_followup_only"
    rfb = r.get("requires_followup_before_approval")
    if rfb is None:
        rfb = not out["executable_candidate"]
    out["requires_followup_before_approval"] = bool(rfb)
    # Phase 37: candidate review readiness (derived from proposal fields)
    try:
        from NEXUS.candidate_review_workflow import evaluate_candidate_review_readiness
        rev = evaluate_candidate_review_readiness(out)
        out["review_status"] = rev.get("review_status", "not_ready_for_review")
        out["review_readiness"] = rev.get("review_readiness", "low")
        out["review_reason"] = rev.get("review_reason", "")[:300]
        out["review_requirements_met"] = rev.get("review_requirements_met", [])[:10]
        out["review_requirements_missing"] = rev.get("review_requirements_missing", [])[:10]
        out["human_review_required"] = rev.get("human_review_required", True)
        out["approval_progression_ready"] = rev.get("approval_progression_ready", False)
        out["next_step_recommendation"] = rev.get("next_step_recommendation", "")[:200]
    except Exception:
        out["review_status"] = "not_ready_for_review"
        out["review_readiness"] = "low"
        out["review_reason"] = ""
        out["review_requirements_met"] = []
        out["review_requirements_missing"] = ["evaluation_failed"]
        out["human_review_required"] = True
        out["approval_progression_ready"] = False
        out["next_step_recommendation"] = "Review readiness evaluation failed; assume manual review."
    return out


def append_patch_proposal(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized patch proposal to the project's journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_patch_proposal_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_patch_proposal(record)
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_patch_proposal_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_patch_proposal(project_path=project_path, record=record)
    except Exception:
        return None


def _truncate_for_json(v: Any, max_str_len: int = 2000) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        if isinstance(v, str) and len(v) > max_str_len:
            return v[:max_str_len]
        return v
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, val in list(v.items())[:50]:
            out[str(k)] = _truncate_for_json(val, max_str_len=max_str_len)
        return out
    if isinstance(v, list):
        return [_truncate_for_json(x, max_str_len=max_str_len) for x in v[:50]]
    return str(v)[:max_str_len]


def read_patch_proposal_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n patch proposal journal lines. Corruption-tolerant."""
    path = get_patch_proposal_journal_path(project_path)
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def find_proposal_and_project(patch_id: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Search all projects for patch_id. Return (proposal, project_path, project_key) or (None, None, None)."""
    if not patch_id:
        return None, None, None
    try:
        from NEXUS.registry import PROJECTS
        for proj_key in PROJECTS:
            path = PROJECTS.get(proj_key, {}).get("path")
            if path:
                p = get_patch_proposal_by_id(project_path=path, patch_id=patch_id)
                if p:
                    return p, path, proj_key
    except Exception:
        pass
    return None, None, None


def get_patch_proposal_by_id(
    project_path: str | None,
    patch_id: str,
    n: int = 200,
) -> dict[str, Any] | None:
    """Return patch proposal by id, or None if not found."""
    if not patch_id:
        return None
    tail = read_patch_proposal_journal_tail(project_path=project_path, n=n)
    for r in reversed(tail):
        if r.get("patch_id") == patch_id:
            return r
    return None


def get_patch_proposal_resolution_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped patch proposal resolution journal."""
    state_dir = get_patch_proposal_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PATCH_PROPOSAL_RESOLUTION_FILENAME)


def read_patch_proposal_resolution_tail(
    project_path: str | None,
    n: int = 100,
) -> list[dict[str, Any]]:
    """Read last n resolution records. Corruption-tolerant."""
    path = get_patch_proposal_resolution_journal_path(project_path)
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict) and parsed.get("patch_id"):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def get_latest_resolution_for_patch(
    project_path: str | None,
    patch_id: str,
    n: int = 100,
) -> dict[str, Any] | None:
    """Return latest resolution record for patch_id, or None."""
    if not patch_id:
        return None
    tail = read_patch_proposal_resolution_tail(project_path=project_path, n=n)
    for r in reversed(tail):
        if r.get("patch_id") == patch_id:
            return r
    return None


def get_proposal_effective_status(
    project_path: str | None,
    patch_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """
    Return (effective_status, latest_resolution).
    Effective status = resolution.new_status if resolution exists else proposal.status.
    """
    proposal = get_patch_proposal_by_id(project_path=project_path, patch_id=patch_id)
    base_status = str(proposal.get("status") or "proposed").strip().lower() if proposal else "proposed"
    resolution = get_latest_resolution_for_patch(project_path=project_path, patch_id=patch_id)
    if resolution:
        new_status = str(resolution.get("new_status") or base_status).strip().lower()
        if new_status in PATCH_STATUSES:
            return new_status, resolution
    return base_status, resolution


def append_patch_proposal_resolution(
    project_path: str | None,
    patch_id: str,
    decision: str,
    new_status: str,
    approval_id: str,
    *,
    project_name: str = "",
    reason: str = "",
) -> str | None:
    """
    Append resolution record. Never raises.
    decision: approve | reject
    new_status: approved_pending_apply | rejected
    """
    path = get_patch_proposal_resolution_journal_path(project_path)
    if not path:
        return None
    if decision not in ("approve", "reject", "apply"):
        return None
    if new_status not in PATCH_STATUSES:
        return None
    now = datetime.now().isoformat()
    record = {
        "patch_id": patch_id,
        "decision": decision,
        "new_status": new_status,
        "approval_id": approval_id,
        "project_name": project_name,
        "reason": reason[:500],
        "timestamp": now,
    }
    if new_status == "approved_pending_apply":
        try:
            from NEXUS.approval_staleness import compute_expiry_metadata, get_staleness_hours
            meta = compute_expiry_metadata(record, record_type="resolution")
            record["expiry_timestamp"] = meta.get("expiry_timestamp", "")
            record["stale_after_hours"] = meta.get("stale_after_hours", 24.0)
        except Exception:
            record["expiry_timestamp"] = ""
            record["stale_after_hours"] = 24.0
    try:
        safe = _truncate_for_json(record)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def resolve_patch_proposal(
    project_path: str | None,
    patch_id: str,
    decision: str,
    *,
    project_name: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """
    Approve or reject a patch proposal.
    Validates proposal exists and is in proposed/approval_required.
    Appends resolution + approval record.
    Returns result dict; never raises.
    """
    result: dict[str, Any] = {
        "resolved": False,
        "patch_id": patch_id,
        "decision": decision,
        "effective_status": "",
        "approval_id": "",
        "reason": "",
        "error": "",
    }
    if not project_path or not patch_id:
        result["error"] = "project_path and patch_id required."
        return result
    proposal = get_patch_proposal_by_id(project_path=project_path, patch_id=patch_id)
    if not proposal:
        result["error"] = "Patch proposal not found."
        return result
    current_status, _ = get_proposal_effective_status(project_path=project_path, patch_id=patch_id)
    if current_status not in ("proposed", "approval_required"):
        result["error"] = f"Proposal not resolvable; current status={current_status}."
        result["effective_status"] = current_status
        return result
    if decision == "approve":
        new_status = "approved_pending_apply"
    elif decision == "reject":
        new_status = "rejected"
    else:
        result["error"] = f"Invalid decision: {decision}."
        return result
    approval_id = uuid.uuid4().hex[:16]
    written = append_patch_proposal_resolution(
        project_path=project_path,
        patch_id=patch_id,
        decision=decision,
        new_status=new_status,
        approval_id=approval_id,
        project_name=project_name or proposal.get("project_name", ""),
        reason=reason,
    )
    if not written:
        result["error"] = "Failed to write resolution."
        return result
    try:
        from NEXUS.approval_registry import append_approval_record_safe
        approval_record = {
            "approval_id": approval_id,
            "project_name": project_name or proposal.get("project_name", ""),
            "status": "approved" if decision == "approve" else "rejected",
            "approval_type": "patch_proposal_resolution",
            "reason": reason or f"{decision} patch proposal {patch_id}",
            "context": {"patch_id": patch_id, "decision": decision, "new_status": new_status},
            "decision": decision,
            "decision_timestamp": datetime.now().isoformat(),
        }
        append_approval_record_safe(project_path=project_path, record=approval_record)
    except Exception:
        pass
    result["resolved"] = True
    result["effective_status"] = new_status
    result["approval_id"] = approval_id
    result["reason"] = reason or f"Patch proposal {decision}d."
    return result
