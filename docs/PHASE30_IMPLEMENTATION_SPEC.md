# Phase 30 — HELIX Deepening: Implementation Specification

## 1. PHASE 30 ARCHITECTURE PLAN

### What already exists

- Architect: multi-approach generation via model call; _normalize_approach; approaches with approach_id, summary, pros, cons, risk_level, scalability
- Critic: correctness_risk, maintainability, scalability, hidden_failure_points
- Optimizer: performance, structure, safety, readability suggestions
- Surgeon: repair_metadata with repair_reason, severity, target_hint, has_patch_payload
- HELIX learning: stage_outcomes, success_class in downstream_effects
- HELIX summary: stage_distribution, surgeon_invocation_frequency

### What is being extended

- **Architect**: complexity, implementation_cost, recommended_when on approaches; selection_rationale, multi_approach_count
- **Critic**: testing_gaps, compatibility_risk in critique_evaluation
- **Optimizer**: implementation_sequencing; added to optimization_suggestions
- **Surgeon**: repair_strategy_category, missing_information_flags, recommended_next_actions when builder lacks patch
- **HELIX learning**: architect_approach_count, critic_repair_recommended, repair_strategy_category, has_patch_payload in downstream_effects
- **HELIX summary**: multi_approach_success_rate, repair_artifact_quality (repair_with_patch_count, repair_without_patch_count, repair_total)

### Why this is the safest path

- Additive only; no removal of existing fields
- No execution power added; no patch apply from Surgeon
- Structured outputs; deterministic where possible
- Honest about builder_no_patch when Surgeon cannot produce patch

---

## 2. FILES CREATED

| File | Purpose |
|------|---------|
| `tests/phase30_helix_deepening_test.py` | 7 tests for architect, critic, optimizer, surgeon, summary, registry |
| `docs/PHASE30_IMPLEMENTATION_SPEC.md` | This specification |

---

## 3. FILES MODIFIED

| File | Why |
|------|-----|
| `NEXUS/helix_stages.py` | Architect approach fields; Critic testing_gaps/compatibility_risk; Optimizer implementation_sequencing; Surgeon repair_metadata extension |
| `NEXUS/helix_registry.py` | normalize_helix_stage_result: selection_rationale, multi_approach_count, implementation_sequencing |
| `NEXUS/helix_pipeline.py` | Learning record: architect_approach_count, critic_repair_recommended, repair_strategy_category, has_patch_payload |
| `NEXUS/helix_summary.py` | multi_approach_success_rate, repair_artifact_quality |
| `NEXUS/integrity_checker.py` | HELIX_SUMMARY_KEYS: multi_approach_success_rate, repair_artifact_quality |
| `NEXUS/registry_dashboard.py` | helix_summary fallback: multi_approach_success_rate, repair_artifact_quality |

---

## 4. HELIX OUTPUT / CONTRACT EXTENSIONS

### Architect approach (extended)

- complexity, implementation_cost, recommended_when (optional strings)
- selection_rationale, multi_approach_count on stage result

### Critic critique_evaluation (extended)

- testing_gaps: list[str]
- compatibility_risk: "low" | "medium"

### Optimizer (extended)

- implementation_sequencing: list[str]
- optimization_suggestions["implementation_sequencing"]

### Surgeon repair_metadata (extended)

- repair_strategy_category: "patch_available" | "builder_no_patch"
- missing_information_flags: list[str]
- recommended_next_actions: list[str]

### Fallback

- helix_summary fallback includes multi_approach_success_rate: 0.0, repair_artifact_quality: {repair_with_patch_count: 0, repair_without_patch_count: 0, repair_total: 0}

---

## 5. RISKS

| Risk | Mitigation |
|------|------------|
| Breaking existing stage consumers | Additive fields only; existing keys unchanged |
| Overclaiming reasoning depth | Honest; still single model call for Architect |
| Surgeon applying patches | No change; Surgeon still does not apply |

---

## 6. TESTS / VALIDATION

```powershell
cd C:\FORGE
python tests/phase30_helix_deepening_test.py
```

Expected: 7/7 passed.

---

## 7. REMAINING LIMITATIONS

- Architect still uses single model call for approaches
- Critic/Optimizer are rule-based, not deep model evaluators
- Surgeon does not generate full patches when Builder lacks one; provides structured recommendations instead
- HELIX does not apply patches directly
- Learning remains append-only
