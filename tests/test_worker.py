"""The worker: D5's order, the engine cache and the catch-all (task 01/2.2).

R4, R8, R11, R12, R26, R27.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scanscribe
from scanscribe import EngineMissingError, PageSource

from scanscribe_mcp.jobs import JobState

from .fakes import FakeEngineFactory, make_pages, make_pdf
from .service_helpers import running_service, wait_for


def test_job_succeeds_with_pages_and_device(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)
    with running_service() as service:
        job = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert job.state is JobState.SUCCEEDED
    assert job.total == 3 and job.page == 3
    assert job.device == "fake:0"
    assert job.pages == [["page 1", "gray 1"], ["page 2", "gray 2"], ["page 3", "gray 3"]]


def test_pdf_job_succeeds(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "doc.pdf", 2)
    with running_service() as service:
        job = wait_for(service, service.start_job(input_path=str(pdf), dpi=72).id)
    assert job.state is JobState.SUCCEEDED and job.total == 2


def test_engine_loaded_once_per_language(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    factory = FakeEngineFactory()
    with running_service(factory, langs=["en", "fr"]) as service:
        for _ in range(2):
            assert wait_for(service, service.start_job(input_path=str(folder)).id).device
        assert factory.calls == [("en", None)]


def test_language_change_releases_the_old_engine_first(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    factory = FakeEngineFactory()
    with running_service(factory, langs=["en", "fr"], device="cpu") as service:
        wait_for(service, service.start_job(input_path=str(folder), lang="en").id)
        job = wait_for(service, service.start_job(input_path=str(folder), lang="fr").id)
    assert job.state is JobState.SUCCEEDED
    assert factory.calls == [("en", "cpu"), ("fr", "cpu")]
    assert factory.alive_at_load == [[], [False]]


def test_too_many_pdf_pages_fails_before_the_engine(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "long.pdf", 501)
    factory = FakeEngineFactory()
    with running_service(factory) as service:
        job = wait_for(service, service.start_job(input_path=str(pdf), dpi=72).id)
    assert job.state is JobState.FAILED
    assert job.error is not None and "501 pages" in job.error and "MAX_PAGES" in job.error
    assert factory.calls == []


def test_huge_pdf_page_fails_before_anything_is_rendered(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "huge.pdf", 1, size_pt=(200 * 72, 200 * 72))
    opened: list[Path] = []

    def spy_open(path: Path, dpi: int, columns: int) -> PageSource:
        opened.append(path)
        return scanscribe.open_source(path, dpi, columns)

    factory = FakeEngineFactory()
    with running_service(factory, open_source=spy_open) as service:
        job = wait_for(service, service.start_job(input_path=str(pdf), dpi=200).id)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "page 1 is too large" in job.error and "MAX_PAGE_PIXELS" in job.error
    assert opened == [] and factory.calls == []


def test_missing_engine_fails_the_job_not_the_server(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    factory = FakeEngineFactory(
        error=EngineMissingError(
            "the OCR engine is not installed; install one build: "
            "`uv sync --extra gpu` (NVIDIA GPU) or `uv sync --extra cpu`"
        )
    )
    with running_service(factory) as service:
        failed = wait_for(service, service.start_job(input_path=str(folder)).id)
        factory.error = None
        ok = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert failed.state is JobState.FAILED
    assert failed.error is not None
    assert "uv sync --extra gpu" in failed.error and "--extra cpu" in failed.error
    assert ok.state is JobState.SUCCEEDED


def test_engine_error_fails_the_job_and_drops_the_engine(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)

    def boom() -> None:
        raise RuntimeError(f"engine broke while reading {folder}/p2.png")

    factory = FakeEngineFactory(hooks={2: boom})
    with running_service(factory) as service:
        failed = wait_for(service, service.start_job(input_path=str(folder)).id)
        factory.hooks = None
        ok = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert failed.state is JobState.FAILED
    assert failed.error == "OCR failed (RuntimeError)"
    assert ok.state is JobState.SUCCEEDED
    assert len(factory.calls) == 2


def test_unreadable_page_fails_with_a_scanscribe_message(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    (folder / "p2.png").write_bytes(b"not a png")
    factory = FakeEngineFactory()
    with running_service(factory) as service:
        job = wait_for(service, service.start_job(input_path=str(folder)).id)
    assert job.state is JobState.FAILED
    assert job.error is not None and "p2.png" in job.error
    assert factory.calls == []


@pytest.mark.parametrize("columns", [1, 2])
def test_columns_reach_scanscribe(tmp_path: Path, columns: int) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    factory = FakeEngineFactory()
    with running_service(factory) as service:
        job = wait_for(service, service.start_job(input_path=str(folder), columns=columns).id)
    assert job.state is JobState.SUCCEEDED
    assert factory.last is not None and len(factory.last.seen) == columns
