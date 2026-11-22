"""Jobs from upload links: what a link's files become, the job folder and WORK_DIR (task 02/4.1).

D7, D12, R18, R29.
"""

from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from scanscribe_mcp.config import AppConfig
from scanscribe_mcp.jobs import Step
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory, make_pdf
from .http_helpers import CONTENT_TYPE, HttpServer, http_config, http_server, multipart, png
from .service_helpers import wait_until


async def new_link(s: HttpServer, max_files: int = 20) -> tuple[str, str]:
    result = await s.mcp.call_tool("create_upload_link", {"max_files": max_files})
    fields = result.structured_content
    return s.path(fields["upload_url"]), fields["upload_id"]


async def send(s: HttpServer, url: str, *files: tuple[str, bytes]) -> None:
    response = await s.http.post(
        url, content=multipart(*files), headers={"Content-Type": CONTENT_TYPE}
    )
    assert response.status_code == 200, response.text


async def upload(s: HttpServer, *files: tuple[str, bytes]) -> str:
    url, upload_id = await new_link(s)
    await send(s, url, *files)
    return upload_id


async def run_job(s: HttpServer, **arguments: Any) -> dict[str, Any]:
    started = await s.mcp.call_tool("start_ocr_job", arguments)
    job_id = started.structured_content["job_id"]
    done = await s.mcp.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
    fields: dict[str, Any] = {**done.structured_content, "start": started.structured_content}
    return fields


def pdf_bytes(tmp_path: Path, pages: int) -> bytes:
    return make_pdf(tmp_path / "made.pdf", pages).read_bytes()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def job_folders(tmp_path: Path) -> list[str]:
    return [p.name for p in (tmp_path / "data" / "work").iterdir() if len(p.name) == 32]


async def test_images_run_in_natural_order(tmp_path: Path) -> None:
    factory = FakeEngineFactory()
    async with http_server(tmp_path, factory) as s:
        upload_id = await upload(
            s, ("p10.png", png(10)), ("p2.png", png(2)), ("p1.png", png(1)),
            (".DS_Store", b"junk"), ("Thumbs.db", b"junk"),
        )  # fmt: skip
        done = await run_job(s, upload_id=upload_id)
        assert done["state"] == "succeeded", done
        assert done["input"] == "images" and done["total"] == 3
        assert done["start"]["page_images"] == 3
        assert sorted(done["start"]["files"]) == ["p1.png", "p10.png", "p2.png"]
        engine = factory.last
        assert engine is not None and engine.seen == [1, 2, 10]
        assert job_folders(tmp_path) == []


async def test_a_pdf_is_read_in_place(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        upload_id = await upload(s, ("chapter.pdf", pdf_bytes(tmp_path, 2)))
        done = await run_job(s, upload_id=upload_id, dpi=72)
        assert done["state"] == "succeeded" and done["input"] == "pdf" and done["total"] == 2
        assert not (tmp_path / "data" / "work").joinpath(done["job_id"]).exists()


async def test_a_zip_is_unpacked(tmp_path: Path) -> None:
    factory = FakeEngineFactory()
    async with http_server(tmp_path, factory) as s:
        pages = zip_bytes({"scan/p2.png": png(2), "scan/p1.png": png(1), "scan/": b""})
        upload_id = await upload(s, ("pages.zip", pages))
        done = await run_job(s, upload_id=upload_id)
        assert done["state"] == "succeeded" and done["input"] == "zip" and done["total"] == 2
        assert factory.last is not None and factory.last.seen == [1, 2]
        assert job_folders(tmp_path) == []


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ((("a.pdf", b"%PDF"), ("b.pdf", b"%PDF")), "holds 2 PDFs; a job reads one"),
        ((("a.zip", b"PK"), ("b.zip", b"PK")), "holds 2 zips"),
        ((("a.pdf", b"%PDF"), ("p1.png", b"png")), "mixes 1 PDF and 1 page image"),
        ((("notes.txt", b"x"), (".hidden.png", b"x")), "holds no PDF, zip or page image"),
        ((("a/p1.png", b"1"), ("b/p1.png", b"2")), "both named 'p1.png'"),
    ],
)
async def test_bad_uploads_are_refused_and_the_link_stays_open(
    tmp_path: Path, files: tuple[tuple[str, bytes], ...], message: str
) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        await send(s, url, *files)
        with pytest.raises(ToolError, match=message):
            await s.mcp.call_tool("start_ocr_job", {"upload_id": upload_id})
        checked = await s.mcp.call_tool("check_upload", {"upload_id": upload_id})
        assert checked.structured_content["closed"] is False
        await send(s, url, ("more.png", png()))  # the link still takes files


