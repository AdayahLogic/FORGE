"""
NEXUS cross-artifact trace layer (Phase 27).

Unified trace summary across approvals, patches, HELIX, autonomy, products.
Read-only; uses only real existing data. No fabrication.
Honest partial trace over fake completeness.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

TRACE_STATUSES = ("ok", "partial", "error_fallback")


def build_cross_artifact_trace(
    *,
    project_name: str | None = None,
    project_path: str | None = None,
    n_recent: int = 50,
) -> dict[str, Any]:
    """
    Build cross-artifact trace summary from real journals.
    Uses only existing data; does not invent links.
    """
    now = datetime.now().isoformat()
    approval_ids: list[str] = []
    patch_ids: list[str] = []
    helix_ids: list[str] = []
    autonomy_ids: list[str] = []
    product_ids: list[str] = []
    learning_record_refs: list[str] = []
    link_completeness: dict[str, bool] = {
        "approval_to_patch": False,
        "patch_to_helix": False,
        "patch_to_product": False,
        "autonomy_to_product": False,
        "helix_to_autonomy": False,
    }
    missing_links: list[str] = []

    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.approval_registry import read_approval_journal_tail
        from NEXUS.patch_proposal_registry import (
            read_patch_proposal_journal_tail,
            read_patch_proposal_resolution_tail,
            get_latest_resolution_for_patch,
        )
        from NEXUS.helix_registry import read_helix_journal_tail
        from NEXUS.autonomy_registry import read_autonomy_journal_tail
        from NEXUS.product_builder import build_product_manifest_safe
        from NEXUS.learning_writer import read_learning_journal_tail
    except Exception as e:
        return _fallback_trace(now, f"Trace unavailable: {e}", project_name)

    projects_to_scan = []
    if project_name or project_path:
        key = project_name.strip().lower() if project_name else None
        if key and key in PROJECTS:
            projects_to_scan = [(key, PROJECTS[key].get("path"))]
        elif project_path:
            for k, v in PROJECTS.items():
                if v.get("path") == project_path:
                    projects_to_scan = [(k, project_path)]
                    break
        if not projects_to_scan:
            projects_to_scan = [(project_name or "unknown", project_path)]
    else:
        projects_to_scan = [(k, v.get("path")) for k, v in PROJECTS.items() if v.get("path")]

    approval_to_patch_pairs: set[tuple[str, str]] = set()
    patch_has_helix = False
    patch_has_product = False
    autonomy_has_product = False
    helix_has_autonomy = False

    for proj_key, path in projects_to_scan:
        if not path:
            continue
        # Approvals
        for r in read_approval_journal_tail(project_path=path, n=n_recent):
            aid = r.get("approval_id")
            if aid and isinstance(aid, str):
                approval_ids.append(aid)
            ctx = r.get("context") or {}
            pid = ctx.get("patch_id")
            if pid and isinstance(pid, str):
                approval_to_patch_pairs.add((aid or "", pid))
            for pid_ref in r.get("patch_id_refs") or []:
                if pid_ref and isinstance(pid_ref, str) and aid:
                    approval_to_patch_pairs.add((aid, pid_ref))

        # Patch proposals
        for r in read_patch_proposal_journal_tail(project_path=path, n=n_recent):
            pid = r.get("patch_id")
            if pid and isinstance(pid, str):
                patch_ids.append(pid)
            if r.get("helix_id_refs"):
                patch_has_helix = True
            if r.get("product_id_refs"):
                patch_has_product = True
            for aid in r.get("approval_id_refs") or []:
                if aid and isinstance(aid, str):
                    approval_to_patch_pairs.add((aid, pid or ""))
            # Resolutions link approval to patch
            res = get_latest_resolution_for_patch(project_path=path, patch_id=pid or "")
            if res and res.get("approval_id") and pid:
                approval_to_patch_pairs.add((str(res["approval_id"]), pid))

        # HELIX
        for r in read_helix_journal_tail(project_path=path, n=n_recent):
            hid = r.get("helix_id")
            if hid and isinstance(hid, str):
                helix_ids.append(hid)
            if r.get("autonomy_id_refs"):
                helix_has_autonomy = True

        # Autonomy
        for r in read_autonomy_journal_tail(project_path=path, n=n_recent):
            aid = r.get("autonomy_id")
            if aid and isinstance(aid, str):
                autonomy_ids.append(aid)
            if r.get("product_id_refs"):
                autonomy_has_product = True

        # Product (Phase 29: product refs contribute to linkage)
        try:
            manifest = build_product_manifest_safe(
                project_name=proj_key,
                project_path=path,
                project_key=proj_key,
            )
            pid_val = manifest.get("product_id")
            if pid_val and isinstance(pid_val, str) and pid_val != "error_fallback":
                product_ids.append(pid_val)
            if manifest.get("patch_id_refs"):
                patch_has_product = True
        except Exception:
            pass

        # Learning (best-effort; Phase 28: use patch_id_refs/approval_id_refs when present)
        for i, lr in enumerate(read_learning_journal_tail(project_path=path, n=min(n_recent, 20))):
            ref = lr.get("run_id") or lr.get("timestamp") or str(i)
            if isinstance(ref, str) and ref:
                learning_record_refs.append(f"{proj_key}:{ref}"[:80])
            for aid in lr.get("approval_id_refs") or []:
                if aid and isinstance(aid, str):
                    approval_ids.append(aid)
                for pid_ref in lr.get("patch_id_refs") or []:
                    if pid_ref and isinstance(pid_ref, str):
                        approval_to_patch_pairs.add((aid, pid_ref))

    learning_record_refs = learning_record_refs[:20]

    # Deduplicate ID lists (preserve order)
    def _dedupe(lst: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in lst:
            if x and isinstance(x, str) and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    approval_ids = _dedupe(approval_ids)
    patch_ids = _dedupe(patch_ids)
    helix_ids = _dedupe(helix_ids)
    autonomy_ids = _dedupe(autonomy_ids)
    product_ids = _dedupe(product_ids)

    # Link completeness (honest; only true when we have real data)
    link_completeness["approval_to_patch"] = len(approval_to_patch_pairs) > 0
    link_completeness["patch_to_helix"] = patch_has_helix
    link_completeness["patch_to_product"] = patch_has_product
    link_completeness["autonomy_to_product"] = autonomy_has_product
    link_completeness["helix_to_autonomy"] = helix_has_autonomy

    # Missing links (honest; what we'd expect but don't have)
    if patch_ids and not link_completeness["approval_to_patch"]:
        missing_links.append("No approval-to-patch linkage found.")
    if patch_ids and not patch_has_helix:
        missing_links.append("No patch-to-HELIX linkage in recent proposals.")
    if patch_ids and not patch_has_product:
        missing_links.append("No patch-to-product linkage in recent proposals.")
    if autonomy_ids and not autonomy_has_product:
        missing_links.append("No autonomy-to-product linkage in recent runs.")
    if helix_ids and not helix_has_autonomy:
        missing_links.append("No HELIX-to-autonomy linkage in recent runs.")

    # Trace status
    any_links = any(link_completeness.values())
    if not approval_ids and not patch_ids and not helix_ids and not autonomy_ids and not product_ids:
        trace_status = "partial"
        trace_reason = "No artifacts found; trace empty."
    elif missing_links and not any_links:
        trace_status = "partial"
        trace_reason = "; ".join(missing_links[:3])
    elif missing_links:
        trace_status = "partial"
        trace_reason = f"Some linkage present; {len(missing_links)} missing link type(s)."
    else:
        trace_status = "ok"
        trace_reason = "Trace complete for scanned artifacts."

    return {
        "trace_status": trace_status,
        "project_name": project_name,
        "approval_ids": approval_ids[:50],
        "patch_ids": patch_ids[:50],
        "helix_ids": helix_ids[:50],
        "autonomy_ids": autonomy_ids[:50],
        "product_ids": product_ids[:20],
        "learning_record_refs": learning_record_refs[:20],
        "link_completeness": link_completeness,
        "missing_links": missing_links,
        "trace_reason": trace_reason,
        "generated_at": now,
        "artifact_counts": {
            "approvals": len(approval_ids),
            "patches": len(patch_ids),
            "helix_runs": len(helix_ids),
            "autonomy_runs": len(autonomy_ids),
            "products": len(product_ids),
            "learning_records": len(learning_record_refs),
        },
    }


def build_cross_artifact_trace_safe(
    *,
    project_name: str | None = None,
    project_path: str | None = None,
    n_recent: int = 50,
) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return build_cross_artifact_trace(
            project_name=project_name,
            project_path=project_path,
            n_recent=n_recent,
        )
    except Exception as e:
        return _fallback_trace(
            datetime.now().isoformat(),
            f"Cross-artifact trace failed: {e}",
            project_name,
        )


def _fallback_trace(generated_at: str, reason: str, project_name: str | None) -> dict[str, Any]:
    """Error fallback shape; preserves contract."""
    return {
        "trace_status": "error_fallback",
        "project_name": project_name,
        "approval_ids": [],
        "patch_ids": [],
        "helix_ids": [],
        "autonomy_ids": [],
        "product_ids": [],
        "learning_record_refs": [],
        "link_completeness": {
            "approval_to_patch": False,
            "patch_to_helix": False,
            "patch_to_product": False,
            "autonomy_to_product": False,
            "helix_to_autonomy": False,
        },
        "missing_links": [reason],
        "trace_reason": reason,
        "generated_at": generated_at,
        "artifact_counts": {
            "approvals": 0,
            "patches": 0,
            "helix_runs": 0,
            "autonomy_runs": 0,
            "products": 0,
            "learning_records": 0,
        },
    }
