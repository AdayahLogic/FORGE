"""
Execution package approval actions facade.

Centralizes approval-stage package actions so command/UI layers can integrate with
one governed surface without changing registry lifecycle internals.
"""

from __future__ import annotations

from typing import Any

from NEXUS.execution_package_registry import (
    record_execution_package_decision_safe,
    record_execution_package_eligibility_safe,
    record_execution_package_execution_safe,
    record_execution_package_handoff_safe,
    record_execution_package_release_safe,
)


def record_execution_decision_safe(**kwargs: Any) -> dict[str, Any]:
    return record_execution_package_decision_safe(**kwargs)


def record_execution_eligibility_safe(**kwargs: Any) -> dict[str, Any]:
    return record_execution_package_eligibility_safe(**kwargs)


def record_execution_release_safe(**kwargs: Any) -> dict[str, Any]:
    return record_execution_package_release_safe(**kwargs)


def record_execution_handoff_safe(**kwargs: Any) -> dict[str, Any]:
    return record_execution_package_handoff_safe(**kwargs)


def record_execution_request_safe(**kwargs: Any) -> dict[str, Any]:
    return record_execution_package_execution_safe(**kwargs)
