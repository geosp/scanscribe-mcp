"""The session-end check that the tests never import paddle or paddleocr (task 01/4.1, R24)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from .paddle_guard import imported_engine_modules

ROOT = Path(__file__).resolve().parent.parent
CONFTEST = "from tests.paddle_guard import pytest_sessionfinish  # noqa: F401\n"


def run_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, test_body: str
) -> pytest.RunResult:
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_it=test_body)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    return pytester.runpytest_subprocess("-p", "no:cacheprovider")


def test_guard_fails_a_session_that_imports_paddle(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_session(
        pytester,
        monkeypatch,
        "import sys, types\n\n"
        "def test_imports_paddle():\n"
        "    sys.modules['paddle'] = types.ModuleType('paddle')\n",
    )
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*R24: the tests imported the OCR engine: paddle*"])


def test_guard_passes_a_clean_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_session(
        pytester, monkeypatch, "import scanscribe\n\ndef test_clean():\n    pass\n"
    )
    assert result.ret == pytest.ExitCode.OK


def test_this_session_has_not_imported_the_engine() -> None:
    assert imported_engine_modules() == []
    assert "scanscribe.paddle_engine" not in sys.modules
