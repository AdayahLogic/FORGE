"""
NEXUS integrity checker (hardening phase).

Read-only, deterministic checks for contract consistency, fallback shapes,
and cross-phase refs. No execution; no side effects.
"""

from __future__ import annotations

from typing import Any

# Canonical keys for recent-phase payloads (success and fallback must include these)
APPROVAL_SUMMARY_KEYS = (
    "approval_status",
    "pending_count_total",
    "pending_by_project",
    "recent_approvals",
    "approval_types",
    "stale_count",
    "approved_pending_apply_count",
    "reapproval_required_count",
    "reason",
)
PRODUCT_SUMMARY_KEYS = (
    "product_status",
    "draft_count",
    "ready_count",
    "restricted_count",
    "total_count",
    "products_by_project",
    "safety_indicators",
    "learning_linkage_present",
    "approval_linkage_present",
    "autonomy_linkage_present",
    "patch_linkage_present",
    "helix_linkage_present",
    "reason",
)
PRODUCT_REF_KEYS = (
    "approval_id_refs",
    "approval_refs",
    "patch_id_refs",
    "helix_id_refs",
    "autonomy_id_refs",
    "autonomy_refs",
    "learning_insight_refs",
)
AUTONOMY_SUMMARY_KEYS = (
    "autonomy_posture",
    "last_autonomy_run",
    "last_stop_reason",
    "autonomy_capable",
    "approval_blocked",
    "recent_runs",
    "per_project",
    "execution_environment_posture",
    "reason",
)
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
    "recent_runs",
    "per_project",
    "reason",
)
REF_KEYS = ("approval_id_refs", "autonomy_id_refs", "product_id_refs")
REF_KEYS_PATCH = ("approval_id_refs", "autonomy_id_refs", "product_id_refs", "helix_id_refs")
PATCH_PROPOSAL_SUMMARY_KEYS = (
    "patch_proposal_status",
    "pending_count",
    "proposed_count",
    "approval_required_count",
    "approved_pending_apply_count",
    "approved_pending_apply_stale_count",
    "rejected_count",
    "blocked_count",
    "applied_count",
    "approval_blocked_count",
    "status_counts",
    "by_project",
    "recent_proposals",
    "by_risk_level",
    "reason",
)

# Phase 32: Surgeon repair_metadata core keys (required when repair_recommended)
REPAIR_METADATA_CORE_KEYS = ("repair_reason", "has_patch_payload", "repair_strategy_category")
REPAIR_METADATA_EXTENDED_KEYS = ("patch_readiness", "issue_scope", "target_files_candidate", "operator_handoff_notes")
VALID_PATCH_READINESS = ("low", "medium", "high")
VALID_ISSUE_SCOPE = ("single_file", "multi_file", "unknown")
VALID_PATCH_DRAFTABILITY = ("low", "medium", "high")
VALID_CANDIDATE_PATCH_STRATEGY = ("direct_diff", "guided_patch_followup", "advisory_only")
VALID_PROPOSAL_READINESS = ("fully_ready", "draft_followup", "advisory_only")
VALID_REFINEMENT_STATUS = ("not_refinable", "partially_refined", "draft_ready")
VALID_CONVERSION_STATUS = ("not_convertible", "conditionally_convertible", "converted_to_patch_candidate")
VALID_PROPOSAL_MATURITY = ("advisory", "guided_followup", "strong_candidate", "executable")
VALID_COMPLETION_STATUS = ("not_completable", "partially_completable", "completed_patch_candidate")
VALID_REVIEW_STATUS = ("not_ready_for_review", "ready_for_review", "reviewed", "changes_requested", "approved_for_approval", "error_fallback")
VALID_REVIEW_READINESS = ("low", "medium", "high")

