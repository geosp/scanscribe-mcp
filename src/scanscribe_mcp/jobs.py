"""Jobs, the job table and the FIFO queue (D2).

The table is shared by the event loop (tools) and the worker thread, so every read and write of a
job goes through its lock. Readers get a copy of the job; only the table changes the real one.
Nothing here imports MCP or scanscribe.
"""

from __future__ import annotations

import dataclasses
import enum
import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Clock = Callable[[], float]


class JobState(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


FINAL_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED}
)


class Step(enum.StrEnum):
    """What a running job is doing, in this order."""

    CHECKING_PAGES = "checking pages"
    LOADING_ENGINE = "loading engine"
    RECOGNIZING = "recognizing"


@dataclass(frozen=True)
class OcrOptions:
    lang: str
    dpi: int
    columns: int


@dataclass(frozen=True)
class JobInput:
    """What a job reads.

    `path` is the server's path and never leaves the server; `name` is the caller's own name for
    the input (the `input_path` as given), used in error messages (D11). `size` is the file size
    in bytes, and `page_count` the number of images when the input is a folder.
    """

    kind: str
    path: Path
    name: str
    size: int | None = None
    page_count: int | None = None


@dataclass
class Job:
    id: str
    input: JobInput
    options: OcrOptions
    created: float
    state: JobState = JobState.QUEUED
    step: Step | None = None
    page: int | None = None
    total: int | None = None
    page_started: float | None = None
    device: str | None = None
    error: str | None = None
    pages: list[list[str]] | None = None
    started: float | None = None
    finished: float | None = None
    cancel_requested: bool = field(default=False, repr=False)

    @property
    def is_final(self) -> bool:
        return self.state in FINAL_STATES


class QueueFullError(ValueError):
    """The queue already holds its limit of queued jobs (R6)."""


class UnknownJobError(ValueError):
    """No job has this id, or it was purged."""


def new_job_id() -> str:
    return uuid.uuid4().hex


class JobTable:
    """Every job by id, the FIFO queue of job ids, and the rules for expiry and retention."""

    def __init__(
        self,
        *,
        max_queued: int,
        queue_timeout_s: float,
        retention_s: float,
        clock: Clock,
    ) -> None:
        self.max_queued = max_queued
        self.queue_timeout_s = queue_timeout_s
        self.retention_s = retention_s
        self.clock = clock
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str | None] = queue.Queue()

    # --- used by the tools -------------------------------------------------------------------

    def submit(self, job_input: JobInput, options: OcrOptions) -> Job:
        """Create a queued job and put it at the end of the queue (R5, R6)."""
        with self._lock:
            self._refresh()
            queued = sum(1 for job in self._jobs.values() if job.state is JobState.QUEUED)
            if queued >= self.max_queued:
                raise QueueFullError(
                    f"the queue is full ({self.max_queued} jobs waiting); try again later"
                )
            job = Job(id=new_job_id(), input=job_input, options=options, created=self.clock())
            self._jobs[job.id] = job
            self._queue.put(job.id)
            return dataclasses.replace(job)

    def get(self, job_id: str) -> Job:
        """A copy of the job, with expiry applied (R7)."""
        with self._lock:
            self._refresh()
            return dataclasses.replace(self._find(job_id))

    def cancel(self, job_id: str) -> tuple[Job, bool]:
        """Cancel a job: a queued one at once, a running one at its next check (R10).

        Returns a copy of the job and whether the cancel changed anything; a finished job is
        left as it is.
        """
        with self._lock:
            self._refresh()
            job = self._find(job_id)
            if job.state is JobState.QUEUED:
                self._finish(job, JobState.CANCELLED)
                return dataclasses.replace(job), True
            if job.state is JobState.RUNNING:
                changed = not job.cancel_requested
                job.cancel_requested = True
                return dataclasses.replace(job), changed
            return dataclasses.replace(job), False

    def counts(self) -> dict[JobState, int]:
        with self._lock:
            self._refresh()
            result = dict.fromkeys(JobState, 0)
            for job in self._jobs.values():
                result[job.state] += 1
            return result

    # --- used by the worker ------------------------------------------------------------------

    def next_job(self, timeout: float | None = None) -> Job | None:
        """Wait for the next queued job, mark it running and return a copy.

        Cancelled and expired entries are skipped. Returns None on `stop()` or after `timeout`.
        """
        while True:
            try:
                job_id = self._queue.get(timeout=timeout)
            except queue.Empty:
                return None
            if job_id is None:
                return None
            with self._lock:
                self._refresh()
                job = self._jobs.get(job_id)
                if job is None or job.state is not JobState.QUEUED:
                    continue
                job.state = JobState.RUNNING
                job.started = self.clock()
                return dataclasses.replace(job)

    def update(self, job_id: str, **changes: object) -> bool:
        """Change fields of a running job. Returns False, changing nothing, once it has left
        `running` (a watchdog may have failed it meanwhile)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not JobState.RUNNING:
                return False
            for name, value in changes.items():
                setattr(job, name, value)
            return True

    def finish(
        self,
        job_id: str,
        state: JobState,
        *,
        error: str | None = None,
        pages: list[list[str]] | None = None,
    ) -> bool:
        """Move a running job to a final state. Returns False if it had already left `running`."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not JobState.RUNNING:
                return False
            job.error = error
            job.pages = pages
            self._finish(job, state)
            return True

    def cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return job is not None and job.cancel_requested

    def running(self) -> Job | None:
        """A copy of the running job, if any."""
        with self._lock:
            for job in self._jobs.values():
                if job.state is JobState.RUNNING:
                    return dataclasses.replace(job)
            return None

    def fail_queued(self, error: str) -> int:
        """Fail every queued job with `error`; returns how many."""
        with self._lock:
            self._refresh()
            queued = [job for job in self._jobs.values() if job.state is JobState.QUEUED]
            for job in queued:
                job.error = error
                self._finish(job, JobState.FAILED)
            return len(queued)

    def stop(self) -> None:
        """Wake the worker so that `next_job` returns None."""
        self._queue.put(None)

    # --- internal ----------------------------------------------------------------------------

    def _find(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise UnknownJobError(f"no job with id {job_id!r}; it may have expired")
        return job

    def _finish(self, job: Job, state: JobState) -> None:
        job.state = state
        job.finished = self.clock()
        job.page_started = None
        job.cancel_requested = False

    def _refresh(self) -> None:
        """Expire queued jobs past the queue timeout and purge finished jobs past retention."""
        now = self.clock()
        for job_id, job in list(self._jobs.items()):
            if job.state is JobState.QUEUED and now - job.created > self.queue_timeout_s:
                job.error = (
                    f"the job waited longer than {self.queue_timeout_s:g} s in the queue "
                    "and was not run"
                )
                self._finish(job, JobState.EXPIRED)
            elif (
                job.is_final and job.finished is not None and now - job.finished > self.retention_s
            ):
                del self._jobs[job_id]
