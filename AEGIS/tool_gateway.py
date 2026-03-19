"""
AEGIS tool gateway: route structured tool requests through policy, file guard, and ForgeShell.

- Receives structured tool requests only.
- Calls policy engine, workspace/file guard when needed.
- Routes allowlisted shell-family requests to ForgeShell.
- Returns normalized results; supported tool families kept small in this phase.
"""

from __future__ import annotations

from typing import Any

_FORGESHELL_FAMILIES = frozenset({"shell_test", "shell_lint", "shell_build", "git_status"})


def route_tool_request(
    *,
    tool_family: str,
    project_path: str | None = None,
    action_mode: str = "evaluation",
    requested_reads: list[str] | None = None,
    requested_writes: list[str] | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Route a tool request through policy, file guard, and optionally ForgeShell.

    Result shape:
    {
      "tool_gateway_status": "allowed" | "denied" | "routed" | "error_fallback",
      "tool_family": "...",
      "policy_decision": "allow" | "deny" | "approval_required" | null,
      "file_guard_status": "allow" | "deny" | ... | null,
      "forgeshell_result": { ... } | null,
      "reason": "..."
    }
    """
    req = request or {}
    family = str(tool_family or req.get("tool_family") or "").strip().lower()
    proj = project_path or req.get("project_path")
    mode = str(action_mode or req.get("action_mode") or "evaluation").strip().lower()
    reads = req.get("requested_reads") or requested_reads or []
    writes = req.get("requested_writes") or requested_writes or []

    if not family:
        return {
            "tool_gateway_status": "denied",
            "tool_family": "",
            "policy_decision": None,
            "file_guard_status": None,
            "forgeshell_result": None,
            "reason": "Missing tool_family.",
        }

    # 1) Policy
    try:
        from AEGIS import policy_engine, environment_controller
        policy_req = {
            "action_mode": mode,
            "project_path": proj,
            "tool_family": family,
            "environment": environment_controller.determine_environment(req),
        }
        policy_res = policy_engine.evaluate_policy(policy_req)
        decision = (policy_res.get("decision") or "deny").strip().lower()
    except Exception as e:
        return {
            "tool_gateway_status": "error_fallback",
            "tool_family": family,
            "policy_decision": None,
            "file_guard_status": None,
            "forgeshell_result": None,
            "reason": f"Policy evaluation failed: {e}",
        }

    if decision == "deny":
        return {
            "tool_gateway_status": "denied",
            "tool_family": family,
            "policy_decision": decision,
            "file_guard_status": None,
            "forgeshell_result": None,
            "reason": policy_res.get("reason") or "Policy denied.",
        }

    if decision == "approval_required":
        return {
            "tool_gateway_status": "allowed",
            "tool_family": family,
            "policy_decision": decision,
            "file_guard_status": None,
            "forgeshell_result": None,
            "reason": policy_res.get("reason") or "Approval required (routing marker).",
        }

    # 2) File guard when file paths are involved
    file_guard_status: str | None = None
    if reads or writes:
        try:
            from AEGIS.file_guard import evaluate_file_guard_safe
            fg = evaluate_file_guard_safe(
                project_path=proj,
                action_mode=mode,
                requested_reads=reads,
                requested_writes=writes,
            )
            file_guard_status = fg.get("file_guard_status")
            if file_guard_status in ("deny", "error_fallback"):
                return {
                    "tool_gateway_status": "denied",
                    "tool_family": family,
                    "policy_decision": decision,
                    "file_guard_status": file_guard_status,
                    "forgeshell_result": None,
                    "reason": fg.get("file_guard_reason") or "File guard denied.",
                }
        except Exception as e:
            return {
                "tool_gateway_status": "error_fallback",
                "tool_family": family,
                "policy_decision": decision,
                "file_guard_status": None,
                "forgeshell_result": None,
                "reason": f"File guard failed: {e}",
            }

    # 3) Route shell-family to ForgeShell
    if family in _FORGESHELL_FAMILIES:
        try:
            from AEGIS.forgeshell import execute_forgeshell_command_safe
            fs = execute_forgeshell_command_safe(
                command_family=family,
                project_path=proj,
                timeout_seconds=30.0,
                request=req,
            )
            fs_status = fs.get("forgeshell_status")
            if fs_status == "blocked":
                return {
                    "tool_gateway_status": "denied",
                    "tool_family": family,
                    "policy_decision": decision,
                    "file_guard_status": file_guard_status,
                    "forgeshell_result": fs,
                    "reason": fs.get("blocked_reason") or "ForgeShell blocked.",
                }
            return {
                "tool_gateway_status": "routed",
                "tool_family": family,
                "policy_decision": decision,
                "file_guard_status": file_guard_status,
                "forgeshell_result": fs,
                "reason": f"ForgeShell {fs_status}.",
            }
        except Exception as e:
            return {
                "tool_gateway_status": "error_fallback",
                "tool_family": family,
                "policy_decision": decision,
                "file_guard_status": file_guard_status,
                "forgeshell_result": None,
                "reason": f"ForgeShell failed: {e}",
            }

    return {
        "tool_gateway_status": "allowed",
        "tool_family": family,
        "policy_decision": decision,
        "file_guard_status": file_guard_status,
        "forgeshell_result": None,
        "reason": "Policy allowed; no ForgeShell route for this family.",
    }


def route_tool_request_safe(**kwargs: Any) -> dict[str, Any]:
    """Safe wrapper: never raises."""
    try:
        return route_tool_request(**kwargs)
    except Exception as e:
        return {
            "tool_gateway_status": "error_fallback",
            "tool_family": kwargs.get("tool_family") or "",
            "policy_decision": None,
            "file_guard_status": None,
            "forgeshell_result": None,
            "reason": str(e)[: 512],
        }
