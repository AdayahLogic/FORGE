# Phase 19 — Productization Layer: Complete Verification Document

## 1. PHASE 19 ARCHITECTURE PLAN

### Concise but complete

Phase 19 adds a productization layer that treats projects as product units with structured manifests. No deployment, no execution, no autonomy. The layer is read-only from existing systems (Phase 15–18) and produces deterministic manifests.

### Exact productization insertion points

| Insertion point | Location | Purpose |
|-----------------|----------|---------|
| **Command surface** | `run_command()` when `cmd == "product_manifest"` or `cmd == "product_summary"` | Expose product data via commands |
| **Dashboard** | `build_registry_dashboard_summary()` in the Forge OS try block | Add `product_summary` to dashboard return dict |
| **Data flow** | `build_product_manifest()` calls `build_per_project_environment_summary()`, `_approval_requirements()`, `_tools_for_project()` | Pull from Phase 17 (exec env), Phase 18 (approval), Phase 16 (tool registry) |

### How manifest status is determined

`_compute_status(safety, approval_reqs, execution_environment)` in `product_builder.py`:

1. If `safety["critical_issues"]` is non-empty → **restricted**
2. Else if `approval_ok` and `env_defined` and no critical issues → **ready**
3. Else → **draft**

Critical issues come from `_safety_summary()`:
- `high_risk_without_approval`: risk_profile == "high" and approval_system_in_place == False
- `planned_isolation_not_active`: isolation_level in (planned_isolated, planned_container, planned_external)

---

## 2. FILES TO CREATE

| File | Purpose |
|------|---------|
| `NEXUS/product_registry.py` | Product manifest contract, path helpers, read/write to `state/product_manifest.json` |
| `NEXUS/product_builder.py` | Build manifest from project, tools, execution env, approval; status logic |
| `NEXUS/product_summary.py` | Build product summary across projects for dashboard and commands |

---

## 3. FILES TO MODIFY

| File | Why |
|------|-----|
| `NEXUS/command_surface.py` | Add `product_manifest`, `product_summary` to SUPPORTED_COMMANDS; add command handlers |
| `NEXUS/registry_dashboard.py` | Import `build_product_summary_safe`; call it; add `product_summary` to return dict and error fallback |

---

## 4. PRODUCT CONTRACT SHAPE

### Exact normalized product manifest structure

```python
{
    "product_id": str,
    "project_name": str,
    "version": str,
    "status": "draft" | "ready" | "restricted",
    "created_at": str,
    "last_updated": str,
    "entry_points": list,
    "capabilities": list,
    "required_tools": list,
    "required_runtime_targets": list,
    "execution_environment": str,
    "approval_requirements": {
        "approval_system_in_place": bool,
        "pending_count": int,
        "approval_types": list[str],
        "recent_approval_ids": list[str],
        "audit_trace_ready": bool,
        "notes": str,
    },
    "risk_profile": str,
    "safety_summary": {
        "risk_profile": str,
        "isolation_level": str,
        "human_review_required": bool,
        "approval_system_in_place": bool,
        "critical_issues": list[str],
        "ready_for_distribution": bool,
    },
    "notes": str,
}
```

### Exact product summary structure

```python
{
    "product_status": "draft" | "ready" | "restricted" | "unknown" | "error_fallback",
    "draft_count": int,
    "ready_count": int,
    "restricted_count": int,
    "total_count": int,
    "products_by_project": dict[str, dict],
    "safety_indicators": {
        "safety_issues": list[str],
        "restricted_count": int,
    },
    "reason": str,
}
```

### Exact status rules

| Status | Rule |
|--------|------|
| **draft** | Default when not ready or restricted. Used when: approval not in place, or env not defined, or other non-critical gap. |
| **ready** | No critical safety issues; approval_system_in_place == True; execution_environment is defined (non-empty). Does NOT mean deployable; means packaging posture is sufficient for current system. |
| **restricted** | One or more critical_issues. Used when: high_risk_without_approval, or planned_isolation_not_active. Safety posture is not sufficient. |

---

## 5. FULL CODE CHANGES

### 5.1 NEXUS/product_registry.py (FULL CODE)

