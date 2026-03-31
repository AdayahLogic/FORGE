from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACE_FILENAME = "portfolio_autonomy_trace.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _trace_path(base_path: str | None = None) -> Path:
    if base_path:
        root = Path(base_path).resolve()
    else:
        env_path = str(os.getenv("FORGE_PORTFOLIO_CONTROL_DIR") or "").strip()
        root = Path(env_path).resolve() if env_path else (Path(__file__).resolve().parent.parent / "state")
    root.mkdir(parents=True, exist_ok=True)
    return root / TRACE_FILENAME


def _compact_text(value: Any, *, limit: int = 320) -> str:
    text = str(value or "").strip()
    compact = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def normalize_portfolio_trace_event(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    decision_inputs = dict(raw.get("decision_inputs") or {})
    compact_inputs = {
        _compact_text(k, limit=80): _compact_text(v, limit=180)
        for k, v in list(decision_inputs.items())[:12]
    }
    return {
        "timestamp": _compact_text(raw.get("timestamp"), limit=64) or _now_iso(),
        "event_type": _compact_text(raw.get("event_type"), limit=80) or "portfolio_event",
        "project_id": _compact_text(raw.get("project_id"), limit=120),
        "mission_ref": _compact_text(raw.get("mission_ref"), limit=120),
        "reason": _compact_text(raw.get("reason")),
        "decision_inputs": compact_inputs,
        "resulting_action": _compact_text(raw.get("resulting_action"), limit=120),
        "visibility": _compact_text(raw.get("visibility"), limit=40) or "operator",
        "source": _compact_text(raw.get("source"), limit=80) or "portfolio_autonomy",
    }


def append_portfolio_trace_event(event: dict[str, Any], base_path: str | None = None) -> str:
    normalized = normalize_portfolio_trace_event(event)
    path = _trace_path(base_path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    return str(path)


def append_portfolio_trace_event_safe(event: dict[str, Any], base_path: str | None = None) -> str | None:
    try:
        return append_portfolio_trace_event(event, base_path=base_path)
    except Exception:
        return None


def read_portfolio_trace_tail(n: int = 50, *, event_type: str = "", base_path: str | None = None) -> list[dict[str, Any]]:
    path = _trace_path(base_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    normalized_type = _compact_text(event_type).lower()
    for line in lines[-max(1, min(int(n or 50), 200)) :]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        if normalized_type and str(parsed.get("event_type") or "").strip().lower() != normalized_type:
            continue
        out.append(parsed)
    return out
