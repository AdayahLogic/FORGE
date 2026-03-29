from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.execution_package_registry import list_execution_package_journal_entries
from NEXUS.learning_writer import read_learning_journal_tail
from NEXUS.studio_config import LOGS_DIR


SELF_OPTIMIZATION_VERSION = "1.0"
STRATEGY_VERSION_LOG = "strategy_versions.jsonl"
OPTIMIZATION_STATUS_FILE = "optimization_status.json"

DEFAULT_DYNAMIC_WEIGHTS: dict[str, float] = {
    "execution_reliability": 0.23,
    "conversion_signals": 0.24,
    "roi_signals": 0.18,
    "urgency_signals": 0.12,
    "follow_up_effectiveness": 0.15,
    "mission_completion": 0.08,
}
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.40
MAX_WEIGHT_SHIFT = 0.08


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def _to_score(value: float) -> float:
    return round(max(0.0, min(100.0, value * 100.0)), 2)


def _safe_weight_profile(profile: dict[str, Any] | None) -> dict[str, float]:
    base = dict(DEFAULT_DYNAMIC_WEIGHTS)
    raw = profile or {}
    for key in list(base.keys()):
        base[key] = max(WEIGHT_MIN, min(WEIGHT_MAX, _to_float(raw.get(key), base[key])))
    total = sum(base.values())
    if total <= 0:
        return dict(DEFAULT_DYNAMIC_WEIGHTS)
    return {k: round(v / total, 4) for k, v in base.items()}


def _strategy_store_dir(custom_store_dir: str | None = None) -> Path:
    root = Path(custom_store_dir).resolve() if custom_store_dir else LOGS_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _strategy_log_path(custom_store_dir: str | None = None) -> Path:
    return _strategy_store_dir(custom_store_dir) / STRATEGY_VERSION_LOG


def _optimization_status_path(custom_store_dir: str | None = None) -> Path:
    return _strategy_store_dir(custom_store_dir) / OPTIMIZATION_STATUS_FILE


def _read_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit):]:
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                out.append(parsed)
        except Exception:
            continue
    return out


def _append_jsonl(path: Path, payload: dict[str, Any]) -> bool:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_strategy_versions(*, n: int = 20, strategy_store_dir: str | None = None) -> dict[str, Any]:
    path = _strategy_log_path(strategy_store_dir)
    rows = _read_jsonl(path, limit=max(20, n * 3))
    rows.sort(key=lambda r: str(r.get("recorded_at") or ""), reverse=True)
    return {
        "strategy_versions_status": "ok",
        "strategy_contract_version": SELF_OPTIMIZATION_VERSION,
        "strategy_version_count": len(rows[: max(1, n)]),
        "strategy_versions": rows[: max(1, n)],
    }


