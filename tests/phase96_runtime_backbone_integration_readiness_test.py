"""
Phase 96 runtime backbone + integration readiness tests.

Run: python tests/phase96_runtime_backbone_integration_readiness_test.py
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase96_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def _write_package(project_path: Path, package_id: str, **overrides):
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase96proj",
        "project_path": str(project_path),
        "run_id": "run-phase96",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_status": "review_pending",
        "review_status": "reviewed",
        "sealed": True,
        "runtime_target_id": "openclaw",
        "runtime_target_name": "openclaw",
        "requested_action": "adapter_dispatch_call",
        "requires_human_approval": True,
        "decision_status": "approved",
        "eligibility_status": "eligible",
        "release_status": "released",
        "handoff_status": "authorized",
        "handoff_executor_target_id": "openclaw",
        "handoff_executor_target_name": "openclaw",
        "execution_status": "pending",
        "execution_executor_backend_id": "openclaw",
        "mission_id": "msn-phase96",
        "mission_type": "project_delivery",
        "project_id": "proj-phase96",
        "build_status": "completed",
        "setup_required": False,
        "setup_status": "completed",
        "delivery_status": "ready",
        "delivery_requires_approval": True,
        "runtime_artifacts": [{"artifact_type": "execution_log", "log_ref": "phase96.log"}],
        "metadata": {},
    }
    package.update(overrides)
    path = write_execution_package_safe(str(project_path), package)
    assert path


def test_backend_registry_resolution_and_readiness_truth():
    from NEXUS.executor_backend_registry import build_executor_backend_registry_summary, build_executor_backend_status

    openclaw = build_executor_backend_status(backend_id="openclaw")
    assert openclaw["backend_status"] == "ok"
    assert openclaw["backend"]["backend_id"] == "openclaw"
    assert openclaw["backend"]["executor_type"] == "controlled_executor_backend"
    assert openclaw["backend"]["operator_review_required"] is True

    review = build_executor_backend_status(backend_id="windows_review_package")
    assert review["backend_status"] == "ok"
    assert review["backend"]["review_only"] is True
    assert review["backend"]["execution_capable"] is False

    summary = build_executor_backend_registry_summary()
    assert summary["backend_registry_status"] == "ok"
    assert summary["backend_count"] >= 5


def test_handoff_linkage_and_delivery_backbone_contracts():
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-phase96")
        package = read_execution_package(str(tmp), "pkg-phase96")
        assert package
        contract = package.get("executor_handoff_contract") or {}
        assert contract.get("mission_created_package") is True
        assert contract.get("targeted_executor_target_id") == "openclaw"
        assert contract.get("backend_acceptance_status") == "authorized"
        assert contract.get("backend_executed") is False
        assert contract.get("execution_receipt_exists") is False
        assert package.get("delivery_readiness_state") in {"ready_for_delivery_approval", "ready_for_handoff", "ready_for_internal_review"}


def test_delivery_readiness_transition_requires_evidence():
    from NEXUS.execution_package_registry import read_execution_package, record_execution_package_revenue_loop_safe

    with _local_test_dir() as tmp:
        _write_package(
            tmp,
            "pkg-delivery",
            delivery_status="delivered",
            runtime_artifacts=[],
            email_message_id="",
        )
        pkg = read_execution_package(str(tmp), "pkg-delivery")
        assert pkg
        assert pkg.get("delivery_completed_truth") is False
        assert pkg.get("delivery_evidence_present") is False

        result = record_execution_package_revenue_loop_safe(
            project_path=str(tmp),
            package_id="pkg-delivery",
            updates={
                "email_status": "sent",
                "email_message_id": "resend-msg-123",
                "delivery_status": "delivered",
            },
        )
        assert result["status"] == "ok"
        pkg2 = result["package"] or {}
        assert pkg2.get("delivery_evidence_present") is True
        assert pkg2.get("delivery_completed_truth") is True
        assert pkg2.get("delivery_verification_status") in {
            "pending",
            "evidence_present_unverified",
            "verified",
            "unverified",
            "failed",
        }


def test_integration_readiness_reporting():
    from NEXUS.integration_readiness_registry import build_integration_readiness_summary

    summary = build_integration_readiness_summary()
    assert summary["integration_readiness_status"] == "ok"
    assert summary["integration_count"] >= 8
    assert summary["degraded_count"] >= 1
    names = {str(row.get("integration_name") or "") for row in list(summary.get("integrations") or [])}
    assert "stripe" in names
    assert "twilio" in names
    assert "telegram" in names


def test_command_surface_runtime_delivery_and_integration_visibility():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-cmd-phase96")
        backend_res = run_command("runtime_backend_status", project_path=str(tmp), backend_id="openclaw")
        assert backend_res["status"] in {"ok", "error"}
        assert "backend" in backend_res["payload"]

        registry_res = run_command("runtime_backend_status", project_path=str(tmp))
        assert registry_res["status"] == "ok"
        assert registry_res["payload"]["backend_count"] >= 1

        integration_res = run_command("integration_readiness", project_path=str(tmp))
        assert integration_res["status"] == "ok"
        assert integration_res["payload"]["integration_count"] >= 1

        delivery_res = run_command("delivery_status", project_path=str(tmp), execution_package_id="pkg-cmd-phase96")
        assert delivery_res["status"] == "ok"
        assert "delivery_backbone" in delivery_res["payload"]

        handoff_res = run_command("executor_handoff_status", project_path=str(tmp), execution_package_id="pkg-cmd-phase96")
        assert handoff_res["status"] == "ok"
        assert "executor_handoff_contract" in handoff_res["payload"]

        verify_res = run_command("delivery_verification_status", project_path=str(tmp), execution_package_id="pkg-cmd-phase96")
        assert verify_res["status"] == "ok"
        assert "delivery_verification_status" in verify_res["payload"]


def main():
    tests = [
        test_backend_registry_resolution_and_readiness_truth,
        test_handoff_linkage_and_delivery_backbone_contracts,
        test_delivery_readiness_transition_requires_evidence,
        test_integration_readiness_reporting,
        test_command_surface_runtime_delivery_and_integration_visibility,
    ]
    passed = sum(1 for fn in tests if _run(fn.__name__, fn))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())

