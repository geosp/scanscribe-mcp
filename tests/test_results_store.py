"""HTTP results in the document store, and the hourly purge (task 02/2.2).

D6, R20, R22. Jobs are queued straight into the table here: starting them from uploads comes
with task 02/4.3, which tests the whole flow.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import scanscribe

from scanscribe_mcp.config import AppConfig, ScanscribeMcpConfig
from scanscribe_mcp.documents import DocumentStore
from scanscribe_mcp.jobs import JobInput, OcrOptions, Step
from scanscribe_mcp.ocr_service import OcrService
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeClock, FakeEngineFactory, make_pages
from .http_helpers import http_server
from .service_helpers import running_service, wait_for, wait_until

OPTIONS = OcrOptions(lang="en", dpi=200, columns=1)


def queue_folder(ocr: OcrService, folder: Path, documents: tuple[str, ...] = ()) -> str:
    job_input = JobInput(kind="folder", path=folder, name="pages", documents=documents)
    return ocr.table.submit(job_input, OPTIONS).id


async def test_result_is_stored_and_downloads_exactly(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)
    async with http_server(tmp_path, FakeEngineFactory(lines_per_page=2)) as s:
        assert s.service.ocr is not None
        job_id = queue_folder(s.service.ocr, folder)
        job = wait_for(s.service.ocr, job_id)
        expected = scanscribe.format_pages(job.pages or [])
        result = await s.mcp.call_tool("get_ocr_result", {"job_id": job_id})
        fields = result.structured_content
        assert fields["text"] == expected
        assert fields["url"].endswith(f"/documents/{fields['document']}/ocr-{job_id}.txt")
        assert fields["url"] in fields["message"]
        download = await s.http.get(s.path(fields["url"]))
        assert download.status_code == 200 and download.text == expected

        store = s.service.ocr.store
        assert store is not None
        document = store.get(fields["document"])
        assert document is not None
        meta_text = (document.path.parent / "meta.json").read_text()
        meta = store.metadata(document)
        assert meta["pages"] == 3 and meta["job_id"] == job_id and meta["lang"] == "en"
        for line in ("page 1", "gray ", "line 2"):
            assert line not in meta_text

        sliced = await s.mcp.call_tool(
            "get_ocr_result", {"job_id": job_id, "first_page": 2, "last_page": 2}
        )
        assert sliced.structured_content["url"] == fields["url"]


async def test_long_result_offers_the_url(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)
    async with http_server(tmp_path, max_inline_chars=20) as s:
        assert s.service.ocr is not None
        job_id = queue_folder(s.service.ocr, folder)
        wait_for(s.service.ocr, job_id)
        result = await s.mcp.call_tool("get_ocr_result", {"job_id": job_id})
        fields = result.structured_content
        assert fields["inline"] is False and fields["text"] is None
        assert "download it from the URL above" in fields["message"]
        assert "output_path" not in fields["message"]


async def test_stdio_writes_nothing_to_disk(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    output_dir, work_dir = tmp_path / "data" / "documents", tmp_path / "data" / "work"
    config = AppConfig(ocr=ScanscribeMcpConfig(output_dir=output_dir, work_dir=work_dir))
    service = ScanscribeMCPService(config, FakeEngineFactory())
    service.initialize()
    try:
        assert service.ocr is not None and service.ocr.store is None
        job = wait_for(service.ocr, service.ocr.start_job(input_path=str(folder)).id)
        assert job.result_document is None
        assert service.ocr.result_document(job.id) is None
    finally:
        service.cleanup()
    assert not (tmp_path / "data").exists()


def test_timer_purges_while_idle_and_spares_live_jobs(tmp_path: Path) -> None:
    wall = FakeClock(start=30 * 86400.0)
    store = DocumentStore(tmp_path / "documents", "http://x", clock=wall)
    store.ensure_directory()
    clock = FakeClock()
    folder = make_pages(tmp_path / "pages", 1)
    release = threading.Event()
    factory = FakeEngineFactory(hooks={1: lambda: release.wait(10) and None})
    try:
        with running_service(
            factory, transport="http", local_paths=False, store=store, clock=clock,
            purge_poll_s=0.01,
        ) as service:  # fmt: skip
            time.sleep(0.05)  # the first purge runs at start-up, with nothing to delete
            old, used = store.save(b"x", "old.pdf"), store.save(b"x", "used.pdf")
            for document in (old, used):
                past = wall() - 8 * 86400
                os.utime(document.path.parent, (past, past))
            running = queue_folder(service, folder, documents=(used.id,))
            wait_until(service, running, Step.RECOGNIZING, page=1)

            clock.advance(3599)
            time.sleep(0.1)
            assert store.get(old.id) is not None  # not an hour yet

            clock.advance(1)
            deadline = time.monotonic() + 5
            while store.get(old.id) is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert store.get(old.id) is None
            assert store.get(used.id) is not None  # a running job reads it
            release.set()
            wait_for(service, running)
    finally:
        release.set()
