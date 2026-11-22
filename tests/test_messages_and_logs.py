"""Error messages without server paths, and logs without book material (task 01/2.4).

D11, R22, R26.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scanscribe_mcp.jobs import JobState

from .fakes import FakeEngineFactory, make_pages, make_pdf
from .service_helpers import running_service, wait_for

SECRET = "very-private-detail"


def all_log_text(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        f"{record.name} {record.getMessage()} {record.exc_text or ''}" for record in caplog.records
    )


def test_logs_of_a_failing_job_hold_no_name_message_or_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    pdf = make_pdf(tmp_path / "chapter-3.pdf", 3)

    def boom() -> None:
        raise RuntimeError(f"{SECRET} while reading {pdf}")

    factory = FakeEngineFactory(hooks={2: boom}, lines_per_page=3)
    with running_service(factory) as service:
        failed = wait_for(service, service.start_job(input_path=str(pdf), dpi=72).id)
        factory.hooks = None
        ok = wait_for(service, service.start_job(input_path=str(pdf), dpi=72).id)
        cancelled_id = service.start_job(input_path=str(pdf), dpi=72).id
        service.cancel_job(cancelled_id)
        wait_for(service, cancelled_id)
    assert failed.state is JobState.FAILED and ok.state is JobState.SUCCEEDED
    assert failed.error == "OCR failed (RuntimeError)"
    logs = all_log_text(caplog)
    assert failed.id in logs and "RuntimeError" in logs
    for forbidden in ("chapter-3", SECRET, str(tmp_path), "line 2 of page", "gray "):
        assert forbidden not in logs


def test_unreadable_page_names_the_page_as_the_caller_gave_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    folder = make_pages(tmp_path / "my-scan-folder", 3)
    (folder / "p2.png").write_bytes(b"this is not an image")
    monkeypatch.chdir(tmp_path)
    with running_service() as service:
        job = wait_for(service, service.start_job(input_path="my-scan-folder").id)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "my-scan-folder/p2.png" in job.error
    assert str(tmp_path) not in job.error
    assert "p2.png" not in all_log_text(caplog) and "my-scan-folder" not in all_log_text(caplog)


def test_unexpected_error_text_is_hidden(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)

    def boom() -> None:
        raise RuntimeError("/tmp/server-only/work/abc/p1.png exploded")

    with running_service(FakeEngineFactory(hooks={1: boom})) as service:
        job = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert job.error == "OCR failed (RuntimeError)"


def test_engine_load_error_is_hidden(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    factory = FakeEngineFactory(error=OSError(f"cannot write {tmp_path}/.paddlex/model"))
    with running_service(factory) as service:
        job = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert job.error == "OCR failed (OSError)"
