"""
Safe Telegram bridge for Forge operator control.

This bridge exposes a strict allowlisted command surface only. It never forwards
arbitrary text into execution paths and remains approval-aware for risky changes.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from NEXUS.command_surface import run_command
from NEXUS.logging_engine import log_system_event
from NEXUS.mission_system import MISSION_TYPES, build_mission_packet
from NEXUS.project_state import load_project_state, update_project_state_fields
from NEXUS.registry import PROJECTS


TELEGRAM_API_BASE = "https://api.telegram.org"
OFFSET_FILENAME = "telegram_bridge_offset.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_allowed_chat_ids(raw: str | None) -> set[int]:
    ids: set[int] = set()
    for part in str(raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except Exception:
            continue
    return ids


def _offset_file_from_env() -> Path:
    custom = _sanitize_text(os.getenv("TELEGRAM_OFFSET_FILE"))
    if custom:
        return Path(custom).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "ops" / OFFSET_FILENAME).resolve()


def _load_last_offset(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(payload.get("last_update_offset") or 0))
    except Exception:
        return 0


def _persist_last_offset(path: Path, offset: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_update_offset": max(0, int(offset)),
            "saved_at": _utc_now_iso(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Polling loop should remain alive even if persistence fails.
        return


def _telegram_post(token: str, method: str, payload: dict[str, Any], timeout_seconds: float = 20.0) -> dict[str, Any]:
    endpoint = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    data = parse.urlencode(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise RuntimeError("Telegram API returned invalid payload.")
    return decoded


def _project_rows() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for key in sorted(PROJECTS.keys()):
        meta = PROJECTS.get(key)
        if isinstance(meta, dict) and _sanitize_text(meta.get("path")):
            out.append((key, meta))
    return out


def _default_project_key() -> str | None:
    configured = _sanitize_text(os.getenv("FORGE_TELEGRAM_DEFAULT_PROJECT")).lower()
    if configured and configured in PROJECTS:
        return configured
    keys = sorted(PROJECTS.keys())
    return keys[0] if keys else None


def _fmt_section(title: str, lines: list[str]) -> str:
    body = [f"*{title}*"]
    for line in lines:
        text = _sanitize_text(line)
        if text:
            body.append(f"- {text}")
    return "\n".join(body)


def _bool_marker(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _focus_from_alias(value: str) -> str:
    token = _sanitize_text(value).lower()
    mapping = {
        "revenue": "revenue_business_ops",
        "self_build": "forge_self_build",
        "delivery": "project_delivery",
    }
    return mapping.get(token, "")


def _mission_alias(value: str) -> str:
    token = _sanitize_text(value).lower()
    mapping = {
        "revenue": "revenue_business_ops",
        "self_build": "forge_self_build",
        "delivery": "project_delivery",
        "research": "research_ops",
    }
    return mapping.get(token, token)


class TelegramCommandRouter:
    """Strict allowlist router for Telegram commands."""

    def __init__(self) -> None:
        self.allowed_patterns = {
            "help",
            "status",
            "operator_snapshot",
            "execution_package_queue",
            "approvals",
            "approve <id>",
            "deny <id>",
            "missions",
            "mission <id>",
            "run mission <type>",
            "pause mission <id>",
            "resume mission <id>",
            "autopilot status",
            "autopilot on",
            "autopilot off",
            "autopilot focus revenue",
            "autopilot focus self_build",
            "autopilot focus delivery",
            "leads",
            "lead <id>",
            "followups",
            "closing",
            "deals",
            "projects",
            "run lead mission",
            "review_queue",
            "blocked",
            "builds",
            "deliveries",
        }

    def route(self, text: str) -> str:
        raw = _sanitize_text(text)
        normalized = " ".join(raw.lower().split())
        if not normalized:
            return self._not_allowed()
        if normalized == "help":
            return self.help_text()
        if normalized == "status":
            return self._status()
        if normalized == "operator_snapshot":
            return self._operator_snapshot()
        if normalized == "execution_package_queue":
            return self._execution_package_queue()
        if normalized == "approvals":
            return self._approvals()
        if normalized.startswith("approve "):
            return self._resolve_approval(normalized.split(" ", 1)[1], approve=True)
        if normalized.startswith("deny "):
            return self._resolve_approval(normalized.split(" ", 1)[1], approve=False)
        if normalized == "missions":
            return self._missions()
        if normalized.startswith("mission "):
            return self._mission_details(normalized.split(" ", 1)[1])
        if normalized.startswith("run mission "):
            return self._run_mission(normalized.split(" ", 2)[2])
        if normalized.startswith("pause mission "):
            return self._set_mission_status(normalized.split(" ", 2)[2], mission_status="paused")
        if normalized.startswith("resume mission "):
            return self._set_mission_status(normalized.split(" ", 2)[2], mission_status="approved_for_execution")
        if normalized == "autopilot status":
            return self._autopilot_status()
        if normalized == "autopilot on":
            return self._autopilot_on()
        if normalized == "autopilot off":
            return self._autopilot_off()
        if normalized.startswith("autopilot focus "):
            return self._autopilot_focus(normalized.split(" ", 2)[2])
        if normalized == "leads":
            return self._revenue_rows(kind="leads")
        if normalized.startswith("lead "):
            return self._lead_details(normalized.split(" ", 1)[1])
        if normalized == "followups":
            return self._revenue_rows(kind="followups")
        if normalized == "closing":
            return self._revenue_rows(kind="closing")
        if normalized == "deals":
            return self._revenue_rows(kind="deals")
        if normalized == "projects":
            return self._projects_summary()
        if normalized == "run lead mission":
            return self._run_lead_mission()
        if normalized == "review_queue":
            return self._execution_rows(kind="review_queue")
        if normalized == "blocked":
            return self._execution_rows(kind="blocked")
        if normalized == "builds":
            return self._execution_rows(kind="builds")
        if normalized == "deliveries":
            return self._execution_rows(kind="deliveries")
        return self._not_allowed()

    def help_text(self) -> str:
        return "\n\n".join(
            [
                _fmt_section("Core", ["help", "status", "operator_snapshot", "execution_package_queue", "approvals", "approve <id>", "deny <id>"]),
                _fmt_section("Missions", ["missions", "mission <id>", "run mission <type>", "pause mission <id>", "resume mission <id>"]),
                _fmt_section("Autopilot", ["autopilot status", "autopilot on", "autopilot off", "autopilot focus revenue", "autopilot focus self_build", "autopilot focus delivery"]),
                _fmt_section("Revenue", ["leads", "lead <id>", "followups", "closing", "deals", "projects", "run lead mission"]),
                _fmt_section("Execution", ["review_queue", "blocked", "builds", "deliveries"]),
            ]
        )

    def _not_allowed(self) -> str:
        return "Command not allowed.\nUse `help` for the approved command set."

    def _primary_project(self) -> tuple[str, dict[str, Any]] | tuple[None, None]:
        key = _default_project_key()
        if key and key in PROJECTS:
            return key, PROJECTS[key]
        return None, None

    def _queue_rows_for_project(self, key: str, path: str, n: int = 30) -> list[dict[str, Any]]:
        res = run_command("execution_package_queue", project_name=key, project_path=path, n=n)
        payload = res.get("payload") if isinstance(res, dict) else {}
        rows = payload.get("queue_rows") if isinstance(payload, dict) else []
        out: list[dict[str, Any]] = []
        for row in rows or []:
            if isinstance(row, dict):
                out.append({**row, "_project_key": key})
        return out

    def _all_queue_rows(self, n: int = 20) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, meta in _project_rows():
            rows.extend(self._queue_rows_for_project(key, str(meta.get("path")), n=n))
        return rows

    def _status(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Forge status unavailable: no projects registered."
        dashboard = run_command("dashboard_summary")
        approvals = run_command("pending_approvals", project_name=key, project_path=str(project.get("path")))
        auto = run_command("project_autopilot_status", project_name=key, project_path=str(project.get("path")))
        queue_rows = self._queue_rows_for_project(key, str(project.get("path")), n=50)
        active_missions = sum(1 for row in queue_rows if str(row.get("mission_status") or "").lower() in {"approved_for_execution", "executing"})
        pending_approvals = int(((approvals.get("payload") or {}).get("pending_count_total") or 0))
        autopilot = (auto.get("payload") or {}).get("autopilot") or {}
        status_payload = dashboard.get("payload") or {}
        return "\n\n".join(
            [
                _fmt_section("Forge", [f"status: online", f"project: {key}", f"portfolio_status: {status_payload.get('portfolio_status') or 'unknown'}"]),
                _fmt_section(
                    "Autopilot",
                    [
                        f"enabled: {_bool_marker(autopilot.get('autopilot_enabled'))}",
                        f"status: {autopilot.get('autopilot_status') or 'unknown'}",
                        f"focus: {autopilot.get('autopilot_current_focus') or 'none'}",
                    ],
                ),
                _fmt_section("Queue", [f"pending approvals: {pending_approvals}", f"active missions: {active_missions}", f"queue rows: {len(queue_rows)}"]),
            ]
        )

    def _operator_snapshot(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Operator snapshot unavailable: no projects registered."
        res = run_command("operator_snapshot", project_name=key, project_path=str(project.get("path")))
        payload = res.get("payload") if isinstance(res, dict) else {}
        return _fmt_section(
            "Operator Snapshot",
            [
                f"project: {key}",
                f"dispatch: {payload.get('dispatch_status') or 'unknown'}",
                f"governance: {payload.get('governance_status') or 'unknown'}",
                f"enforcement: {payload.get('enforcement_status') or 'unknown'}",
                f"review_queue_items: {len(payload.get('review_queue') or [])}",
            ],
        )

    def _execution_package_queue(self) -> str:
        rows = self._all_queue_rows(n=20)
        if not rows:
            return _fmt_section("Execution Package Queue", ["queue is empty"])
        lines = []
        for row in rows[:10]:
            lines.append(
                f"{row.get('package_id') or 'unknown'} | project={row.get('_project_key')} | mission={row.get('mission_status') or 'proposed'} | review={row.get('review_status') or 'pending'} | autopilot={row.get('autopilot_status') or 'idle'}"
            )
        return "\n\n".join([_fmt_section("Execution Package Queue", [f"rows: {len(rows)}"]), _fmt_section("Top Entries", lines)])

    def _approvals(self) -> str:
        res = run_command("pending_approvals")
        payload = res.get("payload") if isinstance(res, dict) else {}
        pending = int(payload.get("pending_count_total") or 0)
        recent = payload.get("recent_approvals") if isinstance(payload, dict) else []
        lines = [f"pending approvals: {pending}"]
        for row in (recent or [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"{row.get('approval_id') or 'n/a'} | status={row.get('status') or 'unknown'} | project={row.get('project_name') or row.get('project') or 'unknown'}"
            )
        return _fmt_section("Approvals", lines)

    def _resolve_approval(self, candidate_id: str, *, approve: bool) -> str:
        target = _sanitize_text(candidate_id)
        if not target:
            return "Approval id required. Use `approve <id>` or `deny <id>`."
        details = run_command("approval_details", approval_id=target)
        payload = details.get("payload") if isinstance(details, dict) else {}
        approval = payload.get("approval") if isinstance(payload, dict) else None
        patch_id = ""
        if isinstance(approval, dict):
            patch_id = _sanitize_text(approval.get("patch_id_ref") or (approval.get("context") or {}).get("patch_id"))
        if not patch_id:
            patch_id = target
        command_name = "approve_patch_proposal" if approve else "reject_patch_proposal"
        result = run_command(command_name, patch_id=patch_id, reason="telegram_operator")
        status = "approved" if approve else "denied"
        return _fmt_section(
            "Approval Decision",
            [
                f"decision: {status}",
                f"requested id: {target}",
                f"patch id: {patch_id}",
                f"result: {result.get('status') or 'error'}",
                f"summary: {result.get('summary') or ''}",
            ],
        )

    def _mission_rows(self) -> list[dict[str, Any]]:
        rows = self._all_queue_rows(n=40)
        mission_rows = [row for row in rows if _sanitize_text(row.get("mission_id")) or _sanitize_text(row.get("package_id"))]
        return mission_rows

    def _missions(self) -> str:
        rows = self._mission_rows()
        if not rows:
            return _fmt_section("Missions", ["no missions found"])
        lines = []
        for row in rows[:12]:
            mission_id = _sanitize_text(row.get("mission_id") or row.get("package_id"))
            approval_state = "awaiting_approval" if bool(row.get("approval_queue_requires_initial_approval")) else "governed"
            lines.append(
                f"{mission_id} | type={row.get('mission_type') or 'project_delivery'} | status={row.get('mission_status') or 'proposed'} | executor={row.get('executor_route') or 'n/a'} | approval={approval_state} | risk={row.get('mission_risk_level') or 'medium'} | focus={row.get('autopilot_current_focus') or 'none'}"
            )
        return _fmt_section("Missions", lines)

    def _mission_details(self, mission_id: str) -> str:
        target = _sanitize_text(mission_id)
        if not target:
            return "Mission id required. Use `mission <id>`."
        for row in self._mission_rows():
            row_id = _sanitize_text(row.get("mission_id") or row.get("package_id"))
            if row_id != target:
                continue
            approval_state = "awaiting_approval" if bool(row.get("approval_queue_requires_initial_approval")) else "governed"
            stop_reason = row.get("mission_stop_condition_reason") if bool(row.get("mission_stop_condition_hit")) else "none"
            return _fmt_section(
                "Mission",
                [
                    f"id: {row_id}",
                    f"type: {row.get('mission_type') or 'project_delivery'}",
                    f"status: {row.get('mission_status') or 'proposed'}",
                    f"executor: {row.get('executor_route') or 'n/a'}",
                    f"approval state: {approval_state}",
                    f"risk level: {row.get('mission_risk_level') or 'medium'}",
                    f"current focus: {row.get('autopilot_current_focus') or 'none'}",
                    f"stop condition: {stop_reason}",
                ],
            )
        return f"Mission not found: {target}"

    def _run_mission(self, mission_type_token: str) -> str:
        requested = _mission_alias(mission_type_token)
        if requested not in MISSION_TYPES:
            allowed = ", ".join(sorted(MISSION_TYPES))
            return f"Mission type not allowed. Allowed: {allowed}"
        key, project = self._primary_project()
        if not key or not project:
            return "Cannot run mission: no project configured."
        mission_id = f"tg-{requested}-{int(time.time())}"
        packet = build_mission_packet(
            mission_id=mission_id,
            task={"type": requested, "payload": {"source": "telegram_bridge", "bounded": True}},
            mission_type=requested,
            objective=f"Telegram requested mission ({requested}) with bounded supervision.",
            risk_level="medium",
            requires_initial_approval=True,
            requires_final_approval=True,
        )
        packet["mission_status"] = "awaiting_initial_approval"
        update_project_state_fields(
            str(project.get("path")),
            mission_packet=packet,
            mission_status="awaiting_initial_approval",
            mission_requires_initial_approval=True,
            mission_requires_final_approval=True,
            autopilot_requires_operator_review=True,
        )
        log_system_event(
            project=key,
            subsystem="telegram_bridge",
            action="mission_queued",
            status="ok",
            reason="Mission queued by Telegram operator command.",
            metadata={"mission_id": mission_id, "mission_type": requested},
        )
        return _fmt_section(
            "Mission Queued",
            [
                f"id: {mission_id}",
                f"type: {requested}",
                "status: awaiting_initial_approval",
                "execution: bounded and approval-aware",
            ],
        )

    def _set_mission_status(self, mission_id: str, *, mission_status: str) -> str:
        target = _sanitize_text(mission_id)
        if not target:
            return "Mission id required."
        for key, meta in _project_rows():
            state = load_project_state(str(meta.get("path")))
            if not isinstance(state, dict) or state.get("load_error"):
                continue
            packet = dict(state.get("mission_packet") or {})
            current_id = _sanitize_text(packet.get("mission_id") or state.get("mission_id"))
            if current_id != target:
                continue
            packet["mission_status"] = mission_status
            update_project_state_fields(str(meta.get("path")), mission_packet=packet, mission_status=mission_status)
            log_system_event(
                project=key,
                subsystem="telegram_bridge",
                action=f"mission_{mission_status}",
                status="ok",
                reason="Mission status changed by Telegram command.",
                metadata={"mission_id": target, "mission_status": mission_status},
            )
            return _fmt_section("Mission Control", [f"id: {target}", f"status: {mission_status}", f"project: {key}"])
        return f"Mission not found: {target}"

    def _autopilot_status(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Autopilot status unavailable: no project configured."
        result = run_command("project_autopilot_status", project_name=key, project_path=str(project.get("path")))
        session = (result.get("payload") or {}).get("autopilot") or {}
        return _fmt_section(
            "Autopilot",
            [
                f"project: {key}",
                f"enabled: {_bool_marker(session.get('autopilot_enabled'))}",
                f"status: {session.get('autopilot_status') or 'unknown'}",
                f"focus: {session.get('autopilot_current_focus') or 'none'}",
                f"requires operator review: {_bool_marker(session.get('autopilot_requires_operator_review'))}",
            ],
        )

    def _autopilot_on(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Autopilot control unavailable: no project configured."
        status = run_command("project_autopilot_status", project_name=key, project_path=str(project.get("path")))
        session = (status.get("payload") or {}).get("autopilot") or {}
        if bool(session.get("autopilot_requires_operator_review")):
            return "Autopilot change blocked: operator review is currently required."
        if bool(session.get("autopilot_enabled")) and str(session.get("autopilot_status") or "").lower() in {"ready", "executing"}:
            return "Autopilot is already on."
        command = "project_autopilot_resume" if str(session.get("autopilot_status") or "").lower() == "paused" else "project_autopilot_start"
        result = run_command(command, project_name=key, project_path=str(project.get("path")))
        log_system_event(
            project=key,
            subsystem="telegram_bridge",
            action="autopilot_on",
            status="ok" if result.get("status") == "ok" else "error",
            reason="Autopilot on requested via Telegram.",
        )
        return _fmt_section("Autopilot Control", [f"command: {command}", f"result: {result.get('status')}", f"summary: {result.get('summary') or ''}"])

    def _autopilot_off(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Autopilot control unavailable: no project configured."
        status = run_command("project_autopilot_status", project_name=key, project_path=str(project.get("path")))
        session = (status.get("payload") or {}).get("autopilot") or {}
        if bool(session.get("autopilot_requires_operator_review")):
            return "Autopilot change blocked: operator review is currently required."
        result = run_command("project_autopilot_stop", project_name=key, project_path=str(project.get("path")))
        log_system_event(
            project=key,
            subsystem="telegram_bridge",
            action="autopilot_off",
            status="ok" if result.get("status") == "ok" else "error",
            reason="Autopilot off requested via Telegram.",
        )
        return _fmt_section("Autopilot Control", [f"command: project_autopilot_stop", f"result: {result.get('status')}", f"summary: {result.get('summary') or ''}"])

    def _autopilot_focus(self, focus_token: str) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Autopilot control unavailable: no project configured."
        focus = _focus_from_alias(focus_token)
        if not focus:
            return "Focus not allowed. Allowed: revenue, self_build, delivery."
        state = load_project_state(str(project.get("path")))
        if not isinstance(state, dict) or state.get("load_error"):
            return "Cannot update focus: failed to load project state."
        if bool(state.get("autopilot_requires_operator_review")):
            return "Autopilot focus change blocked: operator review is currently required."
        update_project_state_fields(str(project.get("path")), autopilot_current_focus=focus)
        log_system_event(
            project=key,
            subsystem="telegram_bridge",
            action="autopilot_focus",
            status="ok",
            reason="Autopilot focus changed via Telegram.",
            metadata={"focus": focus},
        )
        return _fmt_section("Autopilot Focus", [f"project: {key}", f"focus: {focus}", "status: updated"])

    def _revenue_rows(self, *, kind: str) -> str:
        rows = self._all_queue_rows(n=40)
        if kind == "leads":
            filtered = [r for r in rows if _sanitize_text(r.get("lead_id"))]
            title = "Leads"
            lines = [f"{r.get('lead_id')} | status={r.get('lead_status') or 'new'} | priority={r.get('lead_priority') or 'medium'} | value={r.get('lead_value_estimate') or 0}" for r in filtered[:12]]
        elif kind == "followups":
            filtered = [r for r in rows if bool(r.get("follow_up_required")) or _sanitize_text(r.get("follow_up_status")) not in {"", "not_required"}]
            title = "Followups"
            lines = [f"{r.get('lead_id') or r.get('package_id')} | status={r.get('follow_up_status') or 'pending'} | next={r.get('follow_up_next_at') or 'n/a'}" for r in filtered[:12]]
        elif kind == "closing":
            filtered = [r for r in rows if bool(r.get("closing_signal_detected")) or _sanitize_text(r.get("conversation_stage")).lower() == "closing"]
            title = "Closing"
            lines = [f"{r.get('lead_id') or r.get('package_id')} | signal={r.get('closing_signal_type') or 'none'} | confidence={r.get('closing_confidence') or 0}" for r in filtered[:12]]
        else:
            filtered = [r for r in rows if _sanitize_text(r.get("deal_status")) and _sanitize_text(r.get("deal_status")).lower() != "open"]
            title = "Deals"
            lines = [f"{r.get('lead_id') or r.get('package_id')} | deal={r.get('deal_status')} | stage={r.get('conversation_stage') or 'lead'}" for r in filtered[:12]]
        if not lines:
            lines = ["no items"]
        return _fmt_section(title, lines)

    def _lead_details(self, lead_id: str) -> str:
        target = _sanitize_text(lead_id)
        if not target:
            return "Lead id required. Use `lead <id>`."
        for row in self._all_queue_rows(n=60):
            if _sanitize_text(row.get("lead_id")) != target:
                continue
            return _fmt_section(
                "Lead",
                [
                    f"id: {target}",
                    f"status: {row.get('lead_status') or 'new'}",
                    f"priority: {row.get('lead_priority') or 'medium'}",
                    f"qualification: {row.get('qualification_status') or 'unqualified'} ({row.get('qualification_score') or 0})",
                    f"stage: {row.get('conversation_stage') or 'lead'}",
                    f"deal: {row.get('deal_status') or 'open'}",
                    f"followup: {row.get('follow_up_status') or 'not_required'}",
                ],
            )
        return f"Lead not found: {target}"

    def _projects_summary(self) -> str:
        lines = []
        for key, meta in _project_rows():
            rows = self._queue_rows_for_project(key, str(meta.get("path")), n=20)
            in_build = sum(1 for r in rows if _sanitize_text(r.get("build_status")).lower() in {"building", "in_progress"})
            ready_delivery = sum(1 for r in rows if _sanitize_text(r.get("delivery_status")).lower() in {"ready", "ready_for_delivery"})
            lines.append(f"{key} | queue={len(rows)} | builds={in_build} | ready_delivery={ready_delivery}")
        if not lines:
            lines = ["no projects configured"]
        return _fmt_section("Projects", lines)

    def _run_lead_mission(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return "Cannot run lead mission: no project configured."
        discovery_configured = bool(_sanitize_text(os.getenv("TAVILY_API_KEY")))
        mission_id = f"tg-lead-{int(time.time())}"
        packet = build_mission_packet(
            mission_id=mission_id,
            task={"type": "lead_discovery", "payload": {"domain": "revenue_business_ops", "bounded": True}},
            mission_type="revenue_business_ops",
            objective="Run bounded lead discovery/processing preparation with explicit approval gating.",
            risk_level="medium",
            requires_initial_approval=True,
            requires_final_approval=True,
        )
        packet["mission_status"] = "awaiting_initial_approval"
        update_project_state_fields(
            str(project.get("path")),
            mission_packet=packet,
            mission_status="awaiting_initial_approval",
            mission_requires_initial_approval=True,
            mission_requires_final_approval=True,
            autopilot_requires_operator_review=True,
            email_requires_approval=True,
        )
        log_system_event(
            project=key,
            subsystem="telegram_bridge",
            action="run_lead_mission",
            status="ok",
            reason="Lead mission queued from Telegram.",
            metadata={"mission_id": mission_id, "discovery_configured": discovery_configured},
        )
        extra = (
            "Lead discovery source not configured yet."
            if not discovery_configured
            else "Lead discovery source key detected, but external discovery integration remains bounded and approval-gated."
        )
        return _fmt_section(
            "Lead Mission",
            [
                f"id: {mission_id}",
                "status: awaiting_initial_approval",
                "outreach: disabled (no auto-send)",
                extra,
            ],
        )

    def _execution_rows(self, *, kind: str) -> str:
        rows = self._all_queue_rows(n=50)
        if kind == "review_queue":
            filtered = [r for r in rows if _sanitize_text(r.get("review_status")).lower() in {"pending", "review_pending"}]
            title = "Review Queue"
            lines = [f"{r.get('package_id')} | project={r.get('_project_key')} | review={r.get('review_status')} | approval_required={_bool_marker(r.get('approval_queue_requires_initial_approval'))}" for r in filtered[:15]]
        elif kind == "blocked":
            filtered = [
                r
                for r in rows
                if _sanitize_text(r.get("mission_status")).lower() in {"failed", "paused", "rejected"}
                or bool(r.get("mission_stop_condition_hit"))
                or _sanitize_text(r.get("autopilot_status")).lower() in {"blocked", "escalated", "awaiting_approval"}
            ]
            title = "Blocked"
            lines = [f"{r.get('package_id')} | project={r.get('_project_key')} | mission={r.get('mission_status')} | reason={r.get('mission_stop_condition_reason') or r.get('autopilot_status')}" for r in filtered[:15]]
        elif kind == "builds":
            filtered = [r for r in rows if _sanitize_text(r.get("build_status")).lower() not in {"", "pending"}]
            title = "Builds"
            lines = [f"{r.get('package_id')} | project={r.get('_project_key')} | build={r.get('build_status')} | setup={r.get('setup_status') or 'pending'}" for r in filtered[:15]]
        else:
            filtered = [r for r in rows if _sanitize_text(r.get("delivery_status")).lower() not in {"", "pending"} or bool(r.get("delivery_requires_approval"))]
            title = "Deliveries"
            lines = [f"{r.get('package_id')} | project={r.get('_project_key')} | delivery={r.get('delivery_status') or 'pending'} | approval_required={_bool_marker(r.get('delivery_requires_approval'))}" for r in filtered[:15]]
        if not lines:
            lines = ["no items"]
        return _fmt_section(title, lines)

    def build_startup_message(self) -> str:
        key, project = self._primary_project()
        if not key or not project:
            return _fmt_section("Forge Startup", ["status: online", "project: none", "autopilot: unknown", "pending approvals: 0", "active missions: 0"])
        approvals = run_command("pending_approvals", project_name=key, project_path=str(project.get("path")))
        auto = run_command("project_autopilot_status", project_name=key, project_path=str(project.get("path")))
        queue_rows = self._queue_rows_for_project(key, str(project.get("path")), n=50)
        active_missions = sum(1 for row in queue_rows if _sanitize_text(row.get("mission_status")).lower() in {"approved_for_execution", "executing"})
        pending_approvals = int(((approvals.get("payload") or {}).get("pending_count_total") or 0))
        autopilot = (auto.get("payload") or {}).get("autopilot") or {}
        return _fmt_section(
            "Forge Startup",
            [
                "status: online",
                f"project: {key}",
                f"autopilot: {autopilot.get('autopilot_status') or 'unknown'}",
                f"pending approvals: {pending_approvals}",
                f"active missions: {active_missions}",
            ],
        )


class TelegramBridge:
    def __init__(self, *, token: str, allowed_chat_ids: set[int], poll_interval_seconds: float = 2.0) -> None:
        self.token = _sanitize_text(token)
        self.allowed_chat_ids = set(allowed_chat_ids)
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self.offset_path = _offset_file_from_env()
        self.router = TelegramCommandRouter()
        self.last_update_offset = _load_last_offset(self.offset_path)

    def is_ready(self) -> bool:
        return bool(self.token) and bool(self.allowed_chat_ids)

    def send_message(self, chat_id: int, text: str) -> None:
        payload = {"chat_id": str(chat_id), "text": _sanitize_text(text)}
        _telegram_post(self.token, "sendMessage", payload)

    def send_startup_message(self) -> None:
        message = self.router.build_startup_message()
        for chat_id in sorted(self.allowed_chat_ids):
            try:
                self.send_message(chat_id, message)
            except Exception:
                continue

    def poll_updates(self) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": "25"}
        if self.last_update_offset > 0:
            payload["offset"] = str(self.last_update_offset)
        result = _telegram_post(self.token, "getUpdates", payload, timeout_seconds=35.0)
        if not bool(result.get("ok")):
            raise RuntimeError(f"Telegram getUpdates failed: {result!r}")
        updates = result.get("result")
        if not isinstance(updates, list):
            return []
        out: list[dict[str, Any]] = []
        for item in updates:
            if isinstance(item, dict):
                out.append(item)
        return out

    def handle_update(self, update: dict[str, Any]) -> None:
        update_id = int(update.get("update_id") or 0)
        message = update.get("message") if isinstance(update.get("message"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        text = _sanitize_text(message.get("text"))
        chat_id = int(chat.get("id") or 0)
        self.last_update_offset = max(self.last_update_offset, update_id + 1)
        _persist_last_offset(self.offset_path, self.last_update_offset)
        if chat_id not in self.allowed_chat_ids:
            return
        if not text:
            self.send_message(chat_id, "Command not allowed.\nUse `help` for allowed commands.")
            return
        response = self.router.route(text)
        self.send_message(chat_id, response)

    def run_forever(self) -> None:
        if not self.is_ready():
            raise RuntimeError("Bridge is not ready. TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS are required.")
        self.send_startup_message()
        backoff_seconds = 1.0
        while True:
            try:
                updates = self.poll_updates()
                for update in updates:
                    self.handle_update(update)
                backoff_seconds = 1.0
                time.sleep(self.poll_interval_seconds)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log_system_event(
                    project="",
                    subsystem="telegram_bridge",
                    action="poll_error",
                    status="error",
                    reason="Telegram polling error; retry with backoff.",
                    metadata={"error": str(exc), "backoff_seconds": backoff_seconds},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(30.0, backoff_seconds * 2.0)


def build_bridge_from_env() -> TelegramBridge:
    token = _sanitize_text(os.getenv("TELEGRAM_BOT_TOKEN"))
    allowed_ids = _parse_allowed_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS"))
    interval_raw = _sanitize_text(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS"))
    try:
        interval = float(interval_raw) if interval_raw else 2.0
    except Exception:
        interval = 2.0
    return TelegramBridge(token=token, allowed_chat_ids=allowed_ids, poll_interval_seconds=interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Forge Telegram bridge")
    parser.add_argument("--once", action="store_true", help="Poll once and process currently available messages.")
    args = parser.parse_args()
    bridge = build_bridge_from_env()
    if not bridge.token:
        print("TELEGRAM_BOT_TOKEN is missing.")
        return 2
    if not bridge.allowed_chat_ids:
        print("TELEGRAM_ALLOWED_CHAT_IDS is empty. Deny-by-default active.")
        return 3
    if args.once:
        updates = bridge.poll_updates()
        for update in updates:
            bridge.handle_update(update)
        return 0
    bridge.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
