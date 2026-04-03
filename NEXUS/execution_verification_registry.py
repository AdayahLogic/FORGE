"""
Post-execution verification registry.

Verification records are append-only and explicitly distinguish execution
attempt/completion/artifacts/claimed-world-change/verification outcomes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERIFICATION_JOURNAL_FILENAME = "execution_verification_journal.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _state_dir(project_path: str | None) -> Path | None:
    if not project_path:
        return None
    try:
        state = Path(project_path).resolve() / "state"
        state.mkdir(parents=True, exist_ok=True)
        return state
    except Exception:
        return None


def get_execution_verification_journal_path(project_path: str | None) -> str | None:
    state = _state_dir(project_path)
    if not state:
        return None
    return str(state / VERIFICATION_JOURNAL_FILENAME)


def normalize_verification_record(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record if isinstance(record, dict) else {}
    evidence = [dict(item) for item in (r.get("verification_evidence") or []) if isinstance(item, dict)]
    errors = [dict(item) for item in (r.get("errors") or []) if isinstance(item, dict)]
    return {
        "verification_id": _text(r.get("verification_id") or f"verify-{uuid.uuid4().hex[:16]}"),
        "receipt_id": _text(r.get("receipt_id")),
        "execution_package_id": _text(r.get("execution_package_id")),
        "verification_status": _text(r.get("verification_status") or "pending").lower(),
        "execution_attempted": bool(r.get("execution_attempted")),
        "execution_completed": bool(r.get("execution_completed")),
        "artifacts_produced": bool(r.get("artifacts_produced")),
        "claimed_world_change": bool(r.get("claimed_world_change")),
        "verified": bool(r.get("verified")),
        "verification_failed": bool(r.get("verification_failed")),
        "verification_summary": _text(r.get("verification_summary")),
        "verification_evidence": evidence[:30],
        "errors": errors[:30],
        "verified_at": _text(r.get("verified_at")),
        "recorded_at": _text(r.get("recorded_at") or _now_iso()),
    }


def build_verification_from_receipt(
    *,
    receipt: dict[str, Any] | None,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    r = receipt if isinstance(receipt, dict) else {}
    p = package if isinstance(package, dict) else {}

    execution_status = _text(r.get("execution_status")).lower()
    attempted = bool(_text(r.get("execution_started_at")))
    completed = bool(_text(r.get("execution_finished_at"))) or execution_status in {
        "succeeded",
        "completed",
        "failed",
        "blocked",
        "rolled_back",
    }
    artifacts_produced = bool(r.get("changed_artifacts")) or int((p.get("execution_receipt") or {}).get("artifacts_written_count") or 0) > 0
    claimed_world_change = bool(r.get("world_change_claims")) and all(
        claim == "no_world_change_claimed" for claim in (r.get("world_change_claims") or [])
    ) is False

    verification_status = "pending"
    verified = False
    verification_failed = False
    summary = "Verification pending."
    if execution_status in {"failed", "blocked", "rolled_back"}:
        verification_status = "failed"
        verification_failed = True
        summary = "Execution did not reach a verifiable success state."
    elif attempted and completed and artifacts_produced:
        verification_status = "verified"
        verified = True
        summary = "Execution completed and produced artifacts with evidence."
    elif attempted and completed:
        verification_status = "unverified"
        summary = "Execution completed but artifact/world-change evidence is insufficient."
    elif attempted:
        verification_status = "running"
        summary = "Execution attempt started; completion evidence pending."

    return normalize_verification_record(
        {
            "receipt_id": r.get("receipt_id"),
            "execution_package_id": r.get("execution_package_id"),
            "verification_status": verification_status,
            "execution_attempted": attempted,
            "execution_completed": completed,
            "artifacts_produced": artifacts_produced,
            "claimed_world_change": claimed_world_change,
            "verified": verified,
            "verification_failed": verification_failed,
            "verification_summary": summary,
            "verification_evidence": r.get("verification_evidence") or [],
            "errors": r.get("errors") or [],
            "verified_at": _now_iso() if verified or verification_failed else "",
        }
    )


def append_execution_verification(
    *,
    project_path: str | None,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    journal_path = get_execution_verification_journal_path(project_path)
    if not journal_path:
        return {"status": "degraded", "reason": "Verification journal unavailable.", "verification": None}
    normalized = normalize_verification_record(record)
    try:
        with open(journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        return {"status": "ok", "reason": "Verification record persisted.", "verification": normalized}
    except Exception as exc:
        return {"status": "degraded", "reason": f"Failed to persist verification record: {exc}", "verification": normalized}


def append_execution_verification_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return append_execution_verification(**kwargs)
    except Exception as exc:
        return {"status": "degraded", "reason": f"Verification persistence failed: {exc}", "verification": None}


def read_execution_verification_journal_tail(
    *,
    project_path: str | None,
    n: int = 50,
) -> list[dict[str, Any]]:
    journal_path = get_execution_verification_journal_path(project_path)
    if not journal_path:
        return []
    file_path = Path(journal_path)
    if not file_path.exists():
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, min(int(n or 50), 500)) :]:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(normalize_verification_record(parsed))
    return out


# ---------------------------------------------------------------------------
# Global execution verification registry (phase-12)
# ---------------------------------------------------------------------------

VERIFICATION_REGISTRY_DIR = "state"
VERIFICATION_REGISTRY_FILE = "execution_verifications.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_execution_verification_registry_path() -> Path:
    state_dir = _repo_root() / VERIFICATION_REGISTRY_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / VERIFICATION_REGISTRY_FILE


def record_execution_verification(
    *,
    project_name: str,
    package_id: str,
    execution_id: str,
    execution_status: str,
    integrity_verification: dict[str, Any],
) -> dict[str, Any]:
    integrity = dict(integrity_verification or {})
    integrity_status = str(integrity.get("integrity_status") or "not_verified").strip().lower()
    verification_status = "verified" if integrity_status == "verified" else ("failed" if integrity_status in ("issues_detected", "verification_failed") else "not_verified")
    record = {
        "verification_record_id": uuid.uuid4().hex,
        "recorded_at": _utc_now_iso(),
        "project_name": str(project_name or ""),
        "package_id": str(package_id or ""),
        "execution_id": str(execution_id or ""),
        "execution_status": str(execution_status or ""),
        "verification_status": verification_status,
        "integrity_verification": integrity,
    }
    path = get_execution_verification_registry_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_latest_execution_verification(*, package_id: str) -> dict[str, Any]:
    target = str(package_id or "").strip()
    if not target:
        return {}
    path = get_execution_verification_registry_path()
    if not path.exists():
        return {}
    latest: dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if str(row.get("package_id") or "") == target:
                    latest = row
    except Exception:
        return {}
    return latest
