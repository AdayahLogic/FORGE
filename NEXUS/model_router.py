"""
Nexus core model routing layer.

Routes model calls through a provider-aware layer with safe fallback to OpenAI
when provider is missing, unknown, or not yet implemented. Returns a normalized
response shape for consistent handling.
"""

from __future__ import annotations

from typing import Any

from NEXUS.model_provider_registry import get_default_model, resolve_provider
from NEXUS.models.model_gateway import ModelGateway


def route_generate(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Route a generation request through the resolved provider.

    - Resolves provider (falls back to openai if missing/unknown/planned).
    - Uses ModelGateway for the actual call.
    - Returns normalized dict: provider, model, output_text, status.

    Does not add streaming, async, or tool calling. On gateway failure,
    exceptions propagate so callers (e.g. planner) can retry or fall back.
    """
    resolved = resolve_provider(provider)
    model_name = model or get_default_model(resolved) or "gpt-5.4"

    gateway = ModelGateway()
    result = gateway.generate(
        prompt=prompt,
        provider=resolved,
        model=model_name,
    )

    return {
        "provider": result.get("provider", resolved),
        "model": result.get("model", model_name),
        "output_text": result.get("output_text", ""),
        "status": result.get("status", "ok"),
    }


def route_model(
    *,
    task_class: str | None = None,
    active_project: str | None = None,
    agent_name: str | None = None,
    runtime_node: str | None = None,
    request_text: str | None = None,
) -> dict[str, Any]:
    """
    Deterministic model routing evaluation (does not execute a model call).

    Stable shape:
    {
      model_router_status, selected_provider, selected_model,
      task_class, routing_reason
    }
    """
    tc = (task_class or "").strip().lower() or "fallback"
    agent = (agent_name or "").strip().lower()
    node = (runtime_node or "").strip().lower()
    text = (request_text or "").strip().lower()

    provider = "openai"
    default_model = get_default_model(provider) or "gpt-5.4"

    # Simple task-class driven selection; keep deterministic.
    if tc in ("planning", "summarization"):
        model = default_model
        reason = f"Task class '{tc}' routed to default OpenAI model."
        status = "selected"
    elif tc in ("coding",):
        model = default_model
        reason = "Coding task routed to default OpenAI model (gateway-managed)."
        status = "selected"
    else:
        model = default_model
        reason = "Fallback task class routed to default OpenAI model."
        status = "fallback_selected"

    return {
        "model_router_status": status,
        "selected_provider": provider,
        "selected_model": model,
        "task_class": tc,
        "routing_reason": reason,
    }


def route_model_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises; returns error_fallback on exception."""
    try:
        return route_model(**kwargs)
    except Exception:
        return {
            "model_router_status": "error_fallback",
            "selected_provider": "openai",
            "selected_model": get_default_model("openai") or "gpt-5.4",
            "task_class": (kwargs.get("task_class") or "fallback"),
            "routing_reason": "Model routing failed.",
        }
