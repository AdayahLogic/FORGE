from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KILL_SWITCH_FILENAME = "portfolio_autonomy_kill_switch.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_state_dir(base_path: str | None = None) -> Path:
    if base_path:
        root = Path(base_path).resolve()
    else:
        env_path = str(os.getenv("FORGE_PORTFOLIO_CONTROL_DIR") or "").strip()
        if env_path:
            root = Path(env_path).resolve()
        else:
            root = Path(__file__).resolve().parent.parent / "state"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _kill_switch_path(base_path: str | None = None) -> Path:
    return _base_state_dir(base_path) / KILL_SWITCH_FILENAME


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def normalize_portfolio_kill_switch(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "changed_at": _normalize_text(raw.get("changed_at"), _now_iso()),
        "changed_by": _normalize_text(raw.get("changed_by"), "system"),
        "source": _normalize_text(raw.get("source"), "portfolio_autonomy"),
        "reason": _normalize_text(raw.get("reason")),
        "scope": _normalize_text(raw.get("scope"), "portfolio_autonomy"),
    }


def read_portfolio_kill_switch(base_path: str | None = None) -> dict[str, Any]:
    path = _kill_switch_path(base_path)
    if not path.exists():
        return normalize_portfolio_kill_switch({})
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return normalize_portfolio_kill_switch(raw)


def write_portfolio_kill_switch(
    *,
    enabled: bool,
    reason: str = "",
    changed_by: str = "system",
    source: str = "portfolio_autonomy",
    scope: str = "portfolio_autonomy",
    base_path: str | None = None,
) -> dict[str, Any]:
    path = _kill_switch_path(base_path)
    payload = normalize_portfolio_kill_switch(
        {
            "enabled": bool(enabled),
            "changed_at": _now_iso(),
            "changed_by": changed_by,
            "source": source,
            "reason": reason,
            "scope": scope,
        }
    )
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent), suffix=".tmp") as tmp:
        tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    return payload


def set_portfolio_kill_switch(
    *,
    enabled: bool,
    reason: str = "",
    changed_by: str = "system",
    source: str = "portfolio_autonomy",
    scope: str = "portfolio_autonomy",
    base_path: str | None = None,
) -> dict[str, Any]:
    return write_portfolio_kill_switch(
        enabled=enabled,
        reason=reason,
        changed_by=changed_by,
        source=source,
        scope=scope,
        base_path=base_path,
    )


def portfolio_kill_switch_active(base_path: str | None = None) -> bool:
    return bool(read_portfolio_kill_switch(base_path).get("enabled"))
