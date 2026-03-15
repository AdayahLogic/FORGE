import json
import re


def extract_json_object(raw_text: str) -> str:
    """
    Best-effort extraction of a JSON object from model output.

    Handles:
    - raw JSON
    - markdown fenced blocks
    - extra text before/after JSON

    Raises ValueError if no JSON object can be found.
    """
    text = (raw_text or "").strip()

    if not text:
        raise ValueError("Empty model output.")

    # Remove common markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())

    # Fast path: already valid JSON object text
    if text.startswith("{") and text.endswith("}"):
        return text

    # Best-effort substring extraction from first { to last }
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")

    candidate = text[start:end + 1].strip()

    # Validate candidate is actually JSON-like enough to try
    if not candidate.startswith("{") or not candidate.endswith("}"):
        raise ValueError("Extracted JSON candidate is invalid.")

    return candidate


def parse_json_object(raw_text: str) -> dict:
    """
    Extract and parse a JSON object from model output.
    """
    candidate = extract_json_object(raw_text)
    parsed = json.loads(candidate)

    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object.")

    return parsed