"""
Firecrawl integration bridge for lead enrichment.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import request


DEFAULT_FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1"
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")


def _text(value: Any) -> str:
    return str(value or "").strip()


def firecrawl_status() -> dict[str, Any]:
    configured = bool(_text(os.getenv("FIRECRAWL_API_KEY")))
    return {
        "status": "ready" if configured else "not_configured",
        "configured": configured,
    }


def _api_url() -> str:
    return _text(os.getenv("FIRECRAWL_API_URL")) or DEFAULT_FIRECRAWL_API_URL


def scrape_page(url: str) -> dict[str, Any]:
    api_key = _text(os.getenv("FIRECRAWL_API_KEY"))
    if not api_key:
        return {
            "status": "not_configured",
            "reason": "Firecrawl not configured",
            "data": {},
        }
    target_url = _text(url)
    if not target_url:
        return {
            "status": "failed",
            "reason": "url is required",
            "data": {},
        }

    endpoint = f"{_api_url().rstrip('/')}/scrape"
    payload = {
        "url": target_url,
        "formats": ["markdown", "html"],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    try:
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        with request.urlopen(req, timeout=25.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        data = parsed.get("data") if isinstance(parsed, dict) else {}
        if not isinstance(data, dict):
            data = {}
        return {
            "status": "ready",
            "reason": "",
            "data": data,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "data": {},
        }


def extract_business_details(url: str) -> dict[str, Any]:
    scraped = scrape_page(url)
    if scraped.get("status") != "ready":
        return {
            "status": scraped.get("status") or "failed",
            "reason": scraped.get("reason") or "",
            "details": {
                "business_name": "",
                "email": "",
                "phone": "",
                "services": [],
                "description": "",
            },
        }

    data = scraped.get("data") if isinstance(scraped.get("data"), dict) else {}
    markdown = _text(data.get("markdown"))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    title = _text(metadata.get("title"))
    business_name = title.split("|")[0].split("-")[0].strip() if title else ""

    email_match = EMAIL_RE.search(markdown)
    phone_match = PHONE_RE.search(markdown)
    email = _text(email_match.group(1) if email_match else "")
    phone = _text(phone_match.group(1) if phone_match else "")

    service_keywords = [
        "automation",
        "web development",
        "seo",
        "marketing",
        "design",
        "consulting",
        "software",
        "integration",
        "ecommerce",
        "mobile app",
    ]
    lowered = markdown.lower()
    services = [item for item in service_keywords if item in lowered][:10]
    description = _text(markdown)[:500]

    return {
        "status": "ready",
        "reason": "",
        "details": {
            "business_name": business_name,
            "email": email,
            "phone": phone,
            "services": services,
            "description": description,
        },
    }
