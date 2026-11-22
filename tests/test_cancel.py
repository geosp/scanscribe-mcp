"""Cancelling jobs at their next check (task 01/2.3; D4, R10)."""

from __future__ import annotations

import threading
from pathlib import Path

import scanscribe
from scanscribe import PageSource

from scanscribe_mcp.jobs import JobState, Step

from .fakes import FakeEngineFactory, make_pages
from .service_helpers import running_service, wait_for, wait_until


def test_cancel_while_recognizing_stops_before_the_next_page(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 5)
    release = threading.Event()
    factory = FakeEngineFactory(hooks={3: lambda: release.wait(10) and None})
    with running_service(factory) as service:
        job_id = service.start_job(input_path=str(folder)).id
        wait_until(service, job_id, Step.RECOGNIZING, page=3)
        job, changed = service.cancel_job(job_id)
        assert changed and job.state is JobState.RUNNING
        release.set()
        job = wait_for(service, job_id)
        engine = factory.last
    assert job.state is JobState.CANCELLED
    assert engine is not None and len(engine.seen) == 3


def test_cancel_during_the_pre_check_stops_before_the_engine(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    entered, release = threading.Event(), threading.Event()

    def slow_open(path: Path, dpi: int, columns: int) -> PageSource:
        entered.set()
        release.wait(10)
        return scanscribe.open_source(path, dpi, columns)

    factory = FakeEngineFactory()
    with running_service(factory, open_source=slow_open) as service:
        job_id = service.start_job(input_path=str(folder)).id
        assert entered.wait(10)
        assert service.get_job(job_id).step is Step.CHECKING_PAGES
        service.cancel_job(job_id)
        release.set()
        job = wait_for(service, job_id)
    assert job.state is JobState.CANCELLED
    assert factory.calls == []


def test_cancel_during_the_engine_load_stops_before_page_one(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    entered, release = threading.Event(), threading.Event()

    def slow_load() -> None:
        entered.set()
        release.wait(10)

    factory = FakeEngineFactory(on_load=slow_load)
    with running_service(factory) as service:
        job_id = service.start_job(input_path=str(folder)).id
        assert entered.wait(10)
        assert service.get_job(job_id).step is Step.LOADING_ENGINE
        service.cancel_job(job_id)
        release.set()
        job = wait_for(service, job_id)
        engine = factory.last
    assert job.state is JobState.CANCELLED
    assert engine is not None and engine.seen == []


def test_cancel_a_queued_job_at_once(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    release = threading.Event()
    factory = FakeEngineFactory(hooks={1: lambda: release.wait(10) and None})
    with running_service(factory) as service:
        first = service.start_job(input_path=str(folder)).id
        wait_until(service, first, Step.RECOGNIZING, page=1)
        second = service.start_job(input_path=str(folder)).id
        job, changed = service.cancel_job(second)
        assert changed and job.state is JobState.CANCELLED
        release.set()
        assert wait_for(service, first).state is JobState.SUCCEEDED
        third = wait_for(service, service.start_job(input_path=str(folder)).id)
        engine = factory.last
    assert third.state is JobState.SUCCEEDED
    assert engine is not None and len(engine.seen) == 2  # the first and third jobs only


def test_cancel_a_succeeded_job_leaves_it(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    with running_service() as service:
        job_id = service.start_job(input_path=str(folder)).id
        wait_for(service, job_id)
        job, changed = service.cancel_job(job_id)
    assert not changed and job.state is JobState.SUCCEEDED
