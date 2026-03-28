"""
Stripe payment link bridge.

One-time payment links only. No subscription support.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import parse, request


STRIPE_API_BASE = "https://api.stripe.com/v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def stripe_status() -> dict[str, Any]:
    configured = bool(_text(os.getenv("STRIPE_SECRET_KEY")))
    return {
        "status": "ready" if configured else "not_configured",
        "configured": configured,
    }


def _stripe_headers(secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _post_form(endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        endpoint,
        data=parse.urlencode(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with request.urlopen(req, timeout=25.0) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def create_payment_link(product_name: str | None = None, price_cents: int | None = None, currency: str | None = None) -> dict[str, Any]:
    secret_key = _text(os.getenv("STRIPE_SECRET_KEY"))
    if not secret_key:
        return {
            "status": "not_configured",
            "reason": "Stripe not configured",
            "payment_url": "",
            "price_cents": 0,
            "currency": "",
            "product_name": "",
        }

    resolved_product = _text(product_name) or _text(os.getenv("FORGE_DEFAULT_PRODUCT_NAME")) or "Forge Service Package"
    default_price_raw = _text(os.getenv("FORGE_DEFAULT_PRICE_CENTS")) or "5000"
    resolved_currency = (_text(currency) or _text(os.getenv("STRIPE_CURRENCY")) or "usd").lower()
    success_url = _text(os.getenv("FORGE_PAYMENT_SUCCESS_URL")) or "https://example.com/payment/success"
    cancel_url = _text(os.getenv("FORGE_PAYMENT_CANCEL_URL")) or "https://example.com/payment/cancel"

    try:
        resolved_price = int(price_cents if price_cents is not None else default_price_raw)
    except Exception:
        resolved_price = 5000
    resolved_price = max(50, resolved_price)

    headers = _stripe_headers(secret_key)
    try:
        product = _post_form(
            f"{STRIPE_API_BASE}/products",
            headers,
            {"name": resolved_product},
        )
        product_id = _text(product.get("id"))
        if not product_id:
            return {
                "status": "failed",
                "reason": "Stripe product creation failed",
                "payment_url": "",
                "price_cents": resolved_price,
                "currency": resolved_currency,
                "product_name": resolved_product,
            }

        price = _post_form(
            f"{STRIPE_API_BASE}/prices",
            headers,
            {
                "product": product_id,
                "unit_amount": str(resolved_price),
                "currency": resolved_currency,
            },
        )
        price_id = _text(price.get("id"))
        if not price_id:
            return {
                "status": "failed",
                "reason": "Stripe price creation failed",
                "payment_url": "",
                "price_cents": resolved_price,
                "currency": resolved_currency,
                "product_name": resolved_product,
            }

        link = _post_form(
            f"{STRIPE_API_BASE}/payment_links",
            headers,
            {
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "after_completion[type]": "redirect",
                "after_completion[redirect][url]": success_url,
                "consent_collection[terms_of_service]": "none",
                "allow_promotion_codes": "false",
                "metadata[forge_mode]": "one_time_payment",
                "metadata[cancel_url]": cancel_url,
            },
        )
        payment_url = _text(link.get("url"))
        if not payment_url:
            return {
                "status": "failed",
                "reason": "Stripe payment link creation failed",
                "payment_url": "",
                "price_cents": resolved_price,
                "currency": resolved_currency,
                "product_name": resolved_product,
            }

        return {
            "status": "ready",
            "reason": "",
            "payment_url": payment_url,
            "price_cents": resolved_price,
            "currency": resolved_currency,
            "product_name": resolved_product,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "payment_url": "",
            "price_cents": resolved_price,
            "currency": resolved_currency,
            "product_name": resolved_product,
        }
