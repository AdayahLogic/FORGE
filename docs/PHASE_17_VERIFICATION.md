# Phase 17 — Execution Environments: Full Verification Document

## 1. FULL CODE CHANGES

### 1.1 NEXUS/execution_environment_registry.py (NEW FILE — FULL CODE)

```python
"""
NEXUS execution environment registry (Phase 17).

Models execution context posture: isolation level, mutation allowance, network posture,
and review requirements. Distinct from runtime targets (where work runs) and AEGIS
environment (local_dev/staging/production). This layer prepares for future sandbox/
container isolation without pretending it exists.

Environment types:
- local_current: Active in-process execution; no isolation; bounded by AEGIS.
- local_bounded: Active IDE-mediated execution; bounded mutation; no real isolation.
- isolated_planned: Planned sandbox/isolated execution; not yet implemented.
- container_planned: Planned container execution; not yet implemented.
- external_runtime_planned: Planned external runtime; not yet implemented.
"""

from __future__ import annotations

from typing import Any

# -----------------------------------------------------------------------------
# Execution environment contract shape
# -----------------------------------------------------------------------------
# Each environment definition has:
#   environment_id: str
#   status: "active" | "planned"
#   isolation_level: "none" | "bounded" | "planned_isolated" | "planned_container" | "planned_external"
#   mutation_posture: "allowed" | "bounded" | "planned_restricted" | "planned_none"
#   network_posture: "allowed" | "restricted" | "planned_restricted" | "planned_none"
#   human_review_required: bool
#   bounded_execution: bool
#   notes: str
# -----------------------------------------------------------------------------

EXECUTION_ENVIRONMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "local_current": {
        "environment_id": "local_current",
        "display_name": "Local Current",
        "status": "active",
        "isolation_level": "none",
        "mutation_posture": "allowed",
        "network_posture": "allowed",
        "human_review_required": False,
        "bounded_execution": True,
        "notes": "In-process execution; no isolation; bounded by AEGIS and file_guard.",
    },
    "local_bounded": {
        "environment_id": "local_bounded",
        "display_name": "Local Bounded",
        "status": "active",
        "isolation_level": "bounded",
        "mutation_posture": "bounded",
        "network_posture": "allowed",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "IDE-mediated execution; bounded mutation via tool gateway; no real isolation.",
    },
    "isolated_planned": {
        "environment_id": "isolated_planned",
        "display_name": "Isolated (Planned)",
        "status": "planned",
        "isolation_level": "planned_isolated",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned sandbox/isolated execution; not yet implemented.",
    },
    "container_planned": {
        "environment_id": "container_planned",
        "display_name": "Container (Planned)",
        "status": "planned",
        "isolation_level": "planned_container",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned container execution; not yet implemented.",
    },
    "external_runtime_planned": {
        "environment_id": "external_runtime_planned",
        "display_name": "External Runtime (Planned)",
        "status": "planned",
        "isolation_level": "planned_external",
        "mutation_posture": "planned_restricted",
        "network_posture": "planned_restricted",
        "human_review_required": True,
        "bounded_execution": True,
        "notes": "Planned external runtime execution; not yet implemented.",
    },
}

# Mapping: runtime target canonical name -> execution environment id
RUNTIME_TARGET_TO_ENVIRONMENT: dict[str, str] = {
    "local": "local_current",
    "cursor": "local_bounded",
    "codex": "local_bounded",
    "container_worker": "container_planned",
    "remote_worker": "external_runtime_planned",
    "cloud_worker": "external_runtime_planned",
}


def get_environment_for_runtime_target(runtime_target: str | None) -> str | None:
    """Return execution environment id for a runtime target, or None if unknown."""
    if not runtime_target:
        return None
    key = str(runtime_target).strip().lower()
    return RUNTIME_TARGET_TO_ENVIRONMENT.get(key)


def get_environment_definition(environment_id: str | None) -> dict[str, Any] | None:
    """Return full environment definition, or None if unknown."""
    if not environment_id:
        return None
    key = str(environment_id).strip().lower()
    return dict(EXECUTION_ENVIRONMENT_REGISTRY.get(key, {}))


def list_active_environments() -> list[str]:
    """Return environment ids marked active."""
    return sorted(
        eid for eid, meta in EXECUTION_ENVIRONMENT_REGISTRY.items()
        if meta.get("status") == "active"
    )


def list_planned_environments() -> list[str]:
    """Return environment ids marked planned."""
    return sorted(
        eid for eid, meta in EXECUTION_ENVIRONMENT_REGISTRY.items()
        if meta.get("status") == "planned"
    )


def get_all_environment_definitions() -> list[dict[str, Any]]:
    """Return normalized list of all environment definitions for visibility."""
    result = []
    for eid in sorted(EXECUTION_ENVIRONMENT_REGISTRY.keys()):
        meta = EXECUTION_ENVIRONMENT_REGISTRY[eid]
        result.append({
            "environment_id": meta.get("environment_id", eid),
            "display_name": meta.get("display_name", eid),
            "status": meta.get("status"),
            "isolation_level": meta.get("isolation_level"),
            "mutation_posture": meta.get("mutation_posture"),
            "network_posture": meta.get("network_posture"),
            "human_review_required": meta.get("human_review_required"),
            "bounded_execution": meta.get("bounded_execution"),
            "notes": meta.get("notes", ""),
        })
    return result
```

