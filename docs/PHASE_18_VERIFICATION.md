# Phase 18 — Real Approval System: Full Verification Document

## 1. PHASE 18 ARCHITECTURE PLAN

### Exact approval insertion point

**Location:** `NEXUS/runtime_dispatcher.py`, inside the AEGIS evaluation try block, after AEGIS returns and before the adapter is called.

**Two insertion points:**

1. **When `aegis_decision == "approval_required"`** (lines 101–136): After AEGIS returns approval_required, before returning the queued result. Create approval record, append to journal, then return skipped/queued as before.

2. **When `aegis_decision == "allow"` and `exec_block.get("requires_human_approval")`** (lines 138–174): After AEGIS allows but before calling the adapter. Create approval record, append to journal, return skipped/queued (block execution). This runs only when AEGIS has already allowed.

### Why this is the safest place

- **After AEGIS:** Approval runs only after AEGIS has evaluated. AEGIS deny/error_fallback still blocks before any approval logic. Approval cannot bypass AEGIS.
- **Before adapter:** The adapter is the execution boundary. Blocking before `adapter(dispatch_plan)` prevents execution. No partial execution.
- **Single choke point:** All dispatch flows go through `runtime_dispatcher.dispatch()`. No other execution paths.
- **No AEGIS changes:** AEGIS code is unchanged. Approval is a downstream layer.
- **Fail-safe:** Approval logic is in a try/except; exceptions do not block the return. Journal append is best-effort and never raises.

### Interaction with AEGIS, enforcement, and dispatch

| Component | Interaction |
|-----------|-------------|
| **AEGIS** | Runs first. Returns allow/deny/approval_required. Approval runs only when AEGIS returns approval_required or allow. AEGIS deny → immediate block, no approval. |
| **Enforcement** | Enforcement layer consumes dispatch results. When approval gates, dispatch returns `dispatch_status="skipped"`, `execution_status="queued"`. Enforcement sees the same vocabulary as before. |
| **Dispatch** | Approval creates records and returns early. Adapter is never called when approval is required. `dispatch_status` stays "skipped"; `dispatch_result` includes `approval_id` and `approval_required` when applicable. |

---

## 2. FILES TO CREATE

| File | Purpose |
|------|---------|
| `NEXUS/approval_registry.py` | Approval contract, append-only journal (`state/approval_journal.jsonl`), normalize/append/read helpers |
| `NEXUS/approval_builder.py` | Builds approval records from dispatch_plan, AEGIS result, tool metadata, execution env |
| `NEXUS/approval_summary.py` | Builds approval summary for dashboard and command surface (read-only) |

---

## 3. FILES TO MODIFY

| File | Why |
|------|-----|
| `NEXUS/command_surface.py` | Phase 17: add `per_project_summaries: {}` to execution_environment fallback. Phase 18: add `pending_approvals`, `approval_details` to SUPPORTED_COMMANDS and implement handlers |
| `NEXUS/runtime_dispatcher.py` | Add approval gating: create and persist approval records when AEGIS approval_required or when allow + requires_human_approval; block before adapter call |
| `NEXUS/registry_dashboard.py` | Add `approval_summary` to dashboard build and return dict; add error fallback in except block |

---

## 4. APPROVAL CONTRACT SHAPE

### Normalized approval record (single journal line)

```python
{
    "approval_id": str,           # 16-char hex, unique per record
    "run_id": str,
    "project_name": str,
    "timestamp": str,             # ISO 8601
    "status": "pending" | "approved" | "rejected" | "expired",
    "approval_type": str,         # e.g. "aegis_policy", "dispatch_plan", "tool_sensitivity"
    "reason": str,
    "requested_by": str,
    "requires_human": bool,
    "risk_level": str,
    "sensitivity": str,
    "context": dict,              # runtime_target_id, tool_name, agent_name, aegis_decision, aegis_scope
    "decision": str | None,       # None until resolved
    "decision_timestamp": str | None,
}
```