def get_latest_strategy_weights(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    versions = list_strategy_versions(n=100, strategy_store_dir=strategy_store_dir).get("strategy_versions") or []
    for row in versions:
        new_weights = row.get("new_weights")
        if isinstance(new_weights, dict):
            return {
                "strategy_version_id": str(row.get("strategy_version_id") or ""),
                "weights": _safe_weight_profile(new_weights),
                "recorded_at": str(row.get("recorded_at") or ""),
            }
    return {
        "strategy_version_id": "strategy-v0-default",
        "weights": dict(DEFAULT_DYNAMIC_WEIGHTS),
        "recorded_at": "",
    }


def record_strategy_version(
    *,
    reason: str,
    change_summary: str,
    previous_weights: dict[str, Any] | None,
    new_weights: dict[str, Any] | None,
    metrics_before: dict[str, Any] | None = None,
    metrics_after: dict[str, Any] | None = None,
    reversible_to: str | None = None,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    latest = get_latest_strategy_weights(strategy_store_dir=strategy_store_dir)
    ts = _utc_now_iso()
    strategy_version_id = f"strategy-v{ts.replace('-', '').replace(':', '').replace('+00:00', 'z').replace('T', '-').lower()}"
    normalized_prev = _safe_weight_profile(previous_weights or latest.get("weights") or {})
    normalized_new = _safe_weight_profile(new_weights or normalized_prev)
    changed_fields = [
        key for key in sorted(normalized_new.keys())
        if abs(_to_float(normalized_new.get(key)) - _to_float(normalized_prev.get(key))) >= 0.0001
    ]
    payload = {
        "strategy_version_id": strategy_version_id,
        "recorded_at": ts,
        "strategy_contract_version": SELF_OPTIMIZATION_VERSION,
        "change_summary": str(change_summary or "").strip(),
        "reason": str(reason or "").strip(),
        "changed_fields": changed_fields,
        "previous_weights": normalized_prev,
        "new_weights": normalized_new,
        "metrics_before": dict(metrics_before or {}),
        "metrics_after": dict(metrics_after or {}),
        "reversible_to": str(reversible_to or latest.get("strategy_version_id") or "strategy-v0-default"),
        "bounded": True,
        "governance_required": True,
        "safe_to_apply": True,
    }
    written = _append_jsonl(_strategy_log_path(strategy_store_dir), payload)
    return {
        "status": "ok" if written else "error",
        "reason": "Strategy version recorded." if written else "Failed to write strategy version log.",
        "strategy_version": payload if written else {},
    }


def _collect_project_observations(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    observations_by_project: dict[str, dict[str, Any]] | None = None,
    n_packages: int = 40,
    n_learning: int = 60,
) -> dict[str, dict[str, Any]]:
    if isinstance(observations_by_project, dict) and observations_by_project:
        normalized: dict[str, dict[str, Any]] = {}
        for project_id, data in observations_by_project.items():
            row = data if isinstance(data, dict) else {}
            normalized[str(project_id)] = {
                "project_path": str(row.get("project_path") or ""),
                "packages": [dict(item) for item in list(row.get("packages") or []) if isinstance(item, dict)],
                "learning": [dict(item) for item in list(row.get("learning") or []) if isinstance(item, dict)],
            }
        return normalized

    states = states_by_project or {}
    out: dict[str, dict[str, Any]] = {}
    for project_id, state in states.items():
        st = state if isinstance(state, dict) else {}
        project_path = str(st.get("project_path") or st.get("persistent_state_path") or "")
        if not project_path:
            continue
        out[str(project_id)] = {
            "project_path": project_path,
            "packages": list_execution_package_journal_entries(project_path, n=n_packages),
            "learning": read_learning_journal_tail(project_path, n=n_learning),
        }
    return out


def analyze_strategy_performance(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    observations_by_project: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    observations = _collect_project_observations(
        states_by_project=states_by_project,
        observations_by_project=observations_by_project,
    )
    all_packages: list[dict[str, Any]] = []
    all_learning: list[dict[str, Any]] = []
    project_breakdown: list[dict[str, Any]] = []

    for project_id, obs in observations.items():
        packages = [dict(item) for item in list(obs.get("packages") or []) if isinstance(item, dict)]
        learning = [dict(item) for item in list(obs.get("learning") or []) if isinstance(item, dict)]
        all_packages.extend(packages)
        all_learning.extend(learning)
        project_breakdown.append(
            {
                "project_id": project_id,
                "package_count": len(packages),
                "learning_count": len(learning),
            }
        )

    total_actions = max(1, len(all_packages))
    conversions = 0
    follow_up_eligible = 0
    follow_up_success = 0
    execution_success = 0
    mission_completed = 0
    urgency_sum = 0.0
    conversion_signal_sum = 0.0
    roi_sum = 0.0

    for row in all_packages:
        conversion_result = str(row.get("linked_conversion_result") or "").strip().lower()
        conversion_prob = _to_float(row.get("conversion_probability"), 0.0)
        roi_estimate = _to_float(row.get("roi_estimate"), 0.0)
        urgency = _to_float(row.get("time_sensitivity"), 0.0)
        follow_up_status = str(row.get("follow_up_status") or "").strip().lower()
        execution_status = str(row.get("execution_status") or "").strip().lower()
        package_status = str(row.get("package_status") or "").strip().lower()
        action_reply = _to_float(row.get("action_to_reply_rate"), 0.0)

        conversion_signal_sum += max(0.0, min(1.0, conversion_prob))
        roi_sum += max(0.0, min(1.0, roi_estimate))
        urgency_sum += max(0.0, min(1.0, urgency))

        if conversion_result in {"converted", "closed_won", "won", "success"}:
            conversions += 1
        if follow_up_status in {"follow_up_due", "follow_up_scheduled", "follow_up_not_needed"}:
            follow_up_eligible += 1
            if conversion_result in {"converted", "closed_won", "won", "success"} or action_reply >= 0.35:
                follow_up_success += 1
        if execution_status in {"completed", "success"} or package_status in {"completed", "done", "released"}:
            execution_success += 1
        if package_status in {"completed", "done", "released"}:
            mission_completed += 1

    learning_success = 0
    learning_failure = 0
    learning_warning = 0
    success_tag_count: dict[str, int] = {}
    failure_tag_count: dict[str, int] = {}
    for rec in all_learning:
        outcome = str(rec.get("actual_outcome") or "").strip().lower()
        tags = [str(tag).strip().lower() for tag in list(rec.get("tags") or []) if str(tag).strip()]
        if outcome == "success":
            learning_success += 1
            for tag in tags[:10]:
                success_tag_count[tag] = success_tag_count.get(tag, 0) + 1
        elif outcome in {"failed", "blocked"}:
            learning_failure += 1
            for tag in tags[:10]:
                failure_tag_count[tag] = failure_tag_count.get(tag, 0) + 1
        elif outcome == "warning":
            learning_warning += 1

    conversion_rate = _ratio(conversions, total_actions)
    follow_up_success_rate = _ratio(follow_up_success, max(1, follow_up_eligible))
    execution_reliability = _ratio(execution_success, total_actions)
    mission_completion_rate = _ratio(mission_completed, total_actions)
    revenue_outcome_score = _ratio((conversion_signal_sum / total_actions + roi_sum / total_actions) / 2.0, 1.0)
    learning_success_rate = _ratio(learning_success, max(1, learning_success + learning_failure + learning_warning))

    strategy_effectiveness = (
        conversion_rate * 0.24
        + follow_up_success_rate * 0.16
        + execution_reliability * 0.21
        + mission_completion_rate * 0.12
        + revenue_outcome_score * 0.17
        + learning_success_rate * 0.10
    )

    success_patterns = [
        {"pattern": key, "count": count}
        for key, count in sorted(success_tag_count.items(), key=lambda item: item[1], reverse=True)[:5]
    ]
    failure_patterns = [
        {"pattern": key, "count": count}
        for key, count in sorted(failure_tag_count.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    avg_urgency = _ratio(urgency_sum, total_actions)
    insights: list[str] = []
    if follow_up_success_rate < 0.45:
        insights.append("Follow-up effectiveness is weak; tighten cadence and improve escalation timing.")
    if conversion_rate < 0.35:
        insights.append("Conversion throughput is low; shift scoring toward conversion and ROI evidence.")
    if execution_reliability < 0.60:
        insights.append("Execution reliability is below target; prioritize safer action sequencing and rollback readiness.")
    if mission_completion_rate < 0.55:
        insights.append("Mission completion is low; de-prioritize long-tail actions with weak completion odds.")
    if avg_urgency > 0.70 and conversion_rate < 0.45:
        insights.append("Urgency appears overvalued against outcomes; reduce urgency weighting.")
    if not insights:
        insights.append("Current strategy is stable; maintain profile and continue bounded monitoring.")

    return {
        "strategy_performance_status": "ok",
        "strategy_contract_version": SELF_OPTIMIZATION_VERSION,
        "observed_at": _utc_now_iso(),
        "analysis_window": {
            "project_count": len(observations),
            "total_actions": total_actions,
            "learning_records": len(all_learning),
        },
        "metrics": {
            "conversion_rate": conversion_rate,
            "follow_up_success_rate": follow_up_success_rate,
            "execution_reliability": execution_reliability,
            "mission_completion_rate": mission_completion_rate,
            "revenue_outcome_score": revenue_outcome_score,
            "learning_success_rate": learning_success_rate,
            "urgency_signal_average": avg_urgency,
        },
        "strategy_effectiveness_score": _to_score(strategy_effectiveness),
        "success_patterns": success_patterns,
        "failure_patterns": failure_patterns,
        "actionable_insights": insights[:8],
        "project_breakdown": project_breakdown,
    }


def adjust_dynamic_weights(
    *,
    performance_summary: dict[str, Any],
    current_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = performance_summary.get("metrics") if isinstance(performance_summary, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    base = _safe_weight_profile(current_weights)
    updated = dict(base)
    changes: list[dict[str, Any]] = []

    def shift(key: str, delta: float, reason: str) -> None:
        bounded_delta = max(-MAX_WEIGHT_SHIFT, min(MAX_WEIGHT_SHIFT, delta))
        old = updated.get(key, 0.0)
        new = max(WEIGHT_MIN, min(WEIGHT_MAX, old + bounded_delta))
        updated[key] = new
        if abs(new - old) >= 0.0001:
            changes.append(
                {
                    "weight": key,
                    "previous": round(old, 4),
                    "updated": round(new, 4),
                    "delta": round(new - old, 4),
                    "reason": reason,
                }
            )

    conversion_rate = _to_float(metrics.get("conversion_rate"), 0.0)
    follow_up_success_rate = _to_float(metrics.get("follow_up_success_rate"), 0.0)
    execution_reliability = _to_float(metrics.get("execution_reliability"), 0.0)
    mission_completion_rate = _to_float(metrics.get("mission_completion_rate"), 0.0)
    urgency_avg = _to_float(metrics.get("urgency_signal_average"), 0.0)

    if conversion_rate < 0.45:
        shift("conversion_signals", +0.04, "Conversion under target; emphasize conversion evidence.")
    elif conversion_rate > 0.70:
        shift("conversion_signals", -0.02, "Conversion is strong; rebalance toward reliability.")

    if follow_up_success_rate < 0.40:
        shift("follow_up_effectiveness", +0.04, "Follow-up performance weak; prioritize follow-up quality.")
    elif follow_up_success_rate > 0.70:
        shift("follow_up_effectiveness", -0.02, "Follow-up strong; reduce overfitting risk.")

    if execution_reliability < 0.60:
        shift("execution_reliability", +0.05, "Execution reliability low; emphasize safe execution.")

    if mission_completion_rate < 0.55:
        shift("mission_completion", +0.03, "Mission completion weak; increase completion pressure.")

    if urgency_avg > 0.70 and conversion_rate < 0.45:
        shift("urgency_signals", -0.04, "Urgency appears overvalued relative to conversion outcomes.")
    elif urgency_avg < 0.35 and mission_completion_rate > 0.70:
        shift("urgency_signals", +0.02, "Urgency signal appears undervalued for currently successful missions.")

    normalized = _safe_weight_profile(updated)
    weight_shift_total = round(
        sum(abs(_to_float(normalized.get(k)) - _to_float(base.get(k))) for k in normalized.keys()),
        4,
    )
    adjustment_direction = "stable" if weight_shift_total < 0.02 else ("moderate" if weight_shift_total < 0.08 else "aggressive")
    reversal_id = get_latest_strategy_weights().get("strategy_version_id")
    return {
        "weight_adjustment_status": "ok",
        "weights_previous": base,
        "weights_proposed": normalized,
        "changes": changes,
        "weight_shift_total": weight_shift_total,
        "adjustment_direction": adjustment_direction,
        "bounded": True,
        "reversible": True,
        "reversal_target_version": reversal_id or "strategy-v0-default",
        "reversibility_plan": {
            "rollback_target_version": reversal_id or "strategy-v0-default",
            "rollback_mechanism": "strategy_version_reapply",
            "max_single_weight_shift": MAX_WEIGHT_SHIFT,
        },
        "explainability": [row["reason"] for row in changes] or ["No changes required by current performance profile."],
    }


def evolve_strategy(
    *,
    performance_summary: dict[str, Any],
    current_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    score = _to_float(performance_summary.get("strategy_effectiveness_score"), 0.0)
    metrics = performance_summary.get("metrics") if isinstance(performance_summary, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    adjustment = adjust_dynamic_weights(performance_summary=performance_summary, current_weights=current_weights)

    mode = "maintain"
    if score < 50:
        mode = "replace_underperforming"
    elif score < 72:
        mode = "refine_existing"

    conversion_rate = _to_float(metrics.get("conversion_rate"), 0.0)
    follow_up_success_rate = _to_float(metrics.get("follow_up_success_rate"), 0.0)
    execution_reliability = _to_float(metrics.get("execution_reliability"), 0.0)

    proposed_changes: list[dict[str, Any]] = []
    if mode == "replace_underperforming":
        proposed_changes.extend(
            [
                {
                    "change_type": "follow_up_timing_adjustment",
                    "previous": "48h",
                    "proposed": "24h",
                    "why": "Low effectiveness indicates delayed follow-up is missing opportunities.",
                },
                {
                    "change_type": "action_type_routing",
                    "previous": "mixed_default",
                    "proposed": "value-first-with-human-escalation",
                    "why": "Underperformance requires safer high-value action sequencing.",
                },
            ]
        )
    elif mode == "refine_existing":
        if conversion_rate < 0.45:
            proposed_changes.append(
                {
                    "change_type": "prioritization_logic",
                    "previous": "balanced",
                    "proposed": "conversion-led",
                    "why": "Conversion under target; prioritize opportunities with stronger conversion evidence.",
                }
            )
        if follow_up_success_rate < 0.45:
            proposed_changes.append(
                {
                    "change_type": "follow_up_cadence",
                    "previous": "static",
                    "proposed": "adaptive-window",
                    "why": "Follow-up effectiveness is weak; apply adaptive cadence by response signals.",
                }
            )
        if execution_reliability < 0.65:
            proposed_changes.append(
                {
                    "change_type": "execution_policy",
                    "previous": "single-pass",
                    "proposed": "checkpointed",
                    "why": "Reliability below target; add checkpointed progression before high-impact actions.",
                }
            )

    if not proposed_changes:
        proposed_changes.append(
            {
                "change_type": "monitor_only",
                "previous": "current_strategy",
                "proposed": "current_strategy",
                "why": "Performance is stable; continue observation without mutation.",
            }
        )

    return {
        "strategy_evolution_status": "ok",
        "evolution_mode": mode,
        "strategy_effectiveness_score": score,
        "proposed_changes": proposed_changes,
        "proposed_weight_adjustment": adjustment,
        "guardrails": {
            "bounded": True,
            "governed": True,
            "transparent": True,
            "reversible": True,
            "requires_operator_approval": True,
            "max_weight_shift": MAX_WEIGHT_SHIFT,
        },
    }


def build_portfolio_intelligence(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    observations_by_project: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    observations = _collect_project_observations(
        states_by_project=states_by_project,
        observations_by_project=observations_by_project,
    )
    rows: list[dict[str, Any]] = []
    for project_id, obs in observations.items():
        packages = [dict(item) for item in list(obs.get("packages") or []) if isinstance(item, dict)]
        learning = [dict(item) for item in list(obs.get("learning") or []) if isinstance(item, dict)]
        count = max(1, len(packages))

        value_signal = 0.0
        converted = 0
        execution_ok = 0
        for pkg in packages:
            value_signal += (
                _to_float(pkg.get("highest_value_next_action_score"), 0.0) * 0.35
                + _to_float(pkg.get("conversion_probability"), 0.0) * 0.30
                + _to_float(pkg.get("roi_estimate"), 0.0) * 0.20
                + _to_float(pkg.get("execution_score"), 0.0) * 0.15
            )
            if str(pkg.get("linked_conversion_result") or "").strip().lower() in {"converted", "closed_won", "won", "success"}:
                converted += 1
            if str(pkg.get("execution_status") or "").strip().lower() in {"completed", "success"}:
                execution_ok += 1

        failure_events = 0
        for rec in learning:
            if str(rec.get("actual_outcome") or "").strip().lower() in {"failed", "blocked"}:
                failure_events += 1

        value_score = _ratio(value_signal, count)
        conversion_rate = _ratio(converted, count)
        reliability_score = _ratio(execution_ok, count)
        failure_drag = _ratio(failure_events, max(1, len(learning)))
        performance = max(0.0, min(1.0, (value_score * 0.45) + (conversion_rate * 0.3) + (reliability_score * 0.35) - (failure_drag * 0.2)))
        performance_score = _to_score(performance)

        if performance_score >= 72:
            allocation_signal = "increase_focus"
        elif performance_score < 40:
            allocation_signal = "pause_candidate"
        elif performance_score < 55:
            allocation_signal = "reduce_focus"
        else:
            allocation_signal = "maintain_focus"

        rows.append(
            {
                "project_id": project_id,
                "project_performance_score": performance_score,
                "project_value_score": _to_score(value_score),
                "conversion_rate": conversion_rate,
                "execution_reliability": reliability_score,
                "learning_failure_rate": failure_drag,
                "resource_allocation_signal": allocation_signal,
                "package_count": len(packages),
                "learning_count": len(learning),
            }
        )

    rows.sort(key=lambda item: (item.get("project_performance_score", 0), item.get("project_id", "")), reverse=True)
    priority_project = rows[0]["project_id"] if rows else None
    avg_score = sum(_to_float(row.get("project_performance_score"), 0.0) for row in rows) / max(1, len(rows))
    concentration_bonus = 0.0
    if len(rows) >= 2:
        concentration_bonus = max(
            -10.0,
            min(10.0, _to_float(rows[0].get("project_performance_score"), 0.0) - _to_float(rows[1].get("project_performance_score"), 0.0)),
        ) * 0.15
    portfolio_priority_score = round(max(0.0, min(100.0, avg_score + concentration_bonus)), 2)

    pause_candidates = [row["project_id"] for row in rows if row.get("resource_allocation_signal") == "pause_candidate"][:10]
    focus_candidates = [row["project_id"] for row in rows if row.get("resource_allocation_signal") == "increase_focus"][:10]
    return {
        "portfolio_intelligence_status": "ok",
        "portfolio_priority_score": portfolio_priority_score,
        "priority_project": priority_project,
        "project_performance": rows,
        "resource_allocation_signals": rows,
        "focus_candidates": focus_candidates,
        "pause_candidates": pause_candidates,
    }


def run_self_optimization_feedback_loop(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    observations_by_project: dict[str, dict[str, Any]] | None = None,
    apply_changes: bool = False,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    previous_weights_payload = get_latest_strategy_weights(strategy_store_dir=strategy_store_dir)
    previous_weights = previous_weights_payload.get("weights") or {}
    performance = analyze_strategy_performance(
        states_by_project=states_by_project,
        observations_by_project=observations_by_project,
    )
    evolution = evolve_strategy(performance_summary=performance, current_weights=previous_weights)
    proposed_weights = (
        evolution.get("proposed_weight_adjustment", {}).get("weights_proposed")
        if isinstance(evolution.get("proposed_weight_adjustment"), dict)
        else previous_weights
    )
    proposed_weights = _safe_weight_profile(proposed_weights if isinstance(proposed_weights, dict) else previous_weights)

    apply_result = {
        "applied": False,
        "strategy_version_id": previous_weights_payload.get("strategy_version_id"),
        "reason": "Dry-run mode; strategy changes not applied.",
    }
    if apply_changes:
        version = record_strategy_version(
            reason="Automated self-optimization loop applied bounded strategy updates.",
            change_summary=f"mode={evolution.get('evolution_mode')}; score={performance.get('strategy_effectiveness_score')}",
            previous_weights=previous_weights,
            new_weights=proposed_weights,
            metrics_before=performance.get("metrics") if isinstance(performance, dict) else {},
            metrics_after={},
            strategy_store_dir=strategy_store_dir,
        )
        if version.get("status") == "ok":
            strategy_version = version.get("strategy_version") if isinstance(version.get("strategy_version"), dict) else {}
            apply_result = {
                "applied": True,
                "strategy_version_id": strategy_version.get("strategy_version_id"),
                "reason": "Strategy update applied with bounded reversible changes.",
            }
        else:
            apply_result = {
                "applied": False,
                "strategy_version_id": previous_weights_payload.get("strategy_version_id"),
                "reason": "Strategy update failed to persist.",
            }

    portfolio = build_portfolio_intelligence(
        states_by_project=states_by_project,
        observations_by_project=observations_by_project,
    )
    status_payload = {
        "optimization_status": "ok",
        "optimization_contract_version": SELF_OPTIMIZATION_VERSION,
        "observed_at": _utc_now_iso(),
        "loop": {
            "observe": {"status": "ok", "project_count": len(observations_by_project or states_by_project or {})},
            "analyze": {"status": "ok", "strategy_effectiveness_score": performance.get("strategy_effectiveness_score")},
            "adjust": {"status": "ok", "change_count": len(evolution.get("proposed_changes") or [])},
            "apply": apply_result,
            "monitor": {"status": "ok", "portfolio_priority_score": portfolio.get("portfolio_priority_score")},
        },
        "strategy_performance": performance,
        "strategy_evolution": evolution,
        "portfolio_intelligence": portfolio,
        "active_weights": proposed_weights if apply_result.get("applied") else previous_weights,
        "bounded": True,
        "governed": True,
        "transparent": True,
        "reversible": True,
    }
    try:
        _optimization_status_path(strategy_store_dir).write_text(json.dumps(status_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return status_payload


def read_optimization_status(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    path = _optimization_status_path(strategy_store_dir)
    if not path.exists():
        return {
            "optimization_status": "idle",
            "reason": "No optimization cycle recorded yet.",
            "bounded": True,
            "governed": True,
            "transparent": True,
            "reversible": True,
        }
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {
        "optimization_status": "error_fallback",
        "reason": "Failed to read optimization status.",
        "bounded": True,
        "governed": True,
        "transparent": True,
        "reversible": True,
    }


def analyze_strategy_performance_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return analyze_strategy_performance(**kwargs)
    except Exception:
        return {
            "strategy_performance_status": "error_fallback",
            "strategy_effectiveness_score": 0.0,
            "metrics": {},
            "success_patterns": [],
            "failure_patterns": [],
            "actionable_insights": ["Performance analysis failed; using safe fallback."],
        }


def evolve_strategy_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return evolve_strategy(**kwargs)
    except Exception:
        return {
            "strategy_evolution_status": "error_fallback",
            "evolution_mode": "maintain",
            "proposed_changes": [],
            "proposed_weight_adjustment": {
                "weight_adjustment_status": "error_fallback",
                "weights_previous": dict(DEFAULT_DYNAMIC_WEIGHTS),
                "weights_proposed": dict(DEFAULT_DYNAMIC_WEIGHTS),
                "changes": [],
                "bounded": True,
                "reversible": True,
            },
            "guardrails": {
                "bounded": True,
                "governed": True,
                "transparent": True,
                "reversible": True,
                "requires_operator_approval": True,
                "max_weight_shift": MAX_WEIGHT_SHIFT,
            },
        }


def adjust_dynamic_weights_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return adjust_dynamic_weights(**kwargs)
    except Exception:
        return {
            "weight_adjustment_status": "error_fallback",
            "weights_previous": dict(DEFAULT_DYNAMIC_WEIGHTS),
            "weights_proposed": dict(DEFAULT_DYNAMIC_WEIGHTS),
            "changes": [],
            "weight_shift_total": 0.0,
            "adjustment_direction": "stable",
            "bounded": True,
            "reversible": True,
            "reversal_target_version": "strategy-v0-default",
            "reversibility_plan": {
                "rollback_target_version": "strategy-v0-default",
                "rollback_mechanism": "strategy_version_reapply",
                "max_single_weight_shift": MAX_WEIGHT_SHIFT,
            },
            "explainability": ["Weight adjustment failed; using default profile."],
        }


def build_portfolio_intelligence_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_portfolio_intelligence(**kwargs)
    except Exception:
        return {
            "portfolio_intelligence_status": "error_fallback",
            "portfolio_priority_score": 0.0,
            "priority_project": None,
            "project_performance": [],
            "resource_allocation_signals": [],
            "focus_candidates": [],
            "pause_candidates": [],
        }


def run_self_optimization_feedback_loop_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return run_self_optimization_feedback_loop(**kwargs)
    except Exception:
        return {
            "optimization_status": "error_fallback",
            "reason": "Self-optimization loop failed.",
            "loop": {
                "observe": {"status": "error"},
                "analyze": {"status": "error"},
                "adjust": {"status": "error"},
                "apply": {"status": "error", "applied": False},
                "monitor": {"status": "error"},
            },
            "bounded": True,
            "governed": True,
            "transparent": True,
            "reversible": True,
        }


def read_optimization_status_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return read_optimization_status(**kwargs)
    except Exception:
        return {
            "optimization_status": "error_fallback",
            "reason": "Optimization status unavailable.",
            "bounded": True,
            "governed": True,
            "transparent": True,
            "reversible": True,
        }