---

### 1.2 NEXUS/execution_environment_summary.py (NEW FILE — FULL CODE)

```python
"""
NEXUS execution environment summary layer (Phase 17).

Builds deterministic summaries for dashboard, command surface, and per-project
visibility. Read-only; no execution capability.
"""

from __future__ import annotations

from typing import Any

from NEXUS.execution_environment_registry import (
    EXECUTION_ENVIRONMENT_REGISTRY,
    RUNTIME_TARGET_TO_ENVIRONMENT,
    get_all_environment_definitions,
    get_environment_definition,
    get_environment_for_runtime_target,
    list_active_environments,
    list_planned_environments,
)
from NEXUS.registry import PROJECTS
from NEXUS.runtime_target_registry import (
    RUNTIME_TARGET_REGISTRY,
    get_runtime_target_summary,
    list_active_runtime_targets,
)


def build_execution_environment_summary(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build execution environment summary for dashboard/visibility.

    Returns:
        execution_environment_status: str
        active_environments: list[str]
        planned_environments: list[str]
        runtime_target_mapping: list[dict]  # target -> env_id
        environments: list[dict]  # full definitions
        per_project_summaries: dict[str, dict]
        reason: str
    """
    rt = runtime_target_summary or get_runtime_target_summary()
    active_targets = rt.get("active_names") or list_active_runtime_targets()
    planned_targets = rt.get("planned_names") or []

    active_envs = list_active_environments()
    planned_envs = list_planned_environments()

    runtime_target_mapping = []
    for target_name in sorted(RUNTIME_TARGET_REGISTRY.keys()):
        env_id = get_environment_for_runtime_target(target_name)
        runtime_target_mapping.append({
            "runtime_target": target_name,
            "execution_environment_id": env_id,
        })

    if active_envs:
        status = "available"
        reason = f"Active execution environments: {active_envs}; planned: {planned_envs}."
    else:
        status = "error_fallback"
        reason = "No active execution environments in registry."

    per_project_summaries: dict[str, dict[str, Any]] = {}
    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        per_project_summaries[proj_key] = build_per_project_environment_summary(
            project_name=proj.get("name") or proj_key,
            project_path=proj.get("path"),
            active_runtime_target="local",
            runtime_target_summary=rt,
        )

    return {
        "execution_environment_status": status,
        "active_environments": active_envs,
        "planned_environments": planned_envs,
        "runtime_target_mapping": runtime_target_mapping,
        "environments": get_all_environment_definitions(),
        "per_project_summaries": per_project_summaries,
        "reason": reason,
    }


def build_execution_environment_summary_safe(
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_execution_environment_summary(
            runtime_target_summary=runtime_target_summary,
            **kwargs,
        )
    except Exception:
        return {
            "execution_environment_status": "error_fallback",
            "active_environments": [],
            "planned_environments": [],
            "runtime_target_mapping": [],
            "environments": [],
            "per_project_summaries": {},
            "reason": "Execution environment summary evaluation failed.",
        }


def build_per_project_environment_summary(
    project_name: str | None = None,
    project_path: str | None = None,
    active_runtime_target: str | None = None,
    *,
    runtime_target_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Deterministic per-project execution environment summary.

    Evaluates what execution environment posture the active project currently has.
    Does not change behavior; read-only visibility.

    Returns:
        project_name: str | None
        project_path: str | None
        active_runtime_target: str | None
        execution_environment_id: str | None
        environment_posture: dict | None  # full env definition
        is_isolated: bool  # True only if actually isolated (currently always False)
        is_planned_isolated: bool  # True if env is planned isolated/container/external
        reason: str
    """
    rt = runtime_target_summary or get_runtime_target_summary()
    env_id = get_environment_for_runtime_target(active_runtime_target)
    env_def = get_environment_definition(env_id) if env_id else None

    isolation_level = (env_def or {}).get("isolation_level") or "none"
    is_isolated = isolation_level in ("planned_isolated", "planned_container", "planned_external") and (
        (env_def or {}).get("status") == "active"
    )
    # Currently no active isolated envs, so is_isolated is always False.
    is_planned_isolated = isolation_level in (
        "planned_isolated",
        "planned_container",
        "planned_external",
    )

    reason = f"Project env: runtime_target={active_runtime_target}; env_id={env_id}; isolation={isolation_level}."

    return {
        "project_name": project_name,
        "project_path": project_path,
        "active_runtime_target": active_runtime_target,
        "execution_environment_id": env_id,
        "environment_posture": env_def,
        "is_isolated": is_isolated,
        "is_planned_isolated": is_planned_isolated,
        "reason": reason,
    }
```

