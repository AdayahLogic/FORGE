# Phase 28 — Forward Link Completion: Implementation Specification

## 1. PHASE 28 ARCHITECTURE PLAN

### What already exists

- Approval records with `context.patch_id` (from resolve_patch_proposal)
- Patch proposals with `approval_id_refs`, `helix_id_refs`, `product_id_refs`, `autonomy_id_refs`
- HELIX records with refs; patch creation from HELIX already stores `helix_id_refs`
- Autonomy records with `approval_id_refs`, `product_id_refs`
- Resolution records with `patch_id`, `approval_id`
- Learning records with `downstream_effects` (dict)

### What is being extended

- **ref_utils.py**: Normalized ref list handling (dedupe, coerce to str, safe defaults)
- **apply_patch_proposal**: Pass `approval_id` from resolution to apply resolution record
- **approval_registry**: Capture `patch_id_refs` from `context.patch_id` when writing
- **learning_models**: Add `patch_id_refs`, `approval_id_refs`, `helix_id_refs`, `autonomy_id_refs`
- **Lifecycle learning records**: Add refs when known (approve, reject, apply, stale, HELIX, autonomy)
- **patch/helix/autonomy registries**: Use `normalize_ref_list` for ref fields
- **cross_artifact_trace**: Use approval `patch_id_refs` and learning refs for linkage
- **integrity_checker**: Validate patch proposal refs including `helix_id_refs`

### Why this is the safest path

- Forward-only: no historical rewrite; no mutation of old records
- Capture only when data is available at creation/update time
- No fabrication; missing refs remain empty
- Normalized helpers ensure consistent shape; backward compatible

---

## 2. FILES CREATED

| File | Purpose |
|------|---------|
| `NEXUS/ref_utils.py` | normalize_ref_list, merge_ref_lists |
| `tests/phase28_forward_link_test.py` | ref_utils, approval, learning, patch, trace, integrity |
| `docs/PHASE28_IMPLEMENTATION_SPEC.md` | This specification |

---

## 3. FILES MODIFIED

| File | Why |
|------|-----|
| `NEXUS/command_surface.py` | Apply resolution gets approval_id; learning records get patch_id_refs, approval_id_refs |
| `NEXUS/approval_registry.py` | normalize_approval_record captures patch_id_refs from context |
| `NEXUS/learning_models.py` | Add patch_id_refs, approval_id_refs, helix_id_refs, autonomy_id_refs |
| `NEXUS/patch_proposal_registry.py` | Use normalize_ref_list for ref fields |
| `NEXUS/helix_registry.py` | Use normalize_ref_list for ref fields |
| `NEXUS/autonomy_registry.py` | Use normalize_ref_list for ref fields |
| `NEXUS/helix_pipeline.py` | Learning records get helix_id_refs, patch_id_refs, approval/autonomy/product refs |
| `NEXUS/bounded_autonomy_runner.py` | Learning record gets autonomy_id_refs, approval_id_refs, product_id_refs |
| `NEXUS/cross_artifact_trace.py` | Use approval patch_id_refs; use learning refs for linkage |
| `NEXUS/integrity_checker.py` | REF_KEYS_PATCH, check_refs_in_record ref_keys param, patch proposal ref check |

---

## 4. REF / LINK CONTRACT EXTENSIONS

### normalize_ref_list(ids, max_len=20) -> list[str]

- Returns [] if None, invalid, or empty
- Coerces elements to str; deduplicates (first occurrence wins)
- Truncates to max_len

### Forward-link capture model

- **Approval**: When context has patch_id, add to patch_id_refs
- **Resolution (apply)**: Pass approval_id from resolution when appending apply record
- **Learning**: Add patch_id_refs, approval_id_refs, helix_id_refs, autonomy_id_refs when known at write time

### Fallback

- Ref fields default to []; normalize_ref_list returns [] for invalid input
- Learning model defaults new ref fields to []

---

## 5. RISKS

| Risk | Mitigation |
|------|-------------|
| Breaking existing readers | Additive fields only; ref fields already list-shaped |
| Fabricating links | Only capture when data exists at creation/update |
| Historical mutation | No rewrite of journals; only new writes capture refs |

---

## 6. TESTS / VALIDATION

```powershell
cd C:\FORGE
python tests/phase28_forward_link_test.py
```

Expected: 7/7 passed.

---

## 7. REMAINING LIMITATIONS

- Historical artifacts remain partially linked
- Learning still append-only, not adaptive
- No automatic backfill of old records
- Product manifest refs not extended (approval_refs only)