async def test_an_upload_in_progress_or_none_yet_is_refused(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        with pytest.raises(ToolError, match="no file has been uploaded"):
            await s.mcp.call_tool("start_ocr_job", {"upload_id": upload_id})
        assert s.service.ocr is not None and s.service.ocr.uploads is not None
        grant = s.service.ocr.uploads.get(upload_id)
        assert grant is not None
        s.service.ocr.uploads.begin(grant)  # as the route does while a file arrives
        with pytest.raises(ToolError, match="still arriving.*wait"):
            await s.mcp.call_tool("start_ocr_job", {"upload_id": upload_id})
        s.service.ocr.uploads.abandon(grant, 0)
        await send(s, url, ("p1.png", png()))
        with pytest.raises(ToolError, match="unknown or expired upload_id"):
            await s.mcp.call_tool("start_ocr_job", {"upload_id": "0" * 32})


async def test_a_job_closes_the_link_and_a_second_start_reuses_its_files(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        await send(s, url, ("p1.png", png(1)), ("p2.png", png(2)))
        first = await run_job(s, upload_id=upload_id)
        assert first["state"] == "succeeded"
        response = await s.http.post(
            url, content=multipart(("p3.png", png(3))), headers={"Content-Type": CONTENT_TYPE}
        )
        assert response.status_code == 404
        checked = await s.mcp.call_tool("check_upload", {"upload_id": upload_id})
        assert checked.structured_content["closed"] is True
        second = await run_job(s, upload_id=upload_id, dpi=300)
        assert second["state"] == "succeeded" and second["total"] == 2
        assert second["start"]["files"] == first["start"]["files"]


async def test_no_job_folder_is_left_after_failure_or_cancel(tmp_path: Path) -> None:
    release = threading.Event()
    factory = FakeEngineFactory(hooks={1: lambda: release.wait(10) and None})
    async with http_server(tmp_path, factory) as s:
        broken = await upload(s, ("p1.png", png()), ("p2.png", b"not an image"))
        failed = await run_job(s, upload_id=broken)
        assert failed["state"] == "failed"
        assert job_folders(tmp_path) == []

        blocked = await upload(s, ("p1.png", png()), ("p2.png", png()))
        started = await s.mcp.call_tool("start_ocr_job", {"upload_id": blocked})
        job_id = started.structured_content["job_id"]
        assert s.service.ocr is not None
        wait_until(s.service.ocr, job_id, Step.RECOGNIZING, page=1)
        assert job_id in job_folders(tmp_path)
        await s.mcp.call_tool("cancel_ocr_job", {"job_id": job_id})
        release.set()
        done = await s.mcp.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
        assert done.structured_content["state"] == "cancelled"
        assert job_folders(tmp_path) == []


def start_service(config: AppConfig) -> ScanscribeMCPService:
    service = ScanscribeMCPService(config, FakeEngineFactory())
    service.initialize()
    return service


def test_start_up_removes_only_stale_job_folders(tmp_path: Path) -> None:
    work = tmp_path / "data" / "work"
    stale = work / ("a" * 32)
    (stale / "pages").mkdir(parents=True)
    (stale / "pages" / "p1.png").write_bytes(b"x")
    (work / ("b" * 32)).write_bytes(b"x")
    keep = work / "notes.txt"
    keep.write_text("not ours")
    (work / "Z").mkdir()
    service = start_service(http_config(tmp_path))
    try:
        assert not stale.exists() and not (work / ("b" * 32)).exists()
        assert keep.read_text() == "not ours" and (work / "Z").is_dir()
    finally:
        service.cleanup()


def test_a_second_server_on_the_same_work_dir_refuses_to_start(tmp_path: Path) -> None:
    first = start_service(http_config(tmp_path))
    try:
        with pytest.raises(ValueError, match="another scanscribe-mcp server is using"):
            start_service(http_config(tmp_path))
    finally:
        first.cleanup()
    start_service(http_config(tmp_path)).cleanup()  # free again once the first one stops
