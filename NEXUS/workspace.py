from pathlib import Path
from datetime import datetime


SAFE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".ini", ".cfg", ".env.example"
}

ENTRYPOINT_CANDIDATES = {
    "main.py", "app.py", "bot.py", "server.py", "index.js", "index.ts",
    "manage.py", "run.py", "cli.py"
}


def scan_workspace(project_path: str, max_files: int = 200) -> dict:
    base_path = Path(project_path)

    if not base_path.exists():
        return {
            "error": f"Project path does not exist: {project_path}"
        }

    all_files = []
    language_counts = {}
    entrypoints = []
    sampled_files = []

    for path in base_path.rglob("*"):
        if len(all_files) >= max_files:
            break

        if path.is_file():
            rel = str(path.relative_to(base_path))
            all_files.append(rel)

            suffix = path.suffix.lower()
            if suffix:
                language_counts[suffix] = language_counts.get(suffix, 0) + 1

            if path.name.lower() in ENTRYPOINT_CANDIDATES:
                entrypoints.append(rel)

            if suffix in SAFE_EXTENSIONS and len(sampled_files) < 12:
                sampled_files.append(rel)

    top_level_dirs = []
    for item in base_path.iterdir():
        if item.is_dir():
            top_level_dirs.append(item.name)

    top_level_dirs.sort()
    entrypoints.sort()
    sampled_files.sort()

    return {
        "project_path": project_path,
        "top_level_dirs": top_level_dirs,
        "file_count_scanned": len(all_files),
        "language_counts": language_counts,
        "entrypoints": entrypoints,
        "sampled_files": sampled_files,
    }


def read_safe_file_snippet(project_path: str, relative_file_path: str, max_chars: int = 1200) -> str:
    base_path = Path(project_path)
    file_path = base_path / relative_file_path

    if not file_path.exists() or not file_path.is_file():
        return f"[Missing file: {relative_file_path}]"

    if file_path.suffix.lower() not in SAFE_EXTENSIONS:
        return f"[Skipped unsupported file type: {relative_file_path}]"

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars].strip() or "[Empty file]"
    except Exception as e:
        return f"[Error reading {relative_file_path}: {e}]"


def write_workspace_report(project_path: str, project_name: str, scan_data: dict) -> str:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)

    report_file = generated_path / "workspace_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "Workspace Intelligence Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
    ]

    if "error" in scan_data:
        lines.append(f"Error: {scan_data['error']}")
        report_file.write_text("\n".join(lines), encoding="utf-8")
        return str(report_file)

    lines.extend([
        "Top-Level Directories:",
    ])
    for d in scan_data.get("top_level_dirs", []):
        lines.append(f"- {d}")

    lines.extend([
        "",
        f"Files Scanned: {scan_data.get('file_count_scanned', 0)}",
        "",
        "Detected File Types:",
    ])
    for ext, count in sorted(scan_data.get("language_counts", {}).items()):
        lines.append(f"- {ext}: {count}")

    lines.extend([
        "",
        "Entrypoint Candidates:",
    ])
    entrypoints = scan_data.get("entrypoints", [])
    if entrypoints:
        for ep in entrypoints:
            lines.append(f"- {ep}")
    else:
        lines.append("[No obvious entrypoints found]")

    lines.extend([
        "",
        "Sampled Files:",
    ])
    sampled = scan_data.get("sampled_files", [])
    if sampled:
        for sf in sampled:
            lines.append(f"- {sf}")
    else:
        lines.append("[No sampled files found]")

    lines.extend([
        "",
        "Sample File Snippets:",
    ])

    for sf in sampled[:5]:
        snippet = read_safe_file_snippet(project_path, sf)
        lines.extend([
            f"--- {sf} ---",
            snippet,
            "",
        ])

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)