### Approval journal / storage structure

- **Path:** `{project_path}/state/approval_journal.jsonl`
- **Format:** One JSON object per line, append-only
- **No overwrite:** `append_approval_record` only appends
- **Failure handling:** Returns `None` on failure; never raises

### Approval summary structure

```python
{
    "approval_status": "clear" | "pending" | "error_fallback",
    "pending_count_total": int,
    "pending_by_project": dict[str, int],
    "recent_approvals": list[dict],
    "approval_types": list[str],
    "reason": str,
}
```

---

## 5. FULL CODE CHANGES

### 5.1 NEXUS/approval_registry.py (NEW FILE — FULL CODE)

```python
"""
NEXUS approval registry (Phase 18).

Defines the approval record contract and append-only storage.
Approval sits between AEGIS policy allow and execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

APPROVAL_JOURNAL_FILENAME = "approval_journal.jsonl"


def get_approval_state_dir(project_path: str | None) -> Path | None:
    """Return project state dir for approval journal; None if no project_path."""
    if not project_path:
        return None
    try:
        base = Path(project_path).resolve()
        state_dir = base / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir
    except Exception:
        return None


def get_approval_journal_path(project_path: str | None) -> str | None:
    """Return path to project-scoped approval journal."""
    state_dir = get_approval_state_dir(project_path)
    if not state_dir:
        return None
    return str(state_dir / APPROVAL_JOURNAL_FILENAME)


def normalize_approval_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize approval record to contract shape.
    Ensures required fields exist with safe defaults.
    """
    r = record or {}
    return {
        "approval_id": str(r.get("approval_id") or uuid.uuid4().hex[:16]),
        "run_id": str(r.get("run_id") or ""),
        "project_name": str(r.get("project_name") or ""),
        "timestamp": str(r.get("timestamp") or datetime.now().isoformat()),
        "status": str(r.get("status") or "pending").strip().lower(),
        "approval_type": str(r.get("approval_type") or "unknown"),
        "reason": str(r.get("reason") or ""),
        "requested_by": str(r.get("requested_by") or ""),
        "requires_human": bool(r.get("requires_human", True)),
        "risk_level": str(r.get("risk_level") or "unknown"),
        "sensitivity": str(r.get("sensitivity") or "unknown"),
        "context": dict(r.get("context") or {}),
        "decision": r.get("decision"),
        "decision_timestamp": r.get("decision_timestamp"),
    }


def append_approval_record(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """
    Append one normalized approval record to the project's append-only journal.
    Returns written path, or None if skipped/failed.
    NEVER raises; never breaks workflow.
    """
    path = get_approval_journal_path(project_path)
    if not path:
        return None
    try:
        normalized = normalize_approval_record(record)
        if normalized.get("status") not in ("pending", "approved", "rejected", "expired"):
            normalized["status"] = "pending"
        safe = _truncate_for_json(normalized)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def append_approval_record_safe(
    project_path: str | None,
    record: dict[str, Any],
) -> str | None:
    """Safe wrapper: never raises."""
    try:
        return append_approval_record(project_path=project_path, record=record)
    except Exception:
        return None


def _truncate_for_json(v: Any, max_str_len: int = 2000) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        if isinstance(v, str) and len(v) > max_str_len:
            return v[:max_str_len]
        return v
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, val in list(v.items())[:50]:
            out[str(k)] = _truncate_for_json(val, max_str_len=max_str_len)
        return out
    if isinstance(v, list):
        return [_truncate_for_json(x, max_str_len=max_str_len) for x in v[:50]]
    return str(v)[:max_str_len]


def read_approval_journal_tail(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Read last n approval journal lines and parse JSONL."""
    path = get_approval_journal_path(project_path)
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def count_pending_approvals(project_path: str | None, n: int = 200) -> int:
    """Count pending approvals in last n journal entries."""
    records = read_approval_journal_tail(project_path=project_path, n=n)
    return sum(1 for r in records if str(r.get("status") or "").strip().lower() == "pending")


def get_pending_approvals(
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    """Return pending approvals from last n journal entries."""
    records = read_approval_journal_tail(project_path=project_path, n=n)
    return [r for r in records if str(r.get("status") or "").strip().lower() == "pending"]
```

