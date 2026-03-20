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
from NEXUS.ref_utils import normalize_ref_list


def get_product_refs(manifest: dict[str, Any] | None) -> dict[str, list[str]]:
    """
    Phase 29: Normalized product ref access.
    Returns dict with approval_id_refs, patch_id_refs, helix_id_refs,
    autonomy_id_refs, learning_insight_refs. Uses both old and new field names.
    """
    m = manifest or {}
    return {
        "approval_id_refs": normalize_ref_list(m.get("approval_id_refs") or m.get("approval_refs")),
        "patch_id_refs": normalize_ref_list(m.get("patch_id_refs")),
        "helix_id_refs": normalize_ref_list(m.get("helix_id_refs")),
        "autonomy_id_refs": normalize_ref_list(m.get("autonomy_id_refs") or m.get("autonomy_refs")),
        "learning_insight_refs": normalize_ref_list(m.get("learning_insight_refs")),
    }


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

    # Phase 29: normalized ref capture from real journals (when available)
    approval_id_refs = normalize_ref_list(approval_reqs.get("recent_approval_ids"))
    patch_id_refs: list[str] = []
    helix_id_refs: list[str] = []
    autonomy_id_refs: list[str] = []
    learning_insight_refs: list[str] = []
    try:
        from NEXUS.patch_proposal_registry import read_patch_proposal_journal_tail
        for r in read_patch_proposal_journal_tail(project_path=path, n=15):
            pid = r.get("patch_id")
            if pid and isinstance(pid, str):
                patch_id_refs.append(pid)
    except Exception:
        pass
    try:
        from NEXUS.helix_registry import read_helix_journal_tail
        for r in read_helix_journal_tail(project_path=path, n=10):
            hid = r.get("helix_id")
            if hid and isinstance(hid, str):
                helix_id_refs.append(hid)
    except Exception:
        pass
    try:
        from NEXUS.autonomy_registry import read_autonomy_journal_tail
        for r in read_autonomy_journal_tail(project_path=path, n=10):
            aid = r.get("autonomy_id")
            if aid and isinstance(aid, str):
                autonomy_id_refs.append(aid)
    except Exception:
        pass
    try:
        from NEXUS.learning_writer import read_learning_journal_tail
        for i, lr in enumerate(read_learning_journal_tail(project_path=path, n=10)):
            ref = lr.get("run_id") or lr.get("timestamp") or str(i)
            if ref and isinstance(ref, str):
                learning_insight_refs.append(f"{key}:{ref}"[:60])
    except Exception:
        pass

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
        "learning_insight_refs": learning_insight_refs[:20],
        "approval_refs": approval_id_refs[:10],
        "autonomy_refs": autonomy_id_refs[:10],
        "approval_id_refs": approval_id_refs[:20],
        "patch_id_refs": patch_id_refs[:20],
        "helix_id_refs": helix_id_refs[:20],
        "autonomy_id_refs": autonomy_id_refs[:20],
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
            "learning_insight_refs": [],
            "approval_refs": [],
            "autonomy_refs": [],
            "approval_id_refs": [],
            "patch_id_refs": [],
            "helix_id_refs": [],
            "autonomy_id_refs": [],
        }
