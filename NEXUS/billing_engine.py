"""
NEXUS billing engine (additive).

This module emits usage records to Stripe when billing credentials are present.
If Stripe is not configured, it returns deterministic skip/error payloads and
never raises.
"""

from __future__ import annotations

import os
from typing import Any


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _resolve_subscription_item_id(customer_id: str) -> str:
    """
    Resolve the Stripe subscription item id for a customer.

    Mapping source:
      STRIPE_CUSTOMER_ITEMS=cus_abc:si_111,cus_xyz:si_222
    Falls back to STRIPE_METER_ITEM_ID when no mapping is found.
    """
    customer = str(customer_id or "").strip()
    raw_map = str(os.getenv("STRIPE_CUSTOMER_ITEMS", "")).strip()
    if raw_map and customer:
        for pair in raw_map.split(","):
            key_value = pair.strip()
            if not key_value:
                continue
            parts = key_value.split(":", 1)
            if len(parts) != 2:
                continue
            mapped_customer, mapped_item = parts[0].strip(), parts[1].strip()
            if mapped_customer == customer and mapped_item:
                return mapped_item
    return str(os.getenv("STRIPE_METER_ITEM_ID") or "").strip()


def dispatch_webhook_event(event_type: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """
    Handle Stripe webhook events with additive, non-destructive defaults.
    """
    normalized_event = str(event_type or "").strip()
    if normalized_event in {"invoice.payment_failed", "customer.subscription.deleted"}:
        return {
            "status": "noted",
            "event_type": normalized_event,
            "action": "log_only",
            "note": "Billing lifecycle event received. Implement execution gating here.",
            "event_data_keys": sorted(list((event_data or {}).keys())),
        }
    return {
        "status": "ignored",
        "event_type": normalized_event,
        "event_data_keys": sorted(list((event_data or {}).keys())),
    }


def record_usage(
    *,
    customer_id: str,
    quantity_tokens: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    customer = str(customer_id or "").strip()
    tokens = max(0, _to_int(quantity_tokens, 0))
    if not customer:
        return {"status": "skipped", "reason": "customer_id missing."}
    if tokens <= 0:
        return {"status": "skipped", "reason": "No billable usage quantity."}

    stripe_api_key = str(os.getenv("STRIPE_SECRET_KEY") or "").strip()
    meter_item_id = _resolve_subscription_item_id(customer)
    if not stripe_api_key or not meter_item_id:
        return {"status": "skipped", "reason": "Stripe billing is not configured."}

    try:
        import stripe  # type: ignore
    except Exception:
        return {"status": "error", "reason": "Stripe SDK is unavailable."}

    try:
        stripe.api_key = stripe_api_key
        usage_metadata = {"customer_id": customer}
        usage_metadata.update(dict(metadata or {}))
        record = stripe.SubscriptionItem.create_usage_record(  # type: ignore[attr-defined]
            meter_item_id,
            quantity=tokens,
            action="increment",
            timestamp="now",
            metadata=usage_metadata,
        )
        return {
            "status": "ok",
            "reason": "Usage record created.",
            "customer_id": customer,
            "tokens": tokens,
            "stripe_usage_record_id": str(getattr(record, "id", "")),
            "metadata": dict(metadata or {}),
        }
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"Stripe usage recording failed: {exc}",
            "customer_id": customer,
            "tokens": tokens,
            "metadata": dict(metadata or {}),
        }
