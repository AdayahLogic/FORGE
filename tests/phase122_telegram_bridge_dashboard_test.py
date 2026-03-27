"""
Phase 122 Telegram bridge dashboard tests.

Run: python tests/phase122_telegram_bridge_dashboard_test.py
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _local_test_dir():
    base = ROOT / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"phase122_{uuid.uuid4().hex[:8]}"
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


def _project_map(project_path: Path) -> dict:
    return {
        "phase122proj": {
            "name": "phase122proj",
            "path": str(project_path),
            "agents": ["operator"],
        }
    }


@contextmanager
def _patched_projects(project_path: Path):
    mapping = _project_map(project_path)
    with patch.dict("NEXUS.registry.PROJECTS", mapping, clear=True), patch.dict("NEXUS.telegram_bridge.PROJECTS", mapping, clear=True):
        yield


def test_help_and_unknown_rejection():
    from NEXUS.telegram_bridge import TelegramCommandRouter

    router = TelegramCommandRouter()
    help_text = router.route("help")
    denied = router.route("drop database now")
    assert "Core" in help_text
    assert "Autopilot" in help_text
    assert "Command not allowed" in denied


def test_status_and_approvals_render_operator_friendly():
    from NEXUS.telegram_bridge import TelegramCommandRouter

    with _local_test_dir() as tmp, _patched_projects(tmp):
        def fake_run(command: str, **kwargs):
            if command == "dashboard_summary":
                return {"status": "ok", "payload": {"portfolio_status": "active"}}
            if command == "pending_approvals":
                return {"status": "ok", "payload": {"pending_count_total": 2, "recent_approvals": [{"approval_id": "a-1", "status": "pending"}]}}
            if command == "project_autopilot_status":
                return {
                    "status": "ok",
                    "payload": {
                        "autopilot": {
                            "autopilot_enabled": True,
                            "autopilot_status": "executing",
                            "autopilot_current_focus": "revenue_business_ops",
                            "autopilot_requires_operator_review": False,
                        }
                    },
                }
            if command == "execution_package_queue":
                return {"status": "ok", "payload": {"queue_rows": [{"package_id": "pkg-1", "mission_status": "executing"}]}}
            raise AssertionError(f"Unexpected command: {command}")

        with patch("NEXUS.telegram_bridge.run_command", side_effect=fake_run):
            router = TelegramCommandRouter()
            status_text = router.route("status")
            approvals_text = router.route("approvals")
        assert "Forge" in status_text
        assert "pending approvals: 2" in status_text
        assert "Approvals" in approvals_text
        assert "a-1" in approvals_text


def test_approve_deny_parsing_routes_to_patch_resolution():
    from NEXUS.telegram_bridge import TelegramCommandRouter

    calls: list[tuple[str, dict]] = []
    with _local_test_dir() as tmp, _patched_projects(tmp):
        def fake_run(command: str, **kwargs):
            calls.append((command, dict(kwargs)))
            if command == "approval_details":
                return {"status": "ok", "payload": {"approval": {"patch_id_ref": "patch-123"}}}
            if command in {"approve_patch_proposal", "reject_patch_proposal"}:
                return {"status": "ok", "summary": "resolved"}
            raise AssertionError(f"Unexpected command: {command}")

        with patch("NEXUS.telegram_bridge.run_command", side_effect=fake_run):
            router = TelegramCommandRouter()
            out1 = router.route("approve appr-1")
            out2 = router.route("deny appr-1")
        assert "decision: approved" in out1
        assert "decision: denied" in out2
        assert ("approve_patch_proposal", {"patch_id": "patch-123", "reason": "telegram_operator"}) in calls
        assert ("reject_patch_proposal", {"patch_id": "patch-123", "reason": "telegram_operator"}) in calls


def test_autopilot_on_off_commands():
    from NEXUS.telegram_bridge import TelegramCommandRouter

    with _local_test_dir() as tmp, _patched_projects(tmp):
        log: list[str] = []

        def fake_run(command: str, **kwargs):
            log.append(command)
            if command == "project_autopilot_status":
                return {"status": "ok", "payload": {"autopilot": {"autopilot_enabled": False, "autopilot_status": "idle", "autopilot_requires_operator_review": False}}}
            if command == "project_autopilot_start":
                return {"status": "ok", "summary": "started"}
            if command == "project_autopilot_stop":
                return {"status": "ok", "summary": "stopped"}
            raise AssertionError(f"Unexpected command: {command}")

        with patch("NEXUS.telegram_bridge.run_command", side_effect=fake_run):
            router = TelegramCommandRouter()
            on_text = router.route("autopilot on")
            off_text = router.route("autopilot off")
        assert "Autopilot Control" in on_text
        assert "Autopilot Control" in off_text
        assert "project_autopilot_start" in log
        assert "project_autopilot_stop" in log


def test_missions_summary_and_unsafe_passthrough_blocked():
    from NEXUS.telegram_bridge import TelegramCommandRouter

    with _local_test_dir() as tmp, _patched_projects(tmp):
        invoked = {"called": False}

        def fake_run(command: str, **kwargs):
            invoked["called"] = True
            if command == "execution_package_queue":
                return {
                    "status": "ok",
                    "payload": {
                        "queue_rows": [
                            {
                                "package_id": "pkg-1",
                                "mission_id": "m-1",
                                "mission_type": "project_delivery",
                                "mission_status": "executing",
                                "executor_route": "forge_internal",
                                "approval_queue_requires_initial_approval": True,
                                "mission_risk_level": "medium",
                                "autopilot_current_focus": "project_delivery",
                            }
                        ]
                    },
                }
            raise AssertionError(f"Unexpected command: {command}")

        with patch("NEXUS.telegram_bridge.run_command", side_effect=fake_run):
            router = TelegramCommandRouter()
            missions_text = router.route("missions")
            invoked["called"] = False
            denied = router.route("python -c \"import os; os.remove('x')\"")
        assert "Missions" in missions_text
        assert "m-1" in missions_text
        assert "Command not allowed" in denied
        assert invoked["called"] is False


def test_whitelist_enforcement_blocks_unapproved_chat_id():
    from NEXUS.telegram_bridge import TelegramBridge

    with _local_test_dir() as tmp, _patched_projects(tmp):
        sent: list[dict] = []

        def fake_post(token: str, method: str, payload: dict, timeout_seconds: float = 20.0):
            sent.append({"method": method, "payload": dict(payload)})
            return {"ok": True, "result": []}

        with patch("NEXUS.telegram_bridge._telegram_post", side_effect=fake_post):
            bridge = TelegramBridge(token="token", allowed_chat_ids={111}, poll_interval_seconds=1.0)
            bridge.offset_path = tmp / "offset.json"
            update = {
                "update_id": 5,
                "message": {
                    "chat": {"id": 999},
                    "text": "status",
                },
            }
            bridge.handle_update(update)
        assert sent == []
        persisted = json.loads((tmp / "offset.json").read_text(encoding="utf-8"))
        assert persisted["last_update_offset"] == 6


if __name__ == "__main__":
    tests = [
        ("help_and_unknown_rejection", test_help_and_unknown_rejection),
        ("status_and_approvals_render_operator_friendly", test_status_and_approvals_render_operator_friendly),
        ("approve_deny_parsing_routes_to_patch_resolution", test_approve_deny_parsing_routes_to_patch_resolution),
        ("autopilot_on_off_commands", test_autopilot_on_off_commands),
        ("missions_summary_and_unsafe_passthrough_blocked", test_missions_summary_and_unsafe_passthrough_blocked),
        ("whitelist_enforcement_blocks_unapproved_chat_id", test_whitelist_enforcement_blocks_unapproved_chat_id),
    ]
    ok = True
    for name, fn in tests:
        ok = _run(name, fn) and ok
    raise SystemExit(0 if ok else 1)
