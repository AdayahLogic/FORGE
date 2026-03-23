from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ProjectMemory:
    """
    Normalized, project-scoped memory snapshot for Nexus.

    This model stays intentionally small and dependency-free so it works in the
    base FORGE environment.
    """

    project_name: Optional[str] = None
    project_overview: Optional[str] = None
    current_focus: Optional[str] = None
    dev_notes: Optional[str] = None
    next_steps: Optional[str] = None
    architecture_notes: Optional[str] = None
    memory_status: str = "empty"

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_text(value: Any, *, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _normalize_evidence(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    for item in items:
        text = _normalize_text(item, limit=300)
        if text and text not in out:
            out.append(text)
    return out[:10]


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


@dataclass
class GovernedMemoryEntry:
    memory_id: str = ""
    source_type: str = ""
    source_project: str = ""
    scope: Literal["project", "cross_project"] = "project"
    category: str = ""
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    attribution: str = ""
    recorded_at: str = ""
    status: str = "active"
    governance_trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.memory_id = _normalize_text(self.memory_id, limit=120)
        self.source_type = _normalize_text(self.source_type, limit=120)
        self.source_project = _normalize_text(self.source_project, limit=120)
        self.scope = "cross_project" if str(self.scope or "").strip().lower() == "cross_project" else "project"
        self.category = _normalize_text(self.category, limit=120)
        self.summary = _normalize_text(self.summary, limit=500)
        self.evidence = _normalize_evidence(self.evidence)
        self.confidence = _normalize_confidence(self.confidence)
        self.attribution = _normalize_text(self.attribution, limit=200)
        self.recorded_at = _normalize_text(self.recorded_at, limit=60)
        self.status = _normalize_text(self.status, limit=80)
        self.governance_trace = dict(self.governance_trace or {})

    def dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GovernedMemoryOperation:
    status: Literal["ok", "denied", "error"] = "error"
    operation: Literal["read", "write"] = "read"
    memory_scope: Literal["project", "cross_project"] = "project"
    actor: str = ""
    source_type: str = ""
    reason: str = ""
    governance_trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ("ok", "denied", "error"):
            self.status = "error"
        if self.operation not in ("read", "write"):
            self.operation = "read"
        self.memory_scope = "cross_project" if str(self.memory_scope or "").strip().lower() == "cross_project" else "project"
        self.actor = _normalize_text(self.actor, limit=120)
        self.source_type = _normalize_text(self.source_type, limit=120)
        self.reason = _normalize_text(self.reason, limit=300)
        self.governance_trace = dict(self.governance_trace or {})

    def dict(self) -> dict[str, Any]:
        return asdict(self)
