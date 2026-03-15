EXECUTION_TARGETS = {
    "coder": {
        "primary_tool": "cursor_agent",
        "secondary_tool": "codex",
        "human_review_required": True,
        "purpose": "Repository-aware implementation and code changes.",
        "cursor_usage": "Use Cursor agent to modify files inside the repo with narrow scope.",
        "codex_usage": "Use Codex for function generation, refactors, or repetitive code patterns.",
    },
    "tester": {
        "primary_tool": "cursor_terminal",
        "secondary_tool": "codex",
        "human_review_required": True,
        "purpose": "Testing, validation, and failure isolation.",
        "cursor_usage": "Use Cursor terminal for running tests and debugging commands.",
        "codex_usage": "Use Codex for generating tests or small test helpers.",
    },
    "docs": {
        "primary_tool": "cursor_agent",
        "secondary_tool": "codex",
        "human_review_required": True,
        "purpose": "Documentation and repo knowledge updates.",
        "cursor_usage": "Use Cursor agent to update markdown, reports, and repo docs.",
        "codex_usage": "Use Codex for drafting structured docs or repetitive documentation text.",
    },
}

DEFAULT_EXECUTION_TARGET = {
    "primary_tool": "human_supervisor",
    "secondary_tool": None,
    "human_review_required": True,
    "purpose": "Fallback execution target.",
    "cursor_usage": "Human should review and decide the next safe action.",
    "codex_usage": "Do not use Codex automatically for unknown routing targets.",
}