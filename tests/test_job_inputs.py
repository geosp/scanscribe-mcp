"""start_ocr_job from an upload_id or a stored document over HTTP (task 02/4.3).

D5, D7, R1, R4.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from .fakes import make_pdf
from .http_helpers import HttpServer, http_server, new_link, png, run_job, send, upload


def zip_of(count: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for n in range(1, count + 1):
            archive.writestr(f"p{n}.png", png(n % 250 + 1))
    return buffer.getvalue()


async def uploaded_ids(s: HttpServer, upload_id: str) -> dict[str, str]:
    checked = await s.mcp.call_tool("check_upload", {"upload_id": upload_id})
    return {f["filename"]: f["id"] for f in checked.structured_content["files"]}


async def start_error(s: HttpServer, **arguments: Any) -> str:
    with pytest.raises(ToolError) as error:
        await s.mcp.call_tool("start_ocr_job", arguments)
    return str(error.value)


async def test_http_instructions_describe_uploads(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        instructions = s.mcp.instructions
        assert instructions is not None
        assert "create_upload_link" in instructions and "input_path" not in instructions


async def test_jobs_from_an_upload_id_and_from_documents(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "made.pdf", 2).read_bytes()
    async with http_server(tmp_path) as s:
        pdf_upload = await upload(s, ("chapter.pdf", pdf))
        by_upload = await run_job(s, upload_id=pdf_upload, dpi=72)
        assert by_upload["state"] == "succeeded" and by_upload["total"] == 2

        pdf_id = (await uploaded_ids(s, pdf_upload))["chapter.pdf"]
        again = await run_job(s, document=pdf_id, dpi=72)
        assert again["state"] == "succeeded" and again["input"] == "pdf"

        zip_upload = await upload(s, ("pages.zip", zip_of(3)))
        zip_id = (await uploaded_ids(s, zip_upload))["pages.zip"]
        from_zip = await run_job(s, document=zip_id)
        assert from_zip["state"] == "succeeded" and from_zip["total"] == 3
        assert from_zip["start"]["page_images"] == 3


async def test_bad_document_ids_are_refused(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        assert "no stored document" in await start_error(s, document="0" * 32)
        assert "no stored document" in await start_error(s, document="../etc")

        image_upload = await upload(s, ("p1.png", png()))
        image_id = (await uploaded_ids(s, image_upload))["p1.png"]
        assert "not an uploaded PDF or zip" in await start_error(s, document=image_id)

        done = await run_job(s, upload_id=image_upload)
        result = await s.mcp.call_tool("get_ocr_result", {"job_id": done["job_id"]})
        result_id = result.structured_content["document"]
        message = await start_error(s, document=result_id)
        assert "not an uploaded PDF or zip" in message

        both = await start_error(s, document=image_id, upload_id=image_upload)
        assert "exactly one input" in both


async def test_an_upload_with_no_files_yet_is_refused(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        _, upload_id = await new_link(s)
        assert "no file has been uploaded" in await start_error(s, upload_id=upload_id)


async def test_too_many_pages_are_refused_at_start(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        zip_upload = await upload(s, ("pages.zip", zip_of(501)))
        message = await start_error(s, upload_id=zip_upload)
        assert "pages.zip has 501 pages" in message and "MAX_PAGES" in message
        zip_id = (await uploaded_ids(s, zip_upload))["pages.zip"]
        assert "501 pages" in await start_error(s, document=zip_id)
        assert s.service.ocr is not None and s.service.ocr.table.counts()  # no job created
        assert sum(s.service.ocr.table.counts().values()) == 0

    async with http_server(tmp_path / "small", max_pages=2) as s:
        url, upload_id = await new_link(s)
        await send(s, url, ("p1.png", png()), ("p2.png", png()), ("p3.png", png()))
        assert "has 3 pages" in await start_error(s, upload_id=upload_id)