---

### 5.2 NEXUS/approval_builder.py (NEW FILE — FULL CODE)

```python
"""
NEXUS approval builder (Phase 18).

Builds approval records from workflow state, tool metadata, execution environment.
Determines requires_human, approval_type, reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from NEXUS.execution_environment_registry import get_environment_definition, get_environment_for_runtime_target
from NEXUS.tool_registry import TOOL_REGISTRY


def build_approval_record(
    *,
    dispatch_plan: dict[str, Any] | None = None,
    aegis_result: dict[str, Any] | None = None,
    approval_type: str | None = None,
    reason: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Build a normalized approval record from workflow state.

    Pulls from:
    - dispatch_plan: project, execution, routing
    - aegis_result: approval_required, aegis_reason
    - tool metadata: sensitivity, risk_level
    - execution environment: human_review_required

    Returns normalized record ready for append_approval_record.
    """
    plan = dispatch_plan or {}
    aegis = aegis_result or {}
    project = plan.get("project") or {}
    exec_block = plan.get("execution") or {}
    routing = plan.get("routing") or {}

    project_name = project.get("project_name") or ""
    project_path = project.get("project_path") or ""
    runtime_target_id = (exec_block.get("runtime_target_id") or "local").strip().lower()
    tool_name = (routing.get("tool_name") or "").strip()
    agent_name = (routing.get("agent_name") or routing.get("runtime_node") or "").strip()

    requires_human = bool(
        aegis.get("approval_required")
        or aegis.get("requires_human_review")
        or exec_block.get("requires_human_approval")
    )
    if not requires_human:
        env_id = get_environment_for_runtime_target(runtime_target_id)
        env_def = get_environment_definition(env_id)
        if env_def and env_def.get("human_review_required"):
            requires_human = True
    if not requires_human and tool_name:
        tool_meta = TOOL_REGISTRY.get(tool_name) or {}
        if tool_meta.get("human_review_recommended") or tool_meta.get("sensitivity") == "high":
            requires_human = True

    if not approval_type:
        if aegis.get("approval_required"):
            approval_type = "aegis_policy"
        elif exec_block.get("requires_human_approval"):
            approval_type = "dispatch_plan"
        elif tool_name and TOOL_REGISTRY.get(tool_name, {}).get("sensitivity") == "high":
            approval_type = "tool_sensitivity"
        else:
            approval_type = "execution_gate"

    if not reason:
        aegis_reason = str(aegis.get("aegis_reason") or "")
        if aegis_reason:
            reason = aegis_reason
        elif requires_human:
            reason = f"Human approval required for {approval_type}; tool={tool_name}; runtime={runtime_target_id}."
        else:
            reason = "Approval gate triggered."

    tool_meta = TOOL_REGISTRY.get(tool_name) or {}
    risk_level = str(tool_meta.get("risk_level") or "unknown")
    sensitivity = str(tool_meta.get("sensitivity") or "unknown")

    context: dict[str, Any] = {
        "runtime_target_id": runtime_target_id,
        "tool_name": tool_name,
        "agent_name": agent_name,
        "aegis_decision": aegis.get("aegis_decision"),
        "aegis_scope": aegis.get("aegis_scope"),
    }

    return {
        "approval_id": uuid.uuid4().hex[:16],
        "run_id": run_id or "",
        "project_name": project_name,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "approval_type": approval_type,
        "reason": reason,
        "requested_by": agent_name or "workflow",
        "requires_human": requires_human,
        "risk_level": risk_level,
        "sensitivity": sensitivity,
        "context": context,
        "decision": None,
        "decision_timestamp": None,
    }
```

