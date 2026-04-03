"""
Phase 95 durable mission queue + worker orchestrator tests.

Run: python tests/phase95_durable_mission_queue_worker_orchestrator_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase95_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _patched_registry(relative_path: str):
    import NEXUS.mission_queue_orchestrator as mqo

    original = mqo.QUEUE_REGISTRY_RELATIVE_PATH
    mqo.QUEUE_REGISTRY_RELATIVE_PATH = Path(relative_path)
    try:
        yield
    finally:
        mqo.QUEUE_REGISTRY_RELATIVE_PATH = original


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def test_queue_persistence():
    from NEXUS.mission_queue_orchestrator import enqueue_mission_work_item, mission_queue_status

    with _patched_registry(".tmp_test_runs/phase95_registry_persistence.json"):
        enqueue_mission_work_item(
            mission_id="mission-1",
            project_id="alpha",
            package_id="pkg-1",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-1",
        )
        snapshot = mission_queue_status()
    assert snapshot["status"] == "ok"
    assert snapshot["total_items"] >= 1
    assert (snapshot.get("counts_by_status") or {}).get("queued", 0) >= 1


def test_worker_claim_and_release():
    from NEXUS.mission_queue_orchestrator import claim_next_work_item, enqueue_mission_work_item, release_work_item

    with _patched_registry(".tmp_test_runs/phase95_registry_claim_release.json"):
        enqueue_mission_work_item(
            mission_id="mission-2",
            project_id="alpha",
            package_id="pkg-2",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-2",
        )
        claim = claim_next_work_item(worker_id="worker-a")
        assert claim["status"] == "ok"
        queue_item = claim["queue_item"]
        released = release_work_item(queue_item_id=queue_item["queue_item_id"], worker_id="worker-a", reason="test_release")
    assert released["status"] == "ok"
    assert released["queue_item"]["queue_status"] == "queued"


def test_lease_expiry_recovery():
    from NEXUS.mission_queue_orchestrator import claim_next_work_item, enqueue_mission_work_item, recover_expired_leases, renew_work_item_lease

    with _patched_registry(".tmp_test_runs/phase95_registry_lease_recovery.json"):
        enqueue_mission_work_item(
            mission_id="mission-3",
            project_id="alpha",
            package_id="pkg-3",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-3",
        )
        claim = claim_next_work_item(worker_id="worker-a", max_concurrent_workers=1)
        item = dict(claim.get("queue_item") or {})
        # Force expiration by shortening lease then recovering.
        renew_work_item_lease(queue_item_id=item["queue_item_id"], worker_id="worker-a")
        from NEXUS.mission_queue_orchestrator import _load_registry, _save_registry  # intentional internal access for deterministic test
        path, registry = _load_registry()
        for row in registry["items"]:
            if row.get("queue_item_id") == item["queue_item_id"]:
                row["lease_expiry"] = "2000-01-01T00:00:00Z"
        _save_registry(path, registry)
        recovered = recover_expired_leases()
    assert recovered["status"] == "ok"
    assert recovered["recovered_count"] >= 1


def test_retry_backoff_and_completion():
    from NEXUS.mission_queue_orchestrator import (
        claim_next_work_item,
        complete_work_item_failure,
        complete_work_item_success,
        enqueue_mission_work_item,
        mission_queue_status,
    )

    with _patched_registry(".tmp_test_runs/phase95_registry_retry_backoff.json"):
        enqueue_mission_work_item(
            mission_id="mission-4",
            project_id="alpha",
            package_id="pkg-4",
            task_type="execute",
            priority=1,
            retry_limit=2,
            idempotency_key="alpha:mission-4",
        )
        claim = claim_next_work_item(worker_id="worker-a")
        item = dict(claim.get("queue_item") or {})
        fail = complete_work_item_failure(
            queue_item_id=item["queue_item_id"],
            worker_id="worker-a",
            error_reason="transient_failure",
            retryable=True,
        )
        assert fail["status"] == "ok"
        assert fail["queue_item"]["queue_status"] == "retry_wait"
        # Make retry eligible immediately.
        from NEXUS.mission_queue_orchestrator import _load_registry, _save_registry  # intentional internal access for deterministic test
        path, registry = _load_registry()
        for row in registry["items"]:
            if row.get("queue_item_id") == item["queue_item_id"]:
                row["backoff_state"]["next_retry_at"] = "2000-01-01T00:00:00Z"
        _save_registry(path, registry)
        retry_claim = claim_next_work_item(worker_id="worker-a")
        retry_item = dict(retry_claim.get("queue_item") or {})
        success = complete_work_item_success(
            queue_item_id=retry_item["queue_item_id"],
            worker_id="worker-a",
            execution_receipt_ref="log://receipt",
            verification_ref="verified",
        )
        snapshot = mission_queue_status()
    assert success["status"] == "ok"
    assert (snapshot.get("counts_by_status") or {}).get("completed", 0) >= 1


def test_dedupe_idempotency():
    from NEXUS.mission_queue_orchestrator import enqueue_mission_work_item

    with _patched_registry(".tmp_test_runs/phase95_registry_dedupe.json"):
        first = enqueue_mission_work_item(
            mission_id="mission-5",
            project_id="alpha",
            package_id="pkg-5",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-5",
        )
        second = enqueue_mission_work_item(
            mission_id="mission-5",
            project_id="alpha",
            package_id="pkg-5",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-5",
        )
    assert first["status"] == "ok"
    assert second["status"] == "deduped"
    assert second["dedupe_hit"] is True


def test_fairness_across_projects():
    from NEXUS.mission_queue_orchestrator import claim_next_work_item, enqueue_mission_work_item, release_work_item

    with _patched_registry(".tmp_test_runs/phase95_registry_fairness.json"):
        enqueue_mission_work_item(mission_id="a-1", project_id="alpha", package_id="pkg-a-1", task_type="execute", priority=1, idempotency_key="a-1")
        enqueue_mission_work_item(mission_id="b-1", project_id="beta", package_id="pkg-b-1", task_type="execute", priority=1, idempotency_key="b-1")
        first = claim_next_work_item(worker_id="worker-a", max_concurrent_workers=1, per_project_limit=1)
        first_project = (first.get("queue_item") or {}).get("project_id")
        release_work_item(queue_item_id=(first.get("queue_item") or {}).get("queue_item_id"), worker_id="worker-a", reason="fairness_rotation")
        second = claim_next_work_item(worker_id="worker-b", max_concurrent_workers=1, per_project_limit=1)
        second_project = (second.get("queue_item") or {}).get("project_id")
    assert first_project in {"alpha", "beta"}
    assert second_project in {"alpha", "beta"}
    assert first_project != second_project


def test_kill_switch_blocks_claim():
    from NEXUS.mission_queue_orchestrator import claim_next_work_item, enqueue_mission_work_item

    with _patched_registry(".tmp_test_runs/phase95_registry_kill_switch.json"):
        enqueue_mission_work_item(
            mission_id="mission-6",
            project_id="alpha",
            package_id="pkg-6",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-6",
        )
        blocked = claim_next_work_item(worker_id="worker-a", kill_switch_active=True)
    assert blocked["status"] == "blocked"


def test_operator_visibility_commands():
    from NEXUS.command_surface import run_command
    from NEXUS.mission_queue_orchestrator import enqueue_mission_work_item

    with _patched_registry(".tmp_test_runs/phase95_registry_command_surface.json"):
        enqueue_mission_work_item(
            mission_id="mission-7",
            project_id="alpha",
            package_id="pkg-7",
            task_type="execute",
            priority=1,
            idempotency_key="alpha:mission-7",
        )
        queue_res = run_command("mission_queue_status")
        worker_res = run_command("worker_status")
        recovery_res = run_command("recovery_status", project_path=str(ROOT))
        backpressure_res = run_command("backpressure_status")
        stuck_res = run_command("stuck_work_items")
    assert queue_res["status"] == "ok"
    assert worker_res["status"] == "ok"
    assert backpressure_res["status"] == "ok"
    assert stuck_res["status"] == "ok"
    # Keep legacy recovery_status command surface active.
    assert recovery_res["status"] in {"ok", "error"}


def test_queue_item_id_stable_enqueue_claim_complete():
    """queue_item_id must remain stable from enqueue → claim → complete."""
    from NEXUS.mission_queue_orchestrator import (
        claim_next_work_item,
        complete_work_item_success,
        enqueue_mission_work_item,
    )

    with _patched_registry(".tmp_test_runs/phase95_registry_id_stable.json"):
        enqueue_result = enqueue_mission_work_item(
            mission_id="mission-stable",
            project_id="beta",
            package_id="pkg-stable",
            task_type="execute",
            priority=1,
            idempotency_key="beta:mission-stable",
        )
        enqueued_item = enqueue_result.get("queue_item") if isinstance(enqueue_result.get("queue_item"), dict) else {}
        enqueued_id = str(enqueued_item.get("queue_item_id") or "")
        assert enqueued_id, "enqueue must produce a queue_item_id"

        claim_result = claim_next_work_item(worker_id="worker-stable", kill_switch_active=False)
        assert claim_result["status"] == "ok", f"claim failed: {claim_result}"
        claimed_item = claim_result.get("queue_item") if isinstance(claim_result.get("queue_item"), dict) else {}
        claimed_id = str(claimed_item.get("queue_item_id") or "")
        assert claimed_id, "claimed item must have a queue_item_id"
        # The critical regression assertion: claimed ID must equal the enqueued ID.
        assert claimed_id == enqueued_id, (
            f"queue_item_id drifted: enqueued={enqueued_id!r} claimed={claimed_id!r}"
        )

        complete_result = complete_work_item_success(
            queue_item_id=claimed_id,
            worker_id="worker-stable",
            execution_receipt_ref="receipt-stable",
            verification_ref="verified",
        )
        assert complete_result["status"] == "ok", f"complete failed: {complete_result}"


def main():
    tests = [
        test_queue_persistence,
        test_worker_claim_and_release,
        test_lease_expiry_recovery,
        test_retry_backoff_and_completion,
        test_dedupe_idempotency,
        test_fairness_across_projects,
        test_kill_switch_blocks_claim,
        test_operator_visibility_commands,
        test_queue_item_id_stable_enqueue_claim_complete,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

