from pathlib import Path
import re

from core.studio_config import STUDIO_ROOT, LOGICAL_PROJECT_NAMES


def to_studio_relative_path(path_value: str | None) -> str | None:
    """
    Convert an absolute path under the studio root into a relative display path.

    Example:
    C:\\AI_STUDIO\\projects\\nexus\\generated\\coder_output.txt
    ->
    projects\\nexus\\generated\\coder_output.txt

    If the value is missing or not inside the studio root, return it unchanged.
    """
    if not path_value:
        return path_value

    try:
        raw = Path(path_value)
        resolved = raw.resolve()
        studio_root = Path(STUDIO_ROOT).resolve()
        return str(resolved.relative_to(studio_root))
    except Exception:
        return path_value


def normalize_display_data(value):
    """
    Recursively normalize path-like fields for display/storage.

    Rules:
    - dict keys ending in `_path` are normalized
    - dict keys named `target` are normalized
    - nested dicts/lists are handled recursively
    """
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                normalized[key] = normalize_display_data(item)
            elif isinstance(item, str) and (key.endswith("_path") or key == "target"):
                normalized[key] = to_studio_relative_path(item)
            else:
                normalized[key] = item
        return normalized

    if isinstance(value, list):
        return [normalize_display_data(item) for item in value]

    return value


def get_project_display_name(project_name: str | None) -> str:
    """
    Convert a logical project key like 'jarvis' into its display name.
    Falls back safely if the key is unknown.
    """
    if not project_name:
        return "Project"

    lowered = project_name.strip().lower()
    return LOGICAL_PROJECT_NAMES.get(lowered, project_name.title())


def sanitize_identifier(value: str | None) -> str:
    """
    Make a safe Python identifier fragment.
    """
    if not value:
        return "project"

    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if not cleaned:
        return "project"

    if cleaned[0].isdigit():
        cleaned = f"project_{cleaned}"

    return cleaned