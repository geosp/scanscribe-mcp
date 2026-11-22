"""The job table and queue (task 01/2.1; R5, R6, R7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scanscribe_mcp.jobs import (
    JobInput,
    JobState,
    JobTable,
    OcrOptions,
    QueueFullError,
    UnknownJobError,
)

from .fakes import FakeClock

OPTIONS = OcrOptions(lang="en", dpi=200, columns=1)
INPUT = JobInput(kind="input_path", path=Path("/nowhere/book.pdf"), name="book.pdf")


def make_table(clock: FakeClock, max_queued: int = 20) -> JobTable:
    return JobTable(max_queued=max_queued, queue_timeout_s=3600, retention_s=86400, clock=clock)


def test_jobs_run_in_order() -> None:
    table = make_table(FakeClock())
    ids = [table.submit(INPUT, OPTIONS).id for _ in range(3)]
    first = table.next_job(timeout=0)
    assert first is not None and first.id == ids[0] and first.state is JobState.RUNNING
    assert table.get(ids[1]).state is JobState.QUEUED
    table.finish(ids[0], JobState.SUCCEEDED, pages=[["a"]])
    assert [table.next_job(timeout=0).id for _ in range(2)] == ids[1:]  # type: ignore[union-attr]


def test_twenty_first_job_refused() -> None:
    table = make_table(FakeClock())
    for _ in range(20):
        table.submit(INPUT, OPTIONS)
    with pytest.raises(QueueFullError, match="20 jobs waiting"):
        table.submit(INPUT, OPTIONS)
    assert table.counts()[JobState.QUEUED] == 20


def test_cancelled_jobs_do_not_count() -> None:
    table = make_table(FakeClock())
    for _ in range(20):
        table.cancel(table.submit(INPUT, OPTIONS).id)
    assert table.submit(INPUT, OPTIONS).state is JobState.QUEUED


def test_expired_jobs_do_not_count() -> None:
    clock = FakeClock()
    table = make_table(clock)
    for _ in range(20):
        table.submit(INPUT, OPTIONS)
    clock.advance(3601)
    assert table.submit(INPUT, OPTIONS).state is JobState.QUEUED


def test_expiry_on_read() -> None:
    clock = FakeClock()
    table = make_table(clock)
    job = table.submit(INPUT, OPTIONS)
    clock.advance(3600)
    assert table.get(job.id).state is JobState.QUEUED
    clock.advance(1)
    expired = table.get(job.id)
    assert expired.state is JobState.EXPIRED
    assert expired.error is not None and "3600 s" in expired.error


def test_worker_skips_cancelled_and_expired() -> None:
    clock = FakeClock()
    table = make_table(clock)
    old = table.submit(INPUT, OPTIONS)
    clock.advance(3000)
    cancelled = table.submit(INPUT, OPTIONS)
    live = table.submit(INPUT, OPTIONS)
    table.cancel(cancelled.id)
    clock.advance(601)  # `old` is now past the queue timeout, `live` isn't
    job = table.next_job(timeout=0)
    assert job is not None and job.id == live.id
    assert table.next_job(timeout=0) is None
    assert table.get(old.id).state is JobState.EXPIRED
    assert table.get(cancelled.id).state is JobState.CANCELLED


def test_finished_jobs_are_purged_after_retention() -> None:
    clock = FakeClock()
    table = make_table(clock)
    job = table.submit(INPUT, OPTIONS)
    table.next_job(timeout=0)
    table.finish(job.id, JobState.SUCCEEDED, pages=[])
    clock.advance(86400)
    assert table.get(job.id).state is JobState.SUCCEEDED
    clock.advance(1)
    with pytest.raises(UnknownJobError):
        table.get(job.id)


def test_running_job_is_not_purged_or_expired() -> None:
    clock = FakeClock()
    table = make_table(clock)
    job = table.submit(INPUT, OPTIONS)
    table.next_job(timeout=0)
    clock.advance(10**6)
    assert table.get(job.id).state is JobState.RUNNING


def test_cancel_running_sets_flag_and_finished_stays() -> None:
    table = make_table(FakeClock())
    job = table.submit(INPUT, OPTIONS)
    table.next_job(timeout=0)
    copy, changed = table.cancel(job.id)
    assert changed and copy.state is JobState.RUNNING and table.cancel_requested(job.id)
    table.finish(job.id, JobState.CANCELLED)
    copy, changed = table.cancel(job.id)
    assert not changed and copy.state is JobState.CANCELLED


def test_updates_after_leaving_running_are_ignored() -> None:
    table = make_table(FakeClock())
    job = table.submit(INPUT, OPTIONS)
    table.next_job(timeout=0)
    assert table.finish(job.id, JobState.FAILED, error="watchdog")
    assert not table.update(job.id, page=3)
    assert not table.finish(job.id, JobState.SUCCEEDED, pages=[])
    assert table.get(job.id).error == "watchdog"


def test_copies_do_not_alias() -> None:
    table = make_table(FakeClock())
    job = table.submit(INPUT, OPTIONS)
    job.state = JobState.FAILED
    assert table.get(job.id).state is JobState.QUEUED


def test_stop_wakes_the_worker() -> None:
    table = make_table(FakeClock())
    table.stop()
    assert table.next_job() is None
