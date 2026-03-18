from __future__ import annotations

from typing import Any

from elite_layers.change_proposal import build_change_proposal_safe
from NEXUS.change_safety_gate import evaluate_change_gate_safe
from NEXUS.regression_checks import run_regression_checks_safe
from NEXUS.self_improvement_engine import build_self_improvement_backlog_safe, select_next_improvement_safe


def _safe_lower(v: Any) -> str:
    return "" if v is None else str(v).strip().lower()


def _derive_proposed_actions_from_item(*, item: dict[str, Any]) -> list[str]:
    category = _safe_lower(item.get("category"))
    item_id = _safe_lower(item.get("item_id"))
    title = _safe_lower(item.get("title"))
    target_area = _safe_lower(item.get("target_area"))

    actions: list[str] = []

    # Deterministic core actions based on category.
    if category == "hardening":
        actions.extend(
            [
                "Add contract tests for critical safety invariants.",
                "Harden interfaces for stable, non-None guardrail outputs.",
                "Add import-time compatibility checks for self-improvement modules.",
            ]
        )
    elif category == "policy":
        actions.extend(
            [
                "Document policy/guardrail decision semantics and invariants.",
                "Add contract tests for policy output stability (reason/status).",
                "Ensure operator-facing messages remain structured and consistent.",
            ]
        )
    elif category == "monitoring":
        actions.extend(
            [
                "Add regression check gate before accepting any proposal.",
                "Extend dashboard/operator visibility for the updated contract.",
                "Add lightweight reporting hooks for deterministic status surfaces.",
            ]
        )
    elif category == "runtime":
        actions.extend(
            [
                "Harden runtime routing/preflight visibility and contracts.",
                "Add contract tests for runtime dispatch gating behavior.",
                "Ensure no execution authority is granted by proposal-only flows.",
            ]
        )
    elif category == "productization":
        actions.extend(
            [
                "Improve operator console discoverability for the updated surface.",
                "Ensure command outputs remain stable and backwards compatible.",
                "Add minimal UI fields for proposal acceptance readiness signals.",
            ]
        )
    else:
        actions.extend(
            [
                "Add contract tests for interface stability.",
                "Update internal documentation for deterministic behavior.",
            ]
        )

    # Deterministic targeted action supplements based on item_id/title.
    if "recursive" in item_id or "recursive" in title or "nested" in title:
        actions.insert(0, "Audit recursive autonomous launch prevention and document the invariant.")
    if "logging" in item_id or "logging" in title:
        actions.insert(0, "Verify append-only logging write paths and add contract checks.")
    if "validator" in item_id or "validator" in title:
        actions.insert(0, "Validate guardrail outputs are always stable (never None) under edge cases.")
    if "runtime_router_visibility" in item_id or "visibility" in title:
        actions.insert(0, "Ensure runtime/model/deployment preflight surfaces are present in operator UIs.")
    if "operator" in item_id and "discoverability" in title:
        actions.insert(0, "Ensure operator snapshot clearly distinguishes registered vs unregistered scaffolds.")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for a in actions:
        s = str(a).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    # Add a very small scoping adjustment.
    if "command_surface" in target_area:
        out.append("Add backwards-compatible command_surface contract tests.")

    return out