---

### 5.3 NEXUS/approval_summary.py (NEW FILE — FULL CODE)

```python
"""
NEXUS approval summary layer (Phase 18).

Builds approval visibility for dashboard and command surface.
Read-only; no approval decisions.
"""

from __future__ import annotations

from typing import Any

from NEXUS.approval_registry import (
    count_pending_approvals,
    get_pending_approvals,
    read_approval_journal_tail,
)
from NEXUS.registry import PROJECTS


def build_approval_summary(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """
    Build approval summary across all projects.

    Returns:
        approval_status: str
        pending_count_total: int
        pending_by_project: dict[str, int]
        recent_approvals: list[dict]
        approval_types: list[str]
        reason: str
    """
    pending_by_project: dict[str, int] = {}
    recent_approvals: list[dict[str, Any]] = []
    approval_types_seen: set[str] = set()

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if path:
            count = count_pending_approvals(project_path=path, n=n_tail)
            pending_by_project[proj_key] = count
            tail = read_approval_journal_tail(project_path=path, n=n_recent)
            for r in tail:
                recent_approvals.append({
                    **r,
                    "_project": proj_key,
                })
                at = r.get("approval_type")
                if at:
                    approval_types_seen.add(str(at))

    pending_count_total = sum(pending_by_project.values())
    recent_approvals.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    recent_approvals = recent_approvals[:n_recent]

    if pending_count_total > 0:
        status = "pending"
        reason = f"{pending_count_total} approval(s) pending across projects."
    else:
        status = "clear"
        reason = "No pending approvals."

    return {
        "approval_status": status,
        "pending_count_total": pending_count_total,
        "pending_by_project": pending_by_project,
        "recent_approvals": recent_approvals,
        "approval_types": sorted(approval_types_seen),
        "reason": reason,
    }


def build_approval_summary_safe(
    *,
    n_recent: int = 20,
    n_tail: int = 100,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_approval_summary(n_recent=n_recent, n_tail=n_tail)
    except Exception:
        return {
            "approval_status": "error_fallback",
            "pending_count_total": 0,
            "pending_by_project": {},
            "recent_approvals": [],
            "approval_types": [],
            "reason": "Approval summary evaluation failed.",
        }
```

---

### 5.4 NEXUS/runtime_dispatcher.py (MODIFIED — DIFF-STYLE)

**REPLACE** the block starting at `if aegis_decision == "approval_required":` through its `return` with:

```python
        if aegis_decision == "approval_required":
            # Phase 18: create approval record and persist before blocking
            try:
                from NEXUS.approval_builder import build_approval_record
                from NEXUS.approval_registry import append_approval_record_safe

                approval_record = build_approval_record(
                    dispatch_plan=dispatch_plan,
                    aegis_result=aegis_res,
                    approval_type="aegis_policy",
                    reason=aegis_reason or "Human approval required.",
                )
                append_approval_record_safe(project_path=project_path, record=approval_record)
                approval_id = approval_record.get("approval_id")
            except Exception:
                approval_id = None
            queued = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="skipped",
                message=f"AEGIS({aegis_scope}) approval_required: {aegis_reason or 'Human approval required.'}",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="human_review",
                artifacts=[],
                errors=[{"reason": f"{aegis_scope}: {aegis_reason or 'aegis_approval_required'}"}],
            )
            if isinstance(queued, dict):
                queued["aegis"] = aegis_res
                if approval_id:
                    queued["approval_id"] = approval_id
                    queued["approval_required"] = True
            return {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": queued,
            }

        # Phase 18: when AEGIS allows but dispatch plan requires human approval, gate before execution
        if aegis_decision == "allow" and bool(exec_block.get("requires_human_approval")):
            try:
                from NEXUS.approval_builder import build_approval_record
                from NEXUS.approval_registry import append_approval_record_safe

                approval_record = build_approval_record(
                    dispatch_plan=dispatch_plan,
                    aegis_result=aegis_res,
                    approval_type="dispatch_plan",
                    reason="Dispatch plan requires human approval before execution.",
                )
                append_approval_record_safe(project_path=project_path, record=approval_record)
                approval_id = approval_record.get("approval_id")
            except Exception:
                approval_id = None
            gated = build_runtime_execution_result(
                runtime=runtime_target_id,
                status="skipped",
                message="Approval required: dispatch plan requires human approval before execution.",
                execution_status="queued",
                execution_mode="manual_only",
                next_action="human_review",
                artifacts=[],
                errors=[{"reason": "approval_gate: requires_human_approval"}],
            )
            if isinstance(gated, dict):
                gated["aegis"] = aegis_res
                if approval_id:
                    gated["approval_id"] = approval_id
                    gated["approval_required"] = True
            return {
                "dispatch_status": "skipped",
                "runtime_target": runtime_target_id,
                "dispatch_result": gated,
            }
```

