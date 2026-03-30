"""
Durable mission queue and bounded worker orchestrator.

This module provides:
- durable queue storage
- bounded worker claiming with leases
- retry/backoff and lease-expiry recovery
- project-level fairness and backpressure controls
- command-surface friendly status snapshots
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


QUEUE_REGISTRY_RELATIVE_PATH = Path("ops") / "mission_queue_registry.json"
DEFAULT_LEASE_SECONDS = 180
DEFAULT_RETRY_LIMIT = 3
DEFAULT_BACKOFF_SECONDS = 20
DEFAULT_MAX_CONCURRENT_WORKERS = 4
DEFAULT_PER_PROJECT_LIMIT = 2
DEFAULT_OVERLOAD_QUEUE_THRESHOLD = 40

QUEUE_ACTIVE_STATUSES = {"queued", "leased", "retry_wait"}
QUEUE_TERMINAL_STATUSES = {"completed", "failed", "blocked", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _repo_root() -> Path:
    # NEXUS/mission_queue_orchestrator.py -> repo root
    return Path(__file__).resolve().parent.parent


def _registry_path(registry_path: str | None = None) -> Path:
    if registry_path:
        return Path(registry_path).resolve()
    return (_repo_root() / QUEUE_REGISTRY_RELATIVE_PATH).resolve()


def _default_control() -> dict[str, Any]:
    return {
        "max_concurrent_workers": DEFAULT_MAX_CONCURRENT_WORKERS,
        "per_project_limit": DEFAULT_PER_PROJECT_LIMIT,
        "lease_seconds": DEFAULT_LEASE_SECONDS,
        "retry_limit": DEFAULT_RETRY_LIMIT,
        "base_backoff_seconds": DEFAULT_BACKOFF_SECONDS,
        "overload_queue_threshold": DEFAULT_OVERLOAD_QUEUE_THRESHOLD,
        "slowdown_active": False,
        "slowdown_reason": "",
        "kill_switch_active": False,
    }


def _default_registry() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "updated_at": _utc_now_iso(),
        "items": [],
        "worker_runs": [],
        "control": _default_control(),
        "meta": {
            "last_project_claimed": "",
            "recovered_lease_count": 0,
            "last_recovery_at": "",
        },
    }


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    backoff = item.get("backoff_state") if isinstance(item.get("backoff_state"), dict) else {}
    return {
        "queue_item_id": str(item.get("queue_item_id") or uuid.uuid4().hex[:16]),
        "mission_id": str(item.get("mission_id") or ""),
        "project_id": str(item.get("project_id") or "").strip().lower(),
        "package_id": str(item.get("package_id") or ""),
        "task_type": str(item.get("task_type") or "autopilot_task"),
        "priority": int(item.get("priority") or 100),
        "queue_status": str(item.get("queue_status") or "queued").strip().lower(),
        "enqueue_time": str(item.get("enqueue_time") or _utc_now_iso()),
        "lease_owner": str(item.get("lease_owner") or ""),
        "lease_expiry": str(item.get("lease_expiry") or ""),
        "retry_count": max(0, int(item.get("retry_count") or 0)),
        "retry_limit": max(0, int(item.get("retry_limit") or DEFAULT_RETRY_LIMIT)),
        "backoff_state": {
            "base_backoff_seconds": max(1, int(backoff.get("base_backoff_seconds") or DEFAULT_BACKOFF_SECONDS)),
            "last_backoff_seconds": max(0, int(backoff.get("last_backoff_seconds") or 0)),
            "next_retry_at": str(backoff.get("next_retry_at") or ""),
            "cooldown_reason": str(backoff.get("cooldown_reason") or ""),
        },
        "idempotency_key": str(item.get("idempotency_key") or ""),
        "claimed_at": str(item.get("claimed_at") or ""),
        "started_at": str(item.get("started_at") or ""),
        "completed_at": str(item.get("completed_at") or ""),
        "last_error": str(item.get("last_error") or ""),
        "execution_receipt_ref": str(item.get("execution_receipt_ref") or ""),
        "verification_ref": str(item.get("verification_ref") or ""),
        "operator_escalation_ref": str(item.get("operator_escalation_ref") or ""),
        "worker_run_id": str(item.get("worker_run_id") or ""),
    }


def _load_registry(registry_path: str | None = None) -> tuple[Path, dict[str, Any]]:
    path = _registry_path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = _default_registry()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path, payload
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = _default_registry()
    if not isinstance(raw, dict):
        raw = _default_registry()
    control = raw.get("control") if isinstance(raw.get("control"), dict) else {}
    merged_control = {**_default_control(), **control}
    items = [item for item in (raw.get("items") or []) if isinstance(item, dict)]
    worker_runs = [row for row in (raw.get("worker_runs") or []) if isinstance(row, dict)]
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    normalized = {
        "schema_version": "1.0",
        "updated_at": str(raw.get("updated_at") or _utc_now_iso()),
        "items": [_normalize_item(item) for item in items],
        "worker_runs": worker_runs[-500:],
        "control": merged_control,
        "meta": {
            "last_project_claimed": str(meta.get("last_project_claimed") or ""),
            "recovered_lease_count": max(0, int(meta.get("recovered_lease_count") or 0)),
            "last_recovery_at": str(meta.get("last_recovery_at") or ""),
        },
    }
    return path, normalized


def _save_registry(path: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = _utc_now_iso()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _eligible_retry(item: dict[str, Any], now_dt: datetime) -> bool:
    if item.get("queue_status") == "queued":
        return True
    if item.get("queue_status") != "retry_wait":
        return False
    next_retry = _parse_iso(((item.get("backoff_state") or {}).get("next_retry_at")))
    return next_retry is None or next_retry <= now_dt


def _active_leases_by_project(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if str(item.get("queue_status") or "").strip().lower() != "leased":
            continue
        project_id = str(item.get("project_id") or "")
        counts[project_id] = counts.get(project_id, 0) + 1
    return counts


def enqueue_mission_work_item(
    *,
    mission_id: str,
    project_id: str,
    package_id: str,
    task_type: str,
    priority: int = 100,
    retry_limit: int | None = None,
    idempotency_key: str | None = None,
    registry_path: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    dedupe_key = str(idempotency_key or f"{project_id}:{mission_id}:{package_id}:{task_type}").strip().lower()
    existing = None
    for item in registry["items"]:
        if str(item.get("idempotency_key") or "").strip().lower() == dedupe_key:
            if str(item.get("queue_status") or "").strip().lower() in QUEUE_ACTIVE_STATUSES | {"completed"}:
                existing = item
                break
    if existing:
        return {
            "status": "deduped",
            "reason": "Existing queue item already tracks this mission idempotency key.",
            "queue_item": dict(existing),
            "dedupe_hit": True,
        }
    queue_item = _normalize_item(
        {
            "mission_id": mission_id,
            "project_id": project_id,
            "package_id": package_id,
            "task_type": task_type,
            "priority": priority,
            "queue_status": "queued",
            "enqueue_time": _utc_now_iso(),
            "retry_limit": retry_limit if retry_limit is not None else registry["control"]["retry_limit"],
            "idempotency_key": dedupe_key,
        }
    )
    registry["items"].append(queue_item)
    _save_registry(path, registry)
    return {"status": "ok", "reason": "Mission work item enqueued.", "queue_item": queue_item, "dedupe_hit": False}


def recover_expired_leases(*, registry_path: str | None = None) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    now_dt = _utc_now()
    recovered = 0
    expired_failed = 0
    for item in registry["items"]:
        if str(item.get("queue_status") or "").strip().lower() != "leased":
            continue
        expiry = _parse_iso(item.get("lease_expiry"))
        if expiry is None or expiry > now_dt:
            continue
        retry_count = int(item.get("retry_count") or 0)
        retry_limit = int(item.get("retry_limit") or DEFAULT_RETRY_LIMIT)
        if retry_count < retry_limit:
            retry_count += 1
            backoff_seconds = int((item.get("backoff_state") or {}).get("base_backoff_seconds") or DEFAULT_BACKOFF_SECONDS) * (
                2 ** max(0, retry_count - 1)
            )
            item["queue_status"] = "retry_wait"
            item["retry_count"] = retry_count
            item["lease_owner"] = ""
            item["lease_expiry"] = ""
            item["worker_run_id"] = ""
            item["last_error"] = "lease_expired_worker_unavailable"
            item["backoff_state"]["last_backoff_seconds"] = backoff_seconds
            item["backoff_state"]["next_retry_at"] = (_utc_now() + timedelta(seconds=backoff_seconds)).isoformat().replace("+00:00", "Z")
            item["backoff_state"]["cooldown_reason"] = "lease_expired"
            recovered += 1
        else:
            item["queue_status"] = "failed"
            item["lease_owner"] = ""
            item["lease_expiry"] = ""
            item["worker_run_id"] = ""
            item["last_error"] = "lease_expired_retry_exhausted"
            item["completed_at"] = _utc_now_iso()
            expired_failed += 1
    if recovered or expired_failed:
        registry["meta"]["recovered_lease_count"] = int(registry["meta"].get("recovered_lease_count") or 0) + recovered
        registry["meta"]["last_recovery_at"] = _utc_now_iso()
        _save_registry(path, registry)
    return {
        "status": "ok",
        "reason": "Lease recovery evaluated.",
        "recovered_count": recovered,
        "expired_failed_count": expired_failed,
    }


def claim_next_work_item(
    *,
    worker_id: str,
    registry_path: str | None = None,
    max_concurrent_workers: int | None = None,
    per_project_limit: int | None = None,
    kill_switch_active: bool = False,
    project_id_filter: str | None = None,
) -> dict[str, Any]:
    recover_expired_leases(registry_path=registry_path)
    path, registry = _load_registry(registry_path)
    control = registry["control"]
    max_workers = max(1, int(max_concurrent_workers or control.get("max_concurrent_workers") or DEFAULT_MAX_CONCURRENT_WORKERS))
    per_project = max(1, int(per_project_limit or control.get("per_project_limit") or DEFAULT_PER_PROJECT_LIMIT))

    leased = [item for item in registry["items"] if str(item.get("queue_status") or "").strip().lower() == "leased"]
    if kill_switch_active or bool(control.get("kill_switch_active")):
        return {"status": "blocked", "reason": "Kill switch is active.", "queue_item": None}
    if len(leased) >= max_workers:
        return {"status": "blocked", "reason": "Global worker concurrency cap reached.", "queue_item": None}

    now_dt = _utc_now()
    eligible = [
        item
        for item in registry["items"]
        if _eligible_retry(item, now_dt)
        and str(item.get("queue_status") or "").strip().lower() in {"queued", "retry_wait"}
    ]
    if project_id_filter:
        normalized_project_filter = str(project_id_filter).strip().lower()
        eligible = [item for item in eligible if str(item.get("project_id") or "").strip().lower() == normalized_project_filter]
    if not eligible:
        return {"status": "empty", "reason": "No eligible queued work item.", "queue_item": None}

    active_by_project = _active_leases_by_project(registry["items"])
    by_project: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        project_id = str(item.get("project_id") or "")
        if active_by_project.get(project_id, 0) >= per_project:
            continue
        by_project.setdefault(project_id, []).append(item)
    if not by_project:
        return {"status": "blocked", "reason": "Per-project concurrency cap reached.", "queue_item": None}

    ordered_projects = sorted(by_project.keys())
    last_project = str((registry.get("meta") or {}).get("last_project_claimed") or "")
    if last_project in ordered_projects:
        idx = ordered_projects.index(last_project)
        ordered_projects = ordered_projects[idx + 1 :] + ordered_projects[: idx + 1]

    selected_project = ordered_projects[0]
    candidates = sorted(
        by_project[selected_project],
        key=lambda row: (int(row.get("priority") or 100), str(row.get("enqueue_time") or ""), str(row.get("queue_item_id") or "")),
    )
    selected = candidates[0]
    lease_seconds = max(30, int(control.get("lease_seconds") or DEFAULT_LEASE_SECONDS))
    selected["queue_status"] = "leased"
    selected["lease_owner"] = str(worker_id or "").strip()
    selected["claimed_at"] = _utc_now_iso()
    selected["started_at"] = str(selected.get("started_at") or selected.get("claimed_at"))
    selected["lease_expiry"] = (_utc_now() + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    selected["worker_run_id"] = uuid.uuid4().hex[:16]
    selected["backoff_state"]["cooldown_reason"] = ""
    registry["meta"]["last_project_claimed"] = selected_project
    registry["worker_runs"].append(
        {
            "worker_run_id": selected["worker_run_id"],
            "worker_id": selected["lease_owner"],
            "queue_item_id": selected["queue_item_id"],
            "project_id": selected["project_id"],
            "package_id": selected["package_id"],
            "status": "running",
            "started_at": selected["claimed_at"],
            "finished_at": "",
            "reason": "",
        }
    )
    registry["worker_runs"] = registry["worker_runs"][-500:]
    _save_registry(path, registry)
    return {"status": "ok", "reason": "Work item claimed.", "queue_item": dict(selected)}


def renew_work_item_lease(
    *,
    queue_item_id: str,
    worker_id: str,
    registry_path: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    lease_seconds = max(30, int(registry["control"].get("lease_seconds") or DEFAULT_LEASE_SECONDS))
    for item in registry["items"]:
        if str(item.get("queue_item_id") or "") != str(queue_item_id):
            continue
        if str(item.get("queue_status") or "") != "leased" or str(item.get("lease_owner") or "") != str(worker_id):
            return {"status": "denied", "reason": "Lease renewal denied for non-owner or inactive lease."}
        item["lease_expiry"] = (_utc_now() + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
        _save_registry(path, registry)
        return {"status": "ok", "reason": "Lease renewed.", "queue_item": dict(item)}
    return {"status": "error", "reason": "Queue item not found."}


def release_work_item(
    *,
    queue_item_id: str,
    worker_id: str,
    reason: str = "released",
    registry_path: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    for item in registry["items"]:
        if str(item.get("queue_item_id") or "") != str(queue_item_id):
            continue
        if str(item.get("queue_status") or "") != "leased" or str(item.get("lease_owner") or "") != str(worker_id):
            return {"status": "denied", "reason": "Release denied for non-owner or inactive lease."}
        worker_run_id = str(item.get("worker_run_id") or "")
        item["queue_status"] = "queued"
        item["lease_owner"] = ""
        item["lease_expiry"] = ""
        item["worker_run_id"] = ""
        item["last_error"] = str(reason or "released")
        for run in reversed(registry["worker_runs"]):
            if str(run.get("worker_run_id") or "") == worker_run_id:
                run["status"] = "released"
                run["finished_at"] = _utc_now_iso()
                run["reason"] = str(reason or "released")
                break
        _save_registry(path, registry)
        return {"status": "ok", "reason": "Work item released back to queue.", "queue_item": dict(item)}
    return {"status": "error", "reason": "Queue item not found."}


def complete_work_item_success(
    *,
    queue_item_id: str,
    worker_id: str,
    execution_receipt_ref: str = "",
    verification_ref: str = "",
    registry_path: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    target = None
    for item in registry["items"]:
        if str(item.get("queue_item_id") or "") == str(queue_item_id):
            target = item
            break
    if target is None:
        return {"status": "error", "reason": "Queue item not found."}
    if str(target.get("lease_owner") or "") != str(worker_id):
        return {"status": "denied", "reason": "Only lease owner may complete work item."}
    target["queue_status"] = "completed"
    target["lease_owner"] = ""
    target["lease_expiry"] = ""
    target["completed_at"] = _utc_now_iso()
    target["execution_receipt_ref"] = str(execution_receipt_ref or "")
    target["verification_ref"] = str(verification_ref or "")
    for run in reversed(registry["worker_runs"]):
        if str(run.get("worker_run_id") or "") == str(target.get("worker_run_id") or ""):
            run["status"] = "succeeded"
            run["finished_at"] = target["completed_at"]
            run["reason"] = "completed"
            break
    _save_registry(path, registry)
    return {"status": "ok", "reason": "Work item completed.", "queue_item": dict(target)}


def complete_work_item_failure(
    *,
    queue_item_id: str,
    worker_id: str,
    error_reason: str,
    retryable: bool = True,
    operator_escalation_ref: str = "",
    registry_path: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_registry(registry_path)
    target = None
    for item in registry["items"]:
        if str(item.get("queue_item_id") or "") == str(queue_item_id):
            target = item
            break
    if target is None:
        return {"status": "error", "reason": "Queue item not found."}
    if str(target.get("lease_owner") or "") != str(worker_id):
        return {"status": "denied", "reason": "Only lease owner may fail work item."}

    target["lease_owner"] = ""
    target["lease_expiry"] = ""
    target["last_error"] = str(error_reason or "unknown_error")
    target["operator_escalation_ref"] = str(operator_escalation_ref or target.get("operator_escalation_ref") or "")
    retry_count = int(target.get("retry_count") or 0)
    retry_limit = int(target.get("retry_limit") or DEFAULT_RETRY_LIMIT)

    if retryable and retry_count < retry_limit:
        retry_count += 1
        target["retry_count"] = retry_count
        base = int((target.get("backoff_state") or {}).get("base_backoff_seconds") or DEFAULT_BACKOFF_SECONDS)
        backoff_seconds = base * (2 ** max(0, retry_count - 1))
        target["queue_status"] = "retry_wait"
        target["backoff_state"]["last_backoff_seconds"] = backoff_seconds
        target["backoff_state"]["next_retry_at"] = (_utc_now() + timedelta(seconds=backoff_seconds)).isoformat().replace("+00:00", "Z")
        target["backoff_state"]["cooldown_reason"] = "retry_backoff"
    else:
        target["queue_status"] = "failed"
        target["completed_at"] = _utc_now_iso()

    for run in reversed(registry["worker_runs"]):
        if str(run.get("worker_run_id") or "") == str(target.get("worker_run_id") or ""):
            run["status"] = "failed"
            run["finished_at"] = _utc_now_iso()
            run["reason"] = str(error_reason or "failed")
            break
    _save_registry(path, registry)
    return {"status": "ok", "reason": "Work item failure recorded.", "queue_item": dict(target)}


def mission_queue_status(*, registry_path: str | None = None) -> dict[str, Any]:
    _, registry = _load_registry(registry_path)
    counts: dict[str, int] = {}
    for item in registry["items"]:
        status = str(item.get("queue_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "status": "ok",
        "registry_path": str(_registry_path(registry_path)),
        "updated_at": registry.get("updated_at"),
        "total_items": len(registry["items"]),
        "counts_by_status": counts,
        "active_items": [row for row in registry["items"] if str(row.get("queue_status") or "") in QUEUE_ACTIVE_STATUSES][:20],
        "control": dict(registry.get("control") or {}),
    }


def worker_status(*, registry_path: str | None = None) -> dict[str, Any]:
    _, registry = _load_registry(registry_path)
    active_runs = [row for row in registry["worker_runs"] if str(row.get("status") or "") == "running"]
    return {
        "status": "ok",
        "active_worker_runs": active_runs,
        "active_worker_count": len({str(row.get("worker_id") or "") for row in active_runs if str(row.get("worker_id") or "")}),
        "recent_worker_runs": registry["worker_runs"][-30:],
        "max_concurrent_workers": int((registry.get("control") or {}).get("max_concurrent_workers") or DEFAULT_MAX_CONCURRENT_WORKERS),
    }


def recovery_status(*, registry_path: str | None = None) -> dict[str, Any]:
    _, registry = _load_registry(registry_path)
    recovery_waiting = [row for row in registry["items"] if str(row.get("queue_status") or "") == "retry_wait"]
    lease_expired_count = len([row for row in registry["items"] if str(row.get("last_error") or "") == "lease_expired_worker_unavailable"])
    return {
        "status": "ok",
        "recovery_waiting_count": len(recovery_waiting),
        "lease_expired_recovered_count": int((registry.get("meta") or {}).get("recovered_lease_count") or 0),
        "lease_expired_current_count": lease_expired_count,
        "last_recovery_at": str((registry.get("meta") or {}).get("last_recovery_at") or ""),
        "retry_items": recovery_waiting[:20],
    }


def backpressure_status(*, registry_path: str | None = None) -> dict[str, Any]:
    _, registry = _load_registry(registry_path)
    control = registry.get("control") or {}
    leased_count = len([row for row in registry["items"] if str(row.get("queue_status") or "") == "leased"])
    queued_count = len([row for row in registry["items"] if str(row.get("queue_status") or "") in {"queued", "retry_wait"}])
    max_workers = max(1, int(control.get("max_concurrent_workers") or DEFAULT_MAX_CONCURRENT_WORKERS))
    overload_threshold = max(1, int(control.get("overload_queue_threshold") or DEFAULT_OVERLOAD_QUEUE_THRESHOLD))
    overload = queued_count >= overload_threshold or leased_count >= max_workers
    return {
        "status": "ok",
        "leased_count": leased_count,
        "queued_count": queued_count,
        "max_concurrent_workers": max_workers,
        "per_project_limit": int(control.get("per_project_limit") or DEFAULT_PER_PROJECT_LIMIT),
        "overload_threshold": overload_threshold,
        "overload_active": overload,
        "slowdown_active": bool(control.get("slowdown_active") or overload),
        "slowdown_reason": str(control.get("slowdown_reason") or ("queue_overload" if overload else "")),
        "kill_switch_active": bool(control.get("kill_switch_active")),
    }


def stuck_work_items(*, registry_path: str | None = None) -> dict[str, Any]:
    _, registry = _load_registry(registry_path)
    now_dt = _utc_now()
    stuck: list[dict[str, Any]] = []
    for item in registry["items"]:
        status = str(item.get("queue_status") or "")
        if status == "leased":
            expiry = _parse_iso(item.get("lease_expiry"))
            if expiry and expiry <= now_dt:
                stuck.append(item)
        elif status == "retry_wait":
            next_retry = _parse_iso(((item.get("backoff_state") or {}).get("next_retry_at")))
            if next_retry and next_retry <= now_dt:
                stuck.append(item)
    return {
        "status": "ok",
        "stuck_count": len(stuck),
        "items": stuck[:50],
    }