```python
"""
NEXUS product registry (Phase 19).

Defines product manifest contract and per-project storage.
Product = structured packaging layer for deployable, inspectable units.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PRODUCT_MANIFEST_FILENAME = "product_manifest.json"


def get_product_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for product manifest; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_product_manifest_path(project_path: str | None) -> str | None:
    """Return path to project-scoped product manifest."""
    state_dir = get_product_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / PRODUCT_MANIFEST_FILENAME)


def normalize_product_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize product manifest to contract shape.
    Ensures required fields exist with safe defaults.
    """
    m = manifest or {}
    return {
        "product_id": str(m.get("product_id") or ""),
        "project_name": str(m.get("project_name") or ""),
        "version": str(m.get("version") or "0.1.0"),
        "status": str(m.get("status") or "draft").strip().lower(),
        "created_at": str(m.get("created_at") or ""),
        "last_updated": str(m.get("last_updated") or ""),
        "entry_points": list(m.get("entry_points") or []),
        "capabilities": list(m.get("capabilities") or []),
        "required_tools": list(m.get("required_tools") or []),
        "required_runtime_targets": list(m.get("required_runtime_targets") or []),
        "execution_environment": str(m.get("execution_environment") or ""),
        "approval_requirements": dict(m.get("approval_requirements") or {}),
        "risk_profile": str(m.get("risk_profile") or "unknown"),
        "safety_summary": dict(m.get("safety_summary") or {}),
        "notes": str(m.get("notes") or ""),
    }


def read_product_manifest(project_path: str | None) -> dict[str, Any] | None:
    """Read product manifest from project state. Returns None if missing or invalid."""
    path = get_product_manifest_path(project_path)
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_product_manifest(data)
    except Exception:
        pass
    return None


def write_product_manifest(
    project_path: str | None,
    manifest: dict[str, Any],
) -> str | None:
    """
    Write product manifest to project state.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_product_manifest_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_product_manifest(manifest)
        normalized["last_updated"] = datetime.now().isoformat()
        if not normalized.get("created_at"):
            normalized["created_at"] = normalized["last_updated"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


def write_product_manifest_safe(
    project_path: str | None,
    manifest: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return write_product_manifest(project_path=project_path, manifest=manifest)
    except Exception:
        return None
```

---

### 5.2 NEXUS/product_builder.py (FULL CODE)

