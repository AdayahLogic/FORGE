"""
NEXUS runtime adapters.

Each adapter exposes dispatch(dispatch_plan) for simulated routing.
No real execution in this step.
"""

from NEXUS.runtimes.local_runtime import dispatch as local_dispatch
from NEXUS.runtimes.cursor_runtime import dispatch as cursor_dispatch
from NEXUS.runtimes.codex_runtime import dispatch as codex_dispatch
from NEXUS.runtimes.claude_runtime import dispatch as claude_dispatch

RUNTIME_ADAPTERS = {
    "local": local_dispatch,
    "cursor": cursor_dispatch,
    "codex": codex_dispatch,
    "claude": claude_dispatch,
}

__all__ = ["local_dispatch", "cursor_dispatch", "codex_dispatch", "claude_dispatch", "RUNTIME_ADAPTERS"]
