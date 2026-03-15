"""
Nexus core registry of model providers.

Used by the model router to resolve provider names and fall back safely
when a provider is missing, unknown, or not yet implemented.
"""

from __future__ import annotations

from typing import Any

# Status: "implemented" = can be used for generation; "planned" = fallback to openai if requested.
PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai": {
        "status": "implemented",
        "default_model": "gpt-5.4",
        "description": "OpenAI API (Responses API / chat completions).",
    },
    "anthropic": {
        "status": "planned",
        "default_model": None,
        "description": "Anthropic Claude API (planned).",
    },
    "local": {
        "status": "planned",
        "default_model": None,
        "description": "Local / self-hosted models (planned).",
    },
}


def is_provider_implemented(provider: str | None) -> bool:
    """Return True only if provider is non-empty and implemented."""
    if not provider or not isinstance(provider, str):
        return False
    entry = PROVIDER_REGISTRY.get(provider.strip().lower())
    return entry is not None and entry.get("status") == "implemented"


def get_default_model(provider: str) -> str | None:
    """Return the default model for a provider, or None."""
    entry = PROVIDER_REGISTRY.get(provider.strip().lower())
    if not entry:
        return None
    return entry.get("default_model")


def resolve_provider(provider: str | None) -> str:
    """
    Resolve to an implemented provider name.
    Falls back to "openai" if provider is None, unknown, or not implemented.
    """
    if is_provider_implemented(provider):
        return (provider or "").strip().lower()
    return "openai"
