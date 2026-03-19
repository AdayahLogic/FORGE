"""
AEGIS file guard: file mutation guardrails using project scope and blocked path matching.

- Deterministic allow/deny/review_required based on action mode and paths.
- Returns allowed_reads, allowed_writes, denied_matches for auditability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _to_path(v: Any) -> Path | None:
    if v is None:
        return None
    try:
        return Path(str(v)).resolve()
    except Exception:
        return None


def _normalize_paths(paths: Any) -> list[str]:
    if not paths:
        return []
    if isinstance(paths, list):
        out: list[str] = []
        for p in paths:
            try:
                s = str(p).strip()
                if s:
                    out.append(s)
            except Exception:
                pass
        return out
    s = str(paths).strip()
    return [s] if s else []


# Path segments that, if present in a candidate path, trigger deny or review.
_BLOCKED_SEGMENTS = (
    ".git/config",
    ".env",
    "secrets",
    "credentials",
    "id_rsa",
    "id_ed25519",
    "shadow",
    "passwd",
    "/etc/",
    "\\windows\\system32",
)


def evaluate_file_guard(
    *,
    project_path: str | None = None,
    action_mode: str = "evaluation",
    requested_reads: list[str] | None = None,
    requested_writes: list[str] | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate file access against project scope and blocked path rules.

    Result shape:
    {
      "file_guard_status": "allow" | "deny" | "review_required" | "error_fallback",
      "file_guard_reason": "...",
      "allowed_reads": [],
      "allowed_writes": [],
      "denied_matches": []
    }
    """
    req = request or {}
    proj = _to_path(project_path or req.get("project_path"))
    mode = str(action_mode or req.get("action_mode") or "evaluation").strip().lower()
    reads = _normalize_paths(requested_reads or req.get("requested_reads") or req.get("candidate_paths"))
    writes = _normalize_paths(requested_writes or req.get("requested_writes"))

    allowed_reads: list[str] = []
    allowed_writes: list[str] = []
    denied_matches: list[str] = []

    def check_path(path_str: str, for_write: bool) -> bool:
        path_str_lower = path_str.replace("\\", "/").lower()
        for seg in _BLOCKED_SEGMENTS:
            if seg.lower() in path_str_lower:
                denied_matches.append(f"{path_str} (blocked segment: {seg})")
                return False
        p = _to_path(path_str)
        if not p:
            denied_matches.append(f"{path_str} (invalid path)")
            return False
        if proj:
            try:
                rp = p.resolve()
                rproj = proj.resolve()
                if rp != rproj and rproj not in rp.parents:
                    try:
                        rp.relative_to(rproj)
                    except ValueError:
                        denied_matches.append(f"{path_str} (outside project scope)")
                        return False
            except Exception:
                denied_matches.append(f"{path_str} (scope check failed)")
                return False
        return True

    for r in reads:
        if check_path(r, for_write=False):
            allowed_reads.append(r)
    for w in writes:
        if check_path(w, for_write=True):
            allowed_writes.append(w)

    if mode == "evaluation":
        if not reads and not writes:
            return {
                "file_guard_status": "allow",
                "file_guard_reason": "Evaluation mode; no file paths to guard.",
                "allowed_reads": [],
                "allowed_writes": [],
                "denied_matches": [],
            }
        if denied_matches:
            return {
                "file_guard_status": "review_required",
                "file_guard_reason": "Some paths matched blocked segments or scope.",
                "allowed_reads": allowed_reads,
                "allowed_writes": allowed_writes,
                "denied_matches": denied_matches,
            }
        return {
            "file_guard_status": "allow",
            "file_guard_reason": "Evaluation; paths within scope and not blocked.",
            "allowed_reads": allowed_reads,
            "allowed_writes": allowed_writes,
            "denied_matches": [],
        }

    if not proj and (reads or writes):
        return {
            "file_guard_status": "deny",
            "file_guard_reason": "File access requires project_path for execution/mutation.",
            "allowed_reads": [],
            "allowed_writes": [],
            "denied_matches": list(reads) + list(writes),
        }

    if denied_matches:
        return {
            "file_guard_status": "deny",
            "file_guard_reason": "One or more paths denied by scope or blocked segments.",
            "allowed_reads": allowed_reads,
            "allowed_writes": allowed_writes,
            "denied_matches": denied_matches,
        }

    if writes and mode == "mutation":
        return {
            "file_guard_status": "allow",
            "file_guard_reason": "Mutation paths within scope and not blocked.",
            "allowed_reads": allowed_reads,
            "allowed_writes": allowed_writes,
            "denied_matches": [],
        }

    return {
        "file_guard_status": "allow",
        "file_guard_reason": "Paths within scope and not blocked.",
        "allowed_reads": allowed_reads,
        "allowed_writes": allowed_writes,
        "denied_matches": [],
    }


def evaluate_file_guard_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return evaluate_file_guard(**kwargs)
    except Exception as e:
        return {
            "file_guard_status": "error_fallback",
            "file_guard_reason": str(e)[: 512],
            "allowed_reads": [],
            "allowed_writes": [],
            "denied_matches": [f"file_guard_error: {e}"],
        }
