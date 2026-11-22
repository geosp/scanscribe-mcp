"""Fail the test session if PaddlePaddle or PaddleOCR was imported (R24).

Tests use the fake engine only, so neither module may ever be in sys.modules. conftest.py
imports the hook from here; test_paddle_guard.py runs it in a separate session.
"""

from __future__ import annotations

import sys

import pytest

ENGINE_MODULES = frozenset({"paddle", "paddleocr"})


def imported_engine_modules() -> list[str]:
    return sorted(name for name in sys.modules if name.split(".")[0] in ENGINE_MODULES)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    found = imported_engine_modules()
    if not found:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    message = f"R24: the tests imported the OCR engine: {', '.join(found)}"
    if reporter is not None:
        reporter.write_line(message, red=True, bold=True)
    else:
        print(message, file=sys.stderr)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
