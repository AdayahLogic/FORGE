from __future__ import annotations

from typing import Any


def _normalize_str(v: Any, default: str = "") -> str:
    s = "" if v is None else str(v)
    return s.strip() if s is not None else default


def _derive_change_type(category: str | None) -> str:
    cat = _normalize_str(category).lower()
    if cat in ("hardening",):
        return "hardening"
    if cat in ("policy",):
        return "policy"
    if cat in ("monitoring",):
        return "monitoring"
    if cat in ("runtime",):
        return "runtime"
    if cat in ("productization", "ux"):
        return "ux"
    if cat in ("refactor",):
        return "refactor"
    # Safe default: refactor (still proposal-only).
    return "refactor"


def _derive_scope_level(*, selected_priority: str | None, target_area: str | None) -> str:
    pr = _normalize_str(selected_priority).lower()
    ta = _normalize_str(target_area).lower()

    if pr == "high":
        return "high"
    if pr == "medium":
        return "medium"
    if pr == "low":
        return "low"

    # If priority is unknown, infer from target_area core keywords.
    core_markers = ("workflow", "command_surface", "runtime_dispatcher", "production_guardrails", "guardrail", "state", "registry")
    if any(m in ta for m in core_markers):
        return "high"
    if ta:
        return "medium"
    return "low"


def _derive_risk_level(*, gate_status: str | None, gate_review_required: bool | None, regression_status: str | None) -> str:
    gs = _normalize_str(gate_status).lower()
    rs = _normalize_str(regression_status).lower()
    grr = bool(gate_review_required) if gate_review_required is not None else True

    # Hard stops and failure conditions are always high risk.
    if gs in ("blocked", "error_fallback"):
        return "high"
    if rs in ("blocked", "error_fallback"):
        return "high"

    # Review-required or warnings are medium.
    if gs in ("review_required", "error_fallback") or not grr:
        # If review isn't required (unexpected), still keep conservative.
        return "medium"
    if rs in ("warning", "none"):
        return "medium"

    # Allowed + passed is low risk.
    if gs == "allowed" and rs == "passed":
        return "low"

    return "medium"


def _derive_requires_review(*, gate_review_required: bool | None) -> bool:
    return bool(gate_review_required) if gate_review_required is not None else True


def _derive_requires_regression_check(*, regression_status: str | None) -> bool:
    rs = _normalize_str(regression_status).lower()
    # If regression checks aren't passed, request them for proposal acceptance.
    return rs != "passed"


def _derive_recommended_path(*, execution_allowed: bool | None, requires_review: bool, requires_regression_check: bool, gate_status: str | None, regression_status: str | None) -> str:
    gs = _normalize_str(gate_status).lower()
    rs = _normalize_str(regression_status).lower()

    # Critical defers.
    if gs in ("blocked", "error_fallback") or rs in ("blocked", "error_fallback"):
        return "defer"

    # If execution is allowed and safety gates are clean -> review-then-execute.
    if bool(execution_allowed) and not requires_review and not requires_regression_check and rs == "passed":
        return "review_then_execute"

    # In all other HELIOS proposal-only flows -> propose only.
    # (Even when execution could be allowed, the current HELIOS sprint is proposal-only.)
    if requires_review or requires_regression_check or gs in ("review_required", "allowed"):
        return "propose_only"

    return "defer"


def build_change_proposal(
    *,
    proposal_id: str,
    target_area: str | None,
    change_type: str | None,
    selected_priority: str | None,
    gate_status: str | None,
    gate_review_required: bool | None,
    regression_status: str | None,
    execution_allowed: bool | None,
    proposed_actions: list[str] | None = None,
    blocked_by: list[str] | None = None,
    requires_review: bool | None = None,
    requires_regression_check: bool | None = None,
    recommended_path: str | None = None,
) -> dict[str, Any]:
    """
    Deterministically normalize a structured HELIOS internal change proposal.
    """
    ta = _normalize_str(target_area).lower() if target_area is not None else ""
    tc = _normalize_str(change_type).lower() if change_type is not None else ""

    scope_level = _derive_scope_level(selected_priority=selected_priority, target_area=target_area)
    risk_level = _derive_risk_level(gate_status=gate_status, gate_review_required=gate_review_required, regression_status=regression_status)

    req_review_final = _derive_requires_review(gate_review_required=gate_review_required) if requires_review is None else bool(requires_review)
    req_reg_final = _derive_requires_regression_check(regression_status=regression_status) if requires_regression_check is None else bool(requires_regression_check)

    if not tc:
        tc = _derive_change_type(None)
    if not tc or tc not in ("hardening", "refactor", "policy", "monitoring", "ux", "runtime", "docs"):
        tc = _derive_change_type(None)

    rec_path_final = (
        _derive_recommended_path(
            execution_allowed=execution_allowed,
            requires_review=req_review_final,
            requires_regression_check=req_reg_final,
            gate_status=gate_status,
            regression_status=regression_status,
        )
        if recommended_path is None
        else str(recommended_path).strip().lower()
    )

    blocked_by_final = blocked_by or []
    proposed_actions_final = proposed_actions or []

    return {
        "proposal_id": _normalize_str(proposal_id, default="helios-change-proposal"),
        "target_area": ta if ta else (_normalize_str(target_area) if target_area is not None else None),
        "change_type": tc if tc else "refactor",
        "scope_level": scope_level,
        "risk_level": risk_level,
        "requires_review": bool(req_review_final),
        "requires_regression_check": bool(req_reg_final),
        "proposed_actions": list(proposed_actions_final),
        "blocked_by": list(blocked_by_final),
        "recommended_path": rec_path_final,
    }


def build_change_proposal_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_change_proposal(**kwargs)
    except Exception as e:
        return {
            "proposal_id": _normalize_str(kwargs.get("proposal_id"), default="helios-change-proposal-error"),
            "target_area": _normalize_str(kwargs.get("target_area")),
            "change_type": _normalize_str(kwargs.get("change_type") or "refactor"),
            "scope_level": "high",
            "risk_level": "high",
            "requires_review": True,
            "requires_regression_check": True,
            "proposed_actions": [],
            "blocked_by": [f"proposal_build_failed: {e}"],
            "recommended_path": "defer",
        }

