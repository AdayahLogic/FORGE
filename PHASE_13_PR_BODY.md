## Summary
- Add a durable mission queue registry (`ops/mission_queue_registry.json`) with idempotent enqueue keys, queue item leases, bounded retry/backoff state, and persistent worker run metadata linked to mission/project/package identifiers.
- Integrate project autopilot execution with the durable queue: mission work is enqueued, worker leases are claimed/renewed, package pipeline outcomes are recorded as success/failure, and queue events keep receipt/integrity linkage (`execution_receipt_ref`, `verification_ref`, escalation refs).
- Add command-surface visibility endpoints (`mission_queue_status`, `worker_status`, `backpressure_status`, `stuck_work_items`) for operator observability of queue health, active workers, recovery posture, and pressure conditions.

## Queue design
- **Registry model:** append/update durable JSON registry with `queue_item_id`, `mission_id`, `project_id`, `package_id`, `task_type`, `priority`, `queue_status`, enqueue timestamps, lease owner/expiry, retry count/limit, backoff/cooldown fields, and idempotency key.
- **Idempotency + dedupe:** enqueue uses an explicit idempotency key and dedupes active/completed work items to prevent duplicate execution from naive retries.
- **Lease model:** workers claim bounded leases, can renew leases, release claimed work, and complete work with explicit success/failure transitions.

## Worker/lease model
- **Bounded claims:** claim path enforces global worker caps and per-project concurrency caps.
- **Fairness:** project-aware claim rotation uses `last_project_claimed` and per-project active lease counters to reduce starvation.
- **Lifecycle linkage:** worker runs track queue item, worker id, project, package, and completion reason for traceability.

## Recovery/backpressure rules
- **Crash recovery:** expired leases are recovered durably and converted into retry waits with exponential backoff; exhausted retries become terminal failed items.
- **Retry classification:** failures can be marked retryable/non-retryable, and retry windows are cooldown-gated by persisted next-retry timestamps.
- **Backpressure:** command-surface visibility reports overload state from queued/leased pressure vs bounded limits; kill-switch aware claim blocking is enforced.

## Linkage to missions/packages/receipts
- Queue items are linked to `mission_id`, `project_id`, and `package_id`.
- Autopilot pipeline writes queue completion data with package execution receipt log references and integrity verification states.
- Escalation paths preserve operator escalation reason references for blocked/escalated outcomes.

## Tests run
- `python -m compileall "NEXUS" "tests\phase95_durable_mission_queue_worker_orchestrator_test.py"`
- `python "tests\phase95_durable_mission_queue_worker_orchestrator_test.py"`
- `python "tests\phase53_project_autopilot_loop_test.py"`
- `python "tests\phase59_autonomy_stop_rails_test.py"`

## Safety notes
- Existing bounded stop-rails and iteration limits remain enforced.
- Execution package idempotency and package/receipt/integrity contracts remain intact.
- No unbounded worker swarm paths were added; claim caps are bounded and recoverable.
- Queue durability is persisted on disk (no in-memory-only orchestration path).
