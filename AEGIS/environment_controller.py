from __future__ import annotations

import os
from typing import Any


ENV_LOCAL_DEV = "local_dev"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"


def determine_environment(request: dict[str, Any] | None = None) -> str:
    """
    Define environments for AEGIS policy gating.

    Low-risk MVP policy:
    - Prefer explicit FORGE_ENV env var when set.
    - Otherwise use local_dev by default.
    """
    env = os.getenv("FORGE_ENV")
    if env:
        v = str(env).strip().lower()
        if v in (ENV_LOCAL_DEV, ENV_STAGING, ENV_PRODUCTION):
            return v
        # Tolerate synonyms.
        if v in ("prod", "production"):
            return ENV_PRODUCTION
        if v in ("stage", "staging"):
            return ENV_STAGING
        if v in ("dev", "local", "local_dev"):
            return ENV_LOCAL_DEV

    # Heuristic fallback: if runtime target looks external, bias toward staging.
    req = request or {}
    runtime = str(req.get("runtime_target_id") or "").strip().lower()
    if runtime in ("cloud_worker", "remote_worker"):
        return ENV_STAGING
    return ENV_LOCAL_DEV

