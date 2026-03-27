"""
Telegram operator bridge for Forge (hardened).

Key guarantees:
- Deny-all when TELEGRAM_ALLOWED_CHAT_IDS is missing/invalid.
- Only supports explicit command set (no unrestricted passthrough).
- Persists Telegram update offset to avoid replay after restart.
- Keeps polling loop resilient with retry/backoff and exception guards.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in stripped runtimes
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

from NEXUS.approval_summary import build_approval_summary_safe
from NEXUS.command_surface import run_command
from NEXUS.execution_package_registry import list_execution_package_journal_entries
from NEXUS.registry import PROJECTS


_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv((_REPO_ROOT / ".env").resolve())

_OFFSET_STATE_PATH = _REPO_ROOT / "state" / "telegram_bridge_offset.json"
_POLL_TIMEOUT_SECONDS = 25
_POLL_IDLE_SECONDS = 2
_REQUEST_TIMEOUT_SECONDS = 35
_BACKOFF_MIN_SECONDS = 1
_BACKOFF_MAX_SECONDS = 30
_MAX_TELEGRAM_MESSAGE_LENGTH = 3500


def _parse_allowed_chat_ids(raw: str | None) -> tuple[set[int], str | None]:
    text = str(raw or "").strip()
    if not text:
        return set(), "TELEGRAM_ALLOWED_CHAT_IDS is not configured. Deny-all mode is active."
    ids: set[int] = set()
    bad_tokens: list[str] = []
    for token in text.split(","):
        value = token.strip()
        if not value:
            continue
        try:
            ids.add(int(value))
        except Exception:
            bad_tokens.append(value)
    if bad_tokens:
        return set(), (
            "TELEGRAM_ALLOWED_CHAT_IDS contains invalid entries "
            f"({', '.join(bad_tokens)}). Deny-all mode is active."
        )
    if not ids:
        return set(), "TELEGRAM_ALLOWED_CHAT_IDS parsed to empty set. Deny-all mode is active."
    return ids, None


def get_allowed_chat_ids() -> tuple[set[int], str | None]:
    return _parse_allowed_chat_ids(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))


def _is_authorized_chat(chat_id: Any) -> tuple[bool, str | None]:
    allowlist, allowlist_error = get_allowed_chat_ids()
    if allowlist_error:
        return False, allowlist_error
    try:
        chat_num = int(chat_id)
    except Exception:
        return False, "Invalid chat_id received."
    if chat_num not in allowlist:
        return False, f"Unauthorized chat_id={chat_num}."
    return True, None


def _get_bot_token() -> str:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    return token


def _telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_get_bot_token()}/{method}"


def _telegram_get(method: str, params: dict[str, Any]) -> dict[str, Any]:
    import requests

    response = requests.get(_telegram_url(method), params=params, timeout=_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Telegram API returned non-dict payload.")
    return payload


def _load_offset() -> int | None:
    if not _OFFSET_STATE_PATH.exists():
        return None
    try:
        parsed = json.loads(_OFFSET_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            return None
        value = parsed.get("offset")
        return int(value) if value is not None else None
    except Exception:
        return None


def _save_offset(offset: int) -> None:
    try:
        _OFFSET_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OFFSET_STATE_PATH.write_text(
            json.dumps({"offset": int(offset), "saved_at": time.time()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Never crash loop for persistence failures.
        pass


def get_telegram_updates(offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": _POLL_TIMEOUT_SECONDS}
    if offset is not None:
        params["offset"] = int(offset)
    payload = _telegram_get("getUpdates", params)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {payload}")
    result = payload.get("result") or []
    return [row for row in result if isinstance(row, dict)]


def send_telegram_message(chat_id: int | str, text: str) -> None:
    body = str(text or "").strip() or "(empty response)"
    chunks = [body[i : i + _MAX_TELEGRAM_MESSAGE_LENGTH] for i in range(0, len(body), _MAX_TELEGRAM_MESSAGE_LENGTH)]
    if not chunks:
        chunks = ["(empty response)"]
    for chunk in chunks:
        payload = _telegram_get("sendMessage", {"chat_id": str(chat_id), "text": chunk})
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {payload}")


def _resolve_target_project(project_key: str | None = None) -> str:
    if project_key:
        key = str(project_key).strip().lower()
        if key in PROJECTS:
            return key
    snapshot = run_command("operator_snapshot")
    payload = snapshot.get("payload") or {}
    coord = payload.get("studio_coordination_summary") or {}
    priority = str(coord.get("priority_project") or "").strip().lower()
    if priority in PROJECTS:
        return priority
    return "jarvis" if "jarvis" in PROJECTS else sorted(PROJECTS.keys())[0]


def _summarize_status() -> str:
    project_key = _resolve_target_project()
    autopilot = run_command("project_autopilot_status", project_name=project_key)
    approvals = build_approval_summary_safe(n_recent=20, n_tail=100)
    pending_count = int(approvals.get("pending_count_total") or 0)
    summary = str(autopilot.get("summary") or "unknown")
    return (
        "Forge Status\n"
        f"- project: {project_key}\n"
        f"- autopilot: {summary}\n"
        f"- pending approvals: {pending_count}"
    )


def _summarize_missions() -> str:
    snapshot = run_command("operator_snapshot", tail=5)
    payload = snapshot.get("payload") or {}
    rows = [r for r in list(payload.get("projects_table") or []) if isinstance(r, dict)]
    if not rows:
        return "Missions\n- no project status rows available."
    lines = ["Missions"]
    for row in rows[:8]:
        project = str(row.get("project") or "unknown")
        lifecycle = str(row.get("lifecycle_status") or "unknown")
        queue = str(row.get("queue_status") or "unknown")
        autonomy = str(row.get("autonomy_status") or "unknown")
        lines.append(f"- {project}: lifecycle={lifecycle}, queue={queue}, autonomy={autonomy}")
    return "\n".join(lines)


def _summarize_leads() -> str:
    lines = ["Leads"]
    rows: list[dict[str, Any]] = []
    for key, meta in PROJECTS.items():
        project_path = str((meta or {}).get("path") or "")
        if not project_path:
            continue
        entries = list_execution_package_journal_entries(project_path=project_path, n=25)
        for row in entries:
            if isinstance(row, dict):
                rows.append({"project": key, **row})
    if not rows:
        return "Leads\n- no execution packages found."
    ranked = sorted(
        rows,
        key=lambda r: float(r.get("revenue_priority_score") or 0.0),
        reverse=True,
    )
    for row in ranked[:8]:
        package_id = str(row.get("package_id") or "")
        project = str(row.get("project") or "")
        stage = str(row.get("pipeline_stage") or "unknown")
        action = str(row.get("highest_value_next_action") or "review")
        status = str(row.get("revenue_activation_status") or "unknown")
        lines.append(f"- {project}/{package_id}: stage={stage}, status={status}, next={action}")
    return "\n".join(lines)


def _summarize_approvals() -> str:
    summary = build_approval_summary_safe(n_recent=30, n_tail=200)
    pending = int(summary.get("pending_count_total") or 0)
    lines = [f"Approvals\n- pending total: {pending}"]
    recent = [r for r in list(summary.get("recent_approvals") or []) if isinstance(r, dict)]
    pending_rows = [r for r in recent if str(r.get("status") or "").strip().lower() == "pending"]
    for row in pending_rows[:8]:
        lines.append(
            "- id={aid} project={proj} type={typ}".format(
                aid=str(row.get("approval_id") or ""),
                proj=str(row.get("project_name") or "unknown"),
                typ=str(row.get("approval_type") or "unknown"),
            )
        )
    return "\n".join(lines)


def _apply_autopilot(enabled: bool, explicit_project: str | None = None) -> str:
    project_key = _resolve_target_project(explicit_project)
    command = "project_autopilot_start" if enabled else "project_autopilot_stop"
    result = run_command(command, project_name=project_key)
    state = "on" if enabled else "off"
    return f"Autopilot {state} for {project_key}: {result.get('summary') or result.get('status')}"


def _help_text() -> str:
    return (
        "Forge Telegram Commands\n"
        "- help\n"
        "- status\n"
        "- approvals\n"
        "- missions\n"
        "- leads\n"
        "- autopilot on [project]\n"
        "- autopilot off [project]"
    )


def _route_command(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return _help_text()
    parts = [p for p in raw.replace("\n", " ").split(" ") if p.strip()]
    normalized = " ".join(parts).strip().lower()

    if normalized in {"help", "/help"}:
        return _help_text()
    if normalized in {"status", "/status"}:
        return _summarize_status()
    if normalized in {"approvals", "/approvals"}:
        return _summarize_approvals()
    if normalized in {"missions", "/missions"}:
        return _summarize_missions()
    if normalized in {"leads", "/leads"}:
        return _summarize_leads()

    if normalized.startswith("autopilot on") or normalized.startswith("/autopilot on"):
        project = parts[2] if len(parts) >= 3 else None
        return _apply_autopilot(True, project)
    if normalized.startswith("autopilot off") or normalized.startswith("/autopilot off"):
        project = parts[2] if len(parts) >= 3 else None
        return _apply_autopilot(False, project)

    return "Unsupported command. Send `help` for available commands."


def handle_telegram_message(message: dict[str, Any]) -> str:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return "Invalid message: missing chat_id."

    authorized, reason = _is_authorized_chat(chat_id)
    if not authorized:
        if reason and "Unauthorized chat_id" in reason:
            return "Unauthorized."
        return f"Authorization error: {reason or 'unknown'}"

    text = str(message.get("text") or "").strip()
    return _route_command(text)


def _send_startup_health() -> None:
    allowlist, allowlist_error = get_allowed_chat_ids()
    if allowlist_error:
        print(f"[TelegramBridge] startup blocked: {allowlist_error}")
        return
    status_message = "Forge Telegram bridge online.\n" + _summarize_status()
    for chat_id in sorted(allowlist):
        try:
            send_telegram_message(chat_id, status_message)
        except Exception as exc:
            print(f"[TelegramBridge] failed startup notice to {chat_id}: {exc}")


def run_telegram_loop() -> None:
    print("[TelegramBridge] starting polling loop")
    _send_startup_health()

    offset = _load_offset()
    backoff = _BACKOFF_MIN_SECONDS

    while True:
        try:
            updates = get_telegram_updates(offset=offset)
            for update in updates:
                update_id = int(update.get("update_id") or 0)
                message = update.get("message")
                if isinstance(message, dict):
                    chat = message.get("chat") or {}
                    chat_id = chat.get("id")
                    reply = handle_telegram_message(message)
                    if chat_id is not None:
                        try:
                            send_telegram_message(chat_id, reply)
                        except Exception as send_exc:
                            print(f"[TelegramBridge] send reply failed: {send_exc}")
                offset = max(offset or 0, update_id + 1)
                _save_offset(offset)
            backoff = _BACKOFF_MIN_SECONDS
            time.sleep(_POLL_IDLE_SECONDS)
        except Exception as exc:
            print(f"[TelegramBridge] polling error: {exc}; retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(_BACKOFF_MAX_SECONDS, backoff * 2)


if __name__ == "__main__":
    run_telegram_loop()
