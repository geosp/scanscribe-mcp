"""Shared test setup: a clean environment for configuration."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No SCANSCRIBE_MCP_* or MCP_* variable from the developer's shell reaches a test."""
    for name in list(os.environ):
        if name.startswith(("SCANSCRIBE_MCP_", "MCP_")):
            monkeypatch.delenv(name)
