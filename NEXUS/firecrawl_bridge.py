"""Safe Firecrawl enrichment bridge for Forge."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import request

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_services(markdown: str) -> list[str]:
    rows: list[str] = []
    for line in markdown.splitlines():
        text = _to_text(line).lstrip("-*")
        if not text:
            continue
        lowered = text.lower()
        if any(token in lowered for token in ("service", "clean", "consult", "repair", "install", "support")):
            rows.append(text[:120])
        if len(rows) >= 5:
            break
    return rows


def enrich_leads_safe(*, leads: list[dict[str, Any]], timeout_seconds: int = 20) -> dict[str, Any]:
    api_key = _to_text(os.environ.get("FIRECRAWL_API_KEY"))
    if not api_key:
        return {
            "status": "not_configured",
            "reason": "Firecrawl not configured",
            "enrichment_occurred": False,
            "leads": [dict(item) for item in list(leads or []) if isinstance(item, dict)],
        }

    enriched: list[dict[str, Any]] = []
    enriched_count = 0
    for lead in [dict(item) for item in list(leads or []) if isinstance(item, dict)]:
        website = _to_text(lead.get("website"))
        if not website:
            enriched.append(lead)
            continue
        req = request.Request(
            "https://api.firecrawl.dev/v1/scrape",
            data=json.dumps({"url": website, "formats": ["markdown"], "onlyMainContent": True}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=max(5, int(timeout_seconds))) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw.strip() else {}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            markdown = _to_text(data.get("markdown"))
            emails = list(dict.fromkeys(_EMAIL_PATTERN.findall(markdown)))[:3] if markdown else []
            services = _extract_services(markdown) if markdown else []
            if emails:
                lead["contact_email"] = emails[0]
            if services:
                lead["services"] = services
            if markdown:
                lead["snippet"] = markdown[:320].replace("\n", " ").strip() or _to_text(lead.get("snippet"))
                enriched_count += 1
        except Exception:
            pass
        enriched.append(lead)

    return {"status": "ok", "enrichment_occurred": enriched_count > 0, "enriched_count": enriched_count, "leads": enriched}
