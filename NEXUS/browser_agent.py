import webbrowser
from pathlib import Path
from datetime import datetime


SAFE_RESEARCH_URLS = [
    "https://platform.openai.com/docs",
    "https://github.com",
    "https://langchain.com",
    "https://langchain-ai.github.io/langgraph/",
]


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def open_safe_research_urls(max_urls: int = 2) -> dict:
    actions = []
    launched = 0

    for url in SAFE_RESEARCH_URLS[:max_urls]:
        try:
            webbrowser.open(url)
            actions.append({
                "url": url,
                "status": "launched",
            })
            launched += 1
        except Exception as e:
            actions.append({
                "url": url,
                "status": "error",
                "reason": str(e),
            })

    return {
        "urls_considered": min(max_urls, len(SAFE_RESEARCH_URLS)),
        "urls_launched": launched,
        "actions": actions,
    }


def write_browser_research_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "browser_research_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Browser Research Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Summary:",
        f"- urls_considered: {summary.get('urls_considered')}",
        f"- urls_launched: {summary.get('urls_launched')}",
        "",
        "Actions:",
    ]

    for action in summary.get("actions", []):
        lines.append(f"- url: {action.get('url')}")
        lines.append(f"  status: {action.get('status')}")
        lines.append(f"  reason: {action.get('reason', '[none]')}")
        lines.append("")

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)