"""
Nexus core model routing layer.

Routes model calls through a provider-aware layer with safe fallback to OpenAI
when provider is missing, unknown, or not yet implemented. Returns a normalized
response shape for consistent handling.
"""

from __future__ import annotations

from typing import Any

from core.model_provider_registry import get_default_model, resolve_provider
from core.models.model_gateway import ModelGateway


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
