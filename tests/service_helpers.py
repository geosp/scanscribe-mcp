"""Building an OcrService with a fake engine, and waiting for its jobs."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from scanscribe_mcp.config import ScanscribeMcpConfig
from scanscribe_mcp.jobs import FINAL_STATES, Job, JobState, Step
from scanscribe_mcp.ocr_service import OcrService

from .fakes import FakeEngineFactory


@contextmanager
def running_service(
    factory: FakeEngineFactory | None = None,
    *,
    local_paths: bool = True,
    transport: str = "stdio",
    **kwargs: Any,
) -> Iterator[OcrService]:
    config_fields = {k: v for k, v in kwargs.items() if k in ScanscribeMcpConfig.model_fields}
    service_args = {k: v for k, v in kwargs.items() if k not in config_fields}
    service = OcrService(
        ScanscribeMcpConfig(**config_fields),
        factory or FakeEngineFactory(),
        local_paths=local_paths,
        transport=transport,
        **service_args,
    )
    service.start()
    try:
        yield service
    finally:
        service.stop()


def wait_for(service: OcrService, job_id: str, timeout: float = 10.0) -> Job:
    """Wait until the job reaches a final state."""
    deadline = time.monotonic() + timeout
    while True:
        job = service.get_job(job_id)
        if job.state in FINAL_STATES:
            return job
        if time.monotonic() > deadline:
            raise AssertionError(f"job still {job.state} after {timeout} s")
        time.sleep(0.01)


def wait_until(service: OcrService, job_id: str, step: Step, page: int | None = None) -> Job:
    """Wait until a running job reaches a step (and page)."""
    deadline = time.monotonic() + 10
    while True:
        job = service.get_job(job_id)
        if (
            job.state is JobState.RUNNING
            and job.step is step
            and (page is None or job.page == page)
        ):
            return job
        if job.state in FINAL_STATES or time.monotonic() > deadline:
            raise AssertionError(f"job is {job.state}/{job.step}/{job.page}, not {step}/{page}")
        time.sleep(0.005)
