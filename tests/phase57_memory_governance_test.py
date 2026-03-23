"""
Phase 57 memory governance tests.

Run: python tests/phase57_memory_governance_test.py
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
    path = base / f"phase57_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def _patched_memory_store(memory_path: Path):
    with patch("NEXUS.memory_layer.MEMORY_LAYER_PATH", memory_path):
        yield


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def _read_store(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_project_scope_memory_write():
    from NEXUS.memory_layer import write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            result = write_governed_memory_safe(
                actor="nemoclaw",
                entry={
                    "source_type": "nemoclaw_advisory",
                    "source_project": "phase57proj",
                    "scope": "project",
                    "category": "local_analysis:review",
                    "summary": "NemoClaw suggested a project-local review step.",
                    "evidence": ["package_id:pkg-1", "local_analysis_id:la-1"],
                    "confidence": 0.72,
                    "attribution": "nemoclaw:local_analysis_pipeline",
                    "status": "active",
                    "governance_trace": {"origin": "phase57", "advisory_only": True},
                },
                allowed_components=("nemoclaw",),
            )
            store = _read_store(memory_path)
    assert result["status"] == "ok"
    assert result["memory_scope"] == "project"
    assert store["records"][-1]["scope"] == "project"
    assert store["records"][-1]["attribution"] == "nemoclaw:local_analysis_pipeline"


def test_valid_cross_project_memory_write():
    from NEXUS.memory_layer import write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            result = write_governed_memory_safe(
                actor="abacus",
                entry={
                    "source_type": "abacus_evaluation",
                    "source_project": "phase57proj",
                    "scope": "cross_project",
                    "category": "evaluation:completed",
                    "summary": "Abacus observed a reusable low-risk evaluation pattern.",
                    "evidence": ["package_id:pkg-2", "evaluation_id:eval-2"],
                    "confidence": 0.84,
                    "attribution": "abacus:evaluation_pipeline",
                    "status": "active",
                    "governance_trace": {"origin": "phase57", "advisory_only": True},
                },
                allowed_components=("abacus",),
            )
            store = _read_store(memory_path)
    assert result["status"] == "ok"
    assert result["memory_scope"] == "cross_project"
    assert store["records"][-1]["scope"] == "cross_project"


def test_invalid_memory_write_denied_for_missing_attribution_and_evidence():
    from NEXUS.memory_layer import write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            result = write_governed_memory_safe(
                actor="abacus",
                entry={
                    "source_type": "abacus_evaluation",
                    "source_project": "phase57proj",
                    "scope": "cross_project",
                    "category": "evaluation:missing_fields",
                    "summary": "This write should be denied.",
                    "confidence": 0.5,
                },
                allowed_components=("abacus",),
            )
            store = _read_store(memory_path)
    assert result["status"] == "denied"
    assert "attribution is required" in result["reason"]
    assert "evidence is required" in result["reason"]
    assert store.get("records", []) == []


def test_governed_memory_read_path():
    from NEXUS.memory_layer import read_governed_memory_safe, write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            write_governed_memory_safe(
                actor="abacus",
                entry={
                    "source_type": "abacus_evaluation",
                    "source_project": "phase57proj",
                    "scope": "cross_project",
                    "category": "evaluation:readable",
                    "summary": "Reusable evaluation pattern for advisory reading.",
                    "evidence": ["package_id:pkg-3", "evaluation_id:eval-3"],
                    "confidence": 0.88,
                    "attribution": "abacus:evaluation_pipeline",
                },
                allowed_components=("abacus",),
            )
            result = read_governed_memory_safe(
                actor="nexus",
                purpose="advisory_context",
                scope="cross_project",
                project_name="phase57proj",
                limit=5,
                allowed_components=("nexus",),
            )
    assert result["status"] == "ok"
    assert result["operation"] == "read"
    assert result["record_count"] >= 1
    assert result["records"][-1]["category"] == "evaluation:readable"


def test_memory_does_not_override_governance_authority_or_routing_decisions():
    from NEXUS.governance_layer import evaluate_governance_outcome_safe
    from NEXUS.memory_layer import read_governed_memory_safe, write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            write_governed_memory_safe(
                actor="abacus",
                entry={
                    "source_type": "abacus_evaluation",
                    "source_project": "phase57proj",
                    "scope": "cross_project",
                    "category": "evaluation:block_everything",
                    "summary": "Memory should never directly drive governance or routing.",
                    "evidence": ["package_id:pkg-4", "evaluation_id:eval-4"],
                    "confidence": 0.95,
                    "attribution": "abacus:evaluation_pipeline",
                },
                allowed_components=("abacus",),
            )
            read_result = read_governed_memory_safe(
                actor="nexus",
                purpose="governance",
                scope="cross_project",
                project_name="phase57proj",
                allowed_components=("nexus",),
            )
            governance = evaluate_governance_outcome_safe(
                dispatch_status="accepted",
                runtime_execution_status="simulated_execution",
                dispatch_result={"execution_status": "simulated_execution"},
                automation_status="completed",
                automation_result={},
                active_project="phase57proj",
                project_path=str(tmp),
            )
    assert read_result["status"] == "denied"
    assert governance["routing_outcome"] in ("continue", "pause", "escalate", "stop")
    assert governance["final_decision_source"] != "memory_layer"


def test_helios_consumes_memory_as_advisory_only():
    from elite_layers.helios_engine import build_helios_expanded_summary_safe
    from NEXUS.memory_layer import write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            write_governed_memory_safe(
                actor="abacus",
                entry={
                    "source_type": "abacus_evaluation",
                    "source_project": "phase57proj",
                    "scope": "cross_project",
                    "category": "evaluation:helios",
                    "summary": "Advisory evaluation context for HELIOS.",
                    "evidence": ["package_id:pkg-5", "evaluation_id:eval-5"],
                    "confidence": 0.8,
                    "attribution": "abacus:evaluation_pipeline",
                },
                allowed_components=("abacus",),
            )
            result = build_helios_expanded_summary_safe(
                dashboard_summary={"memory_layer_summary": {"total_records": 1, "self_modification_policy": "approval_required"}},
                studio_coordination_summary={},
                studio_driver_summary={},
                project_name="phase57proj",
                live_regression=False,
                helios_evaluation_mode="dashboard_cached",
            )
    advisory = result.get("memory_advisory_context") or {}
    assert advisory.get("advisory_only") is True
    assert advisory.get("status") == "ok"
    assert "memory_usage=advisory_only" in result.get("improvement_reason", "")


def test_persistence_and_summary_verification():
    from NEXUS.command_surface import run_command
    from NEXUS.memory_layer import build_memory_layer_summary_safe, write_governed_memory_safe

    with _local_test_dir() as tmp:
        memory_path = tmp / "memory_store.json"
        with _patched_memory_store(memory_path):
            write_governed_memory_safe(
                actor="nemoclaw",
                entry={
                    "source_type": "nemoclaw_advisory",
                    "source_project": "phase57proj",
                    "scope": "project",
                    "category": "local_analysis:summary",
                    "summary": "Project-local advisory summary for persistence checks.",
                    "evidence": ["package_id:pkg-6", "local_analysis_id:la-6"],
                    "confidence": 0.66,
                    "attribution": "nemoclaw:local_analysis_pipeline",
                },
                allowed_components=("nemoclaw",),
            )
            summary = build_memory_layer_summary_safe(project_name="phase57proj")
            command_result = run_command(
                "memory_status",
                project_name="phase57proj",
                scope="project",
                purpose="advisory_context",
                actor="nexus",
                limit=5,
            )
    assert summary["records_by_scope"]["project"] >= 1
    assert summary["audit_event_count"] >= 1
    assert command_result["status"] == "ok"
    assert command_result["payload"]["memory_read"]["status"] == "ok"


def main():
    tests = [
        test_valid_project_scope_memory_write,
        test_valid_cross_project_memory_write,
        test_invalid_memory_write_denied_for_missing_attribution_and_evidence,
        test_governed_memory_read_path,
        test_memory_does_not_override_governance_authority_or_routing_decisions,
        test_helios_consumes_memory_as_advisory_only,
        test_persistence_and_summary_verification,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
