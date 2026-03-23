"""
Governed reusable memory layer.

Reusable memory is persisted only through explicit, auditable, authority-checked
paths. Memory remains advisory-only and never grants governance, routing, or
execution authority.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.authority_model import enforce_component_authority_safe, infer_component_name
from NEXUS.memory_models import GovernedMemoryEntry, GovernedMemoryOperation


MEMORY_LAYER_PATH = Path(__file__).resolve().parent.parent / "ops" / "forge_memory_patterns.json"
MEMORY_LAYER_VERSION = "2.0"
FORBIDDEN_MEMORY_PURPOSES = frozenset({"governance", "routing", "execution", "package_decision"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_store() -> dict[str, Any]:
    return {
        "memory_layer_version": MEMORY_LAYER_VERSION,
        "last_updated": "",
        "self_modification_policy": "approval_required",
        "records": [],
        "audit_log": [],
    }


def _read_memory_store() -> dict[str, Any]:
    if not MEMORY_LAYER_PATH.exists():
        return _default_store()
    try:
        data = json.loads(MEMORY_LAYER_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            payload = _default_store()
            payload.update(data)
            payload["records"] = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
            payload["audit_log"] = [item for item in (payload.get("audit_log") or []) if isinstance(item, dict)]
            payload["memory_layer_version"] = str(payload.get("memory_layer_version") or MEMORY_LAYER_VERSION)
            payload["self_modification_policy"] = "approval_required"
            return payload
    except Exception:
        pass
    return _default_store()


def _write_memory_store(payload: dict[str, Any]) -> str | None:
    try:
        MEMORY_LAYER_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_LAYER_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(MEMORY_LAYER_PATH)
    except Exception:
        return None


def _normalize_scope(value: Any, default: str = "project") -> str:
    scope = str(value or default).strip().lower()
    return scope if scope in ("project", "cross_project") else default


def _normalize_text(value: Any, *, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _truncate_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return _normalize_text(value, limit=300) if isinstance(value, str) else value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            out[_normalize_text(key, limit=80)] = _truncate_json(item)
        return out
    if isinstance(value, list):
        return [_truncate_json(item) for item in value[:20]]
    return _normalize_text(value, limit=300)


def _build_operation_result(
    *,
    status: str,
    operation: str,
    memory_scope: str,
    actor: str,
    source_type: str,
    reason: str,
    governance_trace: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = GovernedMemoryOperation(
        status=status,
        operation=operation,
        memory_scope=_normalize_scope(memory_scope),
        actor=_normalize_text(actor, limit=120),
        source_type=_normalize_text(source_type, limit=120),
        reason=_normalize_text(reason, limit=300),
        governance_trace=dict(governance_trace or {}),
    ).dict()
    if extra:
        base.update(extra)
    return base


def _append_audit_event(payload: dict[str, Any], event: dict[str, Any]) -> None:
    audit_log = [item for item in (payload.get("audit_log") or []) if isinstance(item, dict)]
    audit_log.append(
        {
            "event_id": f"memory-audit:{uuid.uuid4()}",
            "recorded_at": _utc_now_iso(),
            **_truncate_json(event),
        }
    )
    payload["audit_log"] = audit_log[-500:]
    payload["last_updated"] = _utc_now_iso()


def _normalize_entry_input(entry: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(entry or {})
    scope = _normalize_scope(data.get("scope"), default="project")
    return GovernedMemoryEntry(
        memory_id=_normalize_text(data.get("memory_id") or f"memory:{uuid.uuid4()}", limit=120),
        source_type=_normalize_text(data.get("source_type"), limit=120),
        source_project=_normalize_text(data.get("source_project"), limit=120),
        scope=scope,
        category=_normalize_text(data.get("category"), limit=120),
        summary=_normalize_text(data.get("summary"), limit=500),
        evidence=data.get("evidence"),
        confidence=data.get("confidence"),
        attribution=_normalize_text(data.get("attribution"), limit=200),
        recorded_at=_normalize_text(data.get("recorded_at") or _utc_now_iso(), limit=60),
        status=_normalize_text(data.get("status") or "active", limit=80),
        governance_trace=_truncate_json(data.get("governance_trace") if isinstance(data.get("governance_trace"), dict) else {}),
    ).dict()


def _validate_entry(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not entry.get("source_type"):
        errors.append("source_type is required")
    if not entry.get("source_project"):
        errors.append("source_project is required")
    if not entry.get("category"):
        errors.append("category is required")
    if not entry.get("summary"):
        errors.append("summary is required")
    if not entry.get("attribution"):
        errors.append("attribution is required")
    if not isinstance(entry.get("evidence"), list) or not entry.get("evidence"):
        errors.append("evidence is required")
    return errors


def write_governed_memory(
    *,
    actor: str,
    entry: dict[str, Any] | None,
    allowed_components: list[str] | tuple[str, ...] | set[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    normalized_entry = _normalize_entry_input(entry)
    scope = _normalize_scope(normalized_entry.get("scope"))
    component_name = infer_component_name(actor)
    requested_action = "write_cross_project_memory" if scope == "cross_project" else "write_project_memory"
    allowed = list(allowed_components or ("abacus", "nemoclaw"))
    authority = enforce_component_authority_safe(
        component_name=component_name,
        actor=actor,
        requested_actions=[requested_action],
        allowed_components=allowed,
        authority_context={
            "memory_scope": scope,
            "source_type": normalized_entry.get("source_type"),
            "source_project": normalized_entry.get("source_project"),
            "memory_id": normalized_entry.get("memory_id"),
        },
    )
    governance_trace = {
        "authority_trace": authority.get("authority_trace") or {},
        "authority_denial": authority.get("authority_denial") or {},
        "self_modification_policy": "approval_required",
        "advisory_only": True,
    }
    payload = _read_memory_store()

    if authority.get("status") == "denied":
        result = _build_operation_result(
            status="denied",
            operation="write",
            memory_scope=scope,
            actor=actor,
            source_type=str(normalized_entry.get("source_type") or ""),
            reason=str(((authority.get("authority_denial") or {}).get("reason")) or "Memory write denied."),
            governance_trace=governance_trace,
            extra={"memory_id": normalized_entry.get("memory_id"), "memory_path": str(MEMORY_LAYER_PATH)},
        )
        _append_audit_event(payload, result)
        _write_memory_store(payload)
        return result

    validation_errors = _validate_entry(normalized_entry)
    if validation_errors:
        result = _build_operation_result(
            status="denied",
            operation="write",
            memory_scope=scope,
            actor=actor,
            source_type=str(normalized_entry.get("source_type") or ""),
            reason="; ".join(validation_errors),
            governance_trace={
                **governance_trace,
                "validation_errors": validation_errors,
            },
            extra={"memory_id": normalized_entry.get("memory_id"), "memory_path": str(MEMORY_LAYER_PATH)},
        )
        _append_audit_event(payload, result)
        _write_memory_store(payload)
        return result

    records = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
    records.append(normalized_entry)
    payload["records"] = records[-500:]
    payload["memory_layer_version"] = MEMORY_LAYER_VERSION
    payload["self_modification_policy"] = "approval_required"
    result = _build_operation_result(
        status="ok",
        operation="write",
        memory_scope=scope,
        actor=actor,
        source_type=str(normalized_entry.get("source_type") or ""),
        reason=str(reason or "Governed memory write recorded."),
        governance_trace={
            **governance_trace,
            "memory_id": normalized_entry.get("memory_id"),
        },
        extra={
            "memory_id": normalized_entry.get("memory_id"),
            "entry": normalized_entry,
            "memory_path": str(MEMORY_LAYER_PATH),
        },
    )
    _append_audit_event(payload, result)
    written_path = _write_memory_store(payload)
    if not written_path:
        return _build_operation_result(
            status="error",
            operation="write",
            memory_scope=scope,
            actor=actor,
            source_type=str(normalized_entry.get("source_type") or ""),
            reason="Memory write failed during persistence.",
            governance_trace=governance_trace,
            extra={"memory_id": normalized_entry.get("memory_id"), "memory_path": str(MEMORY_LAYER_PATH)},
        )
    result["memory_path"] = written_path
    return result


def write_governed_memory_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return write_governed_memory(**kwargs)
    except Exception as exc:
        scope = _normalize_scope(((kwargs.get("entry") or {}).get("scope") if isinstance(kwargs.get("entry"), dict) else kwargs.get("scope")), default="project")
        return _build_operation_result(
            status="error",
            operation="write",
            memory_scope=scope,
            actor=str(kwargs.get("actor") or ""),
            source_type=str(((kwargs.get("entry") or {}).get("source_type")) if isinstance(kwargs.get("entry"), dict) else ""),
            reason=f"Memory write failed: {exc}",
            governance_trace={"self_modification_policy": "approval_required", "advisory_only": True},
            extra={"memory_path": str(MEMORY_LAYER_PATH)},
        )


def read_governed_memory(
    *,
    actor: str,
    purpose: str,
    scope: str = "project",
    project_name: str | None = None,
    category: str | None = None,
    source_type: str | None = None,
    limit: int = 20,
    allowed_components: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    normalized_purpose = _normalize_text(purpose, limit=80).lower()
    component_name = infer_component_name(actor)
    requested_action = "read_cross_project_memory" if normalized_scope == "cross_project" else "read_project_memory"
    allowed = list(allowed_components or ("helios", "nexus"))
    authority = enforce_component_authority_safe(
        component_name=component_name,
        actor=actor,
        requested_actions=[requested_action],
        allowed_components=allowed,
        authority_context={
            "purpose": normalized_purpose,
            "memory_scope": normalized_scope,
            "project_name": project_name,
        },
    )
    governance_trace = {
        "authority_trace": authority.get("authority_trace") or {},
        "authority_denial": authority.get("authority_denial") or {},
        "purpose": normalized_purpose,
        "advisory_only": True,
        "self_modification_policy": "approval_required",
    }
    payload = _read_memory_store()

    if normalized_purpose in FORBIDDEN_MEMORY_PURPOSES:
        result = _build_operation_result(
            status="denied",
            operation="read",
            memory_scope=normalized_scope,
            actor=actor,
            source_type=_normalize_text(source_type, limit=120),
            reason="Memory cannot be read for governance, routing, execution, or package decisions.",
            governance_trace=governance_trace,
            extra={"records": [], "memory_path": str(MEMORY_LAYER_PATH)},
        )
        _append_audit_event(payload, result)
        _write_memory_store(payload)
        return result

    if authority.get("status") == "denied":
        result = _build_operation_result(
            status="denied",
            operation="read",
            memory_scope=normalized_scope,
            actor=actor,
            source_type=_normalize_text(source_type, limit=120),
            reason=str(((authority.get("authority_denial") or {}).get("reason")) or "Memory read denied."),
            governance_trace=governance_trace,
            extra={"records": [], "memory_path": str(MEMORY_LAYER_PATH)},
        )
        _append_audit_event(payload, result)
        _write_memory_store(payload)
        return result

    records = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
    filtered: list[dict[str, Any]] = []
    for item in records:
        if _normalize_scope(item.get("scope")) != normalized_scope:
            continue
        if normalized_scope == "project" and project_name and _normalize_text(item.get("source_project"), limit=120) != _normalize_text(project_name, limit=120):
            continue
        if category and _normalize_text(item.get("category"), limit=120) != _normalize_text(category, limit=120):
            continue
        if source_type and _normalize_text(item.get("source_type"), limit=120) != _normalize_text(source_type, limit=120):
            continue
        filtered.append(item)
    filtered = filtered[-max(1, min(int(limit or 20), 100)) :]
    result = _build_operation_result(
        status="ok",
        operation="read",
        memory_scope=normalized_scope,
        actor=actor,
        source_type=_normalize_text(source_type, limit=120),
        reason="Governed advisory memory read completed.",
        governance_trace=governance_trace,
        extra={
            "records": filtered,
            "record_count": len(filtered),
            "memory_path": str(MEMORY_LAYER_PATH),
        },
    )
    _append_audit_event(payload, result)
    _write_memory_store(payload)
    return result


def read_governed_memory_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return read_governed_memory(**kwargs)
    except Exception as exc:
        return _build_operation_result(
            status="error",
            operation="read",
            memory_scope=_normalize_scope(kwargs.get("scope"), default="project"),
            actor=str(kwargs.get("actor") or ""),
            source_type=str(kwargs.get("source_type") or ""),
            reason=f"Memory read failed: {exc}",
            governance_trace={"self_modification_policy": "approval_required", "advisory_only": True},
            extra={"records": [], "memory_path": str(MEMORY_LAYER_PATH)},
        )


def record_memory_pattern(
    *,
    project_name: str,
    source: str,
    pattern_key: str,
    attributes: dict[str, Any] | None = None,
    actor: str | None = None,
    scope: str = "cross_project",
    evidence: list[str] | None = None,
    attribution: str | None = None,
) -> dict[str, Any]:
    attrs = dict(attributes or {})
    explicit_evidence = evidence or attrs.get("evidence")
    return write_governed_memory(
        actor=str(actor or source or ""),
        entry={
            "source_type": str(source or ""),
            "source_project": str(project_name or ""),
            "scope": scope,
            "category": str(pattern_key or ""),
            "summary": _normalize_text(attrs.get("summary") or pattern_key, limit=500),
            "evidence": explicit_evidence,
            "confidence": attrs.get("confidence", 0.0),
            "attribution": attribution or attrs.get("attribution"),
            "status": attrs.get("status", "active"),
            "governance_trace": attrs.get("governance_trace") if isinstance(attrs.get("governance_trace"), dict) else {},
        },
        allowed_components=("abacus", "nemoclaw"),
        reason="Legacy memory pattern write routed through governed memory layer.",
    )


def record_memory_pattern_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return record_memory_pattern(**kwargs)
    except Exception as exc:
        return _build_operation_result(
            status="error",
            operation="write",
            memory_scope=_normalize_scope(kwargs.get("scope"), default="cross_project"),
            actor=str(kwargs.get("actor") or kwargs.get("source") or ""),
            source_type=str(kwargs.get("source") or ""),
            reason=f"Legacy memory write failed: {exc}",
            governance_trace={"self_modification_policy": "approval_required", "advisory_only": True},
            extra={"memory_path": str(MEMORY_LAYER_PATH)},
        )


def build_memory_layer_summary(*, project_name: str | None = None) -> dict[str, Any]:
    payload = _read_memory_store()
    records = [item for item in (payload.get("records") or []) if isinstance(item, dict)]
    if project_name:
        normalized_project = _normalize_text(project_name, limit=120)
        records = [item for item in records if _normalize_text(item.get("source_project"), limit=120) == normalized_project]

    patterns_by_key: dict[str, int] = {}
    projects: dict[str, int] = {}
    sources: dict[str, int] = {}
    scopes: dict[str, int] = {"project": 0, "cross_project": 0}
    categories: dict[str, int] = {}
    for item in records:
        key = _normalize_text(item.get("category"), limit=120)
        src = _normalize_text(item.get("source_type"), limit=120)
        proj = _normalize_text(item.get("source_project"), limit=120)
        scope = _normalize_scope(item.get("scope"))
        if key:
            patterns_by_key[key] = patterns_by_key.get(key, 0) + 1
            categories[key] = categories.get(key, 0) + 1
        if src:
            sources[src] = sources.get(src, 0) + 1
        if proj:
            projects[proj] = projects.get(proj, 0) + 1
        scopes[scope] = scopes.get(scope, 0) + 1

    audit_log = [item for item in (payload.get("audit_log") or []) if isinstance(item, dict)]
    denied_write_count = sum(1 for item in audit_log if item.get("operation") == "write" and item.get("status") == "denied")
    denied_read_count = sum(1 for item in audit_log if item.get("operation") == "read" and item.get("status") == "denied")

    return {
        "memory_layer_version": str(payload.get("memory_layer_version") or MEMORY_LAYER_VERSION),
        "last_updated": str(payload.get("last_updated") or ""),
        "self_modification_policy": "approval_required",
        "advisory_only": True,
        "total_records": len(records),
        "patterns_by_key": patterns_by_key,
        "records_by_project": projects,
        "records_by_source": sources,
        "records_by_scope": scopes,
        "records_by_category": categories,
        "audit_event_count": len(audit_log),
        "denied_write_count": denied_write_count,
        "denied_read_count": denied_read_count,
        "recent_audit_events": audit_log[-10:],
    }


def build_memory_layer_summary_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_memory_layer_summary(**kwargs)
    except Exception:
        return {
            "memory_layer_version": MEMORY_LAYER_VERSION,
            "last_updated": "",
            "self_modification_policy": "approval_required",
            "advisory_only": True,
            "total_records": 0,
            "patterns_by_key": {},
            "records_by_project": {},
            "records_by_source": {},
            "records_by_scope": {"project": 0, "cross_project": 0},
            "records_by_category": {},
            "audit_event_count": 0,
            "denied_write_count": 0,
            "denied_read_count": 0,
            "recent_audit_events": [],
        }
