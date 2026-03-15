from pathlib import Path


def read_text_files_from_folder(folder_path: Path) -> str:
    if not folder_path.exists() or not folder_path.is_dir():
        return f"[Missing folder: {folder_path}]"

    contents = []

    for file_path in sorted(folder_path.glob("*.txt")):
        try:
            text = file_path.read_text(encoding="utf-8").strip()
            contents.append(f"--- {file_path.name} ---\n{text}")
        except Exception as e:
            contents.append(f"--- {file_path.name} ---\n[Error reading file: {e}]")

    if not contents:
        return f"[No .txt files found in {folder_path}]"

    return "\n\n".join(contents)


def load_project_context(project_path: str) -> dict:
    base_path = Path(project_path)

    docs_path = base_path / "docs"
    memory_path = base_path / "memory"
    tasks_path = base_path / "tasks"

    return {
        "docs": read_text_files_from_folder(docs_path),
        "memory": read_text_files_from_folder(memory_path),
        "tasks": read_text_files_from_folder(tasks_path),
    }