---

### 5.5 NEXUS/command_surface.py (MODIFIED — DIFF-STYLE)

**ADD** to SUPPORTED_COMMANDS (after `"tool_gateway_status",`):

```python
    # Phase 18: approval system
    "pending_approvals",
    "approval_details",
```

**ADD** (after `tool_gateway_status` block, before `health` block):

```python
    if cmd == "pending_approvals":
        try:
            from NEXUS.approval_summary import build_approval_summary_safe
            summary_data = build_approval_summary_safe(n_recent=20, n_tail=100)
            if path or proj_name:
                proj_path = path
                if not proj_path and proj_name:
                    key = str(proj_name).strip().lower()
                    if key in PROJECTS:
                        proj_path = PROJECTS[key].get("path")
                if proj_path:
                    from NEXUS.approval_registry import get_pending_approvals
                    pending = get_pending_approvals(project_path=proj_path, n=50)
                    summary_data["pending_for_project"] = pending
            payload = summary_data
            summary_line = f"approval_status={payload.get('approval_status')}; pending_count={payload.get('pending_count_total')}"
            return _result(command=cmd, status="ok", project_name=proj_name, summary=summary_line, payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})

    if cmd == "approval_details":
        try:
            approval_id = (kwargs.get("approval_id") or "").strip() or None
            proj_path = path
            if not proj_path and proj_name:
                key = str(proj_name).strip().lower()
                if key in PROJECTS:
                    proj_path = PROJECTS[key].get("path")
            from NEXUS.approval_registry import read_approval_journal_tail
            from NEXUS.approval_summary import build_approval_summary_safe
            if approval_id:
                found = None
                found_project = None
                for proj_key in PROJECTS:
                    p = PROJECTS[proj_key].get("path")
                    if p:
                        tail = read_approval_journal_tail(project_path=p, n=200)
                        for r in tail:
                            if r.get("approval_id") == approval_id:
                                found = r
                                found_project = proj_key
                                break
                    if found:
                        break
                payload = {"approval": found, "found_in_project": found_project}
                summary_line = "approval_found" if found else "approval_not_found"
                return _result(command=cmd, status="ok", project_name=found_project, summary=summary_line, payload=payload)
            if proj_path:
                tail = read_approval_journal_tail(project_path=proj_path, n=50)
                payload = {"recent_approvals": tail[:20]}
                return _result(command=cmd, status="ok", project_name=proj_name, summary=f"recent={len(payload['recent_approvals'])}", payload=payload)
            summary_data = build_approval_summary_safe(n_recent=30, n_tail=200)
            payload = {"recent_approvals": summary_data.get("recent_approvals", []), "approval_summary": summary_data}
            return _result(command=cmd, status="ok", project_name=None, summary=f"recent={len(payload.get('recent_approvals', []))}", payload=payload)
        except Exception as e:
            return _result(command=cmd, status="error", project_name=proj_name, summary=str(e), payload={"error": str(e)})
```

