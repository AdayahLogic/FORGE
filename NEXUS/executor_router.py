"""
Executor routing for supervised mission packets.

Routing is policy/readiness-driven and packet-based. This module does not execute.
"""

from __future__ import annotations

from typing import Any

from NEXUS.runtime_target_registry import get_runtime_target_health


TASK_TYPES = {
    "reasoning_review_scoring",
    "coding_repo_implementation",
    "browser_ui_computer_use",
    "unsupported_manual",
}

EXECUTOR_ROUTES = {"forge_internal", "codex", "openclaw", "operator_only"}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _classify_task(task_summary: str, task_type_hint: str | None = None) -> str:
    hint = _normalize_text(task_type_hint)
    text = _normalize_text(task_summary)
    corpus = f"{hint} {text}".strip()
    browser_terms = ("browser", "ui", "click", "navigate", "web", "computer-use", "open tab", "screenshot")
    code_terms = ("code", "repo", "implement", "refactor", "test", "python", "typescript", "fix bug", "patch")
    reasoning_terms = ("reason", "review", "score", "evaluate", "analysis", "governance")
    if any(term in corpus for term in browser_terms):
        return "browser_ui_computer_use"
    if any(term in corpus for term in code_terms):
        return "coding_repo_implementation"
    if any(term in corpus for term in reasoning_terms):
        return "reasoning_review_scoring"
    return "unsupported_manual"


def route_executor(
    *,
    task_summary: str,
    task_type_hint: str | None = None,
    allowed_executors: list[str] | None = None,
) -> dict[str, Any]:
    task_type = _classify_task(task_summary=task_summary, task_type_hint=task_type_hint)
    allowed = [str(x).strip().lower() for x in (allowed_executors or []) if str(x).strip()]
    if not allowed:
        allowed = ["forge_internal", "codex", "openclaw", "operator_only"]

    route = "operator_only"
    route_reason = "Unsupported task; requires operator handling."
    confidence = 0.6
    fallback = "operator_only"
    route_status = "routed"

    if task_type == "reasoning_review_scoring":
        route = "forge_internal"
        route_reason = "Task classified as reasoning/review/scoring."
        confidence = 0.92
        fallback = "operator_only"
    elif task_type == "coding_repo_implementation":
        route = "codex"
        route_reason = "Task classified as coding/repo implementation."
        confidence = 0.9
        fallback = "forge_internal"
    elif task_type == "browser_ui_computer_use":
        route = "openclaw"
        route_reason = "Task classified as browser/UI/computer-use."
        confidence = 0.88
        fallback = "operator_only"
    else:
        route = "operator_only"
        route_reason = "Task classification is unsupported/manual."
        confidence = 0.7
        fallback = "operator_only"

    if route == "openclaw":
        health = get_runtime_target_health("openclaw")
        if not bool(health.get("dispatch_ready")):
            route_status = "readiness_limited"
            route_reason = (
                "OpenClaw route selected by policy, but runtime is not dispatch-ready. "
                "Routing remains packet-level until integration is active."
            )
    if route not in allowed:
        route = "operator_only"
        route_reason = "Requested route is outside mission allowed executors."
        confidence = min(confidence, 0.65)
        route_status = "policy_constrained"
        fallback = "operator_only"

    return {
        "executor_task_type": task_type if task_type in TASK_TYPES else "unsupported_manual",
        "executor_route": route if route in EXECUTOR_ROUTES else "operator_only",
        "executor_route_reason": route_reason,
        "executor_route_confidence": round(float(confidence), 3),
        "executor_route_status": route_status,
        "executor_fallback_route": fallback,
    }
