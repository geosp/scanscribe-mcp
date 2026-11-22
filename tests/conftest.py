"""Shared test setup: a clean environment, and the check that no test imports the engine.

The fake engine and the fixture builders are in fakes.py.
"""

from __future__ import annotations

import os

import pytest

from .paddle_guard import pytest_sessionfinish  # noqa: F401  (a hook: pytest finds it by name)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No SCANSCRIBE_MCP_* or MCP_* variable from the developer's shell reaches a test."""
    for name in list(os.environ):
        if name.startswith(("SCANSCRIBE_MCP_", "MCP_")):
            monkeypatch.delenv(name)
