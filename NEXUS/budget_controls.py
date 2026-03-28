"""
Phase 85 budget controls.

Shared, explicit estimate-based budget evaluation for operation/project/session
scopes with kill-switch signaling.
"""

from __future__ import annotations

from typing import Any


APPROACHING_CAP_THRESHOLD = 0.8
_SCOPE_PRIORITY = {"operation": 3, "project": 2, "session": 1}
_SEVERITY = {
    "within_budget": 0,
    "approaching_cap": 1,
    "cap_exceeded": 2,
    "kill_switch_triggered": 3,
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _cap_value(value: Any) -> float:
    parsed = _to_float(value, default=0.0)
    return round(max(0.0, parsed), 6)


def _cost_value(value: Any) -> float:
    parsed = _to_float(value, default=0.0)
    return round(max(0.0, parsed), 6)


def normalize_budget_caps(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    return {
        "session_budget_cap": _cap_value(raw.get("session_budget_cap")),
        "project_budget_cap": _cap_value(raw.get("project_budget_cap")),
        "operation_budget_cap": _cap_value(raw.get("operation_budget_cap")),
        "kill_switch_enabled": bool(raw.get("kill_switch_enabled", raw.get("budget_kill_switch_enabled", True))),
    }


def resolve_budget_caps(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    if isinstance(raw.get("budget_caps"), dict):
        base = dict(raw.get("budget_caps") or {})
    else:
        base = {}
    # Allow either nested `budget_caps` or direct keys on the source payload.
    for key in ("session_budget_cap", "project_budget_cap", "operation_budget_cap", "kill_switch_enabled", "budget_kill_switch_enabled"):
        if key in raw and key not in base:
            base[key] = raw.get(key)
    return normalize_budget_caps(base)


def _evaluate_scope(
    *,
    scope: str,
    cap: float,
    current_estimated_cost: float,
    kill_switch_enabled: bool,
) -> dict[str, Any]:
    current = _cost_value(current_estimated_cost)
    normalized_cap = _cap_value(cap)
    utilization = round((current / normalized_cap), 6) if normalized_cap > 0 else 0.0

    if normalized_cap <= 0:
        return {
            "budget_status": "within_budget",
            "budget_scope": scope,
            "budget_cap": 0.0,
            "current_estimated_cost": current,
            "remaining_estimated_budget": 0.0,
            "kill_switch_active": False,
            "budget_reason": f"No {scope} budget cap is configured; estimate remains observable only.",
            "utilization_ratio": 0.0,
        }

    if current >= normalized_cap:
        if kill_switch_enabled:
            status = "kill_switch_triggered"
            kill_switch_active = True
            reason = (
                f"Estimated {scope} budget reached or exceeded cap; kill switch is active and governed progression is blocked."
            )
        else:
            status = "cap_exceeded"
            kill_switch_active = False
            reason = (
                f"Estimated {scope} budget reached or exceeded cap; kill switch is disabled so this is reported without forced block."
            )
    elif utilization >= APPROACHING_CAP_THRESHOLD:
        status = "approaching_cap"
        kill_switch_active = False
        reason = f"Estimated {scope} cost is at or above {int(APPROACHING_CAP_THRESHOLD * 100)}% of cap."
    else:
        status = "within_budget"
        kill_switch_active = False
        reason = f"Estimated {scope} cost remains within configured cap."

    return {
        "budget_status": status,
        "budget_scope": scope,
        "budget_cap": normalized_cap,
        "current_estimated_cost": current,
        "remaining_estimated_budget": round(max(0.0, normalized_cap - current), 6),
        "kill_switch_active": kill_switch_active,
        "budget_reason": reason,
        "utilization_ratio": utilization,
    }


def evaluate_budget_controls(
    *,
    budget_caps: Any,
    current_operation_cost: Any,
    current_project_cost: Any,
    current_session_cost: Any,
) -> dict[str, Any]:
    caps = normalize_budget_caps(budget_caps)
    kill_switch_enabled = bool(caps.get("kill_switch_enabled", True))
    evaluations = [
        _evaluate_scope(
            scope="operation",
            cap=caps.get("operation_budget_cap") or 0.0,
            current_estimated_cost=current_operation_cost,
            kill_switch_enabled=kill_switch_enabled,
        ),
        _evaluate_scope(
            scope="project",
            cap=caps.get("project_budget_cap") or 0.0,
            current_estimated_cost=current_project_cost,
            kill_switch_enabled=kill_switch_enabled,
        ),
        _evaluate_scope(
            scope="session",
            cap=caps.get("session_budget_cap") or 0.0,
            current_estimated_cost=current_session_cost,
            kill_switch_enabled=kill_switch_enabled,
        ),
    ]
    ordered = sorted(
        evaluations,
        key=lambda item: (
            _SEVERITY.get(str(item.get("budget_status") or "within_budget"), 0),
            _to_float(item.get("utilization_ratio"), 0.0),
            _SCOPE_PRIORITY.get(str(item.get("budget_scope") or ""), 0),
        ),
        reverse=True,
    )
    governing = dict(ordered[0] if ordered else evaluations[0])
    return {
        "budget_caps": caps,
        "budget_status": str(governing.get("budget_status") or "within_budget"),
        "budget_scope": str(governing.get("budget_scope") or "operation"),
        "budget_cap": _cap_value(governing.get("budget_cap")),
        "current_estimated_cost": _cost_value(governing.get("current_estimated_cost")),
        "remaining_estimated_budget": _cost_value(governing.get("remaining_estimated_budget")),
        "kill_switch_active": bool(governing.get("kill_switch_active")),
        "budget_reason": str(governing.get("budget_reason") or ""),
        "kill_switch_enabled": kill_switch_enabled,
        "progression_blocked": bool(governing.get("kill_switch_active")),
        "scope_evaluations": evaluations,
    }


def normalize_budget_control(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    caps = normalize_budget_caps(raw.get("budget_caps"))
    evaluations = raw.get("scope_evaluations")
    if not isinstance(evaluations, list):
        evaluations = []
    normalized_evals: list[dict[str, Any]] = []
    for item in evaluations[:3]:
        if not isinstance(item, dict):
            continue
        normalized_evals.append(
            {
                "budget_status": str(item.get("budget_status") or "within_budget"),
                "budget_scope": str(item.get("budget_scope") or "operation"),
                "budget_cap": _cap_value(item.get("budget_cap")),
                "current_estimated_cost": _cost_value(item.get("current_estimated_cost")),
                "remaining_estimated_budget": _cost_value(item.get("remaining_estimated_budget")),
                "kill_switch_active": bool(item.get("kill_switch_active")),
                "budget_reason": str(item.get("budget_reason") or ""),
                "utilization_ratio": round(max(0.0, _to_float(item.get("utilization_ratio"), 0.0)), 6),
            }
        )
    return {
        "budget_caps": caps,
        "budget_status": str(raw.get("budget_status") or "within_budget"),
        "budget_scope": str(raw.get("budget_scope") or "operation"),
        "budget_cap": _cap_value(raw.get("budget_cap")),
        "current_estimated_cost": _cost_value(raw.get("current_estimated_cost")),
        "remaining_estimated_budget": _cost_value(raw.get("remaining_estimated_budget")),
        "kill_switch_active": bool(raw.get("kill_switch_active")),
        "budget_reason": str(raw.get("budget_reason") or ""),
        "kill_switch_enabled": bool(raw.get("kill_switch_enabled", caps.get("kill_switch_enabled", True))),
        "progression_blocked": bool(raw.get("progression_blocked")),
        "scope_evaluations": normalized_evals,
    }


def summarize_journal_estimated_costs(journal_rows: list[dict[str, Any]] | None, *, run_id: str = "") -> dict[str, float]:
    rows = [row for row in (journal_rows or []) if isinstance(row, dict)]
    latest_by_package: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for row in rows:
        package_id = str(row.get("package_id") or "").strip()
        if package_id:
            # Keep last observed record for each package in chronological stream.
            latest_by_package[package_id] = row
        else:
            passthrough.append(row)
    deduped = list(latest_by_package.values()) + passthrough
    project_total = 0.0
    session_total = 0.0
    session_key = str(run_id or "").strip()
    for row in deduped:
        cost_tracking = dict(row.get("cost_tracking") or {})
        cost = _cost_value(cost_tracking.get("cost_estimate"))
        project_total += cost
        if not session_key or str(row.get("run_id") or "") == session_key:
            session_total += cost
    return {
        "project_estimated_cost_total": round(project_total, 6),
        "session_estimated_cost_total": round(session_total, 6),
    }


def record_billing_usage_from_cost_tracking(
    *,
    customer_id: Any,
    cost_tracking: Any,
    package_id: str = "",
    run_id: str = "",
    source: str = "execution_package_execution",
) -> dict[str, Any]:
    """
    Emit optional Stripe usage for post-execution cost tracking.

    This hook is additive and intentionally non-blocking. It never raises and
    returns a deterministic status payload for auditability.
    """
    customer = str(customer_id or "").strip()
    if not customer:
        return {"status": "skipped", "reason": "customer_id missing."}
    tracking = dict(cost_tracking) if isinstance(cost_tracking, dict) else {}
    breakdown = dict(tracking.get("cost_breakdown") or {})
    estimated_tokens = max(0, _to_float(breakdown.get("estimated_tokens"), 0.0))
    quantity_tokens = int(round(estimated_tokens))
    if quantity_tokens <= 0:
        return {"status": "skipped", "reason": "No billable estimated tokens."}
    metadata = {
        "package_id": str(package_id or ""),
        "run_id": str(run_id or ""),
        "source": str(source or "execution_package_execution"),
        "cost_source": str(tracking.get("cost_source") or ""),
        "cost_estimate": _cost_value(tracking.get("cost_estimate")),
    }
    try:
        from NEXUS.billing_engine import record_usage
    except Exception:
        return {"status": "error", "reason": "billing_engine import failed.", "metadata": metadata}
    try:
        return record_usage(
            customer_id=customer,
            quantity_tokens=quantity_tokens,
            metadata=metadata,
        )
    except Exception as exc:
        return {"status": "error", "reason": f"Billing usage hook failed: {exc}", "metadata": metadata}