# Phase 27: cross-artifact trace summary
TRACE_SUMMARY_KEYS = (
    "trace_status",
    "project_name",
    "approval_ids",
    "patch_ids",
    "helix_ids",
    "autonomy_ids",
    "product_ids",
    "learning_record_refs",
    "link_completeness",
    "missing_links",
    "trace_reason",
    "generated_at",
)
EXECUTION_PACKAGE_HARDENING_SUMMARY_KEYS = (
    "duplicate_success_blocked_count_total",
    "retry_ready_count_total",
    "repair_required_count_total",
    "rollback_repair_failed_count_total",
    "integrity_verified_count_total",
    "integrity_issues_count_total",
)
EXECUTION_PACKAGE_HARDENING_KEYS = (
    "retry_policy",
    "idempotency",
    "failure_summary",
    "recovery_summary",
    "rollback_repair",
    "integrity_verification",
)
EXECUTION_PACKAGE_EVALUATION_SUMMARY_KEYS = (
    "evaluation_surface_status",
    "pending_count_total",
    "completed_count_total",
    "blocked_count_total",
    "error_count_total",
    "evaluation_counts_by_project",
    "latest_evaluation_status_by_project",
    "execution_quality_band_count_total",
    "integrity_band_count_total",
    "rollback_quality_band_count_total",
    "failure_risk_band_count_total",
    "reason",
)
EXECUTION_PACKAGE_EVALUATION_KEYS = (
    "evaluation_status",
    "evaluation_timestamp",
    "evaluation_actor",
    "evaluation_id",
    "evaluation_version",
    "evaluation_reason",
    "evaluation_basis",
    "evaluation_summary",
)
EXECUTION_PACKAGE_LOCAL_ANALYSIS_SUMMARY_KEYS = (
    "analysis_surface_status",
    "pending_count_total",
    "completed_count_total",
    "blocked_count_total",
    "error_count_total",
    "analysis_counts_by_project",
    "latest_analysis_status_by_project",
    "confidence_band_count_total",
    "suggested_next_action_count_total",
    "reason",
)
EXECUTION_PACKAGE_LOCAL_ANALYSIS_KEYS = (
    "local_analysis_status",
    "local_analysis_timestamp",
    "local_analysis_actor",
    "local_analysis_id",
    "local_analysis_version",
    "local_analysis_reason",
    "local_analysis_basis",
    "local_analysis_summary",
)


def _check_keys(payload: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    """Return list of missing keys."""
    if not isinstance(payload, dict):
        return list(required)
    return [k for k in required if k not in payload]


def _check_refs_shape(refs: Any) -> tuple[bool, str]:
    """Return (valid, message). Refs must be list of strings or empty list."""
    if refs is None:
        return True, "refs absent (defaults to [])"
    if not isinstance(refs, list):
        return False, f"refs must be list, got {type(refs).__name__}"
    for i, x in enumerate(refs):
        if not isinstance(x, str):
            return False, f"refs[{i}] must be str, got {type(x).__name__}"
    return True, "ok"


def check_approval_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check approval summary has required keys. Read-only."""
    missing = _check_keys(payload, APPROVAL_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "approval_summary",
    }


def check_product_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check product summary has required keys. Read-only."""
    missing = _check_keys(payload, PRODUCT_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "product_summary",
    }


def check_autonomy_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check autonomy summary has required keys. Read-only."""
    missing = _check_keys(payload, AUTONOMY_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "autonomy_summary",
    }


def check_helix_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check helix summary has required keys. Read-only."""
    missing = _check_keys(payload, HELIX_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "helix_summary",
    }


def check_patch_proposal_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check patch proposal summary has required keys. Read-only."""
    missing = _check_keys(payload, PATCH_PROPOSAL_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "patch_proposal_summary",
    }


def check_trace_summary_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Check cross-artifact trace summary has required keys (Phase 27). Read-only."""
    missing = _check_keys(payload, TRACE_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "cross_artifact_trace_summary",
    }


def check_execution_package_hardening_summary_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 8 execution-package hardening summary keys exist."""
    missing = _check_keys(payload or {}, EXECUTION_PACKAGE_HARDENING_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "execution_package_execution_summary",
    }


def check_execution_package_hardening_shape(record: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 8 execution-package hardening fields exist."""
    if not isinstance(record, dict):
        return {"valid": True, "issues": [], "payload_type": "execution_package", "skipped": "not a dict"}
    issues: list[str] = []
    for key in EXECUTION_PACKAGE_HARDENING_KEYS:
        if key not in record:
            issues.append(f"missing key: {key}")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "execution_package"}


