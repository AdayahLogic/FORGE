from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.self_optimization_engine import (
    analyze_strategy_performance_safe,
    get_latest_strategy_weights,
    read_strategy_lifecycle_registry_safe,
    update_strategy_lifecycle_safe,
)
from NEXUS.studio_config import LOGS_DIR


CHANGE_PROMOTION_ENGINE_VERSION = "1.0"
PROMOTION_STATUS_FILE = "strategy_promotion_status.json"
EXPERIMENT_LOG_FILE = "strategy_experiments.jsonl"
COMPARISON_LOG_FILE = "strategy_comparison_history.jsonl"
ROLLOUT_STATUS_FILE = "strategy_rollout_status.json"
ROLLBACK_LOG_FILE = "strategy_rollback_history.jsonl"
ACTIVE_STRATEGY_FILE = "strategy_active_version.json"
PROMOTION_DECISIONS = {"reject", "test", "promote_partial", "promote_full"}
EXPERIMENT_MODES = {"shadow", "controlled_rollout", "full_activation"}
VALIDATION_STATUSES = {"candidate_wins", "baseline_wins", "inconclusive", "regression_detected"}
ALLOWED_ACTION_TYPES = {"analysis", "scoring", "routing", "follow_up", "execution_policy", "prioritization"}
ROLLOUT_RAMP = [10, 25, 50, 100]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_ratio(value: Any, default: float = 0.0) -> float:
    return _clamp(_to_float(value, default), 0.0, 1.0)


def _to_score(value: Any, default: float = 0.0) -> float:
    numeric = _to_float(value, default)
    if numeric > 1.0:
        return _clamp(numeric, 0.0, 100.0)
    return _clamp(numeric * 100.0, 0.0, 100.0)


def _store_dir(custom_store_dir: str | None = None) -> Path:
    root = Path(custom_store_dir).resolve() if custom_store_dir else LOGS_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store_path(filename: str, custom_store_dir: str | None = None) -> Path:
    return _store_dir(custom_store_dir) / filename


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> bool:
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _append_jsonl(path: Path, payload: dict[str, Any]) -> bool:
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


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


