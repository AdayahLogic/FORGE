import json
import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

# Load repo-root .env as early as possible (directory containing NEXUS, projects, requirements.txt)
_repo_root = Path(__file__).resolve().parent.parent
_dotenv_path = (_repo_root / ".env").resolve()
load_dotenv(_dotenv_path)
print("[Config] .env loaded from", _dotenv_path)
print("[Config] OPENAI_API_KEY detected: yes" if os.environ.get("OPENAI_API_KEY") else "[Config] OPENAI_API_KEY detected: no")

warnings.filterwarnings("ignore")

from NEXUS.workflow import build_workflow
from NEXUS.state import StudioState
from NEXUS.command_surface import SUPPORTED_COMMANDS, run_command


def run_studio(user_input: str):
    workflow = build_workflow()

    state = StudioState(
        user_input=user_input
    )

    result = workflow.invoke(state)

    print("\n=== WORKFLOW COMPLETE ===")
    print("Active Project:", result["active_project"])
    print("Project Path:", result["project_path"])
    print("Agents Used:", result["active_agents"])
    print("Notes:", result["notes"])
    print("Coder Output Path:", result.get("coder_output_path"))
    print("Implementation File Path:", result.get("implementation_file_path"))
    print("Test Report Path:", result.get("test_report_path"))
    print("Docs Output Path:", result.get("docs_output_path"))
    print("Execution Report Path:", result.get("execution_report_path"))
    print("Workspace Report Path:", result.get("workspace_report_path"))
    print("Operator Log Path:", result.get("operator_log_path"))
    print("Supervisor Report Path:", result.get("supervisor_report_path"))
    print("Studio Supervisor Report Path:", result.get("studio_supervisor_report_path"))
    print("Autonomous Cycle Report Path:", result.get("autonomous_cycle_report_path"))
    print("Computer Use Report Path:", result.get("computer_use_report_path"))
    print("Tool Execution Report Path:", result.get("tool_execution_report_path"))
    print("Terminal Report Path:", result.get("terminal_report_path"))
    print("Browser Research Report Path:", result.get("browser_research_report_path"))
    print("File Modification Report Path:", result.get("file_modification_report_path"))
    print("Diff Patch Report Path:", result.get("diff_patch_report_path"))
    print("Full Automation Report Path:", result.get("full_automation_report_path"))
    print("Persistent State Path:", result.get("persistent_state_path"))

    print("\n=== SUPERVISOR DECISION ===")
    decision = result.get("supervisor_decision", {})
    if decision:
        for key, value in decision.items():
            print(f"{key}: {value}")
    else:
        print("[No supervisor decision]")

    print("\n=== STUDIO SUPERVISOR SUMMARY ===")
    summary = result.get("studio_supervisor_summary", [])
    if summary:
        for item in summary:
            print(
                f"- {item['project_name']} | "
                f"has_state={item['has_state']} | "
                f"completed={item['completed_tasks']} | "
                f"pending={item['pending_tasks']} | "
                f"action={item['recommended_action']}"
            )
    else:
        print("[No studio supervisor summary]")

    print("\n=== AUTONOMOUS CYCLE SUMMARY ===")
    cycle = result.get("autonomous_cycle_summary", {})
    if cycle:
        for key, value in cycle.items():
            print(f"{key}: {value}")
    else:
        print("[No autonomous cycle summary]")

    print("\n=== COMPUTER USE SUMMARY ===")
    computer = result.get("computer_use_summary", {})
    if computer:
        for key, value in computer.items():
            if key == "actions":
                print("actions:")
                for action in value:
                    print(" -", action)
            else:
                print(f"{key}: {value}")
    else:
        print("[No computer use summary]")

    print("\n=== TOOL EXECUTION SUMMARY ===")
    tools = result.get("tool_execution_summary", {})
    if tools:
        for key, value in tools.items():
            print(f"{key}: {value}")
    else:
        print("[No tool execution summary]")

    print("\n=== TERMINAL SUMMARY ===")
    terminal = result.get("terminal_summary", {})
    if terminal:
        for key, value in terminal.items():
            print(f"{key}: {value}")
    else:
        print("[No terminal summary]")

    print("\n=== BROWSER RESEARCH SUMMARY ===")
    browser = result.get("browser_research_summary", {})
    if browser:
        for key, value in browser.items():
            print(f"{key}: {value}")
    else:
        print("[No browser research summary]")

    print("\n=== FILE MODIFICATION SUMMARY ===")
    file_mod = result.get("file_modification_summary", {})
    if file_mod:
        for key, value in file_mod.items():
            print(f"{key}: {value}")
    else:
        print("[No file modification summary]")

    print("\n=== DIFF PATCH SUMMARY ===")
    patch = result.get("diff_patch_summary", {})
    if patch:
        for key, value in patch.items():
            print(f"{key}: {value}")
    else:
        print("[No diff patch summary]")

    print("\n=== FULL AUTOMATION SUMMARY ===")
    full_auto = result.get("full_automation_summary", {})
    if full_auto:
        for key, value in full_auto.items():
            print(f"{key}: {value}")
    else:
        print("[No full automation summary]")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0].strip().lower() in SUPPORTED_COMMANDS:
        cmd = args[0].strip().lower()
        project_name = None
        n = 20
        tail = None
        i = 1
        agent_name = None
        tool_name = None
        action_type = None
        task_type = None
        sensitivity = None
        review_context = None
        completion_type = None
        while i < len(args):
            if args[i] == "--project" and i + 1 < len(args):
                project_name = args[i + 1]
                i += 2
                continue
            if args[i] == "-n" and i + 1 < len(args):
                try:
                    n = int(args[i + 1])
                except ValueError:
                    n = 20
                i += 2
                continue
            if args[i] == "--agent" and i + 1 < len(args):
                agent_name = args[i + 1]
                i += 2
                continue
            if args[i] == "--tool" and i + 1 < len(args):
                tool_name = args[i + 1]
                i += 2
                continue
            if args[i] == "--action" and i + 1 < len(args):
                action_type = args[i + 1]
                i += 2
                continue
            if args[i] == "--task" and i + 1 < len(args):
                task_type = args[i + 1]
                i += 2
                continue
            if args[i] == "--sensitivity" and i + 1 < len(args):
                sensitivity = args[i + 1]
                i += 2
                continue
            if args[i] == "--review-context" and i + 1 < len(args):
                review_context = args[i + 1]
                i += 2
                continue
            if args[i] == "--type" and i + 1 < len(args):
                completion_type = args[i + 1]
                i += 2
                continue
            if args[i] == "--tail" and i + 1 < len(args):
                try:
                    tail = int(args[i + 1])
                except Exception:
                    tail = None
                i += 2
                continue
            i += 1
        result = run_command(
            command=cmd,
            project_name=project_name,
            n=n,
            tail=tail,
            agent_name=agent_name,
            tool_name=tool_name,
            action_type=action_type,
            task_type=task_type,
            sensitivity=sensitivity,
            review_context=review_context,
            completion_type=completion_type,
        )
        print(json.dumps(result, indent=2))
    else:
        user_prompt = input("Enter project request: ")
        run_studio(user_prompt)