def check_execution_package_evaluation_summary_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 11 execution-package evaluation dashboard summary keys exist."""
    missing = _check_keys(payload or {}, EXECUTION_PACKAGE_EVALUATION_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "execution_package_evaluation_summary",
    }


def check_execution_package_evaluation_shape(record: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 11 package-level evaluation fields when present."""
    if not isinstance(record, dict):
        return {"valid": True, "issues": [], "payload_type": "execution_package_evaluation", "skipped": "not a dict"}
    if not any(key in record for key in EXECUTION_PACKAGE_EVALUATION_KEYS):
        return {
            "valid": True,
            "issues": [],
            "payload_type": "execution_package_evaluation",
            "skipped": "evaluation fields absent on older package",
        }
    issues: list[str] = []
    for key in EXECUTION_PACKAGE_EVALUATION_KEYS:
        if key not in record:
            issues.append(f"missing key: {key}")
    evaluation_id = str(record.get("evaluation_id") or "").strip()
    if evaluation_id:
        try:
            import uuid

            uuid.UUID(evaluation_id)
        except Exception:
            issues.append("evaluation_id must be UUID formatted")
    reason = record.get("evaluation_reason")
    if reason is not None and not isinstance(reason, dict):
        issues.append("evaluation_reason must be dict")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "execution_package_evaluation"}


def check_execution_package_local_analysis_summary_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 12 execution-package local analysis dashboard summary keys exist."""
    missing = _check_keys(payload or {}, EXECUTION_PACKAGE_LOCAL_ANALYSIS_SUMMARY_KEYS)
    return {
        "valid": len(missing) == 0,
        "missing_keys": missing,
        "payload_type": "execution_package_local_analysis_summary",
    }


def check_execution_package_local_analysis_shape(record: dict[str, Any] | None) -> dict[str, Any]:
    """Validate Phase 12 package-level local analysis fields when present."""
    if not isinstance(record, dict):
        return {"valid": True, "issues": [], "payload_type": "execution_package_local_analysis", "skipped": "not a dict"}
    if not any(key in record for key in EXECUTION_PACKAGE_LOCAL_ANALYSIS_KEYS):
        return {
            "valid": True,
            "issues": [],
            "payload_type": "execution_package_local_analysis",
            "skipped": "local analysis fields absent on older package",
        }
    issues: list[str] = []
    for key in EXECUTION_PACKAGE_LOCAL_ANALYSIS_KEYS:
        if key not in record:
            issues.append(f"missing key: {key}")
    local_analysis_id = str(record.get("local_analysis_id") or "").strip()
    if local_analysis_id:
        try:
            import uuid

            uuid.UUID(local_analysis_id)
        except Exception:
            issues.append("local_analysis_id must be UUID formatted")
    if str(record.get("local_analysis_actor") or "").strip() == "":
        issues.append("local_analysis_actor must be present")
    if str(record.get("local_analysis_version") or "").strip() != "v1":
        issues.append("local_analysis_version must be 'v1'")
    reason = record.get("local_analysis_reason")
    if reason is not None and not isinstance(reason, dict):
        issues.append("local_analysis_reason must be dict")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "execution_package_local_analysis"}


def check_patch_proposal_record_shape(record: dict[str, Any] | None) -> dict[str, Any]:
    """Phase 33: validate patch proposal record has valid proposal_readiness when present."""
    if not isinstance(record, dict):
        return {"valid": True, "issues": [], "payload_type": "patch_proposal_record", "skipped": "not a dict"}
    issues: list[str] = []
    pr = record.get("proposal_readiness")
    if pr is not None and str(pr).strip().lower() not in VALID_PROPOSAL_READINESS:
        issues.append(f"proposal_readiness must be one of {VALID_PROPOSAL_READINESS}, got {pr!r}")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "patch_proposal_record"}


def check_repair_metadata_shape(meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Check Surgeon repair_metadata shape (Phase 32). Read-only, deterministic.
    Lenient: core keys required; extended keys and value validation when present.
    """
    if not isinstance(meta, dict):
        return {"valid": True, "issues": [], "payload_type": "repair_metadata", "skipped": "not a dict"}
    issues: list[str] = []
    for k in REPAIR_METADATA_CORE_KEYS:
        if k not in meta:
            issues.append(f"missing core key: {k}")
    pr = meta.get("patch_readiness")
    if pr is not None and str(pr).strip().lower() not in VALID_PATCH_READINESS:
        issues.append(f"patch_readiness must be one of {VALID_PATCH_READINESS}, got {pr!r}")
    scope = meta.get("issue_scope")
    if scope is not None and str(scope).strip().lower() not in VALID_ISSUE_SCOPE:
        issues.append(f"issue_scope must be one of {VALID_ISSUE_SCOPE}, got {scope!r}")
    mif = meta.get("missing_information_flags")
    if mif is not None and not isinstance(mif, list):
        issues.append("missing_information_flags must be list")
    # Phase 33: draftability fields
    pd = meta.get("patch_draftability")
    if pd is not None and str(pd).strip().lower() not in VALID_PATCH_DRAFTABILITY:
        issues.append(f"patch_draftability must be one of {VALID_PATCH_DRAFTABILITY}, got {pd!r}")
    cps = meta.get("candidate_patch_strategy")
    if cps is not None and str(cps).strip().lower() not in VALID_CANDIDATE_PATCH_STRATEGY:
        issues.append(f"candidate_patch_strategy must be one of {VALID_CANDIDATE_PATCH_STRATEGY}, got {cps!r}")
    # Phase 34: refinement fields
    rfs = meta.get("refinement_status")
    if rfs is not None and str(rfs).strip().lower() not in VALID_REFINEMENT_STATUS:
        issues.append(f"refinement_status must be one of {VALID_REFINEMENT_STATUS}, got {rfs!r}")
    cs = meta.get("conversion_status")
    if cs is not None and str(cs).strip().lower() not in VALID_CONVERSION_STATUS:
        issues.append(f"conversion_status must be one of {VALID_CONVERSION_STATUS}, got {cs!r}")
    cps = meta.get("completion_status")
    if cps is not None and str(cps).strip().lower() not in VALID_COMPLETION_STATUS:
        issues.append(f"completion_status must be one of {VALID_COMPLETION_STATUS}, got {cps!r}")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "payload_type": "repair_metadata",
    }


