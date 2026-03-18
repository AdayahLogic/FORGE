"""
Elite capability layers for the Forge OS layer.

Internal implementation modules use lowercase, Pythonic filenames.
External identity is exposed via uppercase aliases exported from this package.
"""

from __future__ import annotations

from elite_layers.titan import build_titan_summary_safe as TITAN
from elite_layers.leviathan import build_leviathan_summary_safe as LEVIATHAN
from elite_layers.helios import build_helios_summary_safe as HELIOS
from elite_layers.veritas import build_veritas_summary_safe as VERITAS
from elite_layers.sentinel import build_sentinel_summary_safe as SENTINEL

__all__ = [
    "TITAN",
    "LEVIATHAN",
    "HELIOS",
    "VERITAS",
    "SENTINEL",
]

