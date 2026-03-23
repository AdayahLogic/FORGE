"""
Phase 62 Forge Console governed attachment tests.

Run: python tests/phase62_console_attachment_registry_test.py
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
    path = base / f"phase62_{uuid.uuid4().hex[:8]}"
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
    except Exception as e:
        print(f"FAIL: {name} - {e}")
        return False


def test_attachment_classification_and_quarantine_paths_are_explicit():
    from NEXUS.console_attachment_registry import ingest_console_attachment_safe

    with _local_test_dir() as tmp:
        readme = tmp / "requirements.md"
        readme.write_text("# Scope\nForge should keep NEXUS in charge.\n", encoding="utf-8")
        classified = ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase62proj",
            file_path=str(readme),
            file_name=readme.name,
            file_type="text/markdown",
            source="console_upload",
            purpose="specification",
        )
        assert classified["status"] == "ok"
        record = classified["attachment"]
        assert record["status"] == "classified"
        assert "request_preview" in record["allowed_consumers"]
        assert record["extracted_summary"]
        assert record["status_reason"]
        assert record["linked_context"]["project_id"] == "phase62proj"

        executable = tmp / "danger.ps1"
        executable.write_text("Write-Host 'unsafe'\n", encoding="utf-8")
        quarantined = ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase62proj",
            file_path=str(executable),
            file_name=executable.name,
            file_type="text/plain",
            source="console_upload",
            purpose="supporting_context",
        )
        assert quarantined["status"] == "ok"
        quarantined_record = quarantined["attachment"]
        assert quarantined_record["status"] == "quarantined"
        assert quarantined_record["allowed_consumers"] == ["console_review"]
        assert quarantined_record["extracted_summary"] == ""
        assert "quarantined" in quarantined_record["status_reason"].lower()


def test_oversized_attachment_is_denied_and_not_stored_for_preview():
    from NEXUS.console_attachment_registry import ingest_console_attachment_safe

    with _local_test_dir() as tmp:
        large = tmp / "large.txt"
        large.write_bytes(b"a" * (5 * 1024 * 1024 + 1))
        denied = ingest_console_attachment_safe(
            project_path=str(tmp),
            project_id="phase62proj",
            file_path=str(large),
            file_name=large.name,
            file_type="text/plain",
            source="console_upload",
            purpose="evidence",
        )
        assert denied["status"] == "error"
        record = denied["attachment"]
        assert record["status"] == "denied"
        assert record["raw_storage_path"] == ""
        assert record["allowed_consumers"] == []
        assert record["status_reason"]


def main():
    tests = [
        test_attachment_classification_and_quarantine_paths_are_explicit,
        test_oversized_attachment_is_denied_and_not_stored_for_preview,
    ]
    passed = sum(1 for t in tests if _run(t.__name__, t))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