def check_review_record_shape(record: dict[str, Any] | None) -> dict[str, Any]:
    """Phase 37: validate candidate review record shape. Read-only."""
    if not isinstance(record, dict):
        return {"valid": True, "issues": [], "payload_type": "review_record", "skipped": "not a dict"}
    issues: list[str] = []
    rs = record.get("review_status")
    if rs is not None and str(rs).strip().lower() not in VALID_REVIEW_STATUS:
        issues.append(f"review_status must be one of {VALID_REVIEW_STATUS}, got {rs!r}")
    rr = record.get("review_readiness")
    if rr is not None and str(rr).strip().lower() not in VALID_REVIEW_READINESS:
        issues.append(f"review_readiness must be one of {VALID_REVIEW_READINESS}, got {rr!r}")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "review_record"}


# Phase 40: runtime isolation posture
RUNTIME_ISOLATION_KEYS = (
    "isolation_posture",
    "file_scope_status",
    "network_scope_status",
    "secret_scope_status",
    "connector_scope_status",
    "mutation_scope_status",
    "rollback_posture",
    "isolation_reason",
    "runtime_restrictions",
    "allowed_execution_domains",
    "blocked_execution_domains",
    "destructive_risk_posture",
    "generated_at",
)
VALID_ISOLATION_POSTURE = ("weak", "bounded", "restricted", "isolated_planned", "error_fallback")


