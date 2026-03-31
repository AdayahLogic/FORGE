"""
Governed browser execution contract for Playwright lane.

Defines a narrow, auditable action contract and strict validation rules.
"""

from __future__ import annotations

from urllib.parse import urlparse
from typing import Any


ALLOWED_ACTIONS = {
    "open_url",
    "wait_for_selector",
    "click_selector",
    "fill_selector",
    "extract_text",
    "extract_links",
    "capture_screenshot",
}

HIGH_RISK_ACTIONS = {"click_selector", "fill_selector"}
MAX_ACTIONS = 20
MAX_ALLOWED_DOMAINS = 20
MAX_TIMEOUT_MS = 60000
MIN_TIMEOUT_MS = 1000
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_MAX_STEPS = 12
MAX_STEPS = 50


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return ""


def _normalize_timeout_ms(value: Any) -> int:
    try:
        timeout = int(value)
    except Exception:
        timeout = DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, timeout))


def _normalize_step_limit(value: Any) -> int:
    try:
        step_limit = int(value)
    except Exception:
        step_limit = DEFAULT_MAX_STEPS
    return max(1, min(MAX_STEPS, step_limit))


def _validate_domain_allowlist(allowed_domains: list[str], errors: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in allowed_domains[:MAX_ALLOWED_DOMAINS]:
        domain = _clean_text(item).lower()
        if not domain:
            continue
        if domain.startswith("*."):
            domain = domain[2:]
        if "." not in domain:
            errors.append(f"invalid_allowed_domain:{domain}")
            continue
        if domain not in normalized:
            normalized.append(domain)
    if not normalized:
        errors.append("allowed_domains_required")
    return normalized


def _domain_allowed(hostname: str, allowed_domains: list[str]) -> bool:
    host = _clean_text(hostname).lower()
    if not host:
        return False
    for domain in allowed_domains:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def validate_browser_execution_request(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    errors: list[str] = []
    warnings: list[str] = []

    allowed_domains_raw = payload.get("allowed_domains")
    if not isinstance(allowed_domains_raw, list):
        allowed_domains_raw = []
    allowed_domains = _validate_domain_allowlist([_clean_text(x) for x in allowed_domains_raw], errors)

    timeout_ms = _normalize_timeout_ms(payload.get("timeout_ms"))
    max_steps = _normalize_step_limit(payload.get("max_steps"))
    operator_approved = bool(payload.get("operator_approved"))
    headless = bool(payload.get("headless", True))
    actions_raw = payload.get("actions")
    if not isinstance(actions_raw, list):
        actions_raw = []

    normalized_actions: list[dict[str, Any]] = []
    high_risk_count = 0

    if not actions_raw:
        errors.append("actions_required")
    if len(actions_raw) > MAX_ACTIONS:
        errors.append("actions_too_many")

    for index, raw in enumerate(actions_raw[:MAX_ACTIONS]):
        action = dict(raw) if isinstance(raw, dict) else {}
        action_type = _clean_text(action.get("type")).lower()
        if action_type not in ALLOWED_ACTIONS:
            errors.append(f"action_{index}_type_invalid")
            continue

        normalized_action: dict[str, Any] = {"type": action_type}
        if action_type == "open_url":
            url = _clean_text(action.get("url"))
            if not _is_http_url(url):
                errors.append(f"action_{index}_url_invalid")
                continue
            host = _hostname(url)
            if not _domain_allowed(host, allowed_domains):
                errors.append(f"action_{index}_domain_not_allowed")
                continue
            normalized_action["url"] = url
        elif action_type in {"click_selector", "wait_for_selector", "extract_text", "extract_links"}:
            selector = _clean_text(action.get("selector"))
            if not selector:
                errors.append(f"action_{index}_selector_required")
                continue
            normalized_action["selector"] = selector
        elif action_type == "fill_selector":
            selector = _clean_text(action.get("selector"))
            value_text = _clean_text(action.get("value"))
            if not selector:
                errors.append(f"action_{index}_selector_required")
                continue
            normalized_action["selector"] = selector
            normalized_action["value"] = value_text
        elif action_type == "capture_screenshot":
            label = _clean_text(action.get("label")) or f"step_{index + 1}"
            normalized_action["label"] = label[:40]

        if action_type in HIGH_RISK_ACTIONS:
            high_risk_count += 1
        normalized_actions.append(normalized_action)

    if len(normalized_actions) > max_steps:
        warnings.append("actions_truncated_to_max_steps")
        normalized_actions = normalized_actions[:max_steps]
    if high_risk_count > 0 and not operator_approved:
        errors.append("operator_approval_required_for_interactive_actions")

    contract = {
        "contract_version": "browser_execution_v1",
        "lane": "openclaw_browser",
        "backend_id": "playwright_browser",
        "allowed_domains": allowed_domains,
        "timeout_ms": timeout_ms,
        "max_steps": max_steps,
        "headless": headless,
        "operator_approved": operator_approved,
        "actions": normalized_actions,
        "action_count": len(normalized_actions),
        "high_risk_action_count": high_risk_count,
        "high_risk_actions_present": high_risk_count > 0,
    }
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "contract": contract,
    }
