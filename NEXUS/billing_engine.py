"""
NEXUS billing engine (additive).

This module emits usage records to Stripe when billing credentials are present.
If Stripe is not configured, it returns deterministic skip/error payloads and
never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BLOCKED_CUSTOMERS_PATH = Path(__file__).resolve().parents[1] / "state" / "billing_blocked_customers.json"


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


def _read_blocked_customers() -> dict[str, Any]:
    try:
        if not _BLOCKED_CUSTOMERS_PATH.exists():
            return {}
        raw = _BLOCKED_CUSTOMERS_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _write_blocked_customers(data: dict[str, Any]) -> None:
    try:
        _BLOCKED_CUSTOMERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BLOCKED_CUSTOMERS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _extract_event_customer_id(event_data: dict[str, Any]) -> str:
    data = dict(event_data or {})
    obj = data.get("object")
    if isinstance(obj, dict):
        value = obj.get("customer") or obj.get("id")
        if value:
            return str(value).strip()
    return str(data.get("customer") or "").strip()


def _mark_customer_blocked(customer_id: str, reason: str) -> None:
    customer = str(customer_id or "").strip()
    if not customer:
        return
    blocked = _read_blocked_customers()
    blocked[customer] = {
        "blocked": True,
        "reason": str(reason or "").strip(),
        "blocked_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_blocked_customers(blocked)


def is_customer_billing_blocked(customer_id: str) -> bool:
    customer = str(customer_id or "").strip()
    if not customer:
        return False
    blocked = _read_blocked_customers()
    record = blocked.get(customer)
    return isinstance(record, dict) and bool(record.get("blocked"))


def dispatch_webhook_event(event_type: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """
    Handle Stripe webhook events with additive, non-destructive defaults.
    """
    normalized_event = str(event_type or "").strip()
    if normalized_event in {"invoice.payment_failed", "customer.subscription.deleted"}:
        customer_id = _extract_event_customer_id(event_data)
        if customer_id:
            _mark_customer_blocked(customer_id, normalized_event)
        alert_status = "skipped"
        try:
            from NEXUS.notification_router import notify_operator

            notify_operator(
                event_type="billing_alert",
                message=f"Billing event {normalized_event} for customer {customer_id or 'unknown'}.",
                priority="critical",
                payload={
                    "customer_id": customer_id,
                    "event_type": normalized_event,
                    "event_data": dict(event_data or {}),
                },
                source="billing_engine",
            )
            alert_status = "sent"
        except Exception:
            alert_status = "unavailable"
        return {
            "status": "noted",
            "event_type": normalized_event,
            "action": "blocked_and_alerted",
            "note": "Billing lifecycle event received and customer was blocked.",
            "customer_id": customer_id,
            "alert_status": alert_status,
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
