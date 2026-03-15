from pathlib import Path
from datetime import datetime
import difflib

from NEXUS.path_utils import normalize_display_data, to_studio_relative_path


SAFE_PATCH_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".ini", ".cfg"
}


def ensure_generated_folder(project_path: str) -> Path:
    base_path = Path(project_path)
    generated_path = base_path / "generated"
    generated_path.mkdir(parents=True, exist_ok=True)
    return generated_path


def ensure_patch_backup_folder(project_path: str) -> Path:
    generated_path = ensure_generated_folder(project_path)
    backup_path = generated_path / "patch_backups"
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def build_patch_request_from_architect_plan(architect_plan: dict | None) -> dict | None:
    """
    Expected shape inside architect_plan:

    {
      "patch_request": {
        "approved": True,
        "target_relative_path": "src/example.py",
        "search_text": "old block",
        "replacement_text": "new block",
        "replace_all": False
      }
    }

    Safety rule:
    If approved=True is not explicitly present, the patch will not apply.
    """
    if not architect_plan or not isinstance(architect_plan, dict):
        return None

    patch_request = architect_plan.get("patch_request")
    if not isinstance(patch_request, dict):
        return None

    return {
        "approved": bool(patch_request.get("approved", False)),
        "target_relative_path": patch_request.get("target_relative_path"),
        "search_text": patch_request.get("search_text"),
        "replacement_text": patch_request.get("replacement_text"),
        "replace_all": bool(patch_request.get("replace_all", False)),
    }


def _resolve_safe_target(project_path: str, target_relative_path: str) -> Path:
    base_path = Path(project_path).resolve()
    target_file = (base_path / target_relative_path).resolve()

    if not str(target_file).startswith(str(base_path)):
        raise ValueError("Blocked path traversal outside project directory.")

    if target_file.suffix.lower() not in SAFE_PATCH_EXTENSIONS:
        raise ValueError(f"Blocked unsupported patch target type: {target_file.suffix}")

    if not target_file.exists() or not target_file.is_file():
        raise FileNotFoundError(f"Patch target does not exist: {target_relative_path}")

    return target_file


def _validate_patch_request(patch_request: dict | None) -> tuple[bool, str]:
    if not patch_request:
        return False, "No patch request provided."

    if not patch_request.get("approved", False):
        return False, "Patch request not approved."

    if not patch_request.get("target_relative_path"):
        return False, "Missing target_relative_path."

    search_text = patch_request.get("search_text")
    replacement_text = patch_request.get("replacement_text")

    if not isinstance(search_text, str) or not search_text.strip():
        return False, "Missing search_text."

    if not isinstance(replacement_text, str):
        return False, "Missing replacement_text."

    if "\x00" in search_text or "\x00" in replacement_text:
        return False, "Blocked null-byte content in patch request."

    if len(search_text) > 20000 or len(replacement_text) > 40000:
        return False, "Patch request too large."

    return True, "Patch request valid."


def apply_safe_patch(
    project_path: str,
    project_name: str,
    patch_request: dict | None
) -> dict:
    """
    Supported operation:
    - exact text replacement
    - replace once by default
    - replace all only when explicitly requested

    Safety features:
    - explicit approval required
    - exact match required
    - ambiguous match blocked unless replace_all=True
    - backup created before write
    - unified diff preview generated
    """
    valid, reason = _validate_patch_request(patch_request)
    if not valid:
        return normalize_display_data({
            "status": "skipped",
            "project_name": project_name,
            "reason": reason,
            "patch_applied": False,
        })

    target_relative_path = patch_request["target_relative_path"]
    search_text = patch_request["search_text"]
    replacement_text = patch_request["replacement_text"]
    replace_all = patch_request.get("replace_all", False)

    target_file = _resolve_safe_target(project_path, target_relative_path)
    original_text = target_file.read_text(encoding="utf-8", errors="ignore")

    match_count = original_text.count(search_text)

    if match_count == 0:
        return normalize_display_data({
            "status": "blocked",
            "project_name": project_name,
            "reason": "search_text not found in target file.",
            "target_path": str(target_file),
            "patch_applied": False,
        })

    if match_count > 1 and not replace_all:
        return normalize_display_data({
            "status": "blocked",
            "project_name": project_name,
            "reason": f"search_text matched {match_count} locations. Refusing ambiguous patch without replace_all=True.",
            "target_path": str(target_file),
            "match_count": match_count,
            "patch_applied": False,
        })

    if replace_all:
        new_text = original_text.replace(search_text, replacement_text)
    else:
        new_text = original_text.replace(search_text, replacement_text, 1)

    if new_text == original_text:
        return normalize_display_data({
            "status": "skipped",
            "project_name": project_name,
            "reason": "Patch produced no file change.",
            "target_path": str(target_file),
            "match_count": match_count,
            "patch_applied": False,
        })

    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ensure_patch_backup_folder(project_path)
    backup_file = backup_dir / f"{target_file.name}.{timestamp_slug}.bak"
    backup_file.write_text(original_text, encoding="utf-8")

    target_file.write_text(new_text, encoding="utf-8")

    diff_lines = list(difflib.unified_diff(
        original_text.splitlines(),
        new_text.splitlines(),
        fromfile=f"before/{target_relative_path}",
        tofile=f"after/{target_relative_path}",
        lineterm=""
    ))
    diff_preview = "\n".join(diff_lines[:200]) if diff_lines else "[no diff preview]"

    summary = {
        "status": "applied",
        "project_name": project_name,
        "reason": "Patch applied successfully.",
        "target_path": str(target_file),
        "backup_path": str(backup_file),
        "match_count": match_count,
        "replace_all": replace_all,
        "bytes_before": len(original_text.encode("utf-8")),
        "bytes_after": len(new_text.encode("utf-8")),
        "search_length": len(search_text),
        "replacement_length": len(replacement_text),
        "patch_applied": True,
        "diff_preview": diff_preview,
    }

    return normalize_display_data(summary)


def write_patch_report(project_path: str, project_name: str, summary: dict) -> str:
    generated_path = ensure_generated_folder(project_path)
    report_file = generated_path / "diff_patch_report.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = normalize_display_data(summary)

    lines = [
        "Diff Patch Report",
        f"Timestamp: {timestamp}",
        f"Project: {project_name}",
        "",
        "Patch Summary:",
        f"- status: {summary.get('status')}",
        f"- reason: {summary.get('reason')}",
        f"- patch_applied: {summary.get('patch_applied')}",
        f"- target_path: {summary.get('target_path', '[none]')}",
        f"- backup_path: {summary.get('backup_path', '[none]')}",
        f"- match_count: {summary.get('match_count', '[none]')}",
        f"- replace_all: {summary.get('replace_all', '[none]')}",
        f"- bytes_before: {summary.get('bytes_before', '[none]')}",
        f"- bytes_after: {summary.get('bytes_after', '[none]')}",
        "",
        "Diff Preview:",
        summary.get("diff_preview", "[none]"),
    ]

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return str(report_file)