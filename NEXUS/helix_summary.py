"""
NEXUS HELIX summary layer (Phase 21).

Builds HELIX pipeline visibility for dashboard and command surface.
Read-only; no execution capability.
Phase 31: quality signals, stage quality distribution, critique severity, optimizer actionability.
"""

from __future__ import annotations

from typing import Any

from NEXUS.helix_registry import read_helix_journal_tail
from NEXUS.helix_quality_signals import compute_overall_helix_quality_signal
from NEXUS.registry import PROJECTS


HELIX_SUMMARY_KEYS = (
    "helix_posture",
    "last_helix_run",
    "last_stop_reason",
    "approval_blocked",
    "safety_blocked",
    "requires_surgeon",
    "stage_distribution",
    "surgeon_invocation_frequency",
    "approval_blocked_frequency",
    "autonomy_linkage_presence",
    "multi_approach_success_rate",
    "repair_artifact_quality",
    "helix_quality_signals",
    "recent_runs",
    "per_project",
    "reason",
)


def build_helix_summary(
    *,
    n_recent: int = 10,
) -> dict[str, Any]:
    """
    Build HELIX summary across all projects.

    Returns:
        helix_posture: str  # idle | capable | approval_blocked | safety_blocked
        last_helix_run: dict | None
        last_stop_reason: str
        approval_blocked: bool
        safety_blocked: bool
        requires_surgeon: bool
        recent_runs: list[dict]
        per_project: dict[str, dict]
        reason: str
    """
    recent_runs: list[dict[str, Any]] = []
    per_project: dict[str, dict[str, Any]] = {}
    last_helix_run: dict[str, Any] | None = None
    last_stop_reason = ""
    approval_blocked = False
    safety_blocked = False
    requires_surgeon = False
    stage_distribution: dict[str, int] = {}
    surgeon_count = 0
    approval_blocked_count = 0
    autonomy_linkage_count = 0
    total_runs = 0
    multi_approach_count = 0
    repair_with_patch_count = 0
    repair_without_patch_count = 0

    for proj_key in sorted(PROJECTS.keys()):
        proj = PROJECTS[proj_key]
        path = proj.get("path")
        if not path:
            continue
        tail = read_helix_journal_tail(project_path=path, n=n_recent)
        for r in tail:
            recent_runs.append({**r, "_project": proj_key})
            total_runs += 1
            if r.get("requires_surgeon"):
                surgeon_count += 1
            if r.get("approval_blocked"):
                approval_blocked_count += 1
            if r.get("autonomy_id_refs"):
                autonomy_linkage_count += 1
            for sr in r.get("stage_results") or []:
                stage = sr.get("stage") or "unknown"
                status = sr.get("stage_status") or "unknown"
                key = f"{stage}:{status}"
                stage_distribution[key] = stage_distribution.get(key, 0) + 1
                if stage == "architect" and (sr.get("multi_approach_count") or len(sr.get("approaches") or [])) >= 2:
                    multi_approach_count += 1
                if stage == "surgeon" and sr.get("repair_recommended"):
                    meta = sr.get("repair_metadata") or {}
                    if meta.get("has_patch_payload"):
                        repair_with_patch_count += 1
                    else:
                        repair_without_patch_count += 1
        if tail:
            last = tail[-1]
            if last_helix_run is None or (last.get("finished_at") or "") > (last_helix_run.get("finished_at") or ""):
                last_helix_run = {**last, "_project": proj_key}
                last_stop_reason = last.get("stop_reason") or ""
            per_project[proj_key] = {
                "last_run": tail[-1] if tail else None,
                "recent_count": len(tail),
                "last_stop_reason": tail[-1].get("stop_reason") if tail else "",
                "approval_blocked": bool(tail[-1].get("approval_blocked")) if tail else False,
                "safety_blocked": bool(tail[-1].get("safety_blocked")) if tail else False,
                "requires_surgeon": bool(tail[-1].get("requires_surgeon")) if tail else False,
            }

    recent_runs.sort(key=lambda x: x.get("finished_at") or "", reverse=True)
    recent_runs = recent_runs[:n_recent]

    if last_helix_run:
        approval_blocked = bool(last_helix_run.get("approval_blocked"))
        safety_blocked = bool(last_helix_run.get("safety_blocked"))
        requires_surgeon = bool(last_helix_run.get("requires_surgeon"))

    if approval_blocked:
        posture = "approval_blocked"
        reason = "Last HELIX run stopped; approval required."
    elif safety_blocked:
        posture = "safety_blocked"
        reason = "Last HELIX run stopped; safety blocked."
    elif last_helix_run and last_helix_run.get("pipeline_status") == "completed":
        posture = "capable"
        reason = "HELIX pipeline capable; last run completed."
    elif last_helix_run:
        posture = "idle"
        reason = f"Last run: {last_stop_reason or 'unknown'}."
    else:
        posture = "idle"
        reason = "No recent HELIX runs."

    surgeon_invocation_frequency = surgeon_count / total_runs if total_runs else 0.0
    approval_blocked_frequency = approval_blocked_count / total_runs if total_runs else 0.0
    autonomy_linkage_presence = autonomy_linkage_count / total_runs if total_runs else 0.0
    multi_approach_success_rate = multi_approach_count / total_runs if total_runs else 0.0
    repair_artifact_quality = {
        "repair_with_patch_count": repair_with_patch_count,
        "repair_without_patch_count": repair_without_patch_count,
        "repair_total": repair_with_patch_count + repair_without_patch_count,
    }

    # Phase 31: quality signals from last run (or aggregate from recent)
    helix_quality_signals: dict[str, Any] = {}
    critique_severity_patterns: dict[str, int] = {}
    optimizer_actionability_count = 0
    if last_helix_run:
        stage_results = last_helix_run.get("stage_results") or []
        try:
            qs = compute_overall_helix_quality_signal(stage_results)
            helix_quality_signals = {
                "overall_helix_quality_signal": qs.get("overall_helix_quality_signal", 0.0),
                "architect_output_quality": qs.get("architect_output_quality", 0.0),
                "critic_output_quality": qs.get("critic_output_quality", 0.0),
                "optimizer_output_quality": qs.get("optimizer_output_quality", 0.0),
            }
            critic_result = next((sr for sr in stage_results if sr.get("stage") == "critic"), {})
            ev = critic_result.get("critique_evaluation") or {}
            sev = ev.get("severity") or "unknown"
            critique_severity_patterns[sev] = critique_severity_patterns.get(sev, 0) + 1
            opt_result = next((sr for sr in stage_results if sr.get("stage") == "optimizer"), {})
            swp = opt_result.get("suggestions_with_priority") or []
            optimizer_actionability_count = len([x for x in swp if isinstance(x, dict) and x.get("priority")])
        except Exception:
            helix_quality_signals = {"overall_helix_quality_signal": 0.0, "architect_output_quality": 0.0, "critic_output_quality": 0.0, "optimizer_output_quality": 0.0}

    return {
        "helix_posture": posture,
        "last_helix_run": last_helix_run,
        "last_stop_reason": last_stop_reason,
        "approval_blocked": approval_blocked,
        "safety_blocked": safety_blocked,
        "requires_surgeon": requires_surgeon,
        "stage_distribution": stage_distribution,
        "surgeon_invocation_frequency": round(surgeon_invocation_frequency, 2),
        "approval_blocked_frequency": round(approval_blocked_frequency, 2),
        "autonomy_linkage_presence": round(autonomy_linkage_presence, 2),
        "multi_approach_success_rate": round(multi_approach_success_rate, 2),
        "repair_artifact_quality": repair_artifact_quality,
        "helix_quality_signals": helix_quality_signals,
        "critique_severity_patterns": critique_severity_patterns,
        "optimizer_actionability_count": optimizer_actionability_count,
        "recent_runs": recent_runs,
        "per_project": per_project,
        "reason": reason,
    }


def build_helix_summary_safe(
    *,
    n_recent: int = 10,
) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return build_helix_summary(n_recent=n_recent)
    except Exception:
        return {
            "helix_posture": "error_fallback",
            "last_helix_run": None,
            "last_stop_reason": "",
            "approval_blocked": False,
            "safety_blocked": False,
            "requires_surgeon": False,
            "stage_distribution": {},
            "surgeon_invocation_frequency": 0.0,
            "approval_blocked_frequency": 0.0,
            "autonomy_linkage_presence": 0.0,
            "multi_approach_success_rate": 0.0,
            "repair_artifact_quality": {"repair_with_patch_count": 0, "repair_without_patch_count": 0, "repair_total": 0},
            "helix_quality_signals": {},
            "critique_severity_patterns": {},
            "optimizer_actionability_count": 0,
            "recent_runs": [],
            "per_project": {},
            "reason": "HELIX summary failed.",
        }
