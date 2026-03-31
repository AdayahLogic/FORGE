"""
Phase 95 governed browser execution lane tests.

Run: python tests/phase95_browser_execution_playwright_lane_test.py
"""

from __future__ import annotations

import json
import shutil
import sys
import traceback
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
def _patched_aegis_allow():
    import AEGIS.aegis_core as aegis_core
    from AEGIS.aegis_contract import build_aegis_result

    original = aegis_core.evaluate_action_safe
    aegis_core.evaluate_action_safe = lambda request=None: build_aegis_result(
        aegis_decision="allow",
        aegis_reason="Allowed for governed browser test.",
        action_mode="execution",
        project_name="phase95proj",
        project_path=str((request or {}).get("project_path") or ""),
        workspace_valid=True,
        file_guard_status="allow",
    )
    try:
        yield
    finally:
        aegis_core.evaluate_action_safe = original


class _FakeLocator:
    def __init__(self, selector: str):
        self.selector = selector

    def all_inner_texts(self):
        return [f"text-for:{self.selector}"]


class _FakePage:
    def __init__(self, fail_on: str = ""):
        self.fail_on = fail_on
        self.actions: list[str] = []

    def set_default_timeout(self, timeout_ms: int):
        self.actions.append(f"timeout:{timeout_ms}")

    def goto(self, url: str, wait_until: str = "domcontentloaded"):
        self.actions.append(f"goto:{url}:{wait_until}")
        if self.fail_on == "goto":
            raise RuntimeError("forced_goto_failure")

    def wait_for_selector(self, selector: str):
        self.actions.append(f"wait:{selector}")

    def click(self, selector: str):
        self.actions.append(f"click:{selector}")

    def fill(self, selector: str, value: str):
        self.actions.append(f"fill:{selector}:{value}")

    def locator(self, selector: str):
        self.actions.append(f"locator:{selector}")
        return _FakeLocator(selector)

    def eval_on_selector_all(self, selector: str, script: str):
        self.actions.append(f"eval:{selector}")
        return [{"href": "https://example.com/contact", "text": "Contact"}]

    def screenshot(self, path: str, full_page: bool = True):
        self.actions.append(f"screenshot:{path}:{full_page}")
        Path(path).write_bytes(b"fake-png")


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.page = page

    def new_page(self):
        return self.page

    def close(self):
        return None


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self.page = page

    def new_context(self):
        return _FakeContext(self.page)

    def close(self):
        return None


class _FakeChromium:
    def __init__(self, page: _FakePage):
        self.page = page

    def launch(self, headless: bool = True):
        _ = headless
        return _FakeBrowser(self.page)


class _FakePlaywrightRunner:
    def __init__(self, page: _FakePage):
        self.page = page
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


def _make_sync_playwright(page: _FakePage):
    def _factory():
        return _FakePlaywrightRunner(page)

    return _factory


@contextmanager
def _patched_playwright_loader(*, fail_on: str = ""):
    import NEXUS.executor_backends.playwright_browser_executor as backend_mod

    original = backend_mod._load_playwright
    fake_page = _FakePage(fail_on=fail_on)
    backend_mod._load_playwright = lambda: _make_sync_playwright(fake_page)
    try:
        yield fake_page
    finally:
        backend_mod._load_playwright = original


def _browser_request(*, max_steps: int = 8):
    return {
        "allowed_domains": ["example.com"],
        "timeout_ms": 8000,
        "max_steps": max_steps,
        "headless": True,
        "operator_approved": True,
        "actions": [
            {"type": "open_url", "url": "https://example.com"},
            {"type": "wait_for_selector", "selector": "body"},
            {"type": "extract_text", "selector": "h1"},
            {"type": "extract_links", "selector": "a"},
            {"type": "capture_screenshot", "label": "landing"},
        ],
    }


