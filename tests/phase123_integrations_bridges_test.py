"""
Phase 123 integration bridges tests.

Run: python tests/phase123_integrations_bridges_test.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _temp_env(values: dict[str, str | None]):
    previous = {k: os.environ.get(k) for k in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


class _MockResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_tavily_missing_key_is_safe():
    from NEXUS.tavily_bridge import search_business_leads

    with _temp_env({"TAVILY_API_KEY": None}):
        out = search_business_leads("plumbers", location="miami", limit=5)
    assert out["status"] == "not_configured"
    assert out["results"] == []


def test_tavily_normalizes_results():
    from NEXUS.tavily_bridge import search_business_leads

    fake_payload = {
        "results": [
            {"title": "Acme Co", "url": "https://acme.test", "content": "Software automation experts."}
        ]
    }
    with _temp_env({"TAVILY_API_KEY": "k"}), patch("NEXUS.tavily_bridge.request.urlopen", return_value=_MockResponse(json.dumps(fake_payload).encode("utf-8"))):
        out = search_business_leads("automation agencies", limit=3)
    assert out["status"] == "ready"
    assert out["results"][0]["title"] == "Acme Co"
    assert out["results"][0]["url"] == "https://acme.test"
    assert out["results"][0]["source"] == "tavily"


def test_firecrawl_missing_key_is_safe():
    from NEXUS.firecrawl_bridge import scrape_page

    with _temp_env({"FIRECRAWL_API_KEY": None}):
        out = scrape_page("https://example.com")
    assert out["status"] == "not_configured"


def test_firecrawl_extracts_normalized_details():
    from NEXUS.firecrawl_bridge import extract_business_details

    mock_scrape = {
        "data": {
            "markdown": "Contact us at hello@acme.test or +1 (555) 123-4567. We provide automation and consulting.",
            "metadata": {"title": "Acme Labs | Home"},
        }
    }
    with _temp_env({"FIRECRAWL_API_KEY": "x"}), patch("NEXUS.firecrawl_bridge.request.urlopen", return_value=_MockResponse(json.dumps(mock_scrape).encode("utf-8"))):
        out = extract_business_details("https://acme.test")
    assert out["status"] == "ready"
    details = out["details"]
    assert details["business_name"] == "Acme Labs"
    assert details["email"] == "hello@acme.test"
    assert details["phone"]
    assert isinstance(details["services"], list)


def test_elevenlabs_missing_config_is_safe():
    from NEXUS.elevenlabs_bridge import generate_voice_audio

    with _temp_env({"ELEVENLABS_API_KEY": None, "ELEVENLABS_VOICE_ID": None}):
        out = generate_voice_audio("hello")
    assert out["status"] == "not_configured"


def test_stripe_missing_key_is_safe():
    from NEXUS.stripe_bridge import create_payment_link

    with _temp_env({"STRIPE_SECRET_KEY": None}):
        out = create_payment_link("Test", 5000, "usd")
    assert out["status"] == "not_configured"
    assert out["payment_url"] == ""


def test_stripe_payment_link_creation_isolated_path():
    from NEXUS.stripe_bridge import create_payment_link

    responses = [
        _MockResponse(json.dumps({"id": "prod_123"}).encode("utf-8")),
        _MockResponse(json.dumps({"id": "price_123"}).encode("utf-8")),
        _MockResponse(json.dumps({"url": "https://pay.stripe.test/link"}).encode("utf-8")),
    ]

    with _temp_env({"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_CURRENCY": "usd"}), patch(
        "NEXUS.stripe_bridge.request.urlopen", side_effect=responses
    ):
        out = create_payment_link(product_name="Forge One Time", price_cents=9000, currency="usd")
    assert out["status"] == "ready"
    assert out["payment_url"].startswith("https://")
    assert out["price_cents"] == 9000
    assert out["currency"] == "usd"
    assert out["product_name"] == "Forge One Time"


def test_workflow_approval_gate_blocks_payment_link():
    from NEXUS.integration_workflows import create_deal_payment_link_workflow

    out = create_deal_payment_link_workflow(approval_granted=False)
    assert out["status"] == "approval_required"


if __name__ == "__main__":
    tests = [
        ("tavily_missing_key_is_safe", test_tavily_missing_key_is_safe),
        ("tavily_normalizes_results", test_tavily_normalizes_results),
        ("firecrawl_missing_key_is_safe", test_firecrawl_missing_key_is_safe),
        ("firecrawl_extracts_normalized_details", test_firecrawl_extracts_normalized_details),
        ("elevenlabs_missing_config_is_safe", test_elevenlabs_missing_config_is_safe),
        ("stripe_missing_key_is_safe", test_stripe_missing_key_is_safe),
        ("stripe_payment_link_creation_isolated_path", test_stripe_payment_link_creation_isolated_path),
        ("workflow_approval_gate_blocks_payment_link", test_workflow_approval_gate_blocks_payment_link),
    ]
    ok = True
    for name, fn in tests:
        ok = _run(name, fn) and ok
    raise SystemExit(0 if ok else 1)
