"""Telegram operator bridge for Forge integration control."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from NEXUS.command_surface import run_command
from NEXUS.integration_router import (
    bootstrap_integration_env,
    discover_leads_safe,
    get_recent_integration_events_safe,
    integration_status_safe,
)
from NEXUS.project_state import load_project_state
from NEXUS.registry import PROJECTS

_TELEGRAM_TIMEOUT_SECONDS = 25
_LOOP_INTERVAL_SECONDS = 2
_MAX_TEXT_LEN = 3900


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _bootstrap() -> dict[str, Any]:
    return bootstrap_integration_env()


def _get_bot_token() -> str:
    _bootstrap()
    token = _to_text(os.environ.get("TELEGRAM_BOT_TOKEN"))
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    return token


def _telegram_base_url() -> str:
    return f"https://api.telegram.org/bot{_get_bot_token()}"


def _telegram_allowed_chats() -> set[str]:
    _bootstrap()
    raw = _to_text(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_authorized_chat(chat_id: Any) -> bool:
    allowed = _telegram_allowed_chats()
    if not allowed:
        return False
    return str(chat_id) in allowed


def _telegram_get(method: str, *, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    url = f"{_telegram_base_url()}/{method}"
    query = parse.urlencode(params)
    target = f"{url}?{query}" if query else url
    req = request.Request(target, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    payload = json.loads(raw) if raw.strip() else {}
    return payload if isinstance(payload, dict) else {}


def get_telegram_updates(offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": _TELEGRAM_TIMEOUT_SECONDS}
    if offset is not None:
        params["offset"] = int(offset)
    payload = _telegram_get("getUpdates", params=params, timeout_seconds=_TELEGRAM_TIMEOUT_SECONDS + 5)
    if not payload.get("ok"):
        return []
    rows = payload.get("result") or []
    return [row for row in rows if isinstance(row, dict)]


def send_telegram_message(chat_id: int | str, text: str) -> bool:
    source = _to_text(text) or "(empty response)"
    chunks: list[str] = []
    while source:
        chunks.append(source[:_MAX_TEXT_LEN])
        source = source[_MAX_TEXT_LEN:]
    if not chunks:
        chunks = ["(empty response)"]
    for chunk in chunks:
        payload = _telegram_get("sendMessage", params={"chat_id": str(chat_id), "text": chunk}, timeout_seconds=20)
        if not payload.get("ok"):
            return False
    return True


def send_operator_message_safe(message: str) -> dict[str, Any]:
    chats = sorted(_telegram_allowed_chats())
    if not chats:
        return {"status": "not_configured", "reason": "No TELEGRAM_ALLOWED_CHAT_IDS configured."}
    sent = 0
    for chat_id in chats:
        if send_telegram_message(chat_id, message):
            sent += 1
    if sent == 0:
        return {"status": "failed", "sent_count": 0, "target_count": len(chats)}
    return {"status": "sent", "sent_count": sent, "target_count": len(chats)}


def _normalize_command(raw: Any) -> str:
    text = _to_text(raw)
    if text.startswith("/"):
        text = text[1:]
    return " ".join(text.split())


def _help_text() -> str:
    return (
        "Supported commands\n"
        "- help\n"
        "- status\n"
        "- integration status\n"
        "- run lead mission\n"
        "- run lead mission <query>\n"
        "- leads\n"
        "- deals\n"
        "- projects\n"
        "- billing\n"
        "- activity\n"
        "- recent events\n"
        "- autopilot status\n"
        "- autopilot on\n"
        "- autopilot off"
    )


def _project_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(PROJECTS.keys()):
        path = _to_text((PROJECTS.get(key) or {}).get("path"))
        state = load_project_state(path) if path else {}
        rows.append({"project": key, "runtime": _to_text((state or {}).get("runtime_execution_status")) or "unknown", "governance": _to_text((state or {}).get("governance_status")) or "unknown", "autonomy_mode": _to_text((state or {}).get("autonomy_mode")) or "supervised_build"})
    return rows


def _status_text() -> str:
    status = integration_status_safe()
    integrations = dict(status.get("integrations") or {})
    ready = [name for name, row in integrations.items() if _to_text((row or {}).get("status")) == "ready"]
    return (
        "Forge Status\n"
        f"- projects: {len(PROJECTS)}\n"
        f"- integrations_ready: {len(ready)}\n"
        "- safety: outreach/billing/calling remain approval-gated"
    )


def _integration_status_text() -> str:
    status = integration_status_safe()
    lines = ["Integration Status"]
    for name, row in dict(status.get("integrations") or {}).items():
        lines.append(f"- {name}: {_to_text((row or {}).get('status'))} ({_to_text((row or {}).get('reason'))})")
    lines.append("- safety: no auto-outreach, no auto-billing, no auto-calling")
    return "\n".join(lines)


def _projects_text() -> str:
    rows = _project_rows()
    lines = ["Projects", f"count: {len(rows)}"]
    for row in rows:
        lines.append(f"- {row.get('project')}: runtime={row.get('runtime')} governance={row.get('governance')} mode={row.get('autonomy_mode')}")
    return "\n".join(lines)


def _deals_text() -> str:
    lines = ["Deals"]
    for key in sorted(PROJECTS.keys()):
        res = run_command("execution_package_queue", project_name=key, n=10)
        payload = dict(res.get("payload") or {})
        top = [item for item in list(payload.get("top_revenue_candidates") or []) if isinstance(item, dict)]
        if not top:
            continue
        best = top[0]
        lines.append(f"- {key}: package={_to_text(best.get('package_id'))} score={float(best.get('highest_value_next_action_score') or 0.0):.2f}")
    if len(lines) == 1:
        lines.append("- No ranked deal candidates available.")
    return "\n".join(lines)


def _leads_text() -> str:
    rows: list[dict[str, Any]] = []
    for key in sorted(PROJECTS.keys()):
        path = _to_text((PROJECTS.get(key) or {}).get("path"))
        state_file = Path(path) / "state" / "lead_intake.jsonl"
        if not state_file.exists():
            continue
        try:
            lines = state_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines[-40:]:
            raw = _to_text(line)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            lead = dict(parsed.get("lead") or {})
            if not lead:
                continue
            rows.append({"project": key, "lead_id": _to_text(lead.get("lead_id")), "status": _to_text(lead.get("lead_status")) or "new", "company": _to_text((lead.get("lead_contact_info") or {}).get("company_name")) or "unknown"})
    rows = [row for row in rows if row.get("lead_id")][-10:]
    lines = ["Leads", f"count: {len(rows)}"]
    for row in rows:
        lines.append(f"- {row.get('lead_id')} [{row.get('status')}] {row.get('company')} ({row.get('project')})")
    return "\n".join(lines)


def _activity_text() -> str:
    project_path = _to_text((PROJECTS.get(sorted(PROJECTS.keys())[0]) or {}).get("path")) if PROJECTS else ""
    rows = get_recent_integration_events_safe(project_path=project_path or None, limit=10)
    lines = ["Recent Events", f"count: {len(rows)}"]
    for row in rows:
        lines.append(f"- {_to_text(row.get('recorded_at'))}: {_to_text(row.get('integration'))} {_to_text(row.get('event_type'))} ({_to_text(row.get('status'))})")
    return "\n".join(lines)


def _billing_text() -> str:
    return "Billing\n- Stripe payment links are one-time and approval-gated.\n- No auto-billing is enabled."


def _autopilot_status_text() -> str:
    lines = ["Autopilot Status"]
    for key in sorted(PROJECTS.keys()):
        res = run_command("project_autopilot_status", project_name=key)
        payload = dict(res.get("payload") or {})
        auto = dict(payload.get("autopilot") or {})
        lines.append(f"- {key}: {_to_text(auto.get('autopilot_status')) or _to_text(res.get('status'))} mode={_to_text(auto.get('autopilot_mode')) or 'unknown'}")
    return "\n".join(lines)


def _set_autopilot(on: bool) -> str:
    mode = "assisted_autopilot" if on else "supervised_build"
    lines = [f"Autopilot {'ON' if on else 'OFF'} -> {mode}"]
    for key in sorted(PROJECTS.keys()):
        res = run_command("project_autonomy_mode_set", project_name=key, autonomy_mode=mode, reason="telegram_operator_command")
        lines.append(f"- {key}: {_to_text(res.get('status'))} ({_to_text(res.get('summary'))})")
    return "\n".join(lines)


def _run_lead_mission_text(payload: str) -> str:
    result = discover_leads_safe(query=payload)
    if _to_text(result.get("status")) == "not_configured":
        return "Tavily not configured"
    top = [item for item in list(result.get("top_lead_names") or []) if _to_text(item)]
    return (
        "Run Lead Mission\n"
        f"query: {_to_text(result.get('query'))}\n"
        f"lead_count: {int(result.get('lead_count') or 0)}\n"
        f"top_leads: {', '.join(top) if top else 'none'}\n"
        f"enrichment: {'yes' if bool(result.get('enrichment_occurred')) else 'no'}\n"
        "outreach: disabled (approval-gated)"
    )


def handle_telegram_command_safe(*, command: str) -> dict[str, Any]:
    normalized = _normalize_command(command).lower()
    if normalized in {"", "help", "commands", "?"}:
        return {"status": "ok", "command": "help", "response_text": _help_text()}
    if normalized == "status":
        return {"status": "ok", "command": "status", "response_text": _status_text()}
    if normalized in {"integration status", "integrations", "integration"}:
        return {"status": "ok", "command": "integration_status", "response_text": _integration_status_text()}
    if normalized.startswith("run lead mission"):
        payload = normalized[len("run lead mission") :].strip()
        return {"status": "ok", "command": "run_lead_mission", "response_text": _run_lead_mission_text(payload)}
    if normalized == "leads":
        return {"status": "ok", "command": "leads", "response_text": _leads_text()}
    if normalized == "deals":
        return {"status": "ok", "command": "deals", "response_text": _deals_text()}
    if normalized == "projects":
        return {"status": "ok", "command": "projects", "response_text": _projects_text()}
    if normalized == "billing":
        return {"status": "ok", "command": "billing", "response_text": _billing_text()}
    if normalized in {"activity", "recent events", "recent", "events"}:
        return {"status": "ok", "command": "activity", "response_text": _activity_text()}
    if normalized == "autopilot status":
        return {"status": "ok", "command": "autopilot_status", "response_text": _autopilot_status_text()}
    if normalized == "autopilot on":
        return {"status": "ok", "command": "autopilot_on", "response_text": _set_autopilot(True)}
    if normalized == "autopilot off":
        return {"status": "ok", "command": "autopilot_off", "response_text": _set_autopilot(False)}
    return {"status": "ok", "command": "help", "response_text": _help_text()}


def handle_telegram_message(message: dict[str, Any]) -> str:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = _to_text(message.get("text"))
    if chat_id is None:
        return "Ignored: no chat_id."
    if not _is_authorized_chat(chat_id):
        if not _telegram_allowed_chats():
            return "Authorization error: TELEGRAM_ALLOWED_CHAT_IDS is not configured."
        return "Unauthorized chat_id. Access denied."
    if not text:
        return "Ignored: message has no text."
    result = handle_telegram_command_safe(command=text)
    return _to_text(result.get("response_text")) or "No response."


def run_telegram_loop() -> None:
    env = _bootstrap()
    loaded_path = str(Path(__file__).resolve())
    print("[TelegramBridge] LOADED TELEGRAM BRIDGE VERSION")
    print(f"[TelegramBridge] loaded_file_path={loaded_path}")
    print(f"[TelegramBridge] env_bootstrap_paths={', '.join(env.get('searched_paths') or [])}")
    print(f"[TelegramBridge] tavily_api_key_detected={bool(env.get('tavily_detected'))}")
    print("[TelegramBridge] polling_loop_started=True")
    offset: int | None = None
    while True:
        try:
            updates = get_telegram_updates(offset=offset)
            for update in updates:
                update_id = int(update.get("update_id") or 0)
                message = update.get("message")
                if isinstance(message, dict):
                    reply = handle_telegram_message(message)
                    chat = message.get("chat") or {}
                    chat_id = chat.get("id")
                    if chat_id is not None and _is_authorized_chat(chat_id):
                        send_telegram_message(chat_id, reply)
                offset = max(offset or 0, update_id + 1)
        except Exception as exc:
            print(f"[TelegramBridge] loop error: {exc}")
        time.sleep(_LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_telegram_loop()
