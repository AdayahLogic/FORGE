from core.operator_tools import (
    list_directory,
    read_text_file,
    write_text_file,
    run_safe_command,
    log_operator_action,
)


def run_operator_sequence(project_path: str) -> str:
    log_path = ""

    # 1. List src folder if present, otherwise list project root
    try:
        result = list_directory(project_path, "src")
        log_path = log_operator_action(project_path, "list_directory", result)
    except Exception:
        result = list_directory(project_path, ".")
        log_path = log_operator_action(project_path, "list_directory", result)

    # 2. Read generated module if it exists
    try:
        result = read_text_file(project_path, "src/ai_generated_module.py")
        log_path = log_operator_action(
            project_path,
            "read_text_file",
            {
                "target_path": result["target_path"],
                "preview": result["content"][:500]
            }
        )
    except Exception as e:
        log_path = log_operator_action(
            project_path,
            "read_text_file_error",
            {"error": str(e)}
        )

    # 3. Write a small operator status file
    result = write_text_file(
        project_path,
        "generated/operator_status.txt",
        "Operator tools executed successfully.\n"
        "This file confirms the Step 27D operator layer is active.\n"
    )
    log_path = log_operator_action(project_path, "write_text_file", result)

    # 4. Run one safe command
    try:
        result = run_safe_command(project_path, "python --version")
        log_path = log_operator_action(project_path, "run_safe_command", result)
    except Exception as e:
        log_path = log_operator_action(
            project_path,
            "run_safe_command_error",
            {"error": str(e)}
        )

    return log_path