---

### 1.3 NEXUS/registry_dashboard.py (MODIFIED — DIFF-STYLE)

**ADD** (after line 399, in the Forge OS try block):
```python
        from NEXUS.execution_environment_summary import build_execution_environment_summary_safe
```

**ADD** (after `runtime_infrastructure_summary = build_runtime_infrastructure_summary_safe()`):
```python
        execution_environment_summary = build_execution_environment_summary_safe(
            runtime_target_summary=get_runtime_target_summary(),
        )
```

**ADD** (in the except block, after `runtime_infrastructure_summary = {...}`):
```python
        execution_environment_summary = {
            "execution_environment_status": "error_fallback",
            "active_environments": [],
            "planned_environments": [],
            "runtime_target_mapping": [],
            "environments": [],
            "per_project_summaries": {},
            "reason": "Execution environment summary failed.",
        }
```

**ADD** (in the return dict, after `"runtime_infrastructure_summary": runtime_infrastructure_summary,`):
```python
        "execution_environment_summary": execution_environment_summary,
```

---

### 1.4 NEXUS/command_surface.py (MODIFIED — DIFF-STYLE)

**ADD** (in imports):
```python
from NEXUS.execution_environment_summary import build_per_project_environment_summary
```

**ADD** (in SUPPORTED_COMMANDS frozenset, after `"runtime_infrastructure",`):
```python
    "execution_environment",
```

**ADD** (new command handler, after `runtime_infrastructure` block, before `meta_engine_status`):
```python
    if cmd == "execution_environment":
        try:
            dashboard_summary = build_registry_dashboard_summary()
            fallback = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "reason": "Execution environment summary unavailable.",
            }
            payload = dashboard_summary.get("execution_environment_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(payload, dict) or not payload:
                payload = dict(fallback)
            else:
                payload = dict(payload)
            if path or proj_name:
                per_project = build_per_project_environment_summary(
                    project_name=proj_name,
                    project_path=path,
                    active_runtime_target="local",
                )
                payload["per_project_environment_summary"] = per_project
            summary_line = (
                f"execution_environment_status={payload.get('execution_environment_status')}; "
                f"active={len(payload.get('active_environments') or [])}; "
                f"planned={len(payload.get('planned_environments') or [])}"
            )
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(
                command=cmd,
                status="error",
                project_name=None,
                summary=str(e),
                payload={
                    "execution_environment_status": "error_fallback",
                    "active_environments": [],
                    "planned_environments": [],
                    "runtime_target_mapping": [],
                    "environments": [],
                    "reason": "Execution environment summary failed.",
                    "error": str(e),
                },
            )
```

**ADD** (in forge_os_snapshot try block, after fallback_runtime):
```python
            fallback_exec_env = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "reason": "Execution environment summary unavailable.",
            }
```

**ADD** (after runtime_infrastructure_summary assignment):
```python
            execution_environment_summary = dashboard_summary.get("execution_environment_summary") if isinstance(dashboard_summary, dict) else None
            if not isinstance(execution_environment_summary, dict) or not execution_environment_summary:
                execution_environment_summary = fallback_exec_env
```

**ADD** (in forge_os_snapshot payload dict):
```python
                "execution_environment_summary": execution_environment_summary,
```

