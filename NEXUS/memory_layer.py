"""
Cross-project memory pattern aggregation.

Append/update only for operator-visible summaries. Never grants execution or
automatic self-modification authority.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_LAYER_PATH = Path(__file__).resolve().parent.parent / "ops" / "forge_memory_patterns.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_memory_store() -> dict[str, Any]:
    if not MEMORY_LAYER_PATH.exists():
        return {
            "memory_layer_version": "1.0",
            "last_updated": "",
            "self_modification_policy": "approval_required",
            "records": [],
        }
    try:
        data = json.loads(MEMORY_LAYER_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("memory_layer_version", "1.0")
            data.setdefault("last_updated", "")
            data.setdefault("self_modification_policy", "approval_required")
            data.setdefault("records", [])
            return data
    except Exception:
        pass
    return {
        "memory_layer_version": "1.0",
        "last_updated": "",
        "self_modification_policy": "approval_required",
        "records": [],
    }


def _write_memory_store(payload: dict[str, Any]) -> str | None:
    try:
        MEMORY_LAYER_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_LAYER_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(MEMORY_LAYER_PATH)
    except Exception:
        return None


def record_memory_pattern(
    *,
    project_name: str,
    source: str,
    pattern_key: str,
    attributes: dict[str, Any] | None = None,
) -> str | None:
    payload = _read_memory_store()
    records = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
    records.append(
        {
            "project_name": str(project_name or ""),
            "source": str(source or ""),
            "pattern_key": str(pattern_key or ""),
            "attributes": dict(attributes or {}),
            "recorded_at": _utc_now_iso(),
        }
    )
    payload["records"] = records[-500:]
    payload["last_updated"] = _utc_now_iso()
    return _write_memory_store(payload)


def record_memory_pattern_safe(**kwargs: Any) -> str | None:
    try:
        return record_memory_pattern(**kwargs)
    except Exception:
        return None


def build_memory_layer_summary(*, project_name: str | None = None) -> dict[str, Any]:
    payload = _read_memory_store()
    records = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
    if project_name:
        normalized_project = str(project_name or "")
        records = [item for item in records if str(item.get("project_name") or "") == normalized_project]

    patterns_by_key: dict[str, int] = {}
    projects: dict[str, int] = {}
    sources: dict[str, int] = {}
    for item in records:
        key = str(item.get("pattern_key") or "")
        src = str(item.get("source") or "")
        proj = str(item.get("project_name") or "")
        if key:
            patterns_by_key[key] = patterns_by_key.get(key, 0) + 1
        if src:
            sources[src] = sources.get(src, 0) + 1
        if proj:
            projects[proj] = projects.get(proj, 0) + 1

    return {
        "memory_layer_version": str(payload.get("memory_layer_version") or "1.0"),
        "last_updated": str(payload.get("last_updated") or ""),
        "self_modification_policy": str(payload.get("self_modification_policy") or "approval_required"),
        "total_records": len(records),
        "patterns_by_key": patterns_by_key,
        "records_by_project": projects,
        "records_by_source": sources,
    }


def build_memory_layer_summary_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_memory_layer_summary(**kwargs)
    except Exception:
        return {
            "memory_layer_version": "1.0",
            "last_updated": "",
            "self_modification_policy": "approval_required",
            "total_records": 0,
            "patterns_by_key": {},
            "records_by_project": {},
            "records_by_source": {},
        }
