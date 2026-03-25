"""
Minimal Resend email provider integration for governed explicit send actions.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency in some environments
    load_dotenv = None

if callable(load_dotenv):
    load_dotenv()

RESEND_API_URL = "https://api.resend.com/emails"


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_error(message: str) -> str:
    text = _to_text(message)
    if not text:
        return "Provider request failed."
    if len(text) > 400:
        text = text[:400].rstrip() + "..."
    return text


def send_email_via_resend(
    *,
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """
    Send a single email through Resend and return a normalized provider response.

    This function never returns secrets and does not print API keys.
    """
    resolved_api_key = _to_text(api_key or os.getenv("RESEND_API_KEY"))
    resolved_from = _to_text(from_email or os.getenv("RESEND_FROM_EMAIL"))
    recipient = _to_text(to_email)
    subject_text = _to_text(subject)
    body_text = str(body or "")

    if not resolved_api_key or not resolved_from:
        return {
            "status": "error",
            "provider": "resend",
            "error_code": "provider_not_configured",
            "error_message": "Resend provider configuration is missing.",
            "provider_message_id": "",
        }

    payload = {
        "from": resolved_from,
        "to": [recipient],
        "subject": subject_text,
        "text": body_text,
    }

    encoded_payload = json.dumps(payload).encode("utf-8")
    req = request.Request(
        RESEND_API_URL,
        data=encoded_payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=max(3, int(timeout_seconds or 12))) as response:
            status_code = int(getattr(response, "status", 0) or 0)
            body_bytes = response.read()
        body_json = json.loads(body_bytes.decode("utf-8") or "{}")
        provider_message_id = _to_text(body_json.get("id"))
        if 200 <= status_code < 300 and provider_message_id:
            return {
                "status": "ok",
                "provider": "resend",
                "provider_message_id": provider_message_id,
                "error_code": "",
                "error_message": "",
            }
        return {
            "status": "rejected",
            "provider": "resend",
            "provider_message_id": provider_message_id,
            "error_code": "rejected_by_provider",
            "error_message": _sanitize_error(body_json.get("message") or "Provider rejected request."),
        }
    except error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8")
            parsed = json.loads(err_body) if err_body else {}
        except Exception:
            parsed = {}
        status_text = str(exc.code or "http_error")
        return {
            "status": "rejected",
            "provider": "resend",
            "provider_message_id": "",
            "error_code": f"http_{status_text}",
            "error_message": _sanitize_error(parsed.get("message") or exc.reason or "Provider HTTP error."),
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": "resend",
            "provider_message_id": "",
            "error_code": "provider_request_failed",
            "error_message": _sanitize_error(str(exc)),
        }
