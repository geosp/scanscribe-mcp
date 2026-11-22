"""The OCR service: job checks, the worker thread and the page watchdog (D2-D5, D11).

One worker thread runs one job at a time, because the engine swaps the process-wide sys.stdout
while it runs and pdfium isn't thread safe. The worker's order for each job (D5):

1. PDF page sizes (R27), 2. `open_source` with its pre-check, 3. the page limit (R4),
4. the engine, loaded through the injected factory (D3), 5. `ocr_source`.

Nothing here uses MCP's API. Callers' mistakes raise `ValueError`; the tools turn them into tool
errors. Logs name jobs by id and inputs by kind, size and page count, never by name (R22).
"""

from __future__ import annotations

import contextlib
import gc
import logging
import math
import os
import secrets
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pypdfium2 as pdfium
import scanscribe
from scanscribe import IMAGE_EXTENSIONS, OcrEngine, PageImage, PageSource, ScanscribeError

from .config import ScanscribeMcpConfig
from .documents import DocumentStore, StoredDocument
from .jobs import Clock, Job, JobInput, JobState, JobTable, OcrOptions, Step, new_job_id
from .uploads import (
    IMAGES,
    PDF,
    ZIP,
    Grant,
    InputRefused,
    UploadLinks,
    UploadPlan,
    WorkDir,
    count_zip_pages,
    extract_zip,
    file_kind,
    link_pages,
    plan_upload,
)

logger = logging.getLogger(__name__)


class EngineFactory(Protocol):
    """`scanscribe.load_engine`'s signature (D3)."""

    def __call__(
        self, lang: str, device: str | None, *, on_device: Callable[[str], None] | None = None
    ) -> OcrEngine: ...


SourceOpener = Callable[[Path, int, int], PageSource]


class JobCancelled(Exception):
    """Raised inside the worker to stop a job that was cancelled (D4)."""


class _JobGone(Exception):
    """The job left `running` behind the worker's back (the watchdog failed it)."""


class JobError(Exception):
    """A job failure whose message is safe to show the caller as it is."""


class ServiceStuckError(ValueError):
    """A page hung; no new job may start until the server restarts (R28)."""


STUCK_MESSAGE = (
    "a page took longer than SCANSCRIBE_MCP_PAGE_TIMEOUT_S and the OCR engine may still be "
    "busy with it; restart the server to run more jobs"
)


@dataclass(frozen=True)
class ResultSlice:
    """Part or all of a succeeded job's text, as `get_ocr_result` returns it (R13)."""

    text: str | None
    total_pages: int
    first_page: int | None
    last_page: int | None
    next_first_page: int | None
    chars: int


def page_block(number: int, lines: list[str]) -> str:
    """One page as `scanscribe.format_pages` writes it."""
    return f"--- Page {number} ---\n" + "\n".join(lines)


class _TrackedEngine:
    """Wraps the engine to tell whether an error came from inside it (D3)."""

    def __init__(self, engine: OcrEngine) -> None:
        self.engine = engine
        self.failed = False

    def recognize(self, image: PageImage) -> list[str]:
        try:
            return self.engine.recognize(image)
        except BaseException:
            self.failed = True
            raise


