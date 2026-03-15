from NEXUS.studio_config import PROJECT_ALIASES


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def detect_project(user_input: str) -> str:
    """
    Detect which logical project the user intends.

    IMPORTANT:
    - Returns logical project keys, not physical folder names.
    - Supports legacy aliases during rename transition.
    - Defaults to 'jarvis' for product-level ambiguity.
      The core system remains NEXUS conceptually and is not treated as a product.
    """
    text = _normalize_text(user_input)

    if not text:
        return "jarvis"

    # Check aliases
    for logical_project_key, aliases in PROJECT_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return logical_project_key

    # Heuristic routing
    if any(word in text for word in ["negotiate", "communication", "message", "reply", "email"]):
        return "paragon"

    if any(word in text for word in ["trade", "trading", "bot", "market", "exchange", "crypto"]):
        return "vector"

    if any(word in text for word in ["world", "environment", "generator", "terrain"]):
        return "genesis"

    if any(word in text for word in ["civilization", "simulation", "future", "society"]):
        return "epoch"

    if any(word in text for word in ["rpg", "quest", "combat", "character"]):
        return "rpg_project"

    if any(word in text for word in ["game", "game dev", "mechanic", "level", "multiplayer"]):
        return "game_dev"

    if any(word in text for word in ["jarvis", "assistant", "operator", "personal ai"]):
        return "jarvis"

    # Safe fallback:
    # Use Jarvis as the default product workspace during this transition.
    # Do NOT use "nexus" as a product key anymore.
    return "jarvis"