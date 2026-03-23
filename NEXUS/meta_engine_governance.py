"""
Meta-engine governance priority resolution.
"""

from __future__ import annotations

from typing import Any


META_ENGINE_PRIORITY = ("sentinel", "veritas", "leviathan", "titan", "helios")


def _extract_review_required(summary: dict[str, Any] | None) -> bool:
    return bool((summary or {}).get("review_required", False))


def _extract_status(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict):
        return ""
    for key in ("sentinel_status", "veritas_status", "leviathan_status", "titan_status", "helios_status"):
        if key in summary:
            return str(summary.get(key) or "").strip().lower()
    return ""


def resolve_meta_engine_governance(
    *,
    titan_summary: dict[str, Any] | None = None,
    leviathan_summary: dict[str, Any] | None = None,
    helios_summary: dict[str, Any] | None = None,
    veritas_summary: dict[str, Any] | None = None,
    sentinel_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engines = {
        "sentinel": sentinel_summary or {},
        "veritas": veritas_summary or {},
        "leviathan": leviathan_summary or {},
        "titan": titan_summary or {},
        "helios": helios_summary or {},
    }
    governing_engine = ""
    resolution_reason = "No meta-engine signals available."
    review_required = False
    conflict_detected = False
    active_review_engines: list[str] = []
    for engine_name in META_ENGINE_PRIORITY:
        summary = engines.get(engine_name) or {}
        if _extract_review_required(summary) or _extract_status(summary) in ("review_required", "blocked", "deferred", "error_fallback"):
            active_review_engines.append(engine_name)
            if not governing_engine:
                governing_engine = engine_name
                review_required = True
                resolution_reason = f"{engine_name.upper()} holds highest-priority active governance posture."
    if len(active_review_engines) > 1:
        conflict_detected = True
        resolution_reason = (
            f"Multiple meta-engines requested review ({', '.join(active_review_engines)}); "
            f"resolved by priority order {', '.join(x.upper() for x in META_ENGINE_PRIORITY)}."
        )
    return {
        "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
        "governing_engine": governing_engine.upper() if governing_engine else "",
        "review_required": review_required,
        "conflict_detected": conflict_detected,
        "system_pause_required": bool(conflict_detected and len(active_review_engines) > 2),
        "resolution_reason": resolution_reason,
        "active_review_engines": [name.upper() for name in active_review_engines],
    }


def resolve_meta_engine_governance_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return resolve_meta_engine_governance(**kwargs)
    except Exception as e:
        return {
            "priority_order": [name.upper() for name in META_ENGINE_PRIORITY],
            "governing_engine": "",
            "review_required": True,
            "conflict_detected": True,
            "system_pause_required": True,
            "resolution_reason": f"Meta-engine governance resolution failed: {e}",
            "active_review_engines": [],
        }
