# Phase 27 — Cross-Artifact Trace Completion: Implementation Specification

## 1. PHASE 27 ARCHITECTURE PLAN

### What already exists

| Component | Location | Reused |
|-----------|----------|--------|
| Approval journal | NEXUS.approval_registry | read_approval_journal_tail |
| Patch proposal journal | NEXUS.patch_proposal_registry | read_patch_proposal_journal_tail, read_patch_proposal_resolution_tail, get_latest_resolution_for_patch |
| HELIX journal | NEXUS.helix_registry | read_helix_journal_tail |
| Autonomy journal | NEXUS.autonomy_registry | read_autonomy_journal_tail |
| Product manifest | NEXUS.product_builder | build_product_manifest_safe |
| Learning journal | NEXUS.learning_writer | read_learning_journal_tail |
| Ref fields | patch (approval_id_refs, helix_id_refs, product_id_refs, autonomy_id_refs), helix (approval_id_refs, autonomy_id_refs, product_id_refs), autonomy (approval_id_refs, product_id_refs) | Read-only |
| Resolution records | patch_proposal_resolution | approval_id ↔ patch_id linkage |
| Integrity checker | NEXUS.integrity_checker | Extended with trace shape check |

### What is being extended

- **New module**: `cross_artifact_trace.py` — read-only builder that aggregates IDs and linkage from journals
- **Command surface**: `artifact_trace` command
- **Dashboard**: `cross_artifact_trace_summary` key
- **Integrity checker**: `check_trace_summary_shape`, `TRACE_SUMMARY_KEYS`

### Why this is the safest path

- Read-only: no writes, no mutations, no execution
- Uses only real journal data; no fabrication
- Link completeness derived from actual refs in records
- Missing links reported honestly when expected linkage is absent
- Partial trace is acceptable; `trace_status="partial"` when links are incomplete
- No historical backfill; no auto-repair of refs

---

## 2. FILES TO CREATE

| File | Purpose |
|------|---------|
| `NEXUS/cross_artifact_trace.py` | Trace contract, build_cross_artifact_trace, build_cross_artifact_trace_safe, _fallback_trace |
| `tests/phase27_cross_artifact_trace_test.py` | Contract shape, safe wrapper, fallback, command, dashboard, integrity, no-fabrication |
| `docs/PHASE27_IMPLEMENTATION_SPEC.md` | This specification |

---

## 3. FILES TO MODIFY

| File | Why |
|------|-----|
| `NEXUS/command_surface.py` | Add artifact_trace to SUPPORTED_COMMANDS; add handler calling build_cross_artifact_trace_safe |
| `NEXUS/registry_dashboard.py` | Add _build_cross_artifact_trace_for_dashboard; add cross_artifact_trace_summary to dashboard output |
| `NEXUS/integrity_checker.py` | Add TRACE_SUMMARY_KEYS, check_trace_summary_shape; run trace shape check in run_integrity_check |

---

## 4. TRACE CONTRACT SHAPE

### Exact structure

```python
{
    "trace_status": "ok" | "partial" | "error_fallback",
    "project_name": str | None,
    "approval_ids": list[str],
    "patch_ids": list[str],
    "helix_ids": list[str],
    "autonomy_ids": list[str],
    "product_ids": list[str],
    "learning_record_refs": list[str],
    "link_completeness": {
        "approval_to_patch": bool,
        "patch_to_helix": bool,
        "patch_to_product": bool,
        "autonomy_to_product": bool,
        "helix_to_autonomy": bool,
    },
    "missing_links": list[str],
    "trace_reason": str,
    "generated_at": str,
    "artifact_counts": {
        "approvals": int,
        "patches": int,
        "helix_runs": int,
        "autonomy_runs": int,
        "products": int,
        "learning_records": int,
    },
}
```

### Completeness / missing-link model

- **link_completeness**: True only when real data shows linkage (e.g. patch has helix_id_refs → patch_to_helix True)
- **missing_links**: Human-readable strings when expected linkage is absent (e.g. "No approval-to-patch linkage found.")
- **trace_status**: "ok" when no missing_links; "partial" when missing_links or empty; "error_fallback" on failure

### Fallback shape

Same keys as normal contract. Values:

```python
{
    "trace_status": "error_fallback",
    "project_name": <passed or None>,
    "approval_ids": [],
    "patch_ids": [],
    "helix_ids": [],
    "autonomy_ids": [],
    "product_ids": [],
    "learning_record_refs": [],
    "link_completeness": {all False},
    "missing_links": [reason],
    "trace_reason": reason,
    "generated_at": str,
    "artifact_counts": {all 0},
}
```

---

## 5. RISKS

| Risk | Mitigation |
|------|------------|
| Fabricating links | Only use IDs from journals; no placeholder IDs |
| Breaking journal reads | Use existing read_*_tail functions; no new I/O patterns |
| Overclaiming completeness | trace_status="partial" when missing_links; link_completeness only True when refs exist |
| Backward compatibility | Additive only; no renames; new fields optional for consumers |

---

## 6. IMPLEMENTATION

See `NEXUS/cross_artifact_trace.py` (full), `NEXUS/command_surface.py` (artifact_trace handler), `NEXUS/registry_dashboard.py` (_build_cross_artifact_trace_for_dashboard), `NEXUS/integrity_checker.py` (TRACE_SUMMARY_KEYS, check_trace_summary_shape), `tests/phase27_cross_artifact_trace_test.py` (full).

---

## 7. TESTS / VALIDATION

### Commands

```powershell
cd C:\FORGE
python tests/phase27_cross_artifact_trace_test.py
```

```powershell
python -c "from NEXUS.command_surface import run_command; r=run_command('artifact_trace'); print(r.get('payload',{}).get('trace_status'))"
```

### Expected outcomes

- `phase27_cross_artifact_trace_test.py`: 7/7 passed, exit 0
- artifact_trace: payload has trace_status, link_completeness, missing_links

### What each test proves

| Test | Proves |
|------|--------|
| test_trace_contract_shape | All required keys; trace_status in allowed set; types correct |
| test_trace_safe_never_raises | Safe wrapper never raises |
| test_trace_fallback_shape | Fallback preserves contract |
| test_artifact_trace_command | Command returns expected shape |
| test_dashboard_includes_trace | Dashboard has cross_artifact_trace_summary |
| test_integrity_check_trace_shape | Integrity checker validates trace shape |
| test_trace_no_fabrication | IDs are strings only; no empty placeholders |

---

## 8. REMAINING LIMITATIONS

| Limitation | Status |
|------------|--------|
| Ref linkage still partial | Honest; trace reports missing_links |
| Learning not adaptive | Unchanged; learning linkage is best-effort only |
| No configurable staleness by approval type | Unchanged |
| No explicit expiry timestamp on approvals | Unchanged |
| No forward linkage when proposals created | Not in scope; Phase 27 is read-only visibility |
| advisory_only / safe_patch apply route | Unchanged |

---

## 9. FINAL ASSESSMENT

Phase 27 is implemented and safe to accept:

- Cross-artifact trace contract and builder in place
- artifact_trace command and dashboard integration added
- Integrity checker extended for trace shape
- Tests pass; no fabrication; honest partial trace
