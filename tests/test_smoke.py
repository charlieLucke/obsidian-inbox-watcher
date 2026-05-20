"""Smoke test for the package."""

from __future__ import annotations

import obsidian_inbox_watcher.main


def test_import() -> None:
    """Confirm the package and its main module can be imported."""
    assert obsidian_inbox_watcher.main is not None