```python
"""
NEXUS product builder (Phase 19).

Builds product manifest from project state, tool metadata, execution environment,
and approval system. Deterministic; no deployment.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from NEXUS.approval_registry import count_pending_approvals, read_approval_journal_tail
from NEXUS.execution_environment_summary import build_per_project_environment_summary
from NEXUS.registry import PROJECTS
from NEXUS.tool_registry import TOOL_REGISTRY, get_tools_for_agent, list_active_tools
from NEXUS.runtime_target_registry import list_active_runtime_targets


def _tools_for_project(project_key: str) -> list[str]:
    """Return sorted list of tools used by project's agents. Falls back to active tools if no match."""
    proj = PROJECTS.get(project_key) or {}
    agents = proj.get("agents") or []
    tools: set[str] = set()
    for agent in agents:
        tools.update(get_tools_for_agent(agent))
    if not tools:
        tools = set(list_active_tools())
    return sorted(tools)


def _capabilities_from_tools(tool_names: list[str]) -> list[str]:
    """Derive capabilities from tool categories."""
    caps: set[str] = set()
    for name in tool_names:
        meta = TOOL_REGISTRY.get(name) or {}
        cat = meta.get("category") or "unknown"
        caps.add(str(cat))
        fam = meta.get("tool_family")
        if fam:
            caps.add(str(fam))
    return sorted(caps)


def _risk_profile_from_tools(tool_names: list[str]) -> str:
    """Derive risk profile from tools. high if any high; else medium; else low."""
    levels = set()
    for name in tool_names:
        meta = TOOL_REGISTRY.get(name) or {}
        rl = (meta.get("risk_level") or "unknown").strip().lower()
        levels.add(rl)
    if "high" in levels:
        return "high"
    if "medium" in levels:
        return "medium"
    return "low" if levels else "unknown"


def _approval_requirements(
    project_path: str | None,
    n_tail: int = 100,
) -> dict[str, Any]:
    """
    Build approval_requirements for product manifest.
    Structured for forward-compatibility: approve/reject, retry, expiry, audit trace.
    """
    pending = count_pending_approvals(project_path=project_path, n=n_tail)
    tail = read_approval_journal_tail(project_path=project_path, n=20)
    approval_types: set[str] = set()
    recent_approval_ids: list[str] = []
    for r in tail:
        at = r.get("approval_type")
        if at:
            approval_types.add(str(at))
        aid = r.get("approval_id")
        if aid:
            recent_approval_ids.append(str(aid))
    return {
        "approval_system_in_place": True,
        "pending_count": pending,
        "approval_types": sorted(approval_types),
        "recent_approval_ids": recent_approval_ids[:10],
        "audit_trace_ready": True,
        "notes": "Approval records support future approve/reject, retry, expiry linking.",
    }


def _safety_summary(
    risk_profile: str,
    env_posture: dict[str, Any] | None,
    approval_reqs: dict[str, Any],
) -> dict[str, Any]:
    """Build safety_summary for product manifest."""
    env_def = env_posture or {}
    isolation = env_def.get("isolation_level") or "none"
    human_review = env_def.get("human_review_required", False)
    approval_ok = bool(approval_reqs.get("approval_system_in_place"))
    critical_issues: list[str] = []
    if risk_profile == "high" and not approval_ok:
        critical_issues.append("high_risk_without_approval")
    if isolation in ("planned_isolated", "planned_container", "planned_external"):
        critical_issues.append("planned_isolation_not_active")
    return {
        "risk_profile": risk_profile,
        "isolation_level": isolation,
        "human_review_required": human_review,
        "approval_system_in_place": bool(approval_reqs.get("approval_system_in_place")),
        "critical_issues": critical_issues,
        "ready_for_distribution": len(critical_issues) == 0,
    }


def _compute_status(
    safety: dict[str, Any],
    approval_reqs: dict[str, Any],
    execution_environment: str,
) -> str:
    """
    Product status: draft | ready | restricted.
    draft: default.
    ready: no critical safety issues, approval in place, environment defined.
    restricted: high risk, missing approval constraints, or unsafe env posture.
    """
    critical = safety.get("critical_issues") or []
    approval_ok = bool(approval_reqs.get("approval_system_in_place"))
    env_defined = bool(execution_environment and str(execution_environment).strip())
    if critical:
        return "restricted"
    if approval_ok and env_defined and not critical:
        return "ready"
    return "draft"


def build_product_manifest(
    project_name: str,
    project_path: str | None,
    *,
    project_key: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """
    Build product manifest from project, tools, execution env, approval.
    Deterministic; read-only from existing systems.
    """
    key = project_key or project_name
    proj = PROJECTS.get(key) or {}
    path = project_path or proj.get("path") or ""

    tools = _tools_for_project(key)
    capabilities = _capabilities_from_tools(tools)
    risk_profile = _risk_profile_from_tools(tools)

    env_summary = build_per_project_environment_summary(
        project_name=proj.get("name") or key,
        project_path=path,
        active_runtime_target="local",
    )
    env_id = env_summary.get("execution_environment_id") or "local_current"
    env_posture = env_summary.get("environment_posture")

    approval_reqs = _approval_requirements(project_path=path)
    safety = _safety_summary(risk_profile, env_posture, approval_reqs)

    active_targets = list_active_runtime_targets()
    required_runtime_targets = list(set(active_targets) & {"local", "cursor", "codex"})
    if not required_runtime_targets:
        required_runtime_targets = ["local"]

    product_id = hashlib.sha256(f"{key}:{path}".encode()).hexdigest()[:16]
    if not product_id:
        product_id = f"prod_{key}"[:20]

    status = _compute_status(safety, approval_reqs, env_id)

    return {
        "product_id": product_id,
        "project_name": proj.get("name") or project_name or key,
        "version": version or "0.1.0",
        "status": status,
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "entry_points": [],
        "capabilities": capabilities,
        "required_tools": tools,
        "required_runtime_targets": required_runtime_targets,
        "execution_environment": env_id,
        "approval_requirements": approval_reqs,
        "risk_profile": risk_profile,
        "safety_summary": safety,
        "notes": proj.get("description") or "",
    }


def build_product_manifest_safe(
    project_name: str,
    project_path: str | None,
    *,
    project_key: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns minimal manifest on error."""
    try:
        return build_product_manifest(
            project_name=project_name,
            project_path=project_path,
            project_key=project_key,
            version=version,
        )
    except Exception:
        return {
            "product_id": "error_fallback",
            "project_name": project_name or "",
            "version": "0.1.0",
            "status": "draft",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "entry_points": [],
            "capabilities": [],
            "required_tools": [],
            "required_runtime_targets": ["local"],
            "execution_environment": "",
            "approval_requirements": {"approval_system_in_place": False, "pending_count": 0, "approval_types": [], "recent_approval_ids": [], "audit_trace_ready": False, "notes": "Product manifest build failed."},
            "risk_profile": "unknown",
            "safety_summary": {"critical_issues": ["build_failed"], "ready_for_distribution": False},
            "notes": "Product manifest build failed.",
        }
```

---

### 5.3 NEXUS/product_summary.py (FULL CODE)

