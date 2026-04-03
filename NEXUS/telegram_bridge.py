"""
Telegram operator control bridge for Forge.

Capabilities:
- Poll Telegram bot updates (long polling)
- Route supported operator commands into Forge command surface
- Return status and approval summaries
- Gate access with optional chat-id allowlist
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in minimal runtime
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

from NEXUS.command_surface import run_command
from NEXUS.execution_package_registry import list_execution_package_journal_entries, read_execution_package
from NEXUS.registry import PROJECTS


_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv((_REPO_ROOT / ".env").resolve())

_TELEGRAM_TIMEOUT_SECONDS = 25
_LOOP_INTERVAL_SECONDS = 2
_MAX_TEXT_LEN = 4000

_SAFE_COMMANDS = {
    "help",
    "status",
    "approvals",
    "missions",
    "leads",
    "operator_snapshot",
    "execution_package_queue",
}


def _get_bot_token() -> str:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in environment.")
    return token


def _telegram_base_url() -> str:
    return f"https://api.telegram.org/bot{_get_bot_token()}"


def _telegram_allowed_chats() -> set[str]:
    raw = str(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _is_authorized_chat(chat_id: Any) -> bool:
    allow = _telegram_allowed_chats()
    if not allow:
        return False
    return str(chat_id) in allow


def _telegram_get(method: str, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests is required for Telegram bridge. Install requests first.") from exc

    url = f"{_telegram_base_url()}/{method}"
    response = requests.get(url, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Telegram API response payload.")
    return payload


def get_telegram_updates(offset: int | None = None) -> list[dict[str, Any]]:
    """
    Read updates from Telegram getUpdates endpoint.
    """
    params: dict[str, Any] = {"timeout": _TELEGRAM_TIMEOUT_SECONDS}
    if offset is not None:
        params["offset"] = int(offset)
    payload = _telegram_get("getUpdates", params=params, timeout_seconds=_TELEGRAM_TIMEOUT_SECONDS + 5)
    if not payload.get("ok"):
        return []
    rows = payload.get("result") or []
    return [row for row in rows if isinstance(row, dict)]


def send_telegram_message(chat_id: int | str, text: str) -> bool:
    """
    Send text reply to Telegram chat.
    """
    chunks: list[str] = []
    source = str(text or "").strip() or "(empty response)"
    while source:
        chunks.append(source[:_MAX_TEXT_LEN])
        source = source[_MAX_TEXT_LEN:]

    if not chunks:
        chunks = ["(empty response)"]

    for chunk in chunks:
        payload = _telegram_get(
            "sendMessage",
            params={"chat_id": str(chat_id), "text": chunk},
            timeout_seconds=20,
        )
        if not payload.get("ok"):
            return False
    return True


def get_execution_package_queue(*, project_key: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """
    Return compact execution package queue rows across one/all projects.
    """
    rows: list[dict[str, Any]] = []
    projects = [str(project_key).strip().lower()] if project_key else sorted(PROJECTS.keys())
    for key in projects:
        project = PROJECTS.get(key) or {}
        project_path = str(project.get("path") or "")
        if not project_path:
            continue
        entries = list_execution_package_journal_entries(project_path, n=max(1, min(int(limit), 50)))
        for row in entries:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "project": key,
                    "project_name": project.get("name") or key,
                    "package_id": str(row.get("package_id") or ""),
                    "review_status": str(row.get("review_status") or ""),
                    "decision_status": str(row.get("decision_status") or ""),
                    "release_status": str(row.get("release_status") or ""),
                    "handoff_status": str(row.get("handoff_status") or ""),
                    "execution_status": str(row.get("execution_status") or ""),
                    "operator_action_status": str(row.get("operator_action_status") or ""),
                    "created_at": str(row.get("created_at") or ""),
                }
            )
    return rows


def _format_status_response() -> str:
    snapshot = run_command("operator_snapshot", tail=5)
    payload = snapshot.get("payload") or {}
    queue = get_execution_package_queue(limit=50)
    pending_decisions = [
        row for row in queue if str(row.get("decision_status") or "").strip().lower() in {"", "pending", "review_pending"}
    ]
    blocked = [
        row
        for row in queue
        if str(row.get("execution_status") or "").strip().lower() in {"blocked", "failed", "rolled_back", "error_fallback"}
    ]
    studio_coord = payload.get("studio_coordination_summary") or {}
    return (
        "Forge status\n"
        f"- coordination: {studio_coord.get('coordination_status', 'unknown')}\n"
        f"- priority_project: {studio_coord.get('priority_project', 'n/a')}\n"
        f"- package_queue_count: {len(queue)}\n"
        f"- pending_decisions: {len(pending_decisions)}\n"
        f"- blocked_or_failed: {len(blocked)}"
    )


def _pending_approval_lines() -> list[str]:
    summary = run_command("pending_approvals")
    payload = summary.get("payload") or {}
    lines = [
        f"approval_status={payload.get('approval_status', 'unknown')}",
        f"pending_count_total={payload.get('pending_count_total', 0)}",
    ]
    recent = [r for r in list(payload.get("recent_approvals") or []) if isinstance(r, dict)]
    pending_recent = [r for r in recent if str(r.get("status") or "").strip().lower() == "pending"]
    for row in pending_recent[:5]:
        lines.append(
            "- approval_id={aid} type={typ} project={proj}".format(
                aid=row.get("approval_id", ""),
                typ=row.get("approval_type", "unknown"),
                proj=row.get("project_name", "unknown"),
            )
        )
    queue = get_execution_package_queue(limit=50)
    pending_queue = [r for r in queue if str(r.get("decision_status") or "").strip().lower() in {"", "pending"}]
    if pending_queue:
        lines.append(f"pending_execution_package_decisions={len(pending_queue)}")
        for row in pending_queue[:5]:
            lines.append("- package_id={pid} project={proj}".format(pid=row.get("package_id", ""), proj=row.get("project", "")))
    return lines


def _format_approvals_response() -> str:
    return "Pending approvals\n" + "\n".join(_pending_approval_lines())


def _format_help_response() -> str:
    return (
        "Available commands\n"
        "- status\n"
        "- approvals\n"
        "- missions\n"
        "- leads\n"
        "- approve <id>\n"
        "- deny <id>"
    )


def _format_missions_response() -> str:
    snapshot = run_command("operator_snapshot", tail=5)
    payload = snapshot.get("payload") or {}
    rows = [r for r in list(payload.get("projects_table") or []) if isinstance(r, dict)]
    if not rows:
        return "Missions\n- no mission rows available."
    lines = ["Missions"]
    for row in rows[:8]:
        project = str(row.get("project") or "unknown")
        lifecycle = str(row.get("lifecycle_status") or "unknown")
        queue = str(row.get("queue_status") or "unknown")
        lines.append(f"- {project}: lifecycle={lifecycle}, queue={queue}")
    return "\n".join(lines)


def _format_leads_response() -> str:
    queue = get_execution_package_queue(limit=50)
    if not queue:
        return "Leads\n- no leads in execution package queue."
    lines = ["Leads"]
    for row in queue[:8]:
        lines.append(
            "- {project}/{package_id}: decision={decision_status}, execution={execution_status}".format(
                project=str(row.get("project") or "unknown"),
                package_id=str(row.get("package_id") or ""),
                decision_status=str(row.get("decision_status") or "pending"),
                execution_status=str(row.get("execution_status") or "pending"),
            )
        )
    return "\n".join(lines)


def _format_operator_snapshot_response() -> str:
    snapshot = run_command("operator_snapshot", tail=5)
    payload = snapshot.get("payload") or {}
    coord = payload.get("studio_coordination_summary") or {}
    driver = payload.get("studio_driver_summary") or {}
    return (
        "Operator snapshot\n"
        f"- coordination: {coord.get('coordination_status', 'unknown')}\n"
        f"- priority_project: {coord.get('priority_project', 'n/a')}\n"
        f"- driver_status: {driver.get('driver_status', 'unknown')}\n"
        f"- driver_action: {driver.get('driver_action', 'n/a')}"
    )


def _format_execution_package_queue_response() -> str:
    queue = get_execution_package_queue(limit=50)
    if not queue:
        return "Execution package queue\n- empty."
    pending = [r for r in queue if str(r.get("decision_status") or "").strip().lower() in {"", "pending", "review_pending"}]
    lines = [
        "Execution package queue",
        f"- total: {len(queue)}",
        f"- pending_decisions: {len(pending)}",
    ]
    for row in queue[:8]:
        lines.append(
            "- {project}/{package_id}: review={review_status}, decision={decision_status}".format(
                project=str(row.get("project") or "unknown"),
                package_id=str(row.get("package_id") or ""),
                review_status=str(row.get("review_status") or "unknown"),
                decision_status=str(row.get("decision_status") or "pending"),
            )
        )
    return "\n".join(lines)


def _find_package_project(package_id: str) -> tuple[str | None, str | None]:
    for key in sorted(PROJECTS.keys()):
        project_path = str((PROJECTS.get(key) or {}).get("path") or "")
        if not project_path:
            continue
        package = read_execution_package(project_path=project_path, package_id=package_id)
        if isinstance(package, dict) and package:
            return key, project_path
    return None, None


def _resolve_patch_id_from_approval_id(approval_id: str) -> str | None:
    details = run_command("approval_details", approval_id=approval_id)
    payload = details.get("payload") or {}
    approval = payload.get("approval") or {}
    if not isinstance(approval, dict):
        return None
    context = approval.get("context") or {}
    patch_id = approval.get("patch_id_ref") or context.get("patch_id")
    patch_id_text = str(patch_id or "").strip()
    return patch_id_text or None


def _handle_decision(identifier: str, *, approve: bool) -> str:
    decision_label = "approved" if approve else "rejected"

    project_key, project_path = _find_package_project(identifier)
    if project_key and project_path:
        result = run_command(
            "execution_package_decide",
            project_name=project_key,
            project_path=project_path,
            execution_package_id=identifier,
            decision_status=decision_label,
            decision_actor="telegram_operator",
            decision_notes=f"Telegram operator decision: {decision_label}.",
        )
        if result.get("status") == "ok":
            return f"Execution package {identifier} {decision_label}."
        return f"Decision failed for package {identifier}: {result.get('summary') or 'unknown error'}"

    patch_cmd = "approve_patch_proposal" if approve else "reject_patch_proposal"
    patch_result = run_command(patch_cmd, patch_id=identifier, reason="Telegram operator decision.")
    if patch_result.get("status") == "ok":
        return f"Patch proposal {identifier} {decision_label}."

    mapped_patch_id = _resolve_patch_id_from_approval_id(identifier)
    if mapped_patch_id:
        mapped_result = run_command(patch_cmd, patch_id=mapped_patch_id, reason="Telegram operator decision.")
        if mapped_result.get("status") == "ok":
            return f"Approval {identifier} mapped to patch {mapped_patch_id} and {decision_label}."

    return (
        f"Could not resolve '{identifier}' as execution_package_id, patch_id, or approval_id. "
        "Use `approvals` to list pending ids."
    )


def _route_safe_command(text: str) -> str:
    command = str(text or "").strip().lower()
    if command.startswith("/"):
        command = command[1:]
    if command not in _SAFE_COMMANDS:
        return "Command not allowed"

    if command == "help":
        return _format_help_response()
    if command == "status":
        return _format_status_response()
    if command == "approvals":
        return _format_approvals_response()
    if command == "missions":
        return _format_missions_response()
    if command == "leads":
        return _format_leads_response()
    if command == "operator_snapshot":
        return _format_operator_snapshot_response()
    if command == "execution_package_queue":
        return _format_execution_package_queue_response()
    return "Command not allowed"


def handle_telegram_message(message: dict[str, Any]) -> str:
    """
    Route one Telegram message to Forge command surface and return reply text.
    """
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text") or "").strip()

    if chat_id is None:
        return "Ignored: no chat_id."
    if not _is_authorized_chat(chat_id):
        if not _telegram_allowed_chats():
            return "Authorization error: TELEGRAM_ALLOWED_CHAT_IDS is not configured."
        return "Unauthorized chat_id. Access denied."
    if not text:
        return "Ignored: message has no text."

    lowered = text.lower().strip()
    if lowered in {"help", "/help"}:
        return _format_help_response()
    if lowered in {"status", "/status"}:
        return _format_status_response()

    if lowered in {"approvals", "/approvals"}:
        return _format_approvals_response()

    if lowered.startswith("approve ") or lowered.startswith("/approve "):
        identifier = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        if not identifier:
            return "Usage: approve <execution_package_id|patch_id|approval_id>"
        return _handle_decision(identifier, approve=True)

    if lowered.startswith("deny ") or lowered.startswith("/deny "):
        identifier = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        if not identifier:
            return "Usage: deny <execution_package_id|patch_id|approval_id>"
        return _handle_decision(identifier, approve=False)

    return _route_safe_command(text)


def run_telegram_loop() -> None:
    """
    Continuous Telegram polling loop.
    """
    print("[TelegramBridge] starting loop")
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
