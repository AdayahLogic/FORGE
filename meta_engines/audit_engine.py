from __future__ import annotations

from pathlib import Path
from typing import Any

from NEXUS.studio_config import LOGS_DIR


def evaluate_audit_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Audit/logging posture summary (ledger + studio operations log presence).

    Stable output shape:
    {
      "engine_status": "...",
      "engine_reason": "...",
      "review_required": bool
    }
    """
    try:
        states = states_by_project or {}
        if not states:
            return {
                "engine_status": "warning",
                "engine_reason": "No project state signals available; audit/ledger posture unknown.",
                "review_required": True,
            }

        ledger_total = 0
        ledger_exists = 0
        missing_ledger_projects: list[str] = []

        for key, st in states.items():
            if not isinstance(st, dict):
                continue
            ledger_path = st.get("execution_ledger_path")
            if not ledger_path:
                continue
            ledger_total += 1
            try:
                if Path(str(ledger_path)).exists():
                    ledger_exists += 1
                else:
                    missing_ledger_projects.append(key)
            except Exception:
                missing_ledger_projects.append(key)

        forge_ops_log_path = Path(LOGS_DIR) / "forge_operations.jsonl"
        forge_ops_log_exists = forge_ops_log_path.exists()

        if ledger_total == 0:
            return {
                "engine_status": "review_required",
                "engine_reason": "No execution ledger paths present in project state; audit posture requires review (placeholder).",
                "review_required": True,
            }

        if ledger_exists < ledger_total or not forge_ops_log_exists:
            return {
                "engine_status": "warning",
                "engine_reason": (
                    f"Ledger/audit signals incomplete: ledger_exists={ledger_exists}/{ledger_total}; "
                    f"missing_projects={missing_ledger_projects}; forge_operations.jsonl_exists={forge_ops_log_exists}."
                ),
                "review_required": True,
            }

        return {
            "engine_status": "passed",
            "engine_reason": "Execution ledgers exist for all projects with ledger paths; forge operations log present.",
            "review_required": False,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Audit engine evaluation failed.",
            "review_required": True,
        }

