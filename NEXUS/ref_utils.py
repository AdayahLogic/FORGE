"""
NEXUS ref normalization utilities (Phase 28).

Normalized handling for cross-artifact ref lists.
Defaults to empty lists; deduplicates; coerces to strings.
No fabrication; missing refs degrade safely.
"""

from __future__ import annotations

from typing import Any

REF_LIST_MAX_LEN = 20


def normalize_ref_list(
    ids: Any,
    *,
    max_len: int = REF_LIST_MAX_LEN,
) -> list[str]:
    """
    Normalize ref list to list[str]. Deduplicates, coerces to str.
    Returns empty list if input is None, invalid, or empty.
    """
    if ids is None:
        return []
    if isinstance(ids, str) and ids.strip():
        return [str(ids.strip())][:max_len]
    if not isinstance(ids, (list, tuple)):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for x in ids:
        if x is None:
            continue
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) >= max_len:
                break
    return out


def merge_ref_lists(
    *lists: Any,
    max_len: int = REF_LIST_MAX_LEN,
) -> list[str]:
    """
    Merge multiple ref lists, deduplicate, normalize.
    Order: first occurrence wins.
    """
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for s in normalize_ref_list(lst, max_len=max_len * 2):
            if s not in seen:
                seen.add(s)
                out.append(s)
                if len(out) >= max_len:
                    return out
    return out