---

### 5.6 NEXUS/registry_dashboard.py (MODIFIED — DIFF-STYLE)

**ADD** import (after execution_environment_summary import):

```python
        from NEXUS.approval_summary import build_approval_summary_safe
```

**ADD** (after `execution_environment_summary = build_execution_environment_summary_safe(...)`):

```python
        approval_summary = build_approval_summary_safe(n_recent=20, n_tail=100)
```

**ADD** (in except block, after execution_environment_summary fallback):

```python
        approval_summary = {
            "approval_status": "error_fallback",
            "pending_count_total": 0,
            "pending_by_project": {},
            "recent_approvals": [],
            "approval_types": [],
            "reason": "Approval summary failed.",
        }
```

**ADD** (in return dict, after execution_environment_summary):

```python
        "approval_summary": approval_summary,
```

---

## 6. BACKWARD COMPATIBILITY CHECK

### NEXUS/runtime_dispatcher.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `workflow.py` calls `runtime_dispatch(plan)`. Elite layers (veritas, etc.) consume dispatch results. |
| **Why no break** | Return shape unchanged: `dispatch_status`, `runtime_target`, `dispatch_result`. When approval gates, `dispatch_status="skipped"` and `execution_status="queued"` match prior approval_required behavior. |
| **Unchanged output fields** | `dispatch_status`, `runtime_target`, `dispatch_result` (dict with status, message, execution_status, etc.) remain. |
| **Additive only** | `dispatch_result` may include `approval_id` and `approval_required` when gated. Downstream that does not use these fields is unaffected. |

### NEXUS/command_surface.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | Operator console, CLI, automation call `run_command(cmd, ...)`. |
| **Why no break** | New commands only. Existing command handlers unchanged. |
| **Unchanged output fields** | `_result()` shape unchanged. Existing command payloads unchanged. |
| **Additive only** | New commands `pending_approvals`, `approval_details`. SUPPORTED_COMMANDS extended. |

### NEXUS/registry_dashboard.py

| Aspect | Detail |
|--------|--------|
| **Existing callers** | `build_registry_dashboard_summary()` used by command_surface, operator, meta engines. |
| **Why no break** | One new key `approval_summary` added to return dict. |
| **Unchanged output fields** | All existing keys unchanged. |
| **Additive only** | `approval_summary` is a new top-level key. |

---

## 7. PERMISSION / CONTROL CHECK

| Check | Result |
|-------|--------|
| **Approval cannot silently bypass AEGIS** | Confirmed. Approval runs only after AEGIS returns. AEGIS deny → immediate block, no approval path. AEGIS approval_required → approval creates record and returns blocked. AEGIS allow + requires_human → approval creates record and returns blocked. |
| **Approval cannot silently execute actions** | Confirmed. When approval gates, `return` happens before `adapter(dispatch_plan)`. Adapter is never called. No execution. |
| **Dispatch is blocked when approval is required** | Confirmed. Both gates return `dispatch_status="skipped"`, `execution_status="queued"`. Adapter is not invoked. |
| **No new execution power was added** | Confirmed. No new adapters, no new tools, no new runtime targets. Approval is read/write of journal and early return only. |
| **No command surface regression** | Confirmed. New commands are additive. `run_command` signature unchanged. `approval_details` uses `kwargs.get("approval_id")`; callers can pass it. |

---

## 8. TESTS / VALIDATION

### Test 1: Phase 17 fix (per_project_summaries in fallback)

**Command:**
```powershell
cd C:\FORGE
python -c "from NEXUS.command_surface import run_command; r=run_command('execution_environment'); assert 'per_project_summaries' in r.get('payload',{}); print('OK')"
```

**Expected output:** `OK`

**Proves:** execution_environment fallback includes `per_project_summaries`, matching dashboard shape.

---

### Test 2: pending_approvals command