**ADD** (in forge_os_snapshot summary_line):
```python
                f"exec_env_status={payload.get('execution_environment_summary', {}).get('execution_environment_status')}; "
```

**ADD** (in forge_os_snapshot except block payload):
```python
            fallback_exec_env = {
                "execution_environment_status": "error_fallback",
                "active_environments": [],
                "planned_environments": [],
                "runtime_target_mapping": [],
                "environments": [],
                "reason": "Execution environment summary unavailable.",
            }
            ...
                "execution_environment_summary": fallback_exec_env,
```

---

## 2. BACKWARD COMPATIBILITY CHECK

### NEXUS/registry_dashboard.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `build_registry_dashboard_summary()` is called by: command_surface (dashboard_summary, forge_os_snapshot, meta_engine_status, etc.), operator_agent, meta_engines, elite_layers |
| **Why no break** | Return dict is extended with one new key `execution_environment_summary`. All existing keys unchanged. |
| **Unchanged output fields** | `summary_generated_at`, `studio_name`, `project_summary`, `agent_summary`, `policy_summary`, `tool_summary`, `engine_summary`, `capability_summary`, `runtime_target_summary`, `runtime_infrastructure_summary`, `portfolio_summary`, `meta_engine_summary`, and all other ~60+ keys remain identical in shape and position. |
| **Additive only** | `execution_environment_summary` is a new top-level key. Callers that iterate or index by known keys are unaffected. Callers that do `d.get("execution_environment_summary")` receive the new summary or `None` if they don't handle it. |

### NEXUS/command_surface.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `run_command(cmd, ...)` is called by operator console, CLI, automation. All existing commands unchanged. |
| **Why no break** | New command `execution_environment` is additive. Command routing is `if cmd == "X"`; new branch does not alter existing branches. |
| **Unchanged output fields** | `_result()` shape unchanged: `command`, `status`, `project_name`, `summary`, `payload`. Each existing command's payload shape unchanged. |
| **Additive only** | New command returns its own payload shape. `forge_os_snapshot` payload gains one new key `execution_environment_summary`; all prior keys (`portfolio_summary`, `runtime_infrastructure_summary`, `meta_engine_summary`, `studio_coordination_summary`, `studio_driver_summary`, `dashboard_summary`) unchanged. |

---

## 3. COMMAND SURFACE CHECK

| Check | Result |
|-------|--------|
| **`execution_environment` in SUPPORTED_COMMANDS** | Yes. `SUPPORTED_COMMANDS` frozenset includes `"execution_environment"` (line 68). |
| **New command does not break routing** | Yes. Routing is sequential `if cmd == "X"`. `execution_environment` is a new branch between `runtime_infrastructure` and `meta_engine_status`. No existing branch modified. |
| **`forge_os_snapshot` previous keys preserved** | Yes. Payload still has: `portfolio_summary`, `runtime_infrastructure_summary`, `meta_engine_summary`, `studio_coordination_summary`, `studio_driver_summary`, `dashboard_summary`. |
| **New payload field additive only** | Yes. `execution_environment_summary` is an additional key. `dashboard_summary` (nested) also gains `execution_environment_summary` from the dashboard; that is additive within the nested dict. |

---

## 4. PERMISSION DRIFT CHECK

| Check | Result |
|-------|--------|
| **No runtime target gains new execution permissions** | Confirmed. `NEXUS/runtime_target_registry.py` unchanged. `RUNTIME_TARGET_REGISTRY` and `get_target_capabilities` unchanged. Execution environment registry is read-only metadata; it does not grant or revoke permissions. |
| **No planned environment treated as active isolation** | Confirmed. `is_isolated` in `build_per_project_environment_summary` is True only when `isolation_level in ("planned_isolated", "planned_container", "planned_external")` AND `status == "active"`. All planned envs have `status == "planned"`, so `is_isolated` is always False. |
| **No AEGIS behavior changed** | Confirmed. No edits to `AEGIS/` modules. `environment_controller` (local_dev/staging/production) unchanged. `policy_engine`, `aegis_core`, `approval_gateway` unchanged. |
| **No dispatch/runtime behavior changed** | Confirmed. `runtime_dispatcher.py`, `runtime_target_selector.py`, `execution_bridge` unchanged. Execution environment layer is metadata/summary only; no dispatch or execution paths modified. |

---

## 5. VALIDATION

