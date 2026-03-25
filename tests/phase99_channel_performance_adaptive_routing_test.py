"""
Phase 99 channel performance + adaptive routing tests.

Run: python tests/phase99_channel_performance_adaptive_routing_test.py
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
    path = base / f"phase99_{uuid.uuid4().hex[:8]}"
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


def test_normalize_execution_package_adds_phase99_fields_safely():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase99proj",
            "project_path": "C:/phase99",
            "metadata": {},
        }
    )
    assert normalized["recommended_channel"] in {"email", "sms", "voice", "manual"}
    assert "channel_performance_profile" in normalized
    assert "adaptive_channel_weight" in normalized
    assert "adaptive_channel_selection_score" in normalized
    assert "adaptive_channel_routing_reason" in normalized
    assert "adaptive_channel_learning_status" in normalized
    assert "cross_channel_sequence_status" in normalized
    assert "cross_channel_next_recommended_channel" in normalized
    assert "operator_channel_override_detected" in normalized
    assert "operator_override_effectiveness_signal" in normalized


def test_adaptive_weighting_prefers_higher_signal_channel():
    from NEXUS.execution_package_registry import normalize_execution_package

    email_failures = [
        {
            "channel": "email",
            "outcome": "no_response",
            "responded": False,
            "converted": False,
            "follow_through": False,
            "at": f"2026-03-01T00:00:0{idx}Z",
            "reason": "no reply",
        }
        for idx in range(8)
    ]
    sms_success = [
        {
            "channel": "sms",
            "outcome": "converted",
            "responded": True,
            "converted": True,
            "follow_through": True,
            "at": f"2026-03-02T00:00:0{idx}Z",
            "reason": "fast conversion",
        }
        for idx in range(8)
    ]
    normalized = normalize_execution_package(
        {
            "project_name": "phase99proj",
            "project_path": "C:/phase99",
            "metadata": {
                "channel_recent_outcomes": email_failures + sms_success,
                "channel_operational_availability": {"email": True, "sms": True, "voice": False},
            },
        }
    )
    assert normalized["recommended_channel"] == "sms"
    assert float(normalized["adaptive_channel_weight"]["sms"]) > float(normalized["adaptive_channel_weight"]["email"])


def test_cross_channel_fallback_and_override_memory_surface():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase99proj",
            "project_path": "C:/phase99",
            "metadata": {
                "recommended_channel": "voice",
                "channel_operational_availability": {"email": True, "sms": True, "voice": False},
                "operator_channel_override_history": [
                    {
                        "at": "2026-03-03T00:00:00Z",
                        "recommended_channel": "email",
                        "operator_selected_channel": "sms",
                        "operator_selected_channel_reason": "prior contact requested text",
                        "operator_override_outcome": "converted",
                    }
                ],
            },
        }
    )
    assert normalized["cross_channel_sequence_status"] == "fallback_required"
    assert normalized["cross_channel_next_recommended_channel"] == "manual"
    assert normalized["operator_override_effectiveness_signal"] in {"positive", "insufficient_data", "pending_outcome"}


def test_command_surface_exposes_channel_routing_and_override_command():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        assert write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-channel",
                "project_name": "phase99proj",
                "project_path": str(tmp),
                "metadata": {
                    "channel_operational_availability": {"email": True, "sms": True, "voice": False},
                },
            },
        )

        details_before = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-channel")
        assert details_before["status"] == "ok"
        metadata_section = ((details_before["payload"].get("sections") or {}).get("metadata") or {})
        assert "channel_routing" in metadata_section

        override_result = run_command(
            "execution_package_channel_override",
            project_path=str(tmp),
            execution_package_id="pkg-channel",
            operator_selected_channel="sms",
            operator_selected_channel_reason="contact requested text",
            operator_override_outcome="response",
        )
        assert override_result["status"] == "ok"
        assert override_result["payload"]["operator_selected_channel"] == "sms"

        queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert queue["status"] == "ok"
        payload = queue["payload"]
        assert "top_channel_recommendations" in payload
        assert "low_confidence_channel_routing" in payload


def main():
    tests = [
        test_normalize_execution_package_adds_phase99_fields_safely,
        test_adaptive_weighting_prefers_higher_signal_channel,
        test_cross_channel_fallback_and_override_memory_surface,
        test_command_surface_exposes_channel_routing_and_override_command,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