def check_runtime_isolation_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Phase 40: validate runtime isolation posture has required keys. Read-only."""
    if not isinstance(payload, dict):
        return {"valid": True, "issues": [], "payload_type": "runtime_isolation", "skipped": "not a dict"}
    issues: list[str] = []
    for k in RUNTIME_ISOLATION_KEYS:
        if k not in payload:
            issues.append(f"missing key: {k}")
    iso = payload.get("isolation_posture")
    if iso is not None and str(iso).strip().lower() not in VALID_ISOLATION_POSTURE:
        issues.append(f"isolation_posture must be one of {VALID_ISOLATION_POSTURE}, got {iso!r}")
    rr = payload.get("runtime_restrictions")
    if rr is not None and not isinstance(rr, list):
        issues.append("runtime_restrictions must be list")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "runtime_isolation"}


RELEASE_READINESS_KEYS = (
    "release_readiness_status",
    "critical_blockers",
    "review_items",
    "trace_links_present",
    "review_status_summary",
    "review_blocker_count",
    "review_required_count",
    "review_linkage_present",
)


def check_release_readiness_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Phase 38: validate release readiness has Phase 38 review fields when present. Read-only."""
    if not isinstance(payload, dict):
        return {"valid": True, "issues": [], "payload_type": "release_readiness", "skipped": "not a dict"}
    issues: list[str] = []
    for k in RELEASE_READINESS_KEYS:
        if k not in payload:
            issues.append(f"missing key: {k}")
    status = payload.get("release_readiness_status")
    if status is not None and str(status).strip().lower() not in ("ready", "blocked", "review_required", "error_fallback"):
        issues.append(f"release_readiness_status must be one of (ready, blocked, review_required, error_fallback), got {status!r}")
    rbc = payload.get("review_blocker_count")
    if rbc is not None and not isinstance(rbc, (int, float)):
        issues.append("review_blocker_count must be numeric")
    return {"valid": len(issues) == 0, "issues": issues, "payload_type": "release_readiness"}