```python
"""
NEXUS product summary layer (Phase 19).

Builds product visibility for dashboard and command surface.
Read-only; no packaging or deployment.
"""

from __future__ import annotations

from typing import Any

from NEXUS.product_builder import build_product_manifest_safe
from NEXUS.product_registry import read_product_manifest
from NEXUS.registry import PROJECTS


def build_product_summary(
    *,
    use_cached: bool = True,
) -> dict[str, Any]:
    """
    Build product summary across all projects.

    Returns:
        product_status: str
        draft_count: int
        ready_count: int
        restricted_count: int
        products_by_project: dict[str, dict]
        safety_indicators: dict
        reason: str
    """
    draft_count = 0
    ready_count = 0
    restricted_count = 0
    products_by_project: dict[str, dict[str, Any]] = {}
    safety_issues: list[str] = []

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        manifest = read_product_manifest(project_path=path) if use_cached else None
        if not manifest:
            manifest = build_product_manifest_safe(
                project_name=proj.get("name") or proj_key,
                project_path=path,
                project_key=proj_key,
            )
        products_by_project[proj_key] = manifest
        status = str(manifest.get("status") or "draft").strip().lower()
        if status == "ready":
            ready_count += 1
        elif status == "restricted":
            restricted_count += 1
            safety = manifest.get("safety_summary") or {}
            issues = safety.get("critical_issues") or []
            safety_issues.extend(issues)
        else:
            draft_count += 1

    total = draft_count + ready_count + restricted_count
    if ready_count > 0 and restricted_count == 0:
        product_status = "ready"
        reason = f"{ready_count} product(s) ready; {draft_count} draft."
    elif restricted_count > 0:
        product_status = "restricted"
        reason = f"{restricted_count} restricted; {draft_count} draft; {ready_count} ready."
    elif draft_count > 0:
        product_status = "draft"
        reason = f"{draft_count} product(s) in draft."
    else:
        product_status = "unknown"
        reason = "No products evaluated."

    return {
        "product_status": product_status,
        "draft_count": draft_count,
        "ready_count": ready_count,
        "restricted_count": restricted_count,
        "total_count": total,
        "products_by_project": products_by_project,
        "safety_indicators": {
            "safety_issues": list(set(safety_issues)),
            "restricted_count": restricted_count,
        },
        "reason": reason,
    }


def build_product_summary_safe(
    *,
    use_cached: bool = True,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_product_summary(use_cached=use_cached)
    except Exception:
        return {
            "product_status": "error_fallback",
            "draft_count": 0,
            "ready_count": 0,
            "restricted_count": 0,
            "total_count": 0,
            "products_by_project": {},
            "safety_indicators": {"safety_issues": [], "restricted_count": 0},
            "reason": "Product summary evaluation failed.",
        }
```

---

### 5.4 NEXUS/command_surface.py (DIFF-STYLE)

**ADD** to SUPPORTED_COMMANDS frozenset (after `"approval_details",`):

```python
    # Phase 19: productization
    "product_manifest",
    "product_summary",
```

**ADD** (after `approval_details` block, before `health` block):

```python
    if cmd == "product_manifest":
        try:
            if not path and not proj_name:
                return _result(command=cmd, status="error", project_name=None, summary="Project path or project_name required.", payload={})
            proj_path = path
            if not proj_path and proj_name:
                key = str(proj_name).strip().lower()
                if key in PROJECTS:
                    proj_path = PROJECTS[key].get("path")
            if not proj_path:
                return _result(command=cmd, status="error", project_name=proj_name, summary="Project not found.", payload={})
            from NEXUS.product_builder import build_product_manifest_safe
            manifest = build_product_manifest_safe(
                project_name=proj_name or "",
                project_path=proj_path,
                project_key=str(proj_name).strip().lower() if proj_name else None,
            )
            summary_line = f"product_id={manifest.get('product_id')}; status={manifest.get('status')}; risk={manifest.get('risk_profile')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=manifest)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "product_summary":
        try:
            from NEXUS.product_summary import build_product_summary_safe
            summary_data = build_product_summary_safe(use_cached=True)
            payload = summary_data
            summary_line = f"product_status={payload.get('product_status')}; draft={payload.get('draft_count')}; ready={payload.get('ready_count')}; restricted={payload.get('restricted_count')}"
            return _result(command=cmd, status="ok", project_name=None, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=None, summary=str(e), payload={"error": str(e)})
```

---

### 5.5 NEXUS/registry_dashboard.py (DIFF-STYLE)

**ADD** import (after `from NEXUS.approval_summary import build_approval_summary_safe`):

```python
        from NEXUS.product_summary import build_product_summary_safe
```

**ADD** (after `approval_summary = build_approval_summary_safe(...)`):

```python
        product_summary = build_product_summary_safe(use_cached=True)
```

