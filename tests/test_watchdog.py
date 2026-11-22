"""The page watchdog (task 01/2.5; D2, R28)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import scanscribe
from scanscribe import PageImage, PageSource

from scanscribe_mcp.jobs import JobState, Step
from scanscribe_mcp.ocr_service import ServiceStuckError

from .fakes import FakeClock, FakeEngineFactory, make_pages
from .service_helpers import running_service, wait_for, wait_until


def test_a_hung_page_fails_the_job_and_refuses_new_ones(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)
    clock = FakeClock()
    release = threading.Event()
    stuck_calls: list[bool] = []
    factory = FakeEngineFactory(hooks={2: lambda: release.wait(10) and None})
    with running_service(
        factory,
        clock=clock,
        watchdog_interval_s=0.01,
        on_stuck=lambda: stuck_calls.append(True),
    ) as service:
        job_id = service.start_job(input_path=str(folder)).id
        wait_until(service, job_id, Step.RECOGNIZING, page=2)
        queued_id = service.start_job(input_path=str(folder)).id
        clock.advance(600)
        time.sleep(0.1)
        assert service.get_job(job_id).state is JobState.RUNNING  # not past the timeout yet
        clock.advance(1)
        job = wait_for(service, job_id)
        assert job.state is JobState.FAILED
        assert job.error is not None
        assert "page 2" in job.error and "600 s" in job.error and "PAGE_TIMEOUT_S" in job.error
        assert service.stuck and stuck_calls == [True]
        queued = service.get_job(queued_id)
        assert queued.state is JobState.FAILED and queued.error is not None
        assert "restart the server" in queued.error
        with pytest.raises(ServiceStuckError, match="restart the server"):
            service.start_job(input_path=str(folder))
        release.set()  # the engine comes back late: the job stays failed
        time.sleep(0.1)
        assert service.get_job(job_id).error == job.error
        engine = factory.last
    assert engine is not None and len(engine.seen) == 2


def test_watchdog_ignores_a_job_that_is_not_recognizing(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    clock = FakeClock()
    entered, release = threading.Event(), threading.Event()

    def slow_load() -> None:
        entered.set()
        release.wait(10)

    with running_service(
        FakeEngineFactory(on_load=slow_load), clock=clock, watchdog_interval_s=60
    ) as service:
        job_id = service.start_job(input_path=str(folder)).id
        assert entered.wait(10)
        clock.advance(10_000)
        assert service.check_watchdog() is False
        release.set()
        assert wait_for(service, job_id).state is JobState.SUCCEEDED
        assert not service.stuck


class _SlowFirstRender(PageSource):
    """Wraps a real source; images() blocks before yielding page 1, as a hung pdfium would."""

    def __init__(self, inner: PageSource, release: threading.Event) -> None:
        self.inner = inner
        self.path = inner.path
        self.columns = inner.columns
        self.labels = inner.labels
        self.release = release

    def images(self) -> Iterator[PageImage]:
        self.release.wait(10)
        yield from self.inner.images()

    def close(self) -> None:
        self.inner.close()


def test_a_hung_first_render_trips_the_watchdog(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    clock = FakeClock()
    release = threading.Event()

    def opener(path: Path, dpi: int, columns: int) -> PageSource:
        return _SlowFirstRender(scanscribe.open_source(path, dpi, columns), release)

    try:
        with running_service(clock=clock, open_source=opener, watchdog_interval_s=0.01) as service:
            job_id = service.start_job(input_path=str(folder)).id
            wait_until(service, job_id, Step.RECOGNIZING)
            clock.advance(601)
            job = wait_for(service, job_id)
            assert job.state is JobState.FAILED and service.stuck
            assert job.error is not None and "page 1" in job.error and "600 s" in job.error
    finally:
        release.set()


def test_a_hung_pre_check_trips_the_watchdog(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    clock = FakeClock()
    entered, release = threading.Event(), threading.Event()

    def opener(path: Path, dpi: int, columns: int) -> PageSource:
        entered.set()
        release.wait(10)
        return scanscribe.open_source(path, dpi, columns)

    factory = FakeEngineFactory()
    try:
        with running_service(
            factory, clock=clock, open_source=opener, watchdog_interval_s=0.01
        ) as service:
            job_id = service.start_job(input_path=str(folder)).id
            assert entered.wait(10)
            clock.advance(600)
            time.sleep(0.1)
            assert service.get_job(job_id).state is JobState.RUNNING
            clock.advance(1)
            job = wait_for(service, job_id)
            assert job.state is JobState.FAILED and service.stuck
            assert job.error is not None
            assert "checking the pages" in job.error and "PAGE_TIMEOUT_S" in job.error
            release.set()
            time.sleep(0.1)
            assert factory.calls == []  # the late pre-check doesn't go on to the engine
    finally:
        release.set()
