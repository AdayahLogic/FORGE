## Repo Findings

- Runtime and package lifecycle statuses previously mixed planning, queueing, handoff, and execution semantics, which made it easy for "accepted/queued/prepared" to read like successful execution.
- Execution attempts did not have a durable first-class receipt journal tied to package IDs with verification outcomes.
- Verification intent existed in package metadata but did not consistently persist as canonical attempt/result records.
- Approval records lacked triage metadata (category, priority, batchability), so operator review surfaces had low differentiation and weak ranking.
- Command-surface output exposed package and dispatch details but did not provide a dedicated truth view or operator inbox prioritization from execution+approval signals.

## What Was Misleading Before

- Package creation, review queueing, and runtime acceptance could be interpreted as execution completion.
- "Execution status" was visible without an explicit truth state separating simulation/preparation/handoff from verified execution.
- Operator-facing review lacked strong stale/risk/batch-aware ranking, increasing undifferentiated review load.

## What Changed

- Added a canonical execution truth resolver and snapshot builder used across dispatcher, package lifecycle, workflow persistence, and command surface.
- Added durable execution receipt and verification registries (JSONL + safe append/read APIs) and linked them into execution package execution recording.
- Extended execution package normalized shape with `execution_truth_status`, `execution_receipt_id`, `verification_status`, `verification_id`, and `verification_summary`.
- Added approval triage metadata generation/persistence and built a triage summary service with ranking, stale detection, and batch grouping.
- Added operator inbox synthesis that prioritizes blocked execution, stale approvals, risky/external approvals, verification follow-up, and stop-condition escalations.
- Extended command surface with:
  - `execution_truth_status`
  - `execution_receipt_details`
  - `verification_status`
  - `approval_triage_status`
  - `operator_inbox`
  - plus truth-aware enrichment for `dispatch_status`, `execution_package_queue`, and `execution_package_details`.

## Truth Taxonomy

Implemented explicit statuses that separate orchestration from real execution:

- `simulated`
- `prepared`
- `queued_for_review`
- `approved_not_executed`
- `handed_off`
- `executed_unverified`
- `executed_verified`
- `failed`
- `blocked`
- `rolled_back`

These are resolved from dispatch/package/receipt/verification signals so acceptance, packaging, and handoff do not imply verified execution.

## Execution Receipt Design

New durable registry: `NEXUS/execution_receipt_registry.py`

- Journal-backed, append-safe, queryable receipts.
- Captures execution attempt facts including:
  - `receipt_id`
  - `mission_id`
  - `execution_package_id`
  - `executor_target_id`
  - `executor_backend_id`
  - `execution_actor`
  - `execution_started_at`
  - `execution_finished_at`
  - `execution_status`
  - `verification_status`
  - `rollback_status`
  - `changed_artifacts`
  - `receipt_summary`
  - `world_change_claims`
  - `verification_evidence`
  - `errors`
  - `followup_required`
- Integrated into package execution recording with structured degraded reporting when persistence fails.

## Verification Design

New durable registry: `NEXUS/execution_verification_registry.py`

- Persists verification records linked to receipts/packages.
- Explicitly tracks:
  - execution attempted/completed
  - artifacts produced
  - claimed world change
  - verification outcome
  - verification failure states
- Feeds truth resolution (`executed_unverified` vs `executed_verified`) and command-surface verification visibility.

## Approval Triage Design

New service: `NEXUS/approval_triage.py` plus schema fields in approval builder/registry.

- Categorization:
  - `risky_external`
  - `internal_controlled`
  - `internal_low_risk`
- Priority and focus scoring (risk, staleness, queue posture).
- Batchability via triage keys for safe low-risk internal groups.
- No hidden auto-approval for risky/external actions.

## Tests Run

- `python tests/phase95_execution_truth_and_triage_test.py` (4/4 passed)
- `python tests/phase47_execution_package_runtime_execution_bridge_test.py` (8/8 passed)
- `python tests/phase42_execution_package_review_surface_test.py` (4/4 passed)
- `python tests/phase39_approval_lifecycle_test.py` (7/7 passed)

## Known Risks

- Truth resolution is additive and depends on available signal quality; legacy projects with sparse historical data may remain in conservative/non-verified states until new receipts/verifications are written.
- Operator ranking heuristics are intentionally conservative and may need tuning with real-world load patterns.

## Backward Compatibility Notes

- Changes are additive and preserve existing workflow/package/approval flows.
- Existing status fields remain available; new truth/verification fields are layered in normalized records and command payloads.
- Safe wrappers and degraded reporting paths avoid hard-fail behavior when optional persistence layers encounter IO issues.
