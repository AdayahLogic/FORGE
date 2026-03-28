"""Safe Twilio bridge for approval-gated SMS operations."""

from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib import parse, request


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def send_sms_safe(*, to_number: str, message: str, timeout_seconds: int = 20) -> dict[str, Any]:
    sid = _to_text(os.environ.get("TWILIO_ACCOUNT_SID"))
    token = _to_text(os.environ.get("TWILIO_AUTH_TOKEN"))
    from_number = _to_text(os.environ.get("TWILIO_FROM_NUMBER"))
    if not sid or not token or not from_number:
        return {"status": "not_configured", "reason": "Twilio credentials missing.", "message_sid": ""}

    body = parse.urlencode({"To": _to_text(to_number), "From": from_number, "Body": _to_text(message)[:1200]}).encode("utf-8")
    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req = request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=body,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, int(timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        payload = json.loads(raw) if raw.strip() else {}
        return {"status": "ok", "message_sid": _to_text(payload.get("sid")), "to": _to_text(payload.get("to")), "from": _to_text(payload.get("from"))}
    except Exception as exc:
        return {"status": "failed", "reason": f"Twilio SMS request failed: {exc}", "message_sid": ""}
