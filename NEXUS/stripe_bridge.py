"""Safe Stripe payment-link bridge for Forge (one-time only)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import parse, request


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def create_one_time_payment_link_safe(*, amount_cents: int, currency: str, description: str, metadata: dict[str, Any] | None = None, timeout_seconds: int = 20) -> dict[str, Any]:
    secret = _to_text(os.environ.get("STRIPE_SECRET_KEY"))
    if not secret:
        return {"status": "not_configured", "reason": "Stripe not configured", "payment_link_url": ""}

    amount = max(1, int(amount_cents))
    cur = (_to_text(currency) or "usd").lower()
    label = _to_text(description) or "Forge one-time payment"
    form: dict[str, str] = {
        "line_items[0][price_data][currency]": cur,
        "line_items[0][price_data][product_data][name]": label,
        "line_items[0][price_data][unit_amount]": str(amount),
        "line_items[0][quantity]": "1",
    }
    for key, value in (metadata or {}).items():
        text_key = _to_text(key)
        if not text_key:
            continue
        form[f"metadata[{text_key}]"] = _to_text(value)

    req = request.Request(
        "https://api.stripe.com/v1/payment_links",
        data=parse.urlencode(form).encode("utf-8"),
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, int(timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        payload = json.loads(raw) if raw.strip() else {}
        return {
            "status": "ok",
            "payment_link_id": _to_text(payload.get("id")),
            "payment_link_url": _to_text(payload.get("url")),
            "one_time_only": True,
            "auto_billing_enabled": False,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"Stripe payment link request failed: {exc}",
            "payment_link_url": "",
            "one_time_only": True,
            "auto_billing_enabled": False,
        }
