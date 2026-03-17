from __future__ import annotations

from typing import Any

from NEXUS.runtime_target_registry import get_runtime_target_summary


def evaluate_security_engine(
    *,
    states_by_project: dict[str, dict[str, Any]] | None = None,
    runtime_infrastructure_summary: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Security posture summary focused on secret/runtime exposure posture.

    Summary-only in this sprint (no enforcement).
    """
    try:
        states = states_by_project or {}
        if not states:
            return {
                "engine_status": "warning",
                "engine_reason": "No project state signals available; runtime exposure posture unknown.",
                "review_required": True,
            }

        rt_summary = runtime_infrastructure_summary or {}
        # Build approval-level map from NEXUS registry for meaningful posture signals.
        rt_reg = get_runtime_target_summary()
        approval_by_target: dict[str, str] = {}
        for t in rt_reg.get("targets") or []:
            canonical = str(t.get("canonical_name") or "").strip().lower()
            approval = str(t.get("approval_level") or "").strip().lower()
            if canonical:
                approval_by_target[canonical] = approval

        any_auto = False
        any_human_review = False
        unknown_targets: set[str] = set()

        for _, st in states.items():
            if not isinstance(st, dict):
                continue
            dps = st.get("dispatch_plan_summary") or {}
            if not isinstance(dps, dict):
                continue
            runtime_target_id = (dps.get("runtime_target_id") or dps.get("runtime_node") or "").strip().lower()
            ready_for_dispatch = bool(dps.get("ready_for_dispatch", False))

            if not runtime_target_id:
                continue

            approval = approval_by_target.get(runtime_target_id)
            if approval is None:
                unknown_targets.add(runtime_target_id)
                continue

            # Exposure posture is summarized as "who approves execution" for a given
            # runtime target when work is ready to be dispatched.
            if ready_for_dispatch:
                if approval == "human_review":
                    any_human_review = True
                elif approval == "auto":
                    any_auto = True
                else:
                    unknown_targets.add(runtime_target_id)

        if unknown_targets and not (any_auto or any_human_review):
            return {
                "engine_status": "warning",
                "engine_reason": f"Encountered unknown runtime targets for exposure posture: {sorted(unknown_targets)}.",
                "review_required": True,
            }

        if any_auto and not any_human_review:
            return {
                "engine_status": "warning",
                "engine_reason": "Runtime exposure posture includes auto-approved execution targets.",
                "review_required": True,
            }

        if any_auto and any_human_review:
            return {
                "engine_status": "warning",
                "engine_reason": "Runtime exposure posture mixes auto-approved and human-review targets.",
                "review_required": True,
            }

        if any_human_review:
            return {
                "engine_status": "passed",
                "engine_reason": "Runtime exposure posture indicates human-review approval for dispatch-ready targets.",
                "review_required": False,
            }

        return {
            "engine_status": "warning",
            "engine_reason": "No dispatch-ready runtime approval signals found; runtime exposure posture unknown.",
            "review_required": True,
        }
    except Exception:
        return {
            "engine_status": "error_fallback",
            "engine_reason": "Security engine evaluation failed.",
            "review_required": True,
        }

