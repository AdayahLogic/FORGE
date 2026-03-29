"""
Phase 95 execution truth + receipt + triage tests.

Run: python tests/phase95_execution_truth_and_triage_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
def _patched_aegis(result: dict):
    import AEGIS.aegis_core as aegis_core

    original = aegis_core.evaluate_action_safe
    aegis_core.evaluate_action_safe = lambda request=None: result
    try:
        yield
    finally:
        aegis_core.evaluate_action_safe = original


@contextmanager
def _patched_executor(result: dict):
    import NEXUS.execution_package_executor as executor_mod

    original = executor_mod.execute_execution_package_safe
    executor_mod.execute_execution_package_safe = lambda **kwargs: result
    try:
        yield
    finally:
        executor_mod.execute_execution_package_safe = original


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_executable_package(project_path: Path, package_id: str) -> str:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase95proj",
        "project_path": str(project_path),
        "run_id": "run-phase95",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_status": "review_pending",
        "review_status": "reviewed",
        "sealed": True,
        "runtime_target_id": "local",
        "runtime_target_name": "local",
        "requested_action": "adapter_dispatch_call",
        "requires_human_approval": False,
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "handoff_executor_target_id": "local",
        "handoff_executor_target_name": "local",
        "execution_status": "pending",
        "execution_summary": {"can_execute": False, "review_only": True},
        "command_request": {"task_type": "coder", "summary": "phase95 task"},
        "candidate_paths": ["src/file.py"],
        "rollback_notes": ["rollback if needed"],
        "runtime_artifacts": [],
        "metadata": {"openclaw_active": False},
    }
    path = write_execution_package_safe(str(project_path), package)
    assert path
    return path


def test_truth_separation_model():
    from NEXUS.execution_truth import resolve_dispatch_truth, resolve_package_truth

    simulated = resolve_dispatch_truth(
        dispatch_status="accepted",
        dispatch_result={"status": "accepted", "execution_status": "simulated_execution", "execution_mode": "safe_simulation"},
    )
    assert simulated == "simulated"

    unverified = resolve_package_truth(
        {"execution_status": "succeeded", "verification_status": "pending", "handoff_status": "authorized"}
    )
    assert unverified == "executed_unverified"

    verified = resolve_package_truth(
        {"execution_status": "succeeded", "verification_status": "verified", "handoff_status": "authorized"}
    )
    assert verified == "executed_verified"


def test_execution_receipt_and_verification_persistence():
    from AEGIS.aegis_contract import build_aegis_result
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_execution_safe
    from NEXUS.execution_receipt_registry import read_execution_receipt_journal_tail
    from NEXUS.execution_verification_registry import read_execution_verification_journal_tail

    with _local_test_dir() as tmp:
        _write_executable_package(tmp, "pkg-phase95")
        aegis = build_aegis_result(
            aegis_decision="allow",
            aegis_reason="allowed",
            action_mode="execution",
            project_name="phase95proj",
            project_path=str(tmp),
            workspace_valid=True,
            file_guard_status="allow",
        )
        exec_result = {
            "execution_status": "succeeded",
            "execution_reason": {"code": "succeeded", "message": "ok"},
            "execution_receipt": {
                "result_status": "succeeded",
                "exit_code": 0,
                "log_ref": str(tmp / "state" / "execution_runs" / "phase95.log"),
                "files_touched_count": 1,
                "artifacts_written_count": 1,
            },
            "rollback_status": "not_needed",
            "rollback_timestamp": "",
            "rollback_reason": {"code": "", "message": ""},
            "runtime_artifact": {"artifact_type": "execution_log", "log_ref": "phase95.log"},
            "execution_finished_at": datetime.now(timezone.utc).isoformat(),
        }
        with _patched_aegis(aegis), _patched_executor(exec_result):
            result = record_execution_package_execution_safe(
                project_path=str(tmp),
                package_id="pkg-phase95",
                execution_actor="phase95_operator",
            )
        assert result["status"] == "ok"
        package = read_execution_package(str(tmp), "pkg-phase95")
        assert package
        assert package["execution_receipt_id"]
        assert package["verification_id"]
        assert package["verification_status"] in ("verified", "unverified")
        assert package["execution_truth_status"] in ("executed_unverified", "executed_verified")
        receipts = read_execution_receipt_journal_tail(project_path=str(tmp), n=20)
        assert receipts
        assert receipts[-1]["execution_package_id"] == "pkg-phase95"
        verifications = read_execution_verification_journal_tail(project_path=str(tmp), n=20)
        assert verifications
        assert verifications[-1]["execution_attempted"] is True
        assert verifications[-1]["execution_completed"] is True


def test_approval_triage_grouping_and_stale_priority():
    from NEXUS.approval_registry import append_approval_record_safe
    from NEXUS.approval_triage import build_approval_triage_summary_safe

    with _local_test_dir() as tmp:
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat()
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "appr-old",
                "project_name": "phase95proj",
                "timestamp": old_ts,
                "status": "pending",
                "approval_type": "internal_note",
                "reason": "Old pending approval",
                "risk_level": "low",
                "sensitivity": "low",
                "triage_batchable": True,
                "triage_batch_key": "internal_low_risk:internal_note:local",
            },
        )
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "appr-new",
                "project_name": "phase95proj",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "approval_type": "internal_note",
                "reason": "New pending approval",
                "risk_level": "low",
                "sensitivity": "low",
                "triage_batchable": True,
                "triage_batch_key": "internal_low_risk:internal_note:local",
            },
        )
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "appr-new-2",
                "project_name": "phase95proj",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "approval_type": "internal_note",
                "reason": "Another new pending approval",
                "risk_level": "low",
                "sensitivity": "low",
                "triage_batchable": True,
                "triage_batch_key": "internal_low_risk:internal_note:local",
            },
        )
        summary = build_approval_triage_summary_safe(project_path=str(tmp), n=50)
        assert summary["triage_status"] == "ok"
        assert summary["pending_count"] == 3
        assert summary["stale_pending_count"] >= 1
        assert len(summary["batch_groups"]) >= 1


def test_command_surface_truth_visibility_and_operator_inbox():
    from NEXUS.approval_registry import append_approval_record_safe
    from NEXUS.command_surface import run_command
    from NEXUS.execution_receipt_registry import append_execution_receipt_safe
    from NEXUS.execution_verification_registry import append_execution_verification_safe
    from NEXUS.project_state import save_project_state

    with _local_test_dir() as tmp:
        _write_executable_package(tmp, "pkg-cmd")
        append_execution_receipt_safe(
            project_path=str(tmp),
            record={
                "receipt_id": "receipt-cmd",
                "project_name": "phase95proj",
                "execution_package_id": "pkg-cmd",
                "execution_actor": "phase95_operator",
                "execution_started_at": datetime.now(timezone.utc).isoformat(),
                "execution_finished_at": datetime.now(timezone.utc).isoformat(),
                "execution_status": "succeeded",
                "verification_status": "pending",
                "changed_artifacts": [{"artifact_type": "execution_log"}],
                "world_change_claims": ["runtime_artifacts_updated"],
            },
        )
        append_execution_verification_safe(
            project_path=str(tmp),
            record={
                "verification_id": "verify-cmd",
                "receipt_id": "receipt-cmd",
                "execution_package_id": "pkg-cmd",
                "verification_status": "unverified",
                "execution_attempted": True,
                "execution_completed": True,
                "artifacts_produced": True,
                "claimed_world_change": True,
                "verified": False,
                "verification_failed": False,
                "verification_summary": "Pending manual verification.",
            },
        )
        append_approval_record_safe(
            project_path=str(tmp),
            record={
                "approval_id": "appr-cmd",
                "project_name": "phase95proj",
                "status": "pending",
                "approval_type": "execution_gate",
                "reason": "Operator review required",
                "risk_level": "low",
                "sensitivity": "low",
            },
        )
        save_project_state(
            project_path=str(tmp),
            active_project="phase95proj",
            notes="",
            architect_plan=None,
            task_queue=[],
            coder_output_path=None,
            implementation_file_path=None,
            test_report_path=None,
            docs_output_path=None,
            execution_report_path=None,
            workspace_report_path=None,
            operator_log_path=None,
            supervisor_report_path=None,
            supervisor_decision=None,
            autonomous_cycle_report_path=None,
            autonomous_cycle_summary=None,
            computer_use_report_path=None,
            computer_use_summary=None,
            tool_execution_report_path=None,
            tool_execution_summary=None,
            file_modification_report_path=None,
            file_modification_summary=None,
            diff_patch_report_path=None,
            diff_patch_summary=None,
            agent_routing_report_path=None,
            agent_routing_summary=None,
            execution_bridge_report_path=None,
            execution_bridge_summary=None,
            engine_registry_report_path=None,
            engine_registry_summary=None,
            capability_registry_report_path=None,
            capability_registry_summary=None,
            terminal_report_path=None,
            terminal_summary=None,
            browser_research_report_path=None,
            browser_research_summary=None,
            full_automation_report_path=None,
            full_automation_summary=None,
            execution_package_id="pkg-cmd",
            execution_package_path=str(tmp / "state" / "execution_packages" / "pkg-cmd.json"),
            dispatch_status="accepted",
            dispatch_result={"status": "accepted", "execution_status": "queued", "execution_mode": "manual_only"},
            runtime_execution_status="queued",
            review_queue_entry={"queue_status": "queued", "queue_type": "approval", "queue_reason": "Approval pending."},
            run_id="run-phase95",
        )

        truth_res = run_command("execution_truth_status", project_path=str(tmp))
        assert truth_res["status"] == "ok"
        assert truth_res["payload"]["execution_truth_status"] in (
            "simulated",
            "prepared",
            "queued_for_review",
            "approved_not_executed",
            "handed_off",
            "executed_unverified",
            "executed_verified",
        )

        receipt_res = run_command("execution_receipt_details", project_path=str(tmp), execution_package_id="pkg-cmd")
        assert receipt_res["status"] == "ok"
        assert (receipt_res["payload"]["receipt"] or {}).get("receipt_id") == "receipt-cmd"

        verification_res = run_command("verification_status", project_path=str(tmp), execution_package_id="pkg-cmd")
        assert verification_res["status"] == "ok"
        assert verification_res["payload"]["verification"]["verification_status"] in ("unverified", "verified", "failed", "pending")

        triage_res = run_command("approval_triage_status", project_path=str(tmp))
        assert triage_res["status"] == "ok"
        assert triage_res["payload"]["pending_count"] >= 1

        inbox_res = run_command("operator_inbox", project_path=str(tmp))
        assert inbox_res["status"] in ("ok", "error")
        assert "inbox_items" in inbox_res["payload"]


def main():
    tests = [
        test_truth_separation_model,
        test_execution_receipt_and_verification_persistence,
        test_approval_triage_grouping_and_stale_priority,
        test_command_surface_truth_visibility_and_operator_inbox,
    ]
    passed = sum(1 for fn in tests if _run(fn.__name__, fn))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
