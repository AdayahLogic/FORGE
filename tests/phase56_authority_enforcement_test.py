"""
Phase 56 authority enforcement tests.

Run: python tests/phase56_authority_enforcement_test.py
"""

from __future__ import annotations

import os
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
    path = base / f"phase56_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _patched_aegis_failure():
    import AEGIS.aegis_core as aegis_core

    original = aegis_core.evaluate_action_safe

    def _raise(request=None):
        raise RuntimeError("AEGIS unavailable")

    aegis_core.evaluate_action_safe = _raise
    try:
        yield
    finally:
        aegis_core.evaluate_action_safe = original


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _dispatch_plan(project_path: str, runtime_target_id: str = "local") -> dict:
    return {
        "dispatch_version": "1.0",
        "dispatch_planning_status": "planned",
        "ready_for_dispatch": True,
        "project": {
            "project_name": "phase56proj",
            "project_path": project_path,
        },
        "request": {
            "request_type": "user_request",
            "task_type": "coder",
            "summary": "Dispatch a governed action.",
            "priority": "normal",
        },
        "routing": {
            "runtime_node": "nexus",
            "agent_name": "nexus",
            "tool_name": "runtime_dispatcher",
            "selection_status": "selected",
            "selection_reason": "Authority enforcement test dispatch.",
        },
        "execution": {
            "execution_mode": "targeted_runtime",
            "runtime_target_id": runtime_target_id,
            "runtime_target_name": runtime_target_id,
            "requires_human_approval": False,
            "can_execute": True,
        },
        "artifacts": {"expected_outputs": ["execution package"], "target_files": ["src/module.py"]},
        "timestamps": {"planned_at": "2026-03-22T00:00:00+00:00"},
    }


def test_authorized_abacus_path():
    from NEXUS.authority_model import enforce_component_authority_safe

    result = enforce_component_authority_safe(
        component_name="abacus",
        actor="abacus_operator",
        requested_actions=["evaluate_execution"],
        allowed_components=["abacus"],
    )
    assert result["status"] == "authorized"
    assert result["authority_trace"]["authority_status"] == "authorized"


def test_helix_direct_execution_denied():
    from NEXUS.authority_model import enforce_component_authority_safe

    result = enforce_component_authority_safe(
        component_name="helix",
        actor="helix",
        requested_actions=["execute_package"],
        allowed_components=["helix"],
    )
    denial = result["authority_denial"]
    assert result["status"] == "denied"
    assert denial["status"] == "denied"
    assert denial["denied_action"] == "execute_package"
    assert denial["required_role"] == "generation_only"


def test_nemoclaw_authority_denied():
    from NEXUS.authority_model import enforce_component_authority_safe

    result = enforce_component_authority_safe(
        component_name="nemoclaw",
        actor="nemoclaw_operator",
        requested_actions=["approve_execution"],
        allowed_components=["nemoclaw"],
    )
    denial = result["authority_denial"]
    assert result["status"] == "denied"
    assert denial["denied_action"] == "approve_execution"
    assert denial["required_role"] == "advisory_only"


def test_abacus_authority_denied():
    from NEXUS.authority_model import enforce_component_authority_safe

    result = enforce_component_authority_safe(
        component_name="abacus",
        actor="abacus_operator",
        requested_actions=["execute_package"],
        allowed_components=["abacus"],
    )
    denial = result["authority_denial"]
    assert result["status"] == "denied"
    assert denial["denied_action"] == "execute_package"
    assert denial["required_role"] == "evaluation_only"


def test_cursor_bridge_execution_denied():
    from NEXUS.runtimes.cursor_runtime import dispatch

    result = dispatch(
        {
            "ready_for_dispatch": True,
            "execution": {
                "runtime_target_id": "cursor",
                "execution_mode": "external_runtime",
                "can_execute": True,
            },
        }
    )
    assert result["status"] == "blocked"
    assert result["authority_denial"]["status"] == "denied"
    assert result["authority_denial"]["denied_action"] == "execute_package"


def test_nexus_bypass_attempt_denied():
    from NEXUS.runtime_dispatcher import dispatch

    with _local_test_dir() as tmp, _patched_aegis_failure():
        previous_env = os.environ.get("FORGE_ENV")
        try:
            os.environ["FORGE_ENV"] = "local_dev"
            result = dispatch(_dispatch_plan(str(tmp)))
        finally:
            if previous_env is None:
                os.environ.pop("FORGE_ENV", None)
            else:
                os.environ["FORGE_ENV"] = previous_env
    assert result["dispatch_status"] == "blocked"
    denial = result["dispatch_result"]["authority_denial"]
    assert denial["status"] == "denied"
    assert denial["denied_action"] == "bypass_aegis_for_governed_dispatch"
    assert denial["required_role"] == "approval_authority"


def main():
    tests = [
        test_authorized_abacus_path,
        test_helix_direct_execution_denied,
        test_nemoclaw_authority_denied,
        test_abacus_authority_denied,
        test_cursor_bridge_execution_denied,
        test_nexus_bypass_attempt_denied,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
