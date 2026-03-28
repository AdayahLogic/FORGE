"""
Safe, additive integration workflows for external bridges.
"""

from __future__ import annotations

from typing import Any

from NEXUS.elevenlabs_bridge import elevenlabs_status, generate_voice_audio
from NEXUS.firecrawl_bridge import extract_business_details, firecrawl_status
from NEXUS.stripe_bridge import create_payment_link, stripe_status
from NEXUS.tavily_bridge import search_business_leads, tavily_status


def integration_status_snapshot() -> dict[str, Any]:
    return {
        "tavily": tavily_status(),
        "firecrawl": firecrawl_status(),
        "elevenlabs": elevenlabs_status(),
        "stripe": stripe_status(),
    }


def run_lead_discovery_workflow(
    query: str,
    *,
    location: str | None = None,
    limit: int = 10,
    enrich: bool = True,
) -> dict[str, Any]:
    discovered = search_business_leads(query=query, location=location, limit=limit)
    if discovered.get("status") != "ready":
        return {
            "status": discovered.get("status") or "failed",
            "reason": discovered.get("reason") or "",
            "results": [],
            "enriched_results": [],
            "outreach_status": "manual_only_no_auto_send",
        }

    raw_results = discovered.get("results") if isinstance(discovered.get("results"), list) else []
    enriched_results: list[dict[str, Any]] = []
    if enrich:
        for row in raw_results:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            enrichment = extract_business_details(url)
            enriched_results.append(
                {
                    "lead": row,
                    "enrichment": enrichment.get("details") if isinstance(enrichment.get("details"), dict) else {},
                    "enrichment_status": enrichment.get("status") or "failed",
                }
            )

    return {
        "status": "ready",
        "reason": "",
        "results": raw_results,
        "enriched_results": enriched_results,
        "outreach_status": "manual_only_no_auto_send",
    }


def create_deal_payment_link_workflow(
    *,
    approval_granted: bool = False,
    product_name: str | None = None,
    price_cents: int | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    if not approval_granted:
        return {
            "status": "approval_required",
            "reason": "Payment link creation requires explicit approval.",
            "payment_url": "",
            "price_cents": 0,
            "currency": "",
            "product_name": "",
        }
    result = create_payment_link(product_name=product_name, price_cents=price_cents, currency=currency)
    return {
        **result,
        "billing_mode": "one_time_only",
    }


def generate_voice_audio_workflow(
    *,
    text: str,
    explicit_request: bool = False,
    voice_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    if not explicit_request:
        return {
            "status": "approval_required",
            "reason": "Voice generation requires explicit request.",
            "audio_path": "",
        }
    return generate_voice_audio(text=text, voice_id=voice_id, model_id=model_id)