def _write_package(project_path: Path, package_id: str, *, operation_budget_cap: float | None = None) -> str | None:
    from NEXUS.execution_package_registry import write_execution_package_safe

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "package_kind": "review_only_execution_envelope",
        "project_name": "phase95proj",
        "project_path": str(project_path),
        "run_id": "run-phase95",
        "created_at": "2026-03-31T00:00:00Z",
        "package_status": "review_pending",
        "review_status": "pending",
        "sealed": True,
        "seal_reason": "Governed browser execution package.",
        "runtime_target_id": "windows_review_package",
        "runtime_target_name": "windows_review_package",
        "execution_mode": "manual_only",
        "requested_action": "browser_execution",
        "requested_by": "workflow",
        "requires_human_approval": True,
        "approval_id_refs": ["appr-95"],
        "aegis_decision": "approval_required",
        "aegis_scope": "runtime_dispatch_only",
        "reason": "Governed browser task.",
        "dispatch_plan_summary": {"ready_for_dispatch": True},
        "routing_summary": {"runtime_node": "coder", "tool_name": "browser_playwright_executor"},
        "execution_summary": {"review_only": False, "can_execute": False},
        "command_request": {"request_type": "browser_execution", "task_type": "browser_execution", "summary": "Collect bounded browser evidence."},
        "candidate_paths": [],
        "expected_outputs": ["browser_evidence_manifest"],
        "review_checklist": ["Confirm bounded browser contract and approvals."],
        "rollback_notes": ["Review evidence and logs."],
        "runtime_artifacts": [],
        "metadata": {
            "executor_backend_id": "playwright_browser",
            "browser_execution_request": _browser_request(),
        },
        "decision_status": "approved",
        "decision_timestamp": "2026-03-31T00:01:00Z",
        "decision_actor": "operator_a",
        "decision_notes": "Approved",
        "decision_id": str(uuid.uuid4()),
        "eligibility_status": "eligible",
        "eligibility_timestamp": "2026-03-31T00:02:00Z",
        "eligibility_reason": {"code": "eligible", "message": "Eligible."},
        "eligibility_checked_by": "operator_b",
        "eligibility_check_id": str(uuid.uuid4()),
        "release_status": "released",
        "release_timestamp": "2026-03-31T00:03:00Z",
        "release_actor": "operator_c",
        "release_notes": "Released.",
        "release_id": str(uuid.uuid4()),
        "release_reason": {"code": "released", "message": "Released."},
        "release_version": "v1",
        "handoff_status": "authorized",
        "handoff_timestamp": "2026-03-31T00:04:00Z",
        "handoff_actor": "operator_d",
        "handoff_notes": "Authorized.",
        "handoff_id": str(uuid.uuid4()),
        "handoff_reason": {"code": "authorized", "message": "Authorized."},
        "handoff_version": "v1",
        "handoff_executor_target_id": "openclaw_browser",
        "handoff_executor_target_name": "OpenClaw Browser",
        "handoff_aegis_result": {},
        "execution_status": "pending",
    }
    if operation_budget_cap is not None:
        package["budget_caps"] = {
            "operation_budget_cap": operation_budget_cap,
            "project_budget_cap": 100.0,
            "session_budget_cap": 100.0,
            "kill_switch_enabled": True,
        }
    return write_execution_package_safe(str(project_path), package)


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        traceback.print_exc()
        return False


def test_browser_contract_validation_rejects_invalid():
    from NEXUS.browser_execution_contract import validate_browser_execution_request

    invalid = validate_browser_execution_request(
        {
            "allowed_domains": [],
            "actions": [{"type": "fill_selector", "selector": "#email", "value": "a@b.com"}],
            "operator_approved": False,
        }
    )
    assert invalid["status"] == "invalid"
    assert "allowed_domains_required" in invalid["errors"]
    assert "operator_approval_required_for_interactive_actions" in invalid["errors"]


def test_browser_task_submit_persists_contract_and_backend():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-browser-submit")
        submit_request = _browser_request()
        submit_request["actions"] = submit_request["actions"][:3]
        result = run_command(
            "browser_task_submit",
            project_path=str(tmp),
            execution_package_id="pkg-browser-submit",
            submit_actor="operator_browser",
            browser_request=submit_request,
        )
        assert result["status"] == "ok"
        package = read_execution_package(str(tmp), "pkg-browser-submit")
        assert package is not None
        assert package["execution_executor_backend_id"] == "playwright_browser"
        assert ((package.get("metadata") or {}).get("browser_lane") or {}).get("lane_status") == "configured"


def test_browser_execution_budget_kill_switch_blocks():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-budget-block", operation_budget_cap=0.00001)
        with _patched_aegis_allow():
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-budget-block",
                execution_actor="operator_browser",
            )
        assert result["status"] == "blocked"
        payload = result["payload"]["execution"]
        assert payload["execution_status"] == "blocked"
        assert payload["execution_reason"]["code"] == "budget_kill_switch_triggered"