def build_helios_expanded_summary(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    studio_driver_summary: dict[str, Any] | None = None,
    project_name: str | None = None,
    live_regression: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Expanded HELIOS result shape:
    {
      "helios_status": "planned" | "gated" | "deferred" | "error_fallback",
      "selected_improvement": null,
      "improvement_category": null,
      "improvement_reason": "...",
      "execution_gated": true,
      "change_proposal": { ... }
    }
    """
    try:
        coord = studio_coordination_summary or {}
        driver = studio_driver_summary or {}
        dash = dashboard_summary or {}

        priority_project = coord.get("priority_project")
        target_project = project_name or priority_project or "jarvis"

        # Build deterministic backlog; selection is deterministic.
        backlog_items = build_self_improvement_backlog_safe(
            dashboard_summary=dash,
            studio_coordination_summary=coord,
            driver_summary=driver,
        )
        selected = select_next_improvement_safe(backlog_items=backlog_items)

        selected_item_id = selected.get("selected_item_id")
        selected_item = None
        for it in backlog_items:
            if isinstance(it, dict) and it.get("item_id") == selected_item_id:
                selected_item = it
                break

        # Regression checks: deterministic import/compat checks.
        regression = {"regression_status": "none", "regression_reason": "Regression checks not run."}
        if live_regression:
            regression = run_regression_checks_safe(project_name=str(target_project or "jarvis"))

        # Change gate (planning-only): never grants execution authority.
        # Keep core_files_touched conservative (always False here).
        gate = evaluate_change_gate_safe(
            target_area=(selected_item or {}).get("target_area"),
            category=(selected_item or {}).get("category"),
            priority=(selected_item or {}).get("priority"),
            project_name=str(target_project or "jarvis"),
            core_files_touched=False,
        )

        gate_status = gate.get("change_gate_status") or "blocked"
        gate_review_required = gate.get("review_required", True)
        execution_allowed = bool(gate.get("execution_allowed", False))
        execution_gated = not execution_allowed

        regression_status = regression.get("regression_status") or "none"

        # Context from other systems is optional; only used to explain/adjust risk conservatively.
        veritas_status = dash.get("veritas_summary", {}).get("veritas_status") if isinstance(dash.get("veritas_summary"), dict) else None
        sentinel_status = dash.get("sentinel_summary", {}).get("sentinel_status") if isinstance(dash.get("sentinel_summary"), dict) else None
        sentinel_risk_level = dash.get("sentinel_summary", {}).get("risk_level") if isinstance(dash.get("sentinel_summary"), dict) else None

        # Determine helios status.
        if gate_status in ("blocked", "error_fallback") or regression_status in ("blocked", "error_fallback"):
            helios_status = "deferred"
        elif execution_gated:
            helios_status = "gated"
        else:
            helios_status = "planned"

        if not selected_item:
            selected_improvement = None
            improvement_category = None
            improvement_reason = "No self-improvement candidate selected."
            proposal_id = "helios-change-proposal-none"
            change_proposal = build_change_proposal_safe(
                proposal_id=proposal_id,
                target_area="none",
                change_type="refactor",
                selected_priority=None,
                gate_status=gate_status,
                gate_review_required=gate_review_required,
                regression_status=regression_status,
                execution_allowed=execution_allowed,
                proposed_actions=[],
                blocked_by=["no_candidate_selected"],
            )
        else:
            selected_improvement = selected_item
            improvement_category = selected_item.get("category")

            target_area = selected_item.get("target_area")
            priority = selected_item.get("priority")
            category = selected_item.get("category")

            # Derive change_type using proposal normalizer (it maps category -> change_type).
            # We pass `change_type` through explicitly for deterministic output.
            # (Even though build_change_proposal can derive, explicit keeps it stable.)
            change_type = {
                "hardening": "hardening",
                "policy": "policy",
                "monitoring": "monitoring",
                "runtime": "runtime",
                "productization": "ux",
            }.get(_safe_lower(category), "refactor")

            proposal_id = f"helios-change-proposal:{_safe_lower(selected_item.get('item_id')) or 'unknown'}"

            proposed_actions = _derive_proposed_actions_from_item(item=selected_item)

            blocked_by: list[str] = []
            if not gate.get("execution_allowed", False):
                blocked_by.append(f"change_gate={gate_status}")
            if regression_status != "passed":
                blocked_by.append(f"regression={regression_status}")

            # Conservatively enrich risk blocking with other systems if present.
            if veritas_status in ("error_fallback", "review_required"):
                blocked_by.append(f"veritas={veritas_status}")
            if sentinel_status in ("error_fallback", "review_required"):
                blocked_by.append(f"sentinel={sentinel_status}")
            if _safe_lower(sentinel_risk_level) == "high":
                blocked_by.append("sentinel_risk=high")

            change_proposal = build_change_proposal_safe(
                proposal_id=proposal_id,
                target_area=target_area,
                change_type=change_type,
                selected_priority=priority,
                gate_status=gate_status,
                gate_review_required=gate_review_required,
                regression_status=regression_status,
                execution_allowed=execution_allowed,
                proposed_actions=proposed_actions,
                blocked_by=blocked_by,
            )

            improvement_reason = (
                f"Selected item={selected_item.get('item_id')}; "
                f"gate={gate_status} (review_required={gate_review_required}, execution_allowed={execution_allowed}); "
                f"regression={regression_status}."
            )

        return {
            "helios_status": helios_status,
            "selected_improvement": selected_improvement,
            "improvement_category": improvement_category,
            "improvement_reason": improvement_reason,
            "execution_gated": bool(execution_gated),
            "change_proposal": change_proposal,
        }
    except Exception as e:
        # Safe fallback: always proposal-only with conservative gating.
        return {
            "helios_status": "error_fallback",
            "selected_improvement": None,
            "improvement_category": None,
            "improvement_reason": f"HELIOS expanded evaluation failed: {e}",
            "execution_gated": True,
            "change_proposal": build_change_proposal_safe(
                proposal_id="helios-change-proposal-error_fallback",
                target_area="none",
                change_type="refactor",
                selected_priority=None,
                gate_status="error_fallback",
                gate_review_required=True,
                regression_status="error_fallback",
                execution_allowed=False,
                proposed_actions=[],
                blocked_by=["helios_engine_exception"],
            ),
        }


def build_helios_expanded_summary_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_helios_expanded_summary(**kwargs)
    except Exception:
        return {
            "helios_status": "error_fallback",
            "selected_improvement": None,
            "improvement_category": None,
            "improvement_reason": "HELIOS expanded evaluation failed.",
            "execution_gated": True,
            "change_proposal": build_change_proposal_safe(
                proposal_id="helios-change-proposal-error_fallback",
                target_area="none",
                change_type="refactor",
                selected_priority=None,
                gate_status="error_fallback",
                gate_review_required=True,
                regression_status="error_fallback",
                execution_allowed=False,
                proposed_actions=[],
                blocked_by=["helios_engine_safe_wrapper_exception"],
            ),
        }

