"""
Controlled executor backend registry.
"""

from __future__ import annotations

from typing import Any

from NEXUS.executor_backends.openclaw_executor import (
    BACKEND_ID as OPENCLAW_BACKEND_ID,
    execute_openclaw_package,
    get_adapter_status as get_openclaw_adapter_status,
)
from NEXUS.executor_backends.playwright_browser_executor import (
    BACKEND_ID as PLAYWRIGHT_BROWSER_BACKEND_ID,
    execute_playwright_browser_package,
    get_adapter_status as get_playwright_browser_adapter_status,
)


EXECUTOR_BACKENDS: dict[str, dict[str, Any]] = {
    OPENCLAW_BACKEND_ID: {
        "backend_id": OPENCLAW_BACKEND_ID,
        "executor": execute_openclaw_package,
        "status_getter": get_openclaw_adapter_status,
    },
    PLAYWRIGHT_BROWSER_BACKEND_ID: {
        "backend_id": PLAYWRIGHT_BROWSER_BACKEND_ID,
        "executor": execute_playwright_browser_package,
        "status_getter": get_playwright_browser_adapter_status,
    },
}


def get_executor_backend(backend_id: str | None) -> dict[str, Any] | None:
    if not backend_id:
        return None
    return EXECUTOR_BACKENDS.get(str(backend_id).strip().lower())


def get_executor_backend_status(backend_id: str | None) -> dict[str, Any]:
    backend = get_executor_backend(backend_id)
    if not backend:
        return {
            "backend_id": str(backend_id or "").strip().lower(),
            "adapter_status": "inactive",
            "controlled_executor_only": True,
        }
    getter = backend.get("status_getter")
    if callable(getter):
        try:
            return dict(getter() or {})
        except Exception:
            return {
                "backend_id": str(backend_id or "").strip().lower(),
                "adapter_status": "error",
                "controlled_executor_only": True,
            }
    return {
        "backend_id": str(backend_id or "").strip().lower(),
        "adapter_status": "inactive",
        "controlled_executor_only": True,
    }


__all__ = [
    "EXECUTOR_BACKENDS",
    "get_executor_backend",
    "get_executor_backend_status",
]
