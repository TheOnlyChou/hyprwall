"""
Core business logic for hyprwall.

This module is UI-agnostic and can be used by both CLI and GUI.
"""

from hyprwall.core import (
    detect,
    hypr,
    optimize,
    paths,
    policy,
    power,
    runner,
    session,
)

__all__ = [
    "detect",
    "hypr",
    "optimize",
    "paths",
    "policy",
    "power",
    "runner",
    "session",
]