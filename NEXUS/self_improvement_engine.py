"""
NEXUS self-improvement backlog engine (planning only).

Provides deterministic backlog building and selection for controlled
self-improvement. No execution is performed here.
"""

from __future__ import annotations

from typing import Any, Iterable


def build_self_improvement_backlog(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    driver_summary: dict[str, Any] | None = None,
    backlog_seed: Iterable[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Build a compact deterministic self-improvement backlog.

    Returns a list of backlog items:
    {
      item_id, title, category, priority, status, reason, target_area
    }
    """
    # Deterministic base backlog
    base_items: list[dict[str, Any]] = [
        {
            "item_id": "hardening_no_recursive_launch_guard_audit",
            "title": "Audit nested autonomous launch prevention",
            "category": "hardening",
            "priority": "high",
            "status": "open",
            "reason": "Ensure no recursion path exists; confirm guard behavior in real command flows.",
            "target_area": "autonomous_launcher",
        },
        {
            "item_id": "hardening_logging_write_path_verification",
            "title": "Verify append-only logging write paths",
            "category": "hardening",
            "priority": "high",
            "status": "open",
            "reason": "Ensure logs/forge_operations.jsonl is appended from command/autonomy/driver decisions.",
            "target_area": "logging_engine + command_surface",
        },
        {
            "item_id": "hardening_validator_integration_contracts",
            "title": "Validate guardrail outputs are stable/non-None",
            "category": "policy",
            "priority": "high",
            "status": "open",
            "reason": "Ensure guardrail_status/launch_allowed/reason never return None in command output.",
            "target_area": "production_guardrails + command_surface",
        },
        {
            "item_id": "runtime_router_visibility_contract",
            "title": "Ensure runtime/model/deployment preflight are visible to UI",
            "category": "runtime",
            "priority": "medium",
            "status": "open",
            "reason": "Operator console should provide deterministic routing and preflight visibility.",
            "target_area": "runtime_router + model_router + deployment_preflight",
        },
        {
            "item_id": "monitoring_regression_checks_on_change",
            "title": "Add regression check gate before self-improvement acceptance",
            "category": "monitoring",
            "priority": "medium",
            "status": "open",
            "reason": "Provide import/compile checks and dashboard build checks as safety gates.",
            "target_area": "regression_checks",
        },
        {
            "item_id": "productization_operator_console_discoverability",
            "title": "Improve operator snapshot discoverability for unregistered scaffolds",
            "category": "productization",
            "priority": "low",
            "status": "open",
            "reason": "Operator snapshot should clearly distinguish registered vs scaffolded-but-unregistered projects.",
            "target_area": "operator_snapshot + project_onboarding",
        },
    ]

    backlog_seed_list: list[dict[str, Any]] = []
    if backlog_seed:
        for item in backlog_seed:
            if isinstance(item, dict):
                backlog_seed_list.append(item)

    # Lightweight heuristics based on counts (tolerant/missing)
    ds = dashboard_summary or {}
    guardrail_warning_count = 0
    try:
        # dashboard may represent counts under guardrail_status_count
        g_counts = ds.get("guardrail_status_count") or {}
        guardrail_warning_count = int(g_counts.get("warning") or 0)
    except Exception:
        guardrail_warning_count = 0

    # If warnings exist, push a small additional item deterministically.
    if guardrail_warning_count > 0:
        base_items.append(
            {
                "item_id": "hardening_guardrail_warning_triage",
                "title": "Triage guardrail warnings and stabilize outputs",
                "category": "hardening",
                "priority": "medium",
                "status": "open",
                "reason": f"Dashboard indicates guardrail warnings ({guardrail_warning_count}).",
                "target_area": "production_guardrails",
            }
        )

    # Merge seed items last (still deterministic by sorting).
    combined = base_items + backlog_seed_list

    # Normalize and de-duplicate by item_id
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in combined:
        item_id = str(it.get("item_id") or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        out.append(
            {
                "item_id": item_id,
                "title": str(it.get("title") or ""),
                "category": str(it.get("category") or "hardening"),
                "priority": str(it.get("priority") or "medium"),
                "status": str(it.get("status") or "open"),
                "reason": str(it.get("reason") or ""),
                "target_area": str(it.get("target_area") or ""),
            }
        )

    return sorted(out, key=lambda x: (str(x.get("priority")).lower(), str(x.get("category")).lower(), str(x.get("title")).lower(), str(x.get("item_id")).lower()))


def build_self_improvement_backlog_safe(**kwargs: Any) -> list[dict[str, Any]]:
    """Safe wrapper: never raises."""
    try:
        return build_self_improvement_backlog(**kwargs)
    except Exception:
        return []


def _priority_score(p: str | None) -> int:
    v = (p or "").strip().lower()
    if v == "high":
        return 3
    if v == "medium":
        return 2
    if v == "low":
        return 1
    return 0


def select_next_improvement(
    *,
    backlog_items: list[dict[str, Any]] | None = None,
    studio_coordination_summary: dict[str, Any] | None = None,
    driver_summary: dict[str, Any] | None = None,
    backlog_seed: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Select one next improvement item deterministically.
    """
    items = backlog_items or []
    if backlog_seed:
        items = items + [i for i in backlog_seed if isinstance(i, dict)]

    if not items:
        return {
            "selected_item_id": None,
            "selected_title": None,
            "selected_category": None,
            "improvement_reason": "No backlog items available.",
            "execution_recommended": False,
        }

    def sort_key(x: dict[str, Any]) -> tuple[int, str, str]:
        score = _priority_score(x.get("priority"))
        cat = str(x.get("category") or "")
        title = str(x.get("title") or "")
        return (-score, cat, title)

    selected = sorted(items, key=sort_key)[0]
    return {
        "selected_item_id": selected.get("item_id"),
        "selected_title": selected.get("title"),
        "selected_category": selected.get("category"),
        "improvement_reason": selected.get("reason") or "",
        "execution_recommended": False,
    }


def select_next_improvement_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return select_next_improvement(**kwargs)
    except Exception:
        return {
            "selected_item_id": None,
            "selected_title": None,
            "selected_category": None,
            "improvement_reason": "Selection failed.",
            "execution_recommended": False,
        }

