"""
Persistent global control-plane state for FORGE runtime governance.

This module stores cross-project control flags in a single restart-safe file.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.project_state import load_project_state
from NEXUS.runtime_target_registry import get_runtime_target_entry


GLOBAL_CONTROL_DIRNAME = "state"
GLOBAL_CONTROL_FILENAME = "global_control_state.json"
GLOBAL_CONTROL_LOCK_FILENAME = "global_control_state.lock"
GLOBAL_CONTROL_LOCK_TIMEOUT_SECONDS = 5.0
GLOBAL_CONTROL_LOCK_RETRY_SECONDS = 0.05


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    # NEXUS/global_control_state.py -> repo root
    return Path(__file__).resolve().parent.parent


def get_global_control_state_path() -> Path:
    state_dir = _repo_root() / GLOBAL_CONTROL_DIRNAME
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / GLOBAL_CONTROL_FILENAME


def _get_global_control_lock_path() -> Path:
    return get_global_control_state_path().with_name(GLOBAL_CONTROL_LOCK_FILENAME)


@contextmanager
def _acquire_global_control_lock(timeout_seconds: float = GLOBAL_CONTROL_LOCK_TIMEOUT_SECONDS):
    lock_path = _get_global_control_lock_path()
    started = time.monotonic()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()}\n")
                f.write(f"acquired_at={_utc_now_iso()}\n")
            break
        except FileExistsError:
            if (time.monotonic() - started) >= max(0.1, float(timeout_seconds or 0.0)):
                raise TimeoutError("Timed out acquiring global control state lock.")
            time.sleep(GLOBAL_CONTROL_LOCK_RETRY_SECONDS)
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _normalize_resource_limits(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    return {
        "max_loops": max(0, int(raw.get("max_loops") or 0)),
        "max_operations": max(0, int(raw.get("max_operations") or 0)),
        "max_runtime_seconds": max(0, int(raw.get("max_runtime_seconds") or 0)),
        "max_budget_units": max(0, int(raw.get("max_budget_units") or 0)),
    }


def build_default_global_control_state() -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "state_version": "1.0",
        "updated_at": now,
        "updated_by": "system",
        "update_reason": "initialize",
        "global_system_mode": "normal",
        "kill_switch": {
            "active": False,
            "reason": "",
            "updated_at": now,
            "updated_by": "system",
        },
        "active_missions": {},
        "active_strategy_versions": {},
        "active_loops": {},
        "resource_limits": _normalize_resource_limits(None),
        "autonomy_mode": "supervised_bounded",
        "last_stop_reason": "",
        "degraded_mode_flags": {
            "control_plane_degraded": False,
            "routing_degraded": False,
            "execution_verification_degraded": False,
        },
    }


def normalize_global_control_state(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    defaults = build_default_global_control_state()
    kill = dict(raw.get("kill_switch") or {})
    degraded = dict(raw.get("degraded_mode_flags") or {})
    out = {
        "state_version": "1.0",
        "updated_at": str(raw.get("updated_at") or defaults["updated_at"]),
        "updated_by": str(raw.get("updated_by") or defaults["updated_by"]),
        "update_reason": str(raw.get("update_reason") or defaults["update_reason"]),
        "global_system_mode": str(raw.get("global_system_mode") or defaults["global_system_mode"]).strip().lower(),
        "kill_switch": {
            "active": bool(kill.get("active", defaults["kill_switch"]["active"])),
            "reason": str(kill.get("reason") or ""),
            "updated_at": str(kill.get("updated_at") or defaults["kill_switch"]["updated_at"]),
            "updated_by": str(kill.get("updated_by") or defaults["kill_switch"]["updated_by"]),
        },
        "active_missions": dict(raw.get("active_missions") or {}),
        "active_strategy_versions": dict(raw.get("active_strategy_versions") or {}),
        "active_loops": dict(raw.get("active_loops") or {}),
        "resource_limits": _normalize_resource_limits(raw.get("resource_limits")),
        "autonomy_mode": str(raw.get("autonomy_mode") or defaults["autonomy_mode"]).strip().lower(),
        "last_stop_reason": str(raw.get("last_stop_reason") or ""),
        "degraded_mode_flags": {
            "control_plane_degraded": bool(degraded.get("control_plane_degraded", False)),
            "routing_degraded": bool(degraded.get("routing_degraded", False)),
            "execution_verification_degraded": bool(degraded.get("execution_verification_degraded", False)),
        },
    }
    if out["global_system_mode"] not in ("normal", "degraded", "maintenance", "emergency_stop"):
        out["global_system_mode"] = "normal"
    return out


def _load_global_control_state_unlocked() -> dict[str, Any]:
    path = get_global_control_state_path()
    if not path.exists():
        state = build_default_global_control_state()
        _save_global_control_state_unlocked(state, actor="system", reason="initialize_missing")
        return state
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = build_default_global_control_state()
        _save_global_control_state_unlocked(state, actor="system", reason="recover_from_read_error")
        return state
    return normalize_global_control_state(payload)


def load_global_control_state() -> dict[str, Any]:
    with _acquire_global_control_lock():
        return _load_global_control_state_unlocked()


def _save_global_control_state_unlocked(state: dict[str, Any], *, actor: str, reason: str) -> dict[str, Any]:
    normalized = normalize_global_control_state(state)
    normalized["updated_at"] = _utc_now_iso()
    normalized["updated_by"] = str(actor or "system")
    normalized["update_reason"] = str(reason or "")
    path = get_global_control_state_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
    return normalized


def save_global_control_state(state: dict[str, Any], *, actor: str, reason: str) -> dict[str, Any]:
    with _acquire_global_control_lock():
        return _save_global_control_state_unlocked(state, actor=actor, reason=reason)


def update_global_control_state(*, updates: dict[str, Any], actor: str, reason: str) -> dict[str, Any]:
    with _acquire_global_control_lock():
        current = _load_global_control_state_unlocked()
        merged = {**current, **dict(updates or {})}
        return _save_global_control_state_unlocked(merged, actor=actor, reason=reason)


def set_persistent_kill_switch(*, active: bool, actor: str, reason: str = "") -> dict[str, Any]:
    with _acquire_global_control_lock():
        state = _load_global_control_state_unlocked()
        state["kill_switch"] = {
            "active": bool(active),
            "reason": str(reason or ""),
            "updated_at": _utc_now_iso(),
            "updated_by": str(actor or "system"),
        }
        if active:
            state["last_stop_reason"] = str(reason or "persistent_kill_switch_active")
        if active:
            state["global_system_mode"] = "emergency_stop"
        elif state.get("global_system_mode") == "emergency_stop":
            state["global_system_mode"] = "normal"
        return _save_global_control_state_unlocked(state, actor=actor, reason="persistent_kill_switch_update")


def evaluate_routing_enforcement(
    *,
    project_path: str | None,
    project_name: str | None,
    runtime_target_id: str | None,
    allocation_status: str | None = None,
    mission_key: str | None = None,
    strategy_key: str | None = None,
    operation_type: str = "execution",
) -> dict[str, Any]:
    """
    Hard execution gate used by dispatch + execution.
    """
    control = load_global_control_state()
    project_state = load_project_state(str(project_path)) if project_path else {}
    project_id = str(project_name or project_state.get("active_project") or "").strip().lower()
    target_id = str(runtime_target_id or "").strip().lower()
    denies: list[dict[str, str]] = []

    if bool((control.get("kill_switch") or {}).get("active")):
        denies.append({"code": "kill_switch_active", "reason": str((control.get("kill_switch") or {}).get("reason") or "Persistent kill switch is active.")})

    system_mode = str(control.get("global_system_mode") or "normal").strip().lower()
    if system_mode in ("maintenance", "emergency_stop"):
        denies.append({"code": "global_mode_block", "reason": f"Global system mode '{system_mode}' blocks execution operations."})

    allocation = str(allocation_status or "").strip().lower()
    if allocation in ("denied", "blocked", "defer", "paused", "escalated", "stopped"):
        denies.append({"code": "allocation_denied", "reason": f"Routing/allocation state '{allocation}' disallows execution."})

    governance_status = str(project_state.get("governance_status") or "").strip().lower()
    enforcement_status = str(project_state.get("enforcement_status") or "").strip().lower()
    stop_status = str(project_state.get("autonomy_stop_rail_status") or "").strip().lower()
    workflow_route_status = str(project_state.get("workflow_route_status") or "").strip().lower()
    if governance_status in ("blocked", "approval_required", "review_required", "rejected", "error_fallback"):
        denies.append({"code": "governance_denied", "reason": f"Project governance status '{governance_status}' disallows execution."})
    if enforcement_status in ("blocked", "approval_required", "hold", "error_fallback"):
        denies.append({"code": "enforcement_denied", "reason": f"Project enforcement status '{enforcement_status}' disallows execution."})
    if operation_type != "autonomy_loop" and stop_status in ("paused", "escalated", "stopped"):
        denies.append({"code": "autonomy_stop_rail_active", "reason": f"Autonomy stop-rail status '{stop_status}' disallows execution."})
    if workflow_route_status in ("manual_review_hold", "approval_hold", "hold_state", "blocked_stop"):
        denies.append({"code": "workflow_route_hold", "reason": f"Workflow route '{workflow_route_status}' disallows execution."})

    mission_state = {}
    if mission_key:
        mission_state = dict((control.get("active_missions") or {}).get(str(mission_key), {}))
    elif project_id:
        mission_state = dict((control.get("active_missions") or {}).get(project_id, {}))
    if mission_state:
        mission_status = str(mission_state.get("status") or "").strip().lower()
        if mission_status in ("blocked", "paused", "stopped", "closed"):
            denies.append({"code": "mission_disallowed", "reason": f"Mission status '{mission_status}' disallows execution."})

    strategy_state = {}
    if strategy_key:
        strategy_state = dict((control.get("active_strategy_versions") or {}).get(str(strategy_key), {}))
    elif project_id:
        strategy_state = dict((control.get("active_strategy_versions") or {}).get(project_id, {}))
    if strategy_state:
        promotion_state = str(strategy_state.get("promotion_state") or "").strip().lower()
        if promotion_state in ("blocked", "pending", "rejected", "hold"):
            denies.append({"code": "strategy_disallowed", "reason": f"Strategy promotion state '{promotion_state}' disallows execution."})

    runtime_entry = get_runtime_target_entry(target_id)
    if operation_type in ("execution", "dispatch"):
        if not runtime_entry:
            denies.append({"code": "backend_not_ready", "reason": f"Runtime target '{target_id}' is not registered."})
        else:
            active_or_planned = str(runtime_entry.get("active_or_planned") or runtime_entry.get("status") or "").strip().lower()
            if active_or_planned != "active":
                denies.append({"code": "backend_not_ready", "reason": f"Runtime target '{target_id}' is not active."})

    allowed = len(denies) == 0
    return {
        "routing_enforcement_status": "allowed" if allowed else "denied",
        "operation_type": str(operation_type or "execution"),
        "project_name": project_id,
        "runtime_target_id": target_id,
        "denies": denies,
        "global_system_mode": system_mode,
        "kill_switch_active": bool((control.get("kill_switch") or {}).get("active")),
        "control_state_updated_at": str(control.get("updated_at") or ""),
    }
