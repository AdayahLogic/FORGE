"""
Phase 116-120 project conversion + build + delivery engine tests.

Run: python tests/phase116_120_project_delivery_engine_test.py
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
    path = base / f"phase116_{uuid.uuid4().hex[:8]}"
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


def _write_base_package(project_path: Path, package_id: str) -> None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    payload = {
        "package_id": package_id,
        "project_name": "phase116proj",
        "project_path": str(project_path),
        "created_at": "2026-03-26T00:00:00+00:00",
        "package_status": "review_pending",
        "review_status": "pending",
        "requires_human_approval": True,
        "deal_status": "closed_won",
        "lead_status": "converted",
        "lead_priority": "high",
        "urgency_level": "high",
        "offer_summary": "Deliver governed automation implementation and handoff.",
        "expected_outputs": ["code_changes", "tests", "docs"],
    }
    assert write_execution_package_safe(str(project_path), payload)


def test_deal_to_project_conversion_and_codex_build_mission():
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        package_id = "pkg-phase116-convert"
        _write_base_package(tmp, package_id)
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("deal_status") == "closed_won"
        assert package.get("project_id")
        assert package.get("project_status") == "initialized"
        assert package.get("build_required") is True
        assert package.get("build_status") == "pending"
        assert package.get("build_mission_id")
        assert package.get("build_executor") == "codex"
        assert package.get("executor_route") == "codex"
        assert package.get("mission_id")
        assert package.get("mission_type") == "project_delivery"
        assert "auto_merge" in list(package.get("mission_forbidden_actions") or [])


def test_setup_structure_is_packet_only_and_openclaw_ready():
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        package_id = "pkg-phase116-setup"
        _write_base_package(tmp, package_id)
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("setup_required") is True
        assert package.get("setup_status") in {"pending", "ready"}
        assert package.get("setup_executor") in {"openclaw", "operator"}
        assert package.get("setup_steps_summary")
        assert package.get("setup_environment_requirements")


def test_delivery_is_approval_gated_and_not_auto_delivered():
    from NEXUS.execution_package_registry import read_execution_package, write_execution_package_safe

    with _local_test_dir() as tmp:
        package_id = "pkg-phase116-delivery"
        _write_base_package(tmp, package_id)
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": package_id,
                "project_name": "phase116proj",
                "project_path": str(tmp),
                "deal_status": "closed_won",
                "build_status": "completed",
                "setup_required": False,
            },
        )
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("delivery_requires_approval") is True
        assert package.get("delivery_status") in {"pending", "ready"}
        assert package.get("delivery_status") != "delivered"


def test_post_delivery_follow_up_activates_after_delivery():
    from NEXUS.execution_package_registry import read_execution_package, write_execution_package_safe

    with _local_test_dir() as tmp:
        package_id = "pkg-phase116-post"
        _write_base_package(tmp, package_id)
        write_execution_package_safe(
            str(tmp),
            {
                "package_id": package_id,
                "project_name": "phase116proj",
                "project_path": str(tmp),
                "deal_status": "closed_won",
                "delivery_status": "delivered",
                "delivery_requires_approval": True,
            },
        )
        package = read_execution_package(str(tmp), package_id) or {}
        assert package.get("post_delivery_status") == "active"
        assert package.get("satisfaction_check_required") is True
        assert package.get("satisfaction_status") in {"unknown", "satisfied", "unsatisfied"}
        assert package.get("retention_follow_up_required") is True


def test_read_surfaces_include_project_build_setup_delivery_and_queues():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        package_id = "pkg-phase116-surfaces"
        _write_base_package(tmp, package_id)

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id=package_id)
        assert details["status"] == "ok"
        sections = details["payload"]["sections"]
        assert "project" in sections
        assert "build" in sections
        assert "setup" in sections
        assert "delivery" in sections
        assert "post_delivery" in sections

        queue = run_command("execution_package_queue", project_path=str(tmp), n=10)
        assert queue["status"] == "ok"
        payload = queue["payload"]
        assert "execution_package_queue" in payload
        assert "review_queue" in payload
        assert "projects_in_build" in payload["execution_package_queue"]
        assert "projects_ready_for_delivery" in payload["execution_package_queue"]
        assert "delivery_awaiting_approval" in payload["execution_package_queue"]
        assert "post_delivery_follow_ups" in payload["execution_package_queue"]
        assert "delivery_approvals" in payload["review_queue"]
        assert "high_risk_actions" in payload["review_queue"]


def main():
    tests = [
        test_deal_to_project_conversion_and_codex_build_mission,
        test_setup_structure_is_packet_only_and_openclaw_ready,
        test_delivery_is_approval_gated_and_not_auto_delivered,
        test_post_delivery_follow_up_activates_after_delivery,
        test_read_surfaces_include_project_build_setup_delivery_and_queues,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