def check_refs_in_record(record: dict[str, Any], *, ref_keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Check ref keys are list of str. Read-only. Phase 28: ref_keys param for patch (includes helix_id_refs)."""
    keys = ref_keys or REF_KEYS
    issues: list[str] = []
    for key in keys:
        val = record.get(key)
        if val is None:
            continue
        ok, msg = _check_refs_shape(val)
        if not ok:
            issues.append(f"{key}: {msg}")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "payload_type": "refs",
    }


def check_product_manifest_sections(manifest: dict[str, Any]) -> dict[str, Any]:
    """Check product manifest has required sections. Read-only. Phase 29: product ref keys."""
    required = (
        "product_id",
        "project_name",
        "status",
        "approval_requirements",
        "safety_summary",
        "risk_profile",
    )
    missing = _check_keys(manifest, required)
    refs_ok = check_refs_in_record(manifest, ref_keys=PRODUCT_REF_KEYS)
    return {
        "valid": len(missing) == 0 and refs_ok.get("valid", True),
        "missing_keys": missing,
        "ref_issues": refs_ok.get("issues", []),
        "payload_type": "product_manifest",
    }


def run_integrity_check(
    *,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Run deterministic integrity checks on recent-phase artifacts.
    Read-only; no side effects.
    """
    results: list[dict[str, Any]] = []
    all_valid = True

    try:
        from NEXUS.registry_dashboard import build_registry_dashboard_summary
        dash = build_registry_dashboard_summary()
    except Exception as e:
        return {
            "integrity_status": "error",
            "reason": str(e),
            "checks": [],
            "all_valid": False,
        }

    # Approval summary
    approval = dash.get("approval_summary") or {}
    r = check_approval_summary_shape(approval)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Product summary
    product = dash.get("product_summary") or {}
    r = check_product_summary_shape(product)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Autonomy summary
    autonomy = dash.get("autonomy_summary") or {}
    r = check_autonomy_summary_shape(autonomy)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # HELIX summary
    helix = dash.get("helix_summary") or {}
    r = check_helix_summary_shape(helix)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Patch proposal summary (Phase 23)
    patch_proposal = dash.get("patch_proposal_summary") or {}
    r = check_patch_proposal_summary_shape(patch_proposal)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Cross-artifact trace summary (Phase 27)
    trace_summary = dash.get("cross_artifact_trace_summary") or {}
    r = check_trace_summary_shape(trace_summary)
    r["source"] = "dashboard"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    execution_summary = dash.get("execution_package_execution_summary") or {}
    r = check_execution_package_hardening_summary_shape(execution_summary)
    r["source"] = "dashboard_execution_package_execution_summary"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    evaluation_summary = dash.get("execution_package_evaluation_summary") or {}
    r = check_execution_package_evaluation_summary_shape(evaluation_summary)
    r["source"] = "dashboard_execution_package_evaluation_summary"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    local_analysis_summary = dash.get("execution_package_local_analysis_summary") or {}
    r = check_execution_package_local_analysis_summary_shape(local_analysis_summary)
    r["source"] = "dashboard_execution_package_local_analysis_summary"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Phase 38: Release readiness shape (review-aware)
    release_readiness = dash.get("release_readiness_summary") or {}
    r = check_release_readiness_shape(release_readiness)
    r["source"] = "dashboard_release_readiness"
    results.append(r)
    if not r["valid"]:
        all_valid = False

    # Phase 40: Runtime isolation posture (from execution_environment_summary)
    exec_env = dash.get("execution_environment_summary") or {}
    isolation = exec_env.get("runtime_isolation_posture")
    if isolation:
        r = check_runtime_isolation_shape(isolation)
        r["source"] = "execution_environment_runtime_isolation"
        results.append(r)
        if not r["valid"]:
            all_valid = False

    # Phase 32: Surgeon repair_metadata shape (when present in helix journal)
    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.helix_registry import read_helix_journal_tail
        found = False
        for proj_key in list(PROJECTS.keys())[:2]:
            if found:
                break
            path = PROJECTS.get(proj_key, {}).get("path")
            if not path:
                continue
            tail = read_helix_journal_tail(project_path=path, n=5)
            for rec in tail:
                if found:
                    break
                for sr in rec.get("stage_results") or []:
                    if sr.get("stage") == "surgeon" and sr.get("repair_recommended"):
                        meta = sr.get("repair_metadata")
                        if meta:
                            r = check_repair_metadata_shape(meta)
                            r["source"] = "helix_surgeon_repair_metadata"
                            results.append(r)
                            if not r["valid"]:
                                all_valid = False
                            found = True
                            break
    except Exception:
        pass

    # Ref shape in sample records (Phase 28: autonomy + patch)
    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.autonomy_registry import read_autonomy_journal_tail
        from NEXUS.patch_proposal_registry import read_patch_proposal_journal_tail
        for proj_key in list(PROJECTS.keys())[:1]:
            path = PROJECTS.get(proj_key, {}).get("path")
            if path:
                tail = read_autonomy_journal_tail(project_path=path, n=1)
                if tail:
                    r = check_refs_in_record(tail[-1])
                    r["source"] = "autonomy_journal"
                    results.append(r)
                    if not r["valid"]:
                        all_valid = False
                patch_tail = read_patch_proposal_journal_tail(project_path=path, n=1)
                if patch_tail:
                    r = check_refs_in_record(patch_tail[-1], ref_keys=REF_KEYS_PATCH)
                    r["source"] = "patch_proposal_journal"
                    results.append(r)
                    if not r["valid"]:
                        all_valid = False
            break
    except Exception:
        pass

    try:
        from NEXUS.registry import PROJECTS
        from NEXUS.execution_package_registry import list_execution_package_journal_entries, read_execution_package

        for proj_key in list(PROJECTS.keys())[:2]:
            path = PROJECTS.get(proj_key, {}).get("path")
            if not path:
                continue
            rows = list_execution_package_journal_entries(project_path=path, n=1)
            if not rows:
                continue
            package_id = rows[0].get("package_id")
            if not package_id:
                continue
            pkg = read_execution_package(project_path=path, package_id=package_id)
            if pkg:
                r = check_execution_package_hardening_shape(pkg)
                r["source"] = "execution_package"
                results.append(r)
                if not r["valid"]:
                    all_valid = False
                r = check_execution_package_evaluation_shape(pkg)
                r["source"] = "execution_package_evaluation"
                results.append(r)
                if not r["valid"]:
                    all_valid = False
                r = check_execution_package_local_analysis_shape(pkg)
                r["source"] = "execution_package_local_analysis"
                results.append(r)
                if not r["valid"]:
                    all_valid = False
                break
    except Exception:
        pass

    return {
        "integrity_status": "ok" if all_valid else "issues_detected",
        "reason": "All checks passed." if all_valid else "Some checks failed.",
        "checks": results,
        "all_valid": all_valid,
    }


def run_integrity_check_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return run_integrity_check(**kwargs)
    except Exception as e:
        return {
            "integrity_status": "error",
            "reason": str(e),
            "checks": [],
            "all_valid": False,
        }
