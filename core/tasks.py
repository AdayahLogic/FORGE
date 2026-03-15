def build_task_queue(architect_plan: dict):
    if not architect_plan or not isinstance(architect_plan, dict):
        return []

    steps = architect_plan.get("implementation_steps", [])
    validation_status = architect_plan.get("validation_status", "unknown")
    validation_issues = architect_plan.get("validation_issues", [])

    tasks = []

    # If the planner is invalid, prepend a repair task so the system doesn't blindly continue.
    if validation_status == "invalid":
        tasks.append({
            "task": "Review and repair invalid planner output before continuing implementation.",
            "status": "pending"
        })

    for step in steps:
        tasks.append({
            "task": step,
            "status": "pending"
        })

    # If the plan had warnings, track that as an explicit follow-up task.
    if validation_status == "valid_with_warnings" and validation_issues:
        tasks.append({
            "task": "Review planner validation warnings and confirm the implementation plan is safe.",
            "status": "pending"
        })

    return tasks