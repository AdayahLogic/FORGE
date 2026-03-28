"""
Tavily integration bridge for safe lead discovery.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _text(value: Any) -> str:
    return str(value or "").strip()


def tavily_status() -> dict[str, Any]:
    configured = bool(_text(os.getenv("TAVILY_API_KEY")))
    return {
        "status": "ready" if configured else "not_configured",
        "configured": configured,
    }


def search_business_leads(query: str, location: str | None = None, limit: int = 10) -> dict[str, Any]:
    """
    Search candidate business leads via Tavily.

    Normalized item format:
    - title
    - url
    - snippet
    - source
    """
    api_key = _text(os.getenv("TAVILY_API_KEY"))
    if not api_key:
        return {
            "status": "not_configured",
            "reason": "Tavily not configured",
            "results": [],
        }

    query_text = _text(query)
    if not query_text:
        return {
            "status": "failed",
            "reason": "query is required",
            "results": [],
        }

    max_results = max(1, min(int(limit or 10), 20))
    if _text(location):
        query_text = f"{query_text} in {_text(location)}"

    payload = {
        "api_key": api_key,
        "query": query_text,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        req = request.Request(
            TAVILY_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=20.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        rows = parsed.get("results") if isinstance(parsed, dict) else []
        if not isinstance(rows, list):
            rows = []
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "title": _text(row.get("title")),
                    "url": _text(row.get("url")),
                    "snippet": _text(row.get("content"))[:500],
                    "source": "tavily",
                }
            )
        return {
            "status": "ready",
            "reason": "",
            "results": normalized,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "results": [],
        }