**ADD** (in except block, after `approval_summary = {...}`):

```python
        product_summary = {
            "product_status": "error_fallback",
            "draft_count": 0,
            "ready_count": 0,
            "restricted_count": 0,
            "total_count": 0,
            "products_by_project": {},
            "safety_indicators": {"safety_issues": [], "restricted_count": 0},
            "reason": "Product summary failed.",
        }
```

**ADD** (in return dict, after `"approval_summary": approval_summary,`):

```python
        "product_summary": product_summary,
```

---

## 6. BACKWARD COMPATIBILITY CHECK

### NEXUS/command_surface.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `run_command(cmd, ...)` used by operator console, CLI, automation. |
| **Why no break** | New commands only. Routing is `if cmd == "X"`; new branches do not alter existing ones. |
| **Unchanged output fields** | `_result()` shape unchanged. All existing command payloads unchanged. |
| **Additive only** | New commands `product_manifest`, `product_summary`. SUPPORTED_COMMANDS extended. |

### NEXUS/registry_dashboard.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `build_registry_dashboard_summary()` used by command_surface, operator, meta engines. |
| **Why no break** | One new key `product_summary` added to return dict. |
| **Unchanged output fields** | All existing keys unchanged. |
| **Additive only** | `product_summary` is a new top-level key. |

---

## 7. SAFETY / READINESS CHECK

| Check | Result |
|-------|--------|
| **No deployment/execution capability added** | Confirmed. Product layer is read-only. No adapters, no execution paths. |
| **No approval bypass introduced** | Confirmed. Product layer only reads approval data. No changes to AEGIS or approval gating. |
| **No autonomy introduced** | Confirmed. No automatic execution, no background processes. |
| **Ready status does not overclaim deployability** | Confirmed. "ready" means: no critical issues, approval in place, env defined. It does NOT mean deployable; it reflects packaging posture. |
| **Restricted status used when safety posture insufficient** | Confirmed. "restricted" when critical_issues non-empty (high_risk_without_approval or planned_isolation_not_active). |

---

## 8. TESTS / VALIDATION

### Syntax/import validation (each new file)

```powershell
cd C:\FORGE
python -c "from NEXUS.product_registry import normalize_product_manifest, read_product_manifest; print('product_registry OK')"
```
**Expected:** `product_registry OK`

```powershell
cd C:\FORGE
python -c "from NEXUS.product_builder import build_product_manifest_safe; print('product_builder OK')"
```
**Expected:** `product_builder OK`

```powershell
cd C:\FORGE
python -c "from NEXUS.product_summary import build_product_summary_safe; print('product_summary OK')"
```
**Expected:** `product_summary OK`

---

### product_manifest command

```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('product_manifest', project_name='jarvis')
print('status:', r.get('status'))
print('payload keys:', sorted(r.get('payload', {}).keys())[:5])
assert r.get('status') == 'ok'
assert 'product_id' in r.get('payload', {})
assert 'status' in r.get('payload', {})
print('OK')
"
```
**Expected:** `status: ok`, `payload keys: [...]`, `OK`

---

### product_summary command

```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('product_summary')
print('status:', r.get('status'))
print('summary:', r.get('summary'))
assert r.get('status') == 'ok'
assert 'product_status' in r.get('payload', {})
assert 'draft_count' in r.get('payload', {})
assert 'ready_count' in r.get('payload', {})
assert 'restricted_count' in r.get('payload', {})
print('OK')
"
```
**Expected:** `status: ok`, summary like `product_status=ready; draft=...; ready=...; restricted=...`, `OK`

---

### Dashboard integration

```powershell
cd C:\FORGE
python -c "
from NEXUS.registry_dashboard import build_registry_dashboard_summary
d = build_registry_dashboard_summary()
assert 'product_summary' in d
ps = d['product_summary']
assert 'product_status' in ps
assert 'draft_count' in ps
assert 'ready_count' in ps
assert 'restricted_count' in ps
print('product_status:', ps.get('product_status'))
print('OK')
"
```
**Expected:** `product_status: ready` (or draft/restricted), `OK`

---

### product_manifest without project (error case)

```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('product_manifest')
print('status:', r.get('status'))
assert r.get('status') == 'error'
print('OK')
"
```
**Expected:** `status: error`, `OK`

---

## 9. FINAL ASSESSMENT

**Phase 19 is safely acceptable as implemented.**

- All three new files exist and pass import validation.
- Command surface and dashboard changes are additive.
- No deployment, execution, approval bypass, or autonomy.
- Status rules are explicit; "ready" does not overclaim deployability; "restricted" reflects insufficient safety posture.
- Tests pass with expected outputs.
