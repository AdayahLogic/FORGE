"""Safe Tavily discovery bridge for Forge."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def discover_leads_safe(*, query: str, max_results: int = 5, timeout_seconds: int = 20) -> dict[str, Any]:
    api_key = _to_text(os.environ.get("TAVILY_API_KEY"))
    if not api_key:
        return {"status": "not_configured", "reason": "Tavily not configured", "leads": []}

    body = {
        "api_key": api_key,
        "query": _to_text(query),
        "search_depth": "basic",
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
        "include_images": False,
    }
    req = request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, int(timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        payload = json.loads(raw) if raw.strip() else {}
        results = [item for item in list(payload.get("results") or []) if isinstance(item, dict)]
        leads = [
            {
                "name": _to_text(item.get("title")) or "Unknown Business",
                "website": _to_text(item.get("url")),
                "snippet": _to_text(item.get("content")),
            }
            for item in results
        ]
        return {
            "status": "ok",
            "query": _to_text(query),
            "lead_count": len(leads),
            "leads": leads,
            "response_time": payload.get("response_time"),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"Tavily request failed: {exc}",
            "query": _to_text(query),
            "leads": [],
        }