class OcrService:
    """Checks and queues jobs, runs them on one worker thread, and hands out results."""

    def __init__(
        self,
        config: ScanscribeMcpConfig,
        engine_factory: EngineFactory,
        *,
        local_paths: bool,
        transport: str,
        clock: Clock = time.monotonic,
        open_source: SourceOpener = scanscribe.open_source,
        watchdog_interval_s: float = 1.0,
        on_stuck: Callable[[], None] | None = None,
        store: DocumentStore | None = None,
        uploads: UploadLinks | None = None,
        work_dir: WorkDir | None = None,
        purge_interval_s: float = 3600.0,
        purge_poll_s: float = 60.0,
    ) -> None:
        self.config = config
        self.store = store  # HTTP only (D6)
        self.uploads = uploads  # HTTP only (D7)
        self.work_dir = work_dir  # HTTP only (D12)
        folders = [store.directory for store in (store,) if store is not None]
        folders += [work_dir.path] if work_dir is not None else []
        # Longest first, so a folder inside another is replaced whole.
        self._server_folders = sorted(
            {spelling for folder in folders for spelling in _folder_spellings(folder)},
            key=len,
            reverse=True,
        )
        self.local_paths = local_paths
        self.transport = transport
        self.clock = clock
        self.table = JobTable(
            max_queued=config.max_queued,
            queue_timeout_s=config.queue_timeout_s,
            retention_s=config.job_retention_s,
            clock=clock,
        )
        self._factory = engine_factory
        self._open_source = open_source
        self._watchdog_interval_s = watchdog_interval_s
        self._on_stuck = on_stuck
        self._purge_interval_s = purge_interval_s
        self._purge_poll_s = purge_poll_s
        self._engine: OcrEngine | None = None
        self._engine_lang: str | None = None
        self._engine_device: str | None = None
        self._stuck = False
        self._admission = threading.Lock()
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []

    # --- lifecycle ---------------------------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        self._threads = [
            threading.Thread(target=self._work, name="ocr-worker", daemon=True),
            threading.Thread(target=self._watch, name="ocr-watchdog", daemon=True),
        ]
        if self.store is not None:
            self._threads.append(
                threading.Thread(target=self._purge_loop, name="document-purge", daemon=True)
            )
        for thread in self._threads:
            thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop both threads. A worker stuck inside the engine is left behind (it's a daemon)."""
        self._stopping.set()
        self.table.stop()
        for thread in self._threads:
            thread.join(timeout)
        self._threads = []

    @property
    def stuck(self) -> bool:
        return self._stuck

    # --- starting jobs -----------------------------------------------------------------------

    def start_job(
        self,
        *,
        input_path: str | None = None,
        upload_id: str | None = None,
        document: str | None = None,
        lang: str | None = None,
        dpi: int | None = None,
        columns: int | None = None,
    ) -> Job:
        """Check a job's input and options and queue it (R1-R4, R6, R28)."""
        if input_path is not None:
            self.check_local_paths("input_path")
            if not input_path.strip():
                raise ValueError("input_path is empty; pass the path of a PDF or an image folder")
        given = [
            name
            for name, value in (
                ("upload_id", upload_id),
                ("document", document),
                ("input_path", input_path),
            )
            if value is not None
        ]
        if len(given) != 1:
            raise ValueError(
                "pass exactly one input: upload_id, document or input_path"
                + (f" (got {', '.join(given)})" if given else "")
            )
        options = self.options(lang, dpi, columns)
        job_id = new_job_id()
        grant: Grant | None = None
        if input_path is not None:
            job_input = self._local_input(input_path)
        elif self.store is None or self.uploads is None or self.work_dir is None:
            raise ValueError(
                f"{given[0]} needs the HTTP server's upload links; on this local server, pass "
                "input_path instead"
            )
        elif upload_id is not None:
            grant, job_input = self._upload_input(upload_id, job_id)
        else:
            assert document is not None
            job_input = self._document_input(document, job_id)
        # The stuck check and the submit hold the lock the watchdog takes to go stuck, so no job
        # is queued after the watchdog has failed the queue (R28).
        with self._admission:
            if self._stuck:
                raise ServiceStuckError(STUCK_MESSAGE)
            job = self.table.submit(job_input, options, job_id=job_id)
        if grant is not None and self.uploads is not None and grant.snapshot is None:
            # The job took these files: later starts on this upload_id reuse them (D7).
            grant.snapshot = job_input.documents
            self.uploads.close(grant)
        logger.info(
            "job %s queued: %s, %s bytes, %s page images, lang %s, dpi %d, columns %d",
            job.id,
            job_input.kind,
            job_input.size if job_input.size is not None else "-",
            job_input.page_count if job_input.page_count is not None else "-",
            options.lang,
            options.dpi,
            options.columns,
        )
        return job

    def options(self, lang: str | None, dpi: int | None, columns: int | None) -> OcrOptions:
        """The job's options, with defaults filled in, or ValueError (R3)."""
        config = self.config
        lang = config.lang if lang is None else lang
        dpi = config.default_dpi if dpi is None else dpi
        columns = config.default_columns if columns is None else columns
        if lang not in config.langs:
            raise ValueError(
                f"lang {lang!r} is not available; this server allows: {', '.join(config.langs)}"
            )
        if not config.min_dpi <= dpi <= config.max_dpi:
            raise ValueError(f"dpi must be {config.min_dpi} to {config.max_dpi}, got {dpi}")
        if not 1 <= columns <= config.max_columns:
            raise ValueError(f"columns must be 1 to {config.max_columns}, got {columns}")
        return OcrOptions(lang=lang, dpi=dpi, columns=columns)

    def check_local_paths(self, argument: str) -> None:
        """input_path and output_path only where local paths are allowed (R2)."""
        if self.local_paths:
            return
        if self.transport != "stdio" and argument == "output_path":
            raise ValueError(
                "output_path is not accepted over HTTP: the server can't write your files. "
                "Use the download URL that get_ocr_result returns, or get the text inline or in "
                "page ranges with first_page and last_page. Files reach this server only "
                "through upload links (create_upload_link)"
            )
        if self.transport != "stdio":
            raise ValueError(
                f"{argument} is not accepted over HTTP: the server can't read your files. "
                "Call create_upload_link, upload the files, and pass the upload_id instead"
            )
        raise ValueError(
            f"{argument} is turned off on this server (SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS=false)"
        )

    def _local_input(self, input_path: str) -> JobInput:
        self.check_local_paths("input_path")
        path = Path(input_path).expanduser()
        try:
            path = path.resolve()
            if not path.exists():
                raise ValueError(f"input_path not found: {input_path}")
            if path.is_dir():
                count = count_page_images(path)
                if count > self.config.max_pages:
                    raise ValueError(self._too_many_pages(input_path, count))
                return JobInput(kind="folder", path=path, name=input_path, page_count=count)
            return JobInput(kind="file", path=path, name=input_path, size=path.stat().st_size)
        except OSError as exc:
            raise ValueError(f"cannot read input_path {input_path} ({type(exc).__name__})") from exc

    def _upload_input(self, upload_id: str, job_id: str) -> tuple[Grant, JobInput]:
        """The input from an upload link's files; any refusal leaves the link open (D7, R29)."""
        assert self.uploads is not None and self.store is not None
        grant = self.uploads.get(upload_id)
        if grant is None:
            raise ValueError(f"unknown or expired upload_id {upload_id!r}")
        if grant.snapshot is not None:
            ids = grant.snapshot
        else:
            if grant.requests:
                raise ValueError(
                    f"{grant.requests} upload(s) are still arriving through this link; wait "
                    "for them with check_upload(upload_id, wait_s=60), then start again"
                )
            if not grant.files:
                raise ValueError(
                    "no file has been uploaded through this link yet; upload the pages first "
                    "(check_upload(upload_id, wait_s=60) waits for them)"
                )
            ids = tuple(grant.files)
        documents = []
        for doc_id in ids:
            stored = self.store.get(doc_id)
            if stored is None:
                raise ValueError("the files of this upload are no longer stored; upload them again")
            documents.append((stored, bool(self.store.metadata(stored).get("hidden"))))
        plan = plan_upload(documents)
        return grant, self._planned_input(plan, job_id)

    def _document_input(self, doc_id: str, job_id: str) -> JobInput:
        """The input from one stored document: an uploaded PDF or zip (D7)."""
        assert self.store is not None
        stored = self.store.get(doc_id)
        if stored is None:
            raise ValueError(f"no stored document with id {doc_id!r}; it may have expired")
        kind = file_kind(stored.filename)
        metadata = self.store.metadata(stored)
        if metadata.get("hidden"):
            raise ValueError(
                f"document {doc_id!r} was uploaded as a hidden file, which a job skips; upload "
                "it under a plain name"
            )
        if metadata.get("kind") != "upload" or kind not in (PDF, ZIP):
            raise ValueError(
                f"document {doc_id!r} ({stored.filename}) is not an uploaded PDF or zip; a job "
                "reads an uploaded PDF or zip by its id, or an upload link's files by upload_id"
            )
        return self._planned_input(UploadPlan(kind, (stored,)), job_id)

    def _planned_input(self, plan: UploadPlan, job_id: str) -> JobInput:
        """A JobInput for an upload plan; images and zips are counted here (D5, R4)."""
        assert self.work_dir is not None
        ids = tuple(document.id for document in plan.documents)
        names = tuple(document.filename for document in plan.documents)
        size = sum(document.size for document in plan.documents)
        if plan.kind == PDF:
            pdf = plan.documents[0]
            return JobInput(
                kind=PDF, path=pdf.path, name=pdf.filename, size=size, documents=ids, files=names
            )
        pages_folder = self.work_dir.job_folder(job_id) / "pages"
        if plan.kind == ZIP:
            archive = plan.documents[0]
            count = count_zip_pages(archive.path, archive.filename, self.config.max_upload_bytes)
            name = archive.filename
        else:
            count = len(plan.documents)
            name = "the uploaded pages"
        if count > self.config.max_pages:
            raise ValueError(self._too_many_pages(name, count))
        return JobInput(
            kind=plan.kind,
            path=pages_folder,
            name=name,
            size=size,
            page_count=count,
            documents=ids,
            files=names,
        )

    def _too_many_pages(self, name: str, count: int) -> str:
        return (
            f"{name} has {count} pages; this server takes at most {self.config.max_pages} "
            "per job (SCANSCRIBE_MCP_MAX_PAGES). Split it into smaller jobs"
        )

    # --- jobs and results --------------------------------------------------------------------

    def get_job(self, job_id: str) -> Job:
        return self.table.get(job_id)

    def cancel_job(self, job_id: str) -> tuple[Job, bool]:
        job, changed = self.table.cancel(job_id)
        if changed:
            logger.info("job %s: cancel requested (%s)", job_id, job.state)
        return job, changed

    def succeeded_pages(self, job_id: str) -> list[list[str]]:
        job = self.table.get(job_id)
        if job.state is not JobState.SUCCEEDED or job.pages is None:
            detail = f": {job.error}" if job.error else ""
            raise ValueError(f"job {job_id} has no result: it is {job.state}{detail}")
        return job.pages

    def result(
        self, job_id: str, first_page: int | None = None, last_page: int | None = None
    ) -> ResultSlice:
        """The whole text inline if it fits, else none; or a page range, cut at a page so it
        fits (R13)."""
        pages = self.succeeded_pages(job_id)
        total = len(pages)
        limit = self.config.max_inline_chars
        if first_page is None and last_page is None:
            text = scanscribe.format_pages(pages)
            fits = len(text) <= limit
            return ResultSlice(
                text=text if fits else None,
                total_pages=total,
                first_page=1 if fits and total else None,
                last_page=total if fits and total else None,
                next_first_page=None,
                chars=len(text),
            )
        first = 1 if first_page is None else first_page
        last = total if last_page is None else last_page
        if not 1 <= first <= last <= total:
            raise ValueError(
                f"pages {first} to {last} are out of range; the result has {total} pages"
            )
        blocks: list[str] = []
        length = 0
        number = first
        while number <= last:
            block = page_block(number, pages[number - 1])
            extra = len(block) + (2 if blocks else 0)
            if length + extra > limit:
                break
            blocks.append(block)
            length += extra
            number += 1
        return ResultSlice(
            text="\n\n".join(blocks) if blocks else None,
            total_pages=total,
            first_page=first if blocks else None,
            last_page=number - 1 if blocks else None,
            next_first_page=number if number <= last else None,
            chars=length,
        )

    def write_result(self, job_id: str, output_path: str) -> tuple[Path, int]:
        """Write the whole text to an absolute path whose folder exists, replacing any file
        there (R14). Returns the path and the number of characters."""
        self.check_local_paths("output_path")
        path = Path(output_path).expanduser()
        if not path.is_absolute():
            raise ValueError(f"output_path must be an absolute path, got {output_path}")
        if not path.parent.is_dir():
            raise ValueError(f"the folder of output_path doesn't exist: {path.parent}")
        if path.is_dir():
            raise ValueError(f"output_path is a folder: {output_path}")
        text = scanscribe.format_pages(self.succeeded_pages(job_id))
        try:
            write_replacing(path, text)
        except OSError as exc:
            raise ValueError(f"cannot write {output_path} ({type(exc).__name__})") from exc
        logger.info("job %s: result written to a local file (%d chars)", job_id, len(text))
        return path, len(text)

    # --- the worker --------------------------------------------------------------------------

    def _work(self) -> None:
        while not self._stopping.is_set():
            job = self.table.next_job()
            if job is None:
                return
            self._run(job)

    def _run(self, job: Job) -> None:
        """Run one job inside a catch-all, so no error stops the worker (R26)."""
        started = self.clock()
        logger.info("job %s started", job.id)
        try:
            try:
                # A print() during the job would sit in sys.stdout's buffer and reach the MCP
                # wire at exit, after the transport hands fd 1 back (D10, notes.md#d10).
                with contextlib.redirect_stdout(sys.stderr):
                    pages = self._process(job)
            finally:
                # Before the job leaves `running`: a caller that sees a final state never finds
                # its folder.
                if self.work_dir is not None:
                    self.work_dir.remove(job.id)
            result_document = self._save_result(job, pages)
        except JobCancelled:
            if self.table.finish(job.id, JobState.CANCELLED):
                logger.info("job %s cancelled", job.id)
            return
        except _JobGone:
            return
        except (JobError, ScanscribeError, InputRefused) as exc:
            self._fail(job, public_message(job.input, str(exc)), exc)
            return
        except Exception as exc:
            self._fail(job, f"OCR failed ({type(exc).__name__})", exc)
            return
        if self.table.finish(
            job.id, JobState.SUCCEEDED, pages=pages, result_document=result_document
        ):
            logger.info(
                "job %s succeeded: %d pages in %.1f s", job.id, len(pages), self.clock() - started
            )
        elif result_document is not None and self.store is not None:
            self.store.delete(result_document)  # the job left `running` meanwhile

    def _save_result(self, job: Job, pages: list[list[str]]) -> str | None:
        """Over HTTP, store the text as ocr-<job id>.txt; meta.json gets the options and page
        count, never text (D6, R20, R22)."""
        if self.store is None:
            return None
        options = job.options
        document = self.store.save(
            scanscribe.format_pages(pages).encode("utf-8"),
            f"ocr-{job.id}.txt",
            {
                "kind": "result",
                "job_id": job.id,
                "input": job.input.kind,
                "lang": options.lang,
                "dpi": options.dpi,
                "columns": options.columns,
                "pages": len(pages),
            },
        )
        # Not the document id: with the job id it rebuilds the token-free download URL (D8).
        logger.info("job %s: result stored (%d bytes)", job.id, document.size)
        return document.id

    def scrub(self, message: str) -> str:
        """Hide any server folder left in a message after `public_message` (R23)."""
        for folder in self._server_folders:
            message = message.replace(folder, "<server folder>")
        return message

    def result_document(self, job_id: str) -> StoredDocument | None:
        """The stored text of a succeeded HTTP job, while the store keeps it."""
        self.succeeded_pages(job_id)
        doc_id = self.table.get(job_id).result_document
        if self.store is None or doc_id is None:
            return None
        return self.store.get(doc_id)

    # --- the purge timer ---------------------------------------------------------------------

    def _purge_loop(self) -> None:
        last: float | None = None
        while True:
            now = self.clock()
            if last is None or now - last >= self._purge_interval_s:
                last = now
                self.purge()
            if self._stopping.wait(self._purge_poll_s):
                return

    def purge(self) -> int:
        """Delete stored documents past RETENTION_DAYS, except those a live job reads (R20)."""
        if self.store is None:
            return 0
        try:
            removed = self.store.purge(self.config.retention_days, keep=self.table.live_documents())
        except Exception as exc:
            logger.warning("document purge failed (%s)", type(exc).__name__)
            return 0
        if removed:
            logger.info("purged %d stored documents past the retention", removed)
        return removed

    def _fail(self, job: Job, message: str, exc: BaseException) -> None:
        message = self.scrub(message)
        if self.table.finish(job.id, JobState.FAILED, error=message):
            logger.warning("job %s failed (%s)", job.id, type(exc).__name__)

    def _process(self, job: Job) -> list[list[str]]:
        options = job.options
        # `page_started` times what the watchdog watches (R28): the checking step, then each
        # page from when the job reaches it until the next page is ready. The engine load isn't
        # timed: a first run downloads models.
        self._set(job, step=Step.CHECKING_PAGES, page_started=self.clock())
        self._build_job_folder(job)
        if job.input.path.is_file():
            self._check_pdf_page_sizes(job.input, options.dpi)
        with self._open_source(job.input.path, options.dpi, options.columns) as source:
            self._check_cancel(job)
            if len(source) > self.config.max_pages:
                raise JobError(self._too_many_pages(job.input.name, len(source)))
            logger.info("job %s: %d pages passed the pre-check", job.id, len(source))
            self._set(job, step=Step.LOADING_ENGINE, total=len(source), page_started=None)
            tracked = _TrackedEngine(self._engine_for(job))
            self._check_cancel(job)
            self._set(job, step=Step.RECOGNIZING, page_started=self.clock())

            def on_page(number: int, total: int) -> None:
                self._check_cancel(job)
                self._set(job, page=number, total=total, page_started=self.clock())

            try:
                return scanscribe.ocr_source(source, tracked, on_page)
            finally:
                if tracked.failed:
                    self._drop_engine()
                del tracked

    def _build_job_folder(self, job: Job) -> None:
        """Lay out an upload's pages in WORK_DIR/<job id>/pages/: links to the images, or a
        zip's pages unpacked (D7, R17). A PDF is read where it is stored."""
        job_input = job.input
        if job_input.kind not in (ZIP, IMAGES):
            return
        assert self.store is not None and self.work_dir is not None
        documents = []
        for doc_id in job_input.documents:
            stored = self.store.get(doc_id)
            if stored is None:
                raise JobError("the uploaded files are no longer stored; upload them again")
            documents.append(stored)
        if job_input.kind == IMAGES:
            link_pages(tuple(documents), job_input.path)
            return
        count = extract_zip(
            documents[0].path,
            job_input.name,
            job_input.path,
            self.config.max_pages,
            self.config.max_upload_bytes,
        )
        logger.info("job %s: zip unpacked to %d pages", job.id, count)

    def _set(self, job: Job, **changes: object) -> None:
        if not self.table.update(job.id, **changes):
            raise _JobGone

    def _check_cancel(self, job: Job) -> None:
        if self.table.cancel_requested(job.id):
            raise JobCancelled

    def _check_pdf_page_sizes(self, job_input: JobInput, dpi: int) -> None:
        """Refuse a PDF page that would render above MAX_PAGE_PIXELS, before anything is
        rendered (R27). A file pdfium can't open is left to `open_source` to report."""
        try:
            document = pdfium.PdfDocument(job_input.path)
        except Exception:
            return
        try:
            scale = dpi / 72
            limit = self.config.max_page_pixels
            for index in range(len(document)):
                page = document[index]
                try:
                    width, height = page.get_size()
                finally:
                    page.close()
                pixels = math.ceil(width * scale) * math.ceil(height * scale)
                if pixels > limit:
                    raise JobError(
                        f"{job_input.name} page {index + 1} is too large: {pixels:,} pixels at "
                        f"{dpi} dpi, above the limit of {limit:,} (SCANSCRIBE_MCP_MAX_PAGE_PIXELS)"
                    )
        finally:
            document.close()

    def _engine_for(self, job: Job) -> OcrEngine:
        """The loaded engine if its language matches, else a new one (D3, R11)."""
        lang = job.options.lang
        if self._engine is not None and self._engine_lang == lang:
            self._set(job, device=self._engine_device)
            return self._engine
        self._drop_engine()

        def on_device(device: str) -> None:
            self._engine_device = device
            self.table.update(job.id, device=device)

        gc.collect()  # an engine dropped after an error may only now be unreachable (D3)
        engine = self._factory(lang, self.config.device, on_device=on_device)
        self._engine, self._engine_lang = engine, lang
        logger.info("job %s: engine loaded for lang %s on %s", job.id, lang, self._engine_device)
        return engine

    def _drop_engine(self) -> None:
        if self._engine is None:
            return
        self._engine = None
        self._engine_lang = None
        self._engine_device = None
        gc.collect()

    # --- the watchdog ------------------------------------------------------------------------

    def _watch(self) -> None:
        while not self._stopping.wait(self._watchdog_interval_s):
            self.check_watchdog()

    def check_watchdog(self) -> bool:
        """Fail the running job if its current page, or its checking step, passed
        PAGE_TIMEOUT_S, and refuse new jobs from then on (R28). Returns whether it fired."""
        job = self.table.running()
        timeout = self.config.page_timeout_s
        if job is None or job.page_started is None or self.clock() - job.page_started <= timeout:
            return False
        if job.step is Step.CHECKING_PAGES:
            what = "checking the pages"
        elif job.page is None:
            what = "rendering page 1"
        else:
            what = f"page {job.page} (recognizing it, or rendering the next page)"
        message = (
            f"{what} took longer than {timeout:g} s (SCANSCRIBE_MCP_PAGE_TIMEOUT_S); "
            "restart the server to run more jobs"
        )
        with self._admission:
            if not self.table.finish(job.id, JobState.FAILED, error=message):
                return False
            self._stuck = True
            dropped = self.table.fail_queued(STUCK_MESSAGE)
        logger.error(
            "job %s failed: %s passed the page timeout (step %s, page %s); %d queued jobs "
            "failed; the server needs a restart",
            job.id,
            "the checking step" if job.step is Step.CHECKING_PAGES else "a page",
            job.step,
            job.page,
            dropped,
        )
        if self._on_stuck is not None:
            self._on_stuck()
        return True


def count_page_images(folder: Path) -> int:
    """How many files in a folder scanscribe would read as pages: regular, not hidden, with an
    image suffix in any case (D5)."""
    return sum(
        1
        for path in folder.iterdir()
        if not path.name.startswith(".")
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and path.is_file()
    )


def public_message(job_input: JobInput, message: str) -> str:
    """Replace the input's server path with the caller's own name for it (D11). A page in an
    upload's job folder becomes its own file name: `<job folder>/pages/p7.png` → `p7.png`."""
    for server_path in _path_spellings(job_input.path):
        if job_input.kind in (ZIP, IMAGES):
            message = message.replace(server_path + os.sep, "")
        message = message.replace(server_path, job_input.name)
    return message


def _path_spellings(path: Path) -> Iterator[str]:
    seen = set()
    for spelling in (str(path), os.path.realpath(path)):
        if spelling not in seen:
            seen.add(spelling)
            yield spelling


def _folder_spellings(folder: Path) -> Iterator[str]:
    """Absolute spellings only: a relative one ("data/work") could match a caller's own name."""
    yield str(folder.absolute())
    yield os.path.realpath(folder)


def write_replacing(path: Path, text: str) -> None:
    """Write `text` to a temp file next to `path`, then rename it onto `path`."""
    temp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with open(temp, "x", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temp.unlink()
        raise
