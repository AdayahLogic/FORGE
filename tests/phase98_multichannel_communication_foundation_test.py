"""
Phase 98 multichannel communication foundation tests.

Run: python tests/phase98_multichannel_communication_foundation_test.py
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
    path = base / f"phase98_{uuid.uuid4().hex[:8]}"
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


def test_normalize_execution_package_adds_channel_strategy_fields():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase98proj",
            "project_path": "C:/phase98",
            "pipeline_stage": "follow_up",
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
            },
        }
    )
    assert "communication_channel_strategy" in normalized
    assert "recommended_communication_channel" in normalized
    assert "recommended_communication_channel_reason" in normalized
    assert "communication_channel_priority" in normalized
    assert "communication_channel_readiness" in normalized
    assert "communication_channel_fallback" in normalized
    assert "communication_channel_selection_score" in normalized
    assert normalized["recommended_communication_route"] in {
        "continue_with_email",
        "recommend_sms_follow_up",
        "recommend_voice_escalation",
        "keep_manual_only",
        "block_outreach",
        "defer_contact",
    }


def test_governance_block_hard_stops_channel_recommendation():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase98proj",
            "project_path": "C:/phase98",
            "pipeline_stage": "proposal_pending",
            "metadata": {
                "governance_status": "blocked",
                "governance_routing_outcome": "stop",
                "enforcement_status": "blocked",
            },
        }
    )
    assert normalized["recommended_communication_channel"] == "no_outreach"
    assert normalized["recommended_communication_route"] == "block_outreach"
    assert normalized["communication_channel_readiness"] == "blocked"
    assert normalized["communication_channel_fallback"] == "manual_only"


def test_sms_or_voice_strategy_without_provider_falls_back_safely():
    from NEXUS.execution_package_registry import normalize_execution_package

    normalized = normalize_execution_package(
        {
            "project_name": "phase98proj",
            "project_path": "C:/phase98",
            "pipeline_stage": "negotiation",
            "time_sensitivity": 0.92,
            "conversion_probability": 0.82,
            "roi_estimate": 0.78,
            "metadata": {
                "governance_status": "approved",
                "governance_routing_outcome": "continue",
                "enforcement_status": "continue",
                "drop_off_risk": "high",
                "action_sequence_state": "stalled",
                "communication_capabilities": {
                    "email_send_enabled": False,
                    "sms_send_enabled": False,
                    "voice_send_enabled": False,
                },
            },
        }
    )
    channel = normalized["recommended_communication_channel"]
    if channel in {"sms", "voice"}:
        assert normalized["communication_channel_block_reason"] != ""
        assert normalized["communication_channel_fallback"] in {"email", "manual_only"}
        assert normalized["communication_channel_readiness"] == "future_channel"


def test_command_surface_exposes_channel_fields_in_queue_and_details():
    from NEXUS.command_surface import run_command
    from NEXUS.execution_package_registry import write_execution_package_safe

    with _local_test_dir() as tmp:
        ok = write_execution_package_safe(
            str(tmp),
            {
                "package_id": "pkg-phase98",
                "project_name": "phase98proj",
                "project_path": str(tmp),
                "pipeline_stage": "follow_up",
                "time_sensitivity": 0.88,
                "conversion_probability": 0.74,
                "roi_estimate": 0.7,
                "metadata": {
                    "governance_status": "approved",
                    "governance_routing_outcome": "continue",
                    "enforcement_status": "continue",
                    "drop_off_risk": "high",
                },
            },
        )
        assert ok

        queue = run_command("execution_package_queue", project_path=str(tmp), n=20)
        assert queue["status"] == "ok"
        row = next(item for item in queue["payload"]["packages"] if item["package_id"] == "pkg-phase98")
        assert "recommended_communication_channel" in row
        assert "recommended_communication_channel_reason" in row
        assert "communication_channel_readiness" in row
        assert "communication_channel_fallback" in row

        details = run_command("execution_package_details", project_path=str(tmp), execution_package_id="pkg-phase98")
        assert details["status"] == "ok"
        review_header = details["payload"]["review_header"]
        assert "recommended_communication_channel" in review_header
        assert "recommended_communication_channel_reason" in review_header
        assert "communication_channel_readiness" in review_header
        assert "communication_channel_fallback" in review_header


def main():
    tests = [
        test_normalize_execution_package_adds_channel_strategy_fields,
        test_governance_block_hard_stops_channel_recommendation,
        test_sms_or_voice_strategy_without_provider_falls_back_safely,
        test_command_surface_exposes_channel_fields_in_queue_and_details,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
