# Phase 29 — Product / Trace Ref Alignment: Implementation Specification

## 1. PHASE 29 ARCHITECTURE PLAN

### What already exists

- Product manifest: `approval_refs`, `autonomy_refs`, `learning_insight_refs` (often empty)
- Product summary: `learning_linkage_present`, `approval_linkage_present`, `autonomy_linkage_present`
- Release readiness: `trace_links_present["product_linked"]` from learning/autonomy
- Cross-artifact trace: `patch_to_product` from patch.product_id_refs
- product_registry: `normalize_product_manifest` (core fields only)

### What is being extended

- **product_builder**: Populate `approval_id_refs`, `patch_id_refs`, `helix_id_refs`, `autonomy_id_refs`, `learning_insight_refs` from real journals; add `get_product_refs()` helper
- **product_registry**: Extend `normalize_product_manifest` to include ref fields; support both old and new names
- **product_summary**: Add `patch_linkage_present`, `helix_linkage_present`; check both old and new ref fields
- **release_readiness**: Expand `product_linked` to include approval, patch, helix linkage
- **cross_artifact_trace**: Use product `patch_id_refs` for `patch_to_product` linkage
- **integrity_checker**: PRODUCT_REF_KEYS, PRODUCT_SUMMARY_KEYS extensions, product manifest ref check

### Why this is the safest path

- Additive only; `approval_refs` and `autonomy_refs` retained for backward compat
- Normalized access via `get_product_refs()`; no aggressive renames
- Refs populated only when real data exists from journals
- No historical rewrite; no fabrication

---

## 2. FILES CREATED

| File | Purpose |
|------|---------|
| `tests/phase29_product_trace_ref_test.py` | 6 tests for manifest, get_product_refs, summary, registry, release readiness, integrity |
| `docs/PHASE29_IMPLEMENTATION_SPEC.md` | This specification |

---

## 3. FILES MODIFIED

| File | Why |
|------|-----|
| `NEXUS/product_builder.py` | Populate refs from journals; add `get_product_refs()`; add new ref fields to manifest |
| `NEXUS/product_registry.py` | Extend `normalize_product_manifest` with ref fields; use ref_utils |
| `NEXUS/product_summary.py` | Add `patch_linkage_present`, `helix_linkage_present`; check both old/new ref names |
| `NEXUS/release_readiness.py` | Expand `product_linked` to include approval, patch, helix |
| `NEXUS/cross_artifact_trace.py` | Use product `patch_id_refs` for `patch_has_product` |
| `NEXUS/integrity_checker.py` | PRODUCT_REF_KEYS, PRODUCT_SUMMARY_KEYS; product manifest ref validation |
| `NEXUS/registry_dashboard.py` | Add `patch_linkage_present`, `helix_linkage_present` to product summary fallback |

---

## 4. PRODUCT REF / TRACE CONTRACT EXTENSIONS

### get_product_refs(manifest) -> dict[str, list[str]]

Returns normalized ref lists:
- `approval_id_refs` (from approval_id_refs or approval_refs)
- `patch_id_refs`
- `helix_id_refs`
- `autonomy_id_refs` (from autonomy_id_refs or autonomy_refs)
- `learning_insight_refs`

### Manifest extensions

New fields (additive): `approval_id_refs`, `patch_id_refs`, `helix_id_refs`, `autonomy_id_refs`. Existing `approval_refs`, `autonomy_refs`, `learning_insight_refs` retained and populated from journals.

### Summary extensions

- `patch_linkage_present`: bool (any product has patch_id_refs)
- `helix_linkage_present`: bool (any product has helix_id_refs)

### Fallback

Product summary fallback and product_manifest_safe fallback include all new fields with safe defaults (False, []).

---

## 5. RISKS

| Risk | Mitigation |
|------|------------|
| Breaking callers of approval_refs/autonomy_refs | Kept; populated from same source as approval_id_refs |
| Old manifests on disk | normalize_product_manifest adds defaults for missing ref fields |
| Overclaiming linkage | Only true when ref lists non-empty |

---

## 6. TESTS / VALIDATION

```powershell
cd C:\FORGE
python tests/phase29_product_trace_ref_test.py
```

Expected: 6/6 passed.

---

## 7. REMAINING LIMITATIONS

- Historical manifests on disk may lack ref fields until next build
- Product registry read path normalizes on read; write path includes refs
- Learning linkage still best-effort (learning_insight_refs from journal refs)
