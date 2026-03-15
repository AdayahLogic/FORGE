from NEXUS.planning.planner_engine import PlannerEngine
from NEXUS.planning.plan_validator import validate_and_normalize_plan
from NEXUS.planning.json_utils import parse_json_object


MAX_PLANNER_ATTEMPTS = 3


def _fallback_plan(project_name: str, raw_text: str, reason: str, attempts: list[dict]) -> dict:
    fallback = {
        "objective": f"Fallback planning output for {project_name}",
        "assumptions": [
            "The planner response could not be repaired safely.",
            "A non-destructive fallback plan is safer than guessing.",
        ],
        "implementation_steps": [
            "Review the malformed planner output.",
            "Refine the planner prompt or schema validation.",
            "Retry with a narrower implementation slice.",
        ],
        "risks": [
            reason,
            "Planner output could not be parsed or validated after retries.",
        ],
        "next_agent": "coder",
        "patch_request": None,
    }

    validated = validate_and_normalize_plan(fallback, project_name)
    validated["raw_model_output"] = raw_text[:2000]
    validated["planner_attempt_count"] = len(attempts)
    validated["planner_attempts"] = attempts
    validated["planner_recovery_status"] = "fallback_used"
    return validated


def generate_architect_plan(user_input: str, project_name: str, loaded_context: dict) -> dict:
    planner = PlannerEngine()
    attempts: list[dict] = []

    raw_text = ""
    retry_reason = ""

    for attempt_number in range(1, MAX_PLANNER_ATTEMPTS + 1):
        try:
            if attempt_number == 1:
                raw_text = planner.generate_raw_plan(
                    user_input=user_input,
                    project_name=project_name,
                    loaded_context=loaded_context,
                )
            else:
                raw_text = planner.retry_raw_plan(
                    previous_output=raw_text,
                    project_name=project_name,
                    retry_reason=retry_reason or "Previous output was not acceptable.",
                )

            try:
                parsed = parse_json_object(raw_text)
            except Exception as e:
                retry_reason = f"JSON parse failure: {e}"
                attempts.append({
                    "attempt": attempt_number,
                    "stage": "parse",
                    "status": "failed",
                    "reason": retry_reason,
                })
                continue

            validated = validate_and_normalize_plan(parsed, project_name)
            validation_status = validated.get("validation_status", "invalid")

            if validation_status == "invalid":
                retry_reason = "Validation failure: planner output did not meet required schema."
                attempts.append({
                    "attempt": attempt_number,
                    "stage": "validate",
                    "status": "failed",
                    "reason": retry_reason,
                    "validation_issues": validated.get("validation_issues", []),
                })
                continue

            attempts.append({
                "attempt": attempt_number,
                "stage": "validate",
                "status": "passed",
                "reason": "Planner output parsed and validated successfully.",
                "validation_issues": validated.get("validation_issues", []),
            })

            validated["raw_model_output"] = raw_text[:2000]
            validated["planner_attempt_count"] = len(attempts)
            validated["planner_attempts"] = attempts
            validated["planner_recovery_status"] = (
                "recovered_after_retry" if attempt_number > 1 else "clean_first_pass"
            )

            return validated

        except Exception as e:
            retry_reason = f"Planner engine call failed: {e}"
            attempts.append({
                "attempt": attempt_number,
                "stage": "engine",
                "status": "failed",
                "reason": retry_reason,
            })

    return _fallback_plan(
        project_name=project_name,
        raw_text=raw_text or retry_reason,
        reason=retry_reason or "Unknown planner failure.",
        attempts=attempts,
    )