### 5.1 Environment registry summary

**Command:**
```powershell
cd C:\FORGE
python -c "from NEXUS.execution_environment_registry import list_active_environments, list_planned_environments, get_environment_for_runtime_target; print('active:', list_active_environments()); print('planned:', list_planned_environments()); print('local->', get_environment_for_runtime_target('local')); print('container_worker->', get_environment_for_runtime_target('container_worker'))"
```

**Expected output:**
```
active: ['local_bounded', 'local_current']
planned: ['container_planned', 'external_runtime_planned', 'isolated_planned']
local-> local_current
container_worker-> container_planned
```

---

### 5.2 Per-project environment summary

**Command:**
```powershell
cd C:\FORGE
python -c "
from NEXUS.execution_environment_summary import build_per_project_environment_summary
r = build_per_project_environment_summary(project_name='jarvis', project_path='C:/FORGE/projects/jarvis', active_runtime_target='local')
print('env_id:', r['execution_environment_id'])
print('is_isolated:', r['is_isolated'])
print('is_planned_isolated:', r['is_planned_isolated'])
assert r['execution_environment_id'] == 'local_current'
assert r['is_isolated'] is False
assert r['is_planned_isolated'] is False
print('OK')
"
```

**Expected output:**
```
env_id: local_current
is_isolated: False
is_planned_isolated: False
OK
```

---

### 5.3 Dashboard integration

**Command:**
```powershell
cd C:\FORGE
python -c "
from NEXUS.registry_dashboard import build_registry_dashboard_summary
d = build_registry_dashboard_summary()
ee = d.get('execution_environment_summary')
assert ee is not None
assert ee.get('execution_environment_status') == 'available'
assert 'active_environments' in ee
assert 'planned_environments' in ee
assert 'runtime_target_mapping' in ee
assert 'per_project_summaries' in ee
assert len(ee.get('per_project_summaries', {})) >= 1
print('execution_environment_status:', ee['execution_environment_status'])
print('per_project keys:', list(ee['per_project_summaries'].keys())[:3])
print('OK')
"
```

**Expected output:**
```
execution_environment_status: available
per_project keys: ['epoch', 'game_dev', 'genesis'] (or similar)
OK
```

---

### 5.4 Command surface integration

**Command (execution_environment):**
```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('execution_environment')
assert r['status'] == 'ok'
assert r['command'] == 'execution_environment'
p = r['payload']
assert p.get('execution_environment_status') == 'available'
assert len(p.get('active_environments', [])) == 2
assert len(p.get('planned_environments', [])) == 3
assert len(p.get('runtime_target_mapping', [])) == 6
print('status:', r['status'])
print('summary:', r['summary'])
print('OK')
"
```

**Expected output:**
```
status: ok
summary: execution_environment_status=available; active=2; planned=3
OK
```

**Command (execution_environment with project):**
```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('execution_environment', project_name='jarvis')
assert r['status'] == 'ok'
assert 'per_project_environment_summary' in r['payload']
pp = r['payload']['per_project_environment_summary']
assert pp.get('execution_environment_id') == 'local_current'
assert pp.get('is_isolated') is False
print('OK')
"
```

**Expected output:** `OK`

**Command (forge_os_snapshot):**
```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('forge_os_snapshot')
assert r['status'] == 'ok'
p = r['payload']
assert 'portfolio_summary' in p
assert 'runtime_infrastructure_summary' in p
assert 'execution_environment_summary' in p
assert 'meta_engine_summary' in p
assert 'dashboard_summary' in p
print('keys:', sorted(p.keys()))
print('OK')
"
```

**Expected output:**
```
keys: ['dashboard_summary', 'execution_environment_summary', 'meta_engine_summary', 'portfolio_summary', 'runtime_infrastructure_summary', 'studio_coordination_summary', 'studio_driver_summary']
OK
```

---

## 6. FINAL ASSESSMENT

**Phase 17 is safely acceptable as implemented.**

- All new code is additive and read-only.
- No runtime targets, AEGIS, or dispatch logic was changed.
- Backward compatibility is preserved for dashboard and command surface.
- Planned environments are never treated as active isolation.
- Validation commands above provide deterministic checks.

**Optional minor improvement (non-blocking):** The `execution_environment` command fallback dict could include `per_project_summaries: {}` for consistency with the dashboard error fallback. Callers using `.get("per_project_summaries", {})` are already safe; this would only align the fallback shape.