def test_browser_execution_failure_behavior_persists_receipt():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-browser-fail")
        with _patched_aegis_allow(), _patched_playwright_loader(fail_on="goto"):
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-browser-fail",
                execution_actor="operator_browser",
            )
        assert result["status"] == "ok"
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "failed"
        assert execution["execution_receipt"]["failure_class"] == "runtime_execution_failure"
        assert execution["execution_receipt"]["result_status"] == "failed"


def test_browser_execution_success_receipts_evidence_and_bounded_actions():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import read_execution_package

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-browser-success")
        with _patched_aegis_allow(), _patched_playwright_loader() as fake_page:
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-browser-success",
                execution_actor="operator_browser",
            )
        assert result["status"] == "ok"
        execution = result["payload"]["execution"]
        assert execution["execution_status"] == "succeeded"
        assert execution["execution_receipt"]["result_status"] == "succeeded"
        package = read_execution_package(str(tmp), "pkg-browser-success")
        assert package is not None
        artifact = (package.get("runtime_artifacts") or [])[-1]
        manifest_ref = str(artifact.get("browser_evidence_manifest_ref") or "")
        assert manifest_ref
        manifest = json.loads(Path(manifest_ref).read_text(encoding="utf-8"))
        assert len(manifest.get("extracted_data") or []) >= 2
        assert len(manifest.get("step_summaries") or []) == 5
        assert any(item.startswith("goto:https://example.com") for item in fake_page.actions)

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-browser-bounded")
        from NEXUS.execution_package_registry import record_browser_execution_task_safe

        bounded_request = _browser_request(max_steps=2)
        bounded_request["actions"] = [
            {"type": "open_url", "url": "https://example.com"},
            {"type": "wait_for_selector", "selector": "body"},
            {"type": "extract_text", "selector": "h1"},
            {"type": "extract_links", "selector": "a"},
        ]
        update = record_browser_execution_task_safe(
            project_path=str(tmp),
            package_id="pkg-browser-bounded",
            submit_actor="operator_browser",
            browser_request=bounded_request,
        )
        assert update["status"] == "ok"
        with _patched_aegis_allow(), _patched_playwright_loader():
            result = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-browser-bounded",
                execution_actor="operator_browser",
            )
        assert result["status"] == "ok"
        package = read_execution_package(str(tmp), "pkg-browser-bounded")
        artifact = (package.get("runtime_artifacts") or [])[-1]
        manifest_ref = str(artifact.get("browser_evidence_manifest_ref") or "")
        manifest = json.loads(Path(manifest_ref).read_text(encoding="utf-8"))
        assert len(manifest.get("step_summaries") or []) == 2


def test_command_surface_browser_visibility_commands():
    from NEXUS.command_surface import run_command

    with _local_test_dir() as tmp:
        _write_package(tmp, "pkg-browser-visibility")
        with _patched_aegis_allow(), _patched_playwright_loader():
            execute = run_command(
                "execution_package_execute_request",
                project_path=str(tmp),
                execution_package_id="pkg-browser-visibility",
                execution_actor="operator_browser",
            )
        assert execute["status"] == "ok"
        status = run_command(
            "browser_execution_status",
            project_path=str(tmp),
            execution_package_id="pkg-browser-visibility",
        )
        receipts = run_command(
            "browser_execution_receipts",
            project_path=str(tmp),
            execution_package_id="pkg-browser-visibility",
        )
        evidence = run_command(
            "browser_execution_evidence",
            project_path=str(tmp),
            execution_package_id="pkg-browser-visibility",
        )
        lane = run_command(
            "browser_lane_status",
            project_path=str(tmp),
            execution_package_id="pkg-browser-visibility",
        )
        assert status["status"] == "ok"
        assert receipts["status"] == "ok"
        assert evidence["status"] == "ok"
        assert lane["status"] == "ok"
        assert receipts["payload"]["execution_receipt"]["result_status"] == "succeeded"
        assert evidence["payload"]["evidence"]["runtime_artifact"]["browser_lane"] == "playwright_governed_v1"


def main():
    tests = [
        test_browser_contract_validation_rejects_invalid,
        test_browser_task_submit_persists_contract_and_backend,
        test_browser_execution_budget_kill_switch_blocks,
        test_browser_execution_failure_behavior_persists_receipt,
        test_browser_execution_success_receipts_evidence_and_bounded_actions,
        test_command_surface_browser_visibility_commands,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
