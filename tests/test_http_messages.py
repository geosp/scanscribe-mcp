"""No server path in the errors of HTTP jobs (task 02/4.4).

D11, R23.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest
from scanscribe import InputError, PageSource

from .http_helpers import http_server, png, run_job, upload


def server_folders(tmp_path: Path) -> list[str]:
    data = tmp_path / "data"
    folders = [data / "work", data / "documents"]
    return [spelling for f in folders for spelling in (str(f), os.path.realpath(f))]


def assert_no_server_path(message: str, tmp_path: Path) -> None:
    for folder in server_folders(tmp_path):
        assert folder not in message
    assert str(tmp_path) not in message


async def test_an_unreadable_uploaded_page_is_named_as_uploaded(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        files = [(f"p{n}.png", png(n)) for n in range(1, 7)] + [("p7.png", b"not an image")]
        done = await run_job(s, upload_id=await upload(s, *files))
        assert done["state"] == "failed"
        assert "p7.png" in done["error"]
        assert_no_server_path(done["error"], tmp_path)


async def test_an_unreadable_page_in_a_zip_is_named_as_zipped(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("scan/p1.png", png())
        archive.writestr("scan/p7.png", b"not an image")
    async with http_server(tmp_path) as s:
        done = await run_job(s, upload_id=await upload(s, ("pages.zip", buffer.getvalue())))
        assert done["state"] == "failed" and "p7.png" in done["error"]
        assert_no_server_path(done["error"], tmp_path)


async def test_an_unreadable_pdf_is_named_as_uploaded(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        done = await run_job(s, upload_id=await upload(s, ("chapter.pdf", b"%PDF-1.7 broken")))
        assert done["state"] == "failed" and "chapter.pdf" in done["error"]
        assert_no_server_path(done["error"], tmp_path)


async def test_any_other_server_folder_in_a_message_is_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def opener(path: Path, dpi: int, columns: int) -> PageSource:
        raise InputError(f"cannot read {tmp_path / 'data' / 'documents' / 'x' / 'y.png'}")

    async with http_server(tmp_path) as s:
        assert s.service.ocr is not None
        monkeypatch.setattr(s.service.ocr, "_open_source", opener)
        done = await run_job(s, upload_id=await upload(s, ("p1.png", png())))
        assert done["state"] == "failed"
        assert done["error"] == "cannot read <server folder>/x/y.png"