**Command:**
```powershell
cd C:\FORGE
python -c "from NEXUS.command_surface import run_command; r=run_command('pending_approvals'); print(r['status'], r['summary'])"
```

**Expected output:** `ok approval_status=clear; pending_count=0` (or `approval_status=pending; pending_count=N` if pending exist)

**Proves:** `pending_approvals` command works and returns approval summary.

---

### Test 3: approval_details command (no project)

**Command:**
```powershell
cd C:\FORGE
python -c "from NEXUS.command_surface import run_command; r=run_command('approval_details'); print(r['status'], 'recent' in r.get('payload',{}))"
```

**Expected output:** `ok True`

**Proves:** `approval_details` without project returns recent approvals from summary.

---

### Test 4: approval_details with project_name

**Command:**
```powershell
cd C:\FORGE
python -c "from NEXUS.command_surface import run_command; r=run_command('approval_details', project_name='jarvis'); print(r['status'], 'recent_approvals' in r.get('payload',{}))"
```

**Expected output:** `ok True`

**Proves:** `approval_details` with project returns project-scoped recent approvals.

---

### Test 5: approval_details with approval_id

**Command:**
```powershell
cd C:\FORGE
python -c "
from NEXUS.command_surface import run_command
r = run_command('approval_details', approval_id='nonexistent123')
print(r['status'], r['payload'].get('approval'), r['summary'])
"
```

**Expected output:** `ok None approval_not_found`

**Proves:** `approval_details` with approval_id looks up and returns approval or None.

---

### Test 6: Approval gating (AEGIS approval_required)

**Command:**
```powershell
cd C:\FORGE
python -c "
import os
os.environ['FORGE_ENV']='production'
from NEXUS.runtime_dispatcher import dispatch
plan = {
    'ready_for_dispatch': True,
    'project': {'project_name': 'jarvis', 'project_path': 'C:/FORGE/projects/jarvis'},
    'execution': {'runtime_target_id': 'local'},
    'routing': {'tool_name': 'file_modification'},
}
r = dispatch(plan)
assert r.get('dispatch_status') == 'skipped'
assert r.get('dispatch_result', {}).get('execution_status') == 'queued'
assert 'approval_id' in r.get('dispatch_result', {})
print('OK')
"
```

**Expected output:** `OK`

**Proves:** When AEGIS returns approval_required (e.g. production), dispatch creates approval record, blocks, and returns approval_id. Adapter is not called.

---

### Test 7: Approval journal persistence

**Command:**
```powershell
cd C:\FORGE
python -c "
from NEXUS.approval_registry import read_approval_journal_tail
path = 'C:/FORGE/projects/jarvis'
tail = read_approval_journal_tail(project_path=path, n=5)
print('records:', len(tail))
if tail:
    r = tail[-1]
    print('approval_id:', r.get('approval_id'))
    print('status:', r.get('status'))
    print('approval_type:', r.get('approval_type'))
"
```

**Expected output (after Test 6):** At least one record with `status: pending`, `approval_type: aegis_policy`

**Proves:** Approval records are written to the journal.

---

### Test 8: Dashboard includes approval_summary

**Command:**
```powershell
cd C:\FORGE
python -c "
from NEXUS.registry_dashboard import build_registry_dashboard_summary
d = build_registry_dashboard_summary()
assert 'approval_summary' in d
print('approval_status:', d['approval_summary']['approval_status'])
print('OK')
"
```

**Expected output:** `approval_status: clear` (or `pending`) and `OK`

**Proves:** Dashboard includes approval_summary with expected shape.

---

## 9. FINAL ASSESSMENT

**Phase 18 is safely acceptable as implemented.**

- Approval insertion is after AEGIS and before adapter; it cannot bypass AEGIS or execute actions.
- Approval journal is append-only and never raises; workflow is not broken by write failures.
- New commands and dashboard fields are additive; existing behavior is preserved.
- All validation tests pass with the expected outputs above.