def _extract_metrics(summary: dict[str, Any] | None) -> dict[str, Any]:
    payload = summary if isinstance(summary, dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return {
        "strategy_effectiveness_score": _to_score(payload.get("strategy_effectiveness_score"), 0.0),
        "conversion_rate": _to_ratio(metrics.get("conversion_rate"), 0.0),
        "revenue_outcome_score": _to_ratio(metrics.get("revenue_outcome_score"), 0.0),
        "failure_rate": _clamp(1.0 - _to_ratio(metrics.get("execution_reliability"), 0.0), 0.0, 1.0),
        "follow_up_effectiveness": _to_ratio(metrics.get("follow_up_success_rate"), 0.0),
        "sample_size": int((payload.get("analysis_window") or {}).get("total_actions") or 0),
    }


def _weighted_performance_index(metrics: dict[str, Any]) -> float:
    return _clamp(
        (
            _to_ratio(metrics.get("conversion_rate"), 0.0) * 0.35
            + _to_ratio(metrics.get("revenue_outcome_score"), 0.0) * 0.30
            + (1.0 - _to_ratio(metrics.get("failure_rate"), 0.0)) * 0.20
            + _to_ratio(metrics.get("follow_up_effectiveness"), 0.0) * 0.15
        ),
        0.0,
        1.0,
    )


def _resolve_risk_profile(
    *,
    risk_level: str,
    requires_approval: bool,
    allowed_action_types: list[str] | None,
) -> dict[str, Any]:
    normalized_risk = str(risk_level or "").strip().lower() or "medium"
    if normalized_risk not in {"low", "medium", "high"}:
        normalized_risk = "medium"
    allowed = [str(item).strip().lower() for item in list(allowed_action_types or []) if str(item).strip()]
    if not allowed:
        allowed = sorted(ALLOWED_ACTION_TYPES)
    disallowed = sorted({item for item in allowed if item not in ALLOWED_ACTION_TYPES})
    return {
        "risk_level": normalized_risk,
        "requires_approval": bool(requires_approval or normalized_risk == "high"),
        "allowed_action_types": [item for item in allowed if item in ALLOWED_ACTION_TYPES],
        "disallowed_action_types": disallowed,
    }


def evaluate_change_promotion_decision(
    *,
    baseline_summary: dict[str, Any] | None,
    candidate_summary: dict[str, Any] | None,
    candidate_version_id: str,
    baseline_version_id: str,
    risk_level: str = "medium",
    approval_status: str = "approved",
    allowed_action_types: list[str] | None = None,
    requires_approval: bool = True,
) -> dict[str, Any]:
    baseline = _extract_metrics(baseline_summary)
    candidate = _extract_metrics(candidate_summary)
    baseline_index = _weighted_performance_index(baseline)
    candidate_index = _weighted_performance_index(candidate)
    delta = round(candidate_index - baseline_index, 4)
    failure_delta = round(_to_ratio(candidate.get("failure_rate")) - _to_ratio(baseline.get("failure_rate")), 4)
    sample_size = max(1, min(int(baseline.get("sample_size") or 0), int(candidate.get("sample_size") or 0)))
    sample_factor = _clamp(sample_size / 25.0, 0.15, 1.0)
    confidence = round(_clamp((abs(delta) * 1.8 + (1.0 - abs(failure_delta)) * 0.35) * sample_factor, 0.0, 1.0), 4)

    governance = _resolve_risk_profile(
        risk_level=risk_level,
        requires_approval=requires_approval,
        allowed_action_types=allowed_action_types,
    )
    approval = str(approval_status or "").strip().lower()
    governance_blocked = bool(governance["disallowed_action_types"]) or (governance["requires_approval"] and approval != "approved")

    decision = "test"
    reason = "Candidate requires controlled validation before promotion."
    scope = "shadow_mode"
    if governance_blocked:
        decision = "reject"
        reason = "Promotion blocked by governance requirements or disallowed action types."
        scope = "none"
    elif failure_delta > 0.05 or delta < -0.03:
        decision = "reject"
        reason = "Candidate regresses baseline performance or increases failure risk."
        scope = "none"
    elif confidence < 0.45 or delta <= 0.01:
        decision = "test"
        reason = "Evidence is weak or improvement is marginal; continue experimentation."
        scope = "shadow_mode"
    elif governance["risk_level"] == "high" or confidence < 0.8:
        decision = "promote_partial"
        reason = "Candidate improves baseline with moderate confidence; use staged rollout."
        scope = "controlled_rollout"
    else:
        decision = "promote_full"
        reason = "Candidate outperforms baseline with strong confidence and acceptable risk."
        scope = "full_activation"

    payload = {
        "promotion_status": "ok",
        "recorded_at": _utc_now_iso(),
        "candidate_version_id": str(candidate_version_id or "").strip(),
        "baseline_version_id": str(baseline_version_id or "").strip(),
        "promotion_decision": decision,
        "promotion_reason": reason,
        "promotion_confidence": confidence,
        "promotion_scope": scope,
        "governance": governance,
        "approval_status": approval or "pending",
        "performance_delta": {
            "weighted_index_delta": delta,
            "effectiveness_score_delta": round(
                _to_score(candidate.get("strategy_effectiveness_score")) - _to_score(baseline.get("strategy_effectiveness_score")),
                2,
            ),
            "conversion_rate_delta": round(_to_ratio(candidate.get("conversion_rate")) - _to_ratio(baseline.get("conversion_rate")), 4),
            "revenue_outcome_delta": round(
                _to_ratio(candidate.get("revenue_outcome_score")) - _to_ratio(baseline.get("revenue_outcome_score")),
                4,
            ),
            "failure_rate_delta": failure_delta,
            "follow_up_effectiveness_delta": round(
                _to_ratio(candidate.get("follow_up_effectiveness")) - _to_ratio(baseline.get("follow_up_effectiveness")),
                4,
            ),
        },
    }
    return payload


def run_comparative_validation(
    *,
    baseline_summary: dict[str, Any] | None,
    candidate_summary: dict[str, Any] | None,
    baseline_version_id: str,
    candidate_version_id: str,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    baseline = _extract_metrics(baseline_summary)
    candidate = _extract_metrics(candidate_summary)
    baseline_index = _weighted_performance_index(baseline)
    candidate_index = _weighted_performance_index(candidate)
    delta = round(candidate_index - baseline_index, 4)
    sample_size = max(1, min(int(baseline.get("sample_size") or 0), int(candidate.get("sample_size") or 0)))
    confidence = round(_clamp((abs(delta) * 2.2) + _clamp(sample_size / 40.0, 0.15, 1.0) * 0.35, 0.0, 1.0), 4)

    if delta < -0.02:
        status = "regression_detected"
        winner = str(baseline_version_id or "").strip()
    elif abs(delta) < 0.01 or confidence < 0.45:
        status = "inconclusive"
        winner = str(baseline_version_id or "").strip()
    elif delta > 0:
        status = "candidate_wins"
        winner = str(candidate_version_id or "").strip()
    else:
        status = "baseline_wins"
        winner = str(baseline_version_id or "").strip()

    payload = {
        "comparison_status": "ok",
        "recorded_at": _utc_now_iso(),
        "baseline_version_id": str(baseline_version_id or "").strip(),
        "candidate_version_id": str(candidate_version_id or "").strip(),
        "winner_strategy": winner,
        "performance_delta": {
            "weighted_index_delta": delta,
            "conversion_rate_delta": round(_to_ratio(candidate.get("conversion_rate")) - _to_ratio(baseline.get("conversion_rate")), 4),
            "revenue_delta": round(_to_ratio(candidate.get("revenue_outcome_score")) - _to_ratio(baseline.get("revenue_outcome_score")), 4),
            "failure_rate_delta": round(_to_ratio(candidate.get("failure_rate")) - _to_ratio(baseline.get("failure_rate")), 4),
            "follow_up_delta": round(
                _to_ratio(candidate.get("follow_up_effectiveness")) - _to_ratio(baseline.get("follow_up_effectiveness")),
                4,
            ),
        },
        "statistical_confidence": confidence,
        "validation_status": status,
    }
    _append_jsonl(_store_path(COMPARISON_LOG_FILE, strategy_store_dir), payload)
    return payload


def start_strategy_experiment(
    *,
    candidate_version_id: str,
    baseline_version_id: str,
    mode: str,
    rollout_percentage: int = 0,
    rollout_scope: str = "per_project",
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in EXPERIMENT_MODES:
        normalized_mode = "shadow"
    pct = int(_clamp(float(rollout_percentage), 0.0, 100.0))
    payload = {
        "experiment_status": "ok",
        "recorded_at": _utc_now_iso(),
        "experiment_id": f"exp-{candidate_version_id or 'candidate'}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "mode": normalized_mode,
        "candidate_version_id": str(candidate_version_id or "").strip(),
        "baseline_version_id": str(baseline_version_id or "").strip(),
        "rollout_percentage": pct if normalized_mode == "controlled_rollout" else (100 if normalized_mode == "full_activation" else 0),
        "rollout_scope": str(rollout_scope or "per_project").strip(),
        "safe_external_behavior": True,
        "decision_effective": normalized_mode != "shadow",
    }
    _append_jsonl(_store_path(EXPERIMENT_LOG_FILE, strategy_store_dir), payload)
    update_strategy_lifecycle_safe(
        strategy_version_id=str(candidate_version_id or "").strip(),
        lifecycle_status="testing" if normalized_mode != "full_activation" else "active",
        reason=f"Experiment mode started: {normalized_mode}.",
        strategy_store_dir=strategy_store_dir,
    )
    return payload


def _next_ramp_percentage(current: int) -> int:
    for step in ROLLOUT_RAMP:
        if current < step:
            return step
    return 100


def update_rollout_controller(
    *,
    candidate_version_id: str,
    baseline_version_id: str,
    rollout_percentage: int,
    rollout_scope: str,
    validation_status: str,
    degradation_detected: bool = False,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    current = int(_clamp(float(rollout_percentage), 0.0, 100.0))
    validation = str(validation_status or "").strip().lower()
    if validation not in VALIDATION_STATUSES:
        validation = "inconclusive"

    next_pct = current
    rollout_status = "holding"
    if degradation_detected or validation == "regression_detected":
        next_pct = 0
        rollout_status = "halted"
    elif validation == "candidate_wins":
        next_pct = _next_ramp_percentage(current)
        rollout_status = "advancing" if next_pct > current else "steady"
    elif validation == "baseline_wins":
        next_pct = max(0, min(current, 10))
        rollout_status = "reduced"

    payload = {
        "rollout_status": "ok",
        "recorded_at": _utc_now_iso(),
        "candidate_version_id": str(candidate_version_id or "").strip(),
        "baseline_version_id": str(baseline_version_id or "").strip(),
        "rollout_percentage": next_pct,
        "previous_rollout_percentage": current,
        "rollout_scope": str(rollout_scope or "per_project").strip(),
        "ramp_rule": "10->25->50->100",
        "validation_status": validation,
        "degradation_detected": bool(degradation_detected),
        "controller_status": rollout_status,
        "full_activation_ready": next_pct >= 100 and validation == "candidate_wins",
    }
    _write_json(_store_path(ROLLOUT_STATUS_FILE, strategy_store_dir), payload)
    return payload


def set_active_strategy(
    *,
    strategy_version_id: str,
    previous_strategy_version_id: str = "",
    activation_reason: str = "",
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    strategy_id = str(strategy_version_id or "").strip()
    if not strategy_id:
        return {"status": "error", "reason": "strategy_version_id is required.", "active_strategy": {}}
    now = _utc_now_iso()
    payload = {
        "active_strategy_status": "ok",
        "recorded_at": now,
        "active_strategy_version_id": strategy_id,
        "previous_strategy_version_id": str(previous_strategy_version_id or "").strip(),
        "activation_reason": str(activation_reason or "Activated through governed rollout.").strip(),
        "bounded": True,
        "governed": True,
        "reversible": True,
    }
    written = _write_json(_store_path(ACTIVE_STRATEGY_FILE, strategy_store_dir), payload)
    if written:
        update_strategy_lifecycle_safe(
            strategy_version_id=strategy_id,
            lifecycle_status="active",
            reason=payload["activation_reason"],
            strategy_store_dir=strategy_store_dir,
        )
        previous_id = str(previous_strategy_version_id or "").strip()
        if previous_id and previous_id != strategy_id:
            update_strategy_lifecycle_safe(
                strategy_version_id=previous_id,
                lifecycle_status="deprecated",
                reason=f"Deprecated after activation of {strategy_id}.",
                strategy_store_dir=strategy_store_dir,
            )
    return {
        "status": "ok" if written else "error",
        "reason": "Active strategy updated." if written else "Failed to update active strategy.",
        "active_strategy": payload if written else {},
    }


def get_active_strategy(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    payload = _read_json(_store_path(ACTIVE_STRATEGY_FILE, strategy_store_dir))
    if isinstance(payload, dict) and payload.get("active_strategy_version_id"):
        return payload
    fallback = get_latest_strategy_weights(strategy_store_dir=strategy_store_dir)
    return {
        "active_strategy_status": "fallback",
        "recorded_at": _utc_now_iso(),
        "active_strategy_version_id": str(fallback.get("strategy_version_id") or "strategy-v0-default"),
        "previous_strategy_version_id": "",
        "activation_reason": "No explicit active strategy found; using latest strategy weights.",
        "bounded": True,
        "governed": True,
        "reversible": True,
    }


def trigger_rollback(
    *,
    candidate_version_id: str,
    fallback_version_id: str,
    reason: str,
    degradation_detected: bool,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    should_rollback = bool(degradation_detected)
    payload = {
        "rollback_status": "ok",
        "recorded_at": _utc_now_iso(),
        "rollback_triggered": should_rollback,
        "candidate_version_id": str(candidate_version_id or "").strip(),
        "fallback_version_id": str(fallback_version_id or "").strip(),
        "rollback_reason": str(reason or "No rollback required.").strip(),
        "deterministic": True,
        "fast_path": True,
    }
    if should_rollback:
        set_active_strategy(
            strategy_version_id=str(fallback_version_id or "").strip(),
            previous_strategy_version_id=str(candidate_version_id or "").strip(),
            activation_reason=f"Automatic rollback from {candidate_version_id}.",
            strategy_store_dir=strategy_store_dir,
        )
        update_strategy_lifecycle_safe(
            strategy_version_id=str(candidate_version_id or "").strip(),
            lifecycle_status="rolled_back",
            reason=payload["rollback_reason"],
            rollback_event=payload,
            strategy_store_dir=strategy_store_dir,
        )
        update_strategy_lifecycle_safe(
            strategy_version_id=str(candidate_version_id or "").strip(),
            lifecycle_status="failed",
            reason="Candidate marked failed after rollback trigger.",
            rollback_event=payload,
            strategy_store_dir=strategy_store_dir,
        )
    _append_jsonl(_store_path(ROLLBACK_LOG_FILE, strategy_store_dir), payload)
    return payload


def run_strategy_promotion_cycle(
    *,
    candidate_version_id: str,
    baseline_version_id: str | None = None,
    candidate_summary: dict[str, Any] | None = None,
    baseline_summary: dict[str, Any] | None = None,
    risk_level: str = "medium",
    approval_status: str = "approved",
    rollout_scope: str = "per_project",
    rollout_percentage: int = 0,
    allowed_action_types: list[str] | None = None,
    strategy_store_dir: str | None = None,
) -> dict[str, Any]:
    baseline_id = str(baseline_version_id or "").strip()
    if not baseline_id:
        baseline_id = get_active_strategy(strategy_store_dir=strategy_store_dir).get("active_strategy_version_id") or "strategy-v0-default"
    candidate_id = str(candidate_version_id or "").strip()
    baseline_perf = baseline_summary if isinstance(baseline_summary, dict) and baseline_summary else analyze_strategy_performance_safe()
    candidate_perf = candidate_summary if isinstance(candidate_summary, dict) and candidate_summary else baseline_perf

    comparison = run_comparative_validation(
        baseline_summary=baseline_perf,
        candidate_summary=candidate_perf,
        baseline_version_id=baseline_id,
        candidate_version_id=candidate_id,
        strategy_store_dir=strategy_store_dir,
    )
    promotion = evaluate_change_promotion_decision(
        baseline_summary=baseline_perf,
        candidate_summary=candidate_perf,
        candidate_version_id=candidate_id,
        baseline_version_id=baseline_id,
        risk_level=risk_level,
        approval_status=approval_status,
        allowed_action_types=allowed_action_types,
        requires_approval=True,
    )

    decision = str(promotion.get("promotion_decision") or "test")
    mode = "shadow"
    desired_pct = 0
    if decision == "promote_partial":
        mode = "controlled_rollout"
        desired_pct = max(10, int(_clamp(float(rollout_percentage or 10), 0.0, 100.0)))
    elif decision == "promote_full":
        mode = "full_activation"
        desired_pct = 100
    experiment = start_strategy_experiment(
        candidate_version_id=candidate_id,
        baseline_version_id=baseline_id,
        mode=mode,
        rollout_percentage=desired_pct,
        rollout_scope=rollout_scope,
        strategy_store_dir=strategy_store_dir,
    )

    rollout = update_rollout_controller(
        candidate_version_id=candidate_id,
        baseline_version_id=baseline_id,
        rollout_percentage=int(experiment.get("rollout_percentage") or 0),
        rollout_scope=str(rollout_scope or "per_project"),
        validation_status=str(comparison.get("validation_status") or "inconclusive"),
        degradation_detected=str(comparison.get("validation_status") or "") == "regression_detected",
        strategy_store_dir=strategy_store_dir,
    )

    rollback = {"rollback_status": "ok", "rollback_triggered": False, "rollback_reason": "No rollback required."}
    if str(comparison.get("validation_status")) == "regression_detected":
        rollback = trigger_rollback(
            candidate_version_id=candidate_id,
            fallback_version_id=baseline_id,
            reason="Comparative validation detected regression.",
            degradation_detected=True,
            strategy_store_dir=strategy_store_dir,
        )
    elif decision == "promote_full" and bool(rollout.get("full_activation_ready")):
        set_active_strategy(
            strategy_version_id=candidate_id,
            previous_strategy_version_id=baseline_id,
            activation_reason="Promotion cycle advanced candidate to full activation.",
            strategy_store_dir=strategy_store_dir,
        )

    update_strategy_lifecycle_safe(
        strategy_version_id=candidate_id,
        lifecycle_status="testing" if decision in {"test", "promote_partial"} else ("active" if decision == "promote_full" else "failed"),
        promotion_decision=promotion,
        performance_snapshot={
            "recorded_at": _utc_now_iso(),
            "candidate_effectiveness_score": _to_score(_extract_metrics(candidate_perf).get("strategy_effectiveness_score")),
            "baseline_effectiveness_score": _to_score(_extract_metrics(baseline_perf).get("strategy_effectiveness_score")),
            "validation_status": comparison.get("validation_status"),
        },
        reason=str(promotion.get("promotion_reason") or ""),
        strategy_store_dir=strategy_store_dir,
    )

    status_payload = {
        "strategy_promotion_status": "ok",
        "engine_version": CHANGE_PROMOTION_ENGINE_VERSION,
        "recorded_at": _utc_now_iso(),
        "candidate_version_id": candidate_id,
        "baseline_version_id": baseline_id,
        "promotion": promotion,
        "experiment": experiment,
        "comparison": comparison,
        "rollout": rollout,
        "rollback": rollback,
        "bounded": True,
        "governed": True,
        "reversible": True,
        "observable": True,
    }
    _write_json(_store_path(PROMOTION_STATUS_FILE, strategy_store_dir), status_payload)
    return status_payload


def read_strategy_promotion_status(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    payload = _read_json(_store_path(PROMOTION_STATUS_FILE, strategy_store_dir))
    if payload:
        return payload
    active = get_active_strategy(strategy_store_dir=strategy_store_dir)
    return {
        "strategy_promotion_status": "idle",
        "engine_version": CHANGE_PROMOTION_ENGINE_VERSION,
        "recorded_at": _utc_now_iso(),
        "candidate_version_id": "",
        "baseline_version_id": str(active.get("active_strategy_version_id") or "strategy-v0-default"),
        "promotion": {
            "promotion_decision": "test",
            "promotion_reason": "No promotion cycle has been recorded yet.",
            "promotion_confidence": 0.0,
            "promotion_scope": "shadow_mode",
        },
        "experiment": {},
        "comparison": {},
        "rollout": {},
        "rollback": {},
        "bounded": True,
        "governed": True,
        "reversible": True,
        "observable": True,
    }


def list_strategy_experiments(*, n: int = 20, strategy_store_dir: str | None = None) -> dict[str, Any]:
    rows = _read_jsonl(_store_path(EXPERIMENT_LOG_FILE, strategy_store_dir), limit=max(20, n * 3))
    rows.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
    return {
        "strategy_experiments_status": "ok",
        "experiment_count": len(rows[: max(1, n)]),
        "experiments": rows[: max(1, n)],
    }


def list_strategy_comparisons(*, n: int = 20, strategy_store_dir: str | None = None) -> dict[str, Any]:
    rows = _read_jsonl(_store_path(COMPARISON_LOG_FILE, strategy_store_dir), limit=max(20, n * 3))
    rows.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
    return {
        "strategy_comparison_status": "ok",
        "comparison_count": len(rows[: max(1, n)]),
        "comparisons": rows[: max(1, n)],
    }


def read_rollout_status(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    payload = _read_json(_store_path(ROLLOUT_STATUS_FILE, strategy_store_dir))
    if payload:
        return payload
    return {
        "rollout_status": "idle",
        "recorded_at": _utc_now_iso(),
        "rollout_percentage": 0,
        "ramp_rule": "10->25->50->100",
        "controller_status": "idle",
    }


def list_rollback_history(*, n: int = 20, strategy_store_dir: str | None = None) -> dict[str, Any]:
    rows = _read_jsonl(_store_path(ROLLBACK_LOG_FILE, strategy_store_dir), limit=max(20, n * 3))
    rows.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
    return {
        "rollback_history_status": "ok",
        "rollback_count": len(rows[: max(1, n)]),
        "rollbacks": rows[: max(1, n)],
    }


def read_active_strategy_with_lifecycle(*, strategy_store_dir: str | None = None) -> dict[str, Any]:
    active = get_active_strategy(strategy_store_dir=strategy_store_dir)
    lifecycle = read_strategy_lifecycle_registry_safe(strategy_store_dir=strategy_store_dir)
    active_id = str(active.get("active_strategy_version_id") or "")
    versions = lifecycle.get("versions") if isinstance(lifecycle.get("versions"), dict) else {}
    return {
        "active_strategy_status": "ok",
        "active_strategy": active,
        "active_lifecycle": versions.get(active_id) if isinstance(versions.get(active_id), dict) else {},
        "lifecycle_status": lifecycle.get("strategy_lifecycle_status"),
    }


def run_strategy_promotion_cycle_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return run_strategy_promotion_cycle(**kwargs)
    except Exception as exc:
        return {
            "strategy_promotion_status": "error_fallback",
            "reason": f"Promotion cycle failed: {exc}",
            "bounded": True,
            "governed": True,
            "reversible": True,
            "observable": True,
        }


def read_strategy_promotion_status_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return read_strategy_promotion_status(**kwargs)
    except Exception:
        return {
            "strategy_promotion_status": "error_fallback",
            "promotion": {"promotion_decision": "test", "promotion_confidence": 0.0},
        }


def list_strategy_experiments_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return list_strategy_experiments(**kwargs)
    except Exception:
        return {"strategy_experiments_status": "error_fallback", "experiment_count": 0, "experiments": []}


def list_strategy_comparisons_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return list_strategy_comparisons(**kwargs)
    except Exception:
        return {"strategy_comparison_status": "error_fallback", "comparison_count": 0, "comparisons": []}


def read_rollout_status_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return read_rollout_status(**kwargs)
    except Exception:
        return {"rollout_status": "error_fallback", "rollout_percentage": 0, "controller_status": "error"}


def list_rollback_history_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return list_rollback_history(**kwargs)
    except Exception:
        return {"rollback_history_status": "error_fallback", "rollback_count": 0, "rollbacks": []}


def read_active_strategy_with_lifecycle_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return read_active_strategy_with_lifecycle(**kwargs)
    except Exception:
        return {
            "active_strategy_status": "error_fallback",
            "active_strategy": {"active_strategy_version_id": "strategy-v0-default"},
            "active_lifecycle": {},
        }
