"""
Controlled integration validation for Tavily -> Firecrawl -> Stripe -> ElevenLabs.

Safety constraints:
- No outreach sending.
- No customer charging.
- No autonomous calling/realtime behavior.
- One-time Stripe payment link creation only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url=url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _post_form(
    url: str,
    form: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any] | str]:
    body = urllib.parse.urlencode(form).encode("utf-8")
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url=url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(text)
            except json.JSONDecodeError:
                return response.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text


def _post_binary(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url=url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def validate_tavily() -> dict[str, Any]:
    api_key = _first_env("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "not_configured",
            "summary": "TAVILY_API_KEY missing.",
            "count": 0,
            "leads": [],
        }

    payload = {
        "api_key": api_key,
        "query": "cleaning businesses in Baltimore",
        "search_depth": "basic",
        "max_results": 8,
        "include_answer": False,
        "include_raw_content": False,
    }
    status, body = _post_json("https://api.tavily.com/search", payload, timeout=45)
    if status != 200 or not isinstance(body, dict):
        return {
            "status": "error",
            "summary": f"Tavily request failed with status {status}.",
            "http_status": status,
            "raw": body,
            "count": 0,
            "leads": [],
        }

    raw_results = body.get("results") if isinstance(body.get("results"), list) else []
    leads: list[dict[str, str]] = []
    for idx, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        leads.append(
            {
                "rank": str(idx + 1),
                "name": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("content") or "").strip(),
            }
        )
        if len(leads) >= 5:
            break

    return {
        "status": "ok",
        "summary": f"Found {len(leads)} lead(s) from Tavily.",
        "count": len(leads),
        "leads": leads,
    }


def _extract_email(text: str) -> str:
    match = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text or "")
    return match.group(1) if match else ""


def _extract_services(text: str) -> list[str]:
    lowered = (text or "").lower()
    known = [
        "residential cleaning",
        "commercial cleaning",
        "deep cleaning",
        "move in",
        "move out",
        "janitorial",
        "office cleaning",
        "carpet cleaning",
        "post construction cleaning",
        "disinfection",
    ]
    found: list[str] = []
    for service in known:
        if service in lowered and service not in found:
            found.append(service)
    return found


def validate_firecrawl(tavily_result: dict[str, Any]) -> dict[str, Any]:
    api_key = _first_env("FIRECRAWL_API_KEY")
    if not api_key:
        return {
            "status": "not_configured",
            "summary": "FIRECRAWL_API_KEY missing.",
            "enrichment": {},
        }

    leads = tavily_result.get("leads") if isinstance(tavily_result.get("leads"), list) else []
    if not leads:
        return {
            "status": "skipped",
            "summary": "No Tavily lead available to enrich.",
            "enrichment": {},
        }

    candidate = leads[0] if isinstance(leads[0], dict) else {}
    business_name = str(candidate.get("name") or "").strip()
    url = str(candidate.get("url") or "").strip()
    if not url:
        return {
            "status": "skipped",
            "summary": "First Tavily lead has no URL.",
            "enrichment": {},
        }

    payload = {"url": url, "formats": ["markdown"]}
    status, body = _post_json(
        "https://api.firecrawl.dev/v1/scrape",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if status != 200 or not isinstance(body, dict):
        return {
            "status": "error",
            "summary": f"Firecrawl request failed with status {status}.",
            "http_status": status,
            "raw": body,
            "enrichment": {},
        }

    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    markdown = str(data.get("markdown") or "")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    source_text = "\n".join(
        [
            markdown,
            str(metadata.get("description") or ""),
            str(metadata.get("title") or ""),
        ]
    )
    email = _extract_email(source_text)
    services = _extract_services(source_text)
    site_details = str(metadata.get("description") or "").strip() or markdown[:300].strip()

    return {
        "status": "ok",
        "summary": "Firecrawl enrichment completed for one lead.",
        "enrichment": {
            "business_name": business_name,
            "source_url": url,
            "email": email,
            "services": services,
            "site_details": site_details,
        },
    }


def validate_stripe() -> dict[str, Any]:
    api_key = _first_env("STRIPE_API_KEY")
    if not api_key:
        return {
            "status": "not_configured",
            "summary": "STRIPE_API_KEY missing.",
            "payment_link": {},
        }

    run_tag = f"forge_validation_{int(time.time())}"
    form = {
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": "Forge Integration Validation (One-Time)",
        "line_items[0][price_data][unit_amount]": "500",
        "line_items[0][price_data][tax_behavior]": "exclusive",
        "line_items[0][quantity]": "1",
        "metadata[validation_run]": run_tag,
        "metadata[safety_mode]": "one_time_only",
    }
    status, body = _post_form(
        "https://api.stripe.com/v1/payment_links",
        form,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=45,
    )
    if status not in (200, 201) or not isinstance(body, dict):
        return {
            "status": "error",
            "summary": f"Stripe request failed with status {status}.",
            "http_status": status,
            "raw": body,
            "payment_link": {},
        }

    payment_mode = str(body.get("type") or "payment").strip() or "payment"
    if payment_mode != "payment":
        return {
            "status": "error",
            "summary": f"Unexpected Stripe mode '{payment_mode}' (expected one-time payment).",
            "payment_link": {"id": body.get("id"), "url": body.get("url")},
        }

    return {
        "status": "ok",
        "summary": "Stripe one-time payment link created safely.",
        "payment_link": {
            "id": body.get("id"),
            "url": body.get("url"),
            "livemode": bool(body.get("livemode")),
            "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            "mode": payment_mode,
        },
    }


def validate_elevenlabs() -> dict[str, Any]:
    api_key = _first_env("ELEVENLABS_API_KEY")
    voice_id = _first_env("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
    if not api_key:
        return {
            "status": "not_configured",
            "summary": "ELEVENLABS_API_KEY missing.",
            "audio": {},
        }

    payload = {
        "text": "Forge integration test successful.",
        "model_id": "eleven_multilingual_v2",
    }
    status, audio_bytes = _post_binary(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        payload,
        headers={
            "Accept": "audio/mpeg",
            "xi-api-key": api_key,
        },
        timeout=90,
    )
    if status != 200:
        raw_text = audio_bytes.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = raw_text
        return {
            "status": "error",
            "summary": f"ElevenLabs request failed with status {status}.",
            "http_status": status,
            "raw": parsed,
            "audio": {},
        }

    out_dir = Path("tests") / "artifacts" / "integration_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"forge_integration_test_{int(time.time())}.mp3"
    out_file.write_bytes(audio_bytes)
    return {
        "status": "ok",
        "summary": "Generated one ElevenLabs audio file.",
        "audio": {
            "voice_id": voice_id,
            "path": str(out_file),
            "bytes": len(audio_bytes),
        },
    }


def validate_telegram_readiness() -> dict[str, Any]:
    """
    Telegram readiness for this phase is structural only:
    - Is there an explicit telegram bridge module?
    - Is there an existing command surface route for integration status?
    """
    repo_root = Path(__file__).resolve().parents[1]
    has_telegram_bridge = (repo_root / "NEXUS" / "telegram_bridge.py").exists()
    return {
        "status": "ok" if has_telegram_bridge else "needs_follow_up",
        "summary": (
            "Telegram bridge exists and can be wired to these validation summaries."
            if has_telegram_bridge
            else "No telegram bridge module found; minimal follow-up is adding a bounded status formatter + bridge sender path."
        ),
        "can_surface_integration_status": has_telegram_bridge,
        "can_surface_lead_summary": has_telegram_bridge,
        "can_surface_payment_link_summary": has_telegram_bridge,
        "can_surface_voice_summary": has_telegram_bridge,
    }


def validate_safety() -> dict[str, Any]:
    return {
        "status": "ok",
        "no_auto_outreach": True,
        "no_auto_billing": True,
        "no_auto_delivery": True,
        "no_auto_calling": True,
        "no_unrestricted_command_passthrough": True,
        "notes": [
            "Validation script performs explicit single-step API checks only.",
            "Stripe path creates a payment link only; no charge API calls are made.",
            "ElevenLabs path generates one local audio artifact only.",
            "No outbound messaging/sending APIs are invoked.",
        ],
    }


def run_all() -> dict[str, Any]:
    tavily = validate_tavily()
    firecrawl = validate_firecrawl(tavily)
    stripe = validate_stripe()
    elevenlabs = validate_elevenlabs()
    telegram = validate_telegram_readiness()
    safety = validate_safety()
    return {
        "tavily": tavily,
        "firecrawl": firecrawl,
        "stripe": stripe,
        "elevenlabs": elevenlabs,
        "telegram_readiness": telegram,
        "safety": safety,
    }


if __name__ == "__main__":
    results = run_all()
    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write("\n")
