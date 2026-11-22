"""Uploads with the real curl to the real HTTP server, then OCR and download (task 02/5.3).

R15, R18, R20. The server runs in a subprocess with the fake engine (tests/http_launcher.py), so
no GPU or PaddlePaddle is needed. The images and the zip are made by the test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from .fakes import make_images
from .http_helpers import TOKEN, http_process

pytestmark = pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")

FORM_FILES = ["p10.png", "p2.png", "p1.png"]  # gray levels 1, 2, 3 in this order


def curl(*args: str) -> str:
    done = subprocess.run(
        ["curl", "-sS", "--fail-with-body", *args], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


async def ocr(client: Client[Any], upload_id: str) -> dict[str, Any]:
    started = await client.call_tool("start_ocr_job", {"upload_id": upload_id})
    job_id = started.structured_content["job_id"]
    status = await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
    assert status.structured_content["state"] == "succeeded", status.structured_content
    result = await client.call_tool("get_ocr_result", {"job_id": job_id})
    fields: dict[str, Any] = result.structured_content
    return fields


async def test_curl_uploads_of_images_and_a_zip(tmp_path: Path) -> None:
    folder = make_images(tmp_path / "scan", FORM_FILES)
    archive = tmp_path / "pages.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name in FORM_FILES:
            zipped.write(folder / name, f"scan/{name}")

    with http_process(tmp_path / "server") as (_, base):
        async with Client(f"{base}/mcp", auth=TOKEN) as client:
            # Page images, one -F per file, as create_upload_link's reply shows.
            link = (await client.call_tool("create_upload_link", {})).structured_content
            assert f"curl -F file=@p1.png -F file=@p2.png {link['upload_url']}" in link["message"]
            sent = [arg for name in FORM_FILES for arg in ("-F", f"file=@{folder / name}")]
            reply = json.loads(curl(*sent, link["upload_url"]))
            assert [f["filename"] for f in reply["files"]] == FORM_FILES
            images = await ocr(client, link["upload_id"])

            # One zip of a folder.
            link = (await client.call_tool("create_upload_link", {})).structured_content
            curl("-F", f"file=@{archive}", link["upload_url"])
            zipped_result = await ocr(client, link["upload_id"])

            # The result downloads with curl, byte for byte.
            downloaded = curl(images["url"])

    # Natural order: p1 (gray 3), p2 (gray 2), p10 (gray 1).
    for result in (images, zipped_result):
        assert result["pages"] == 3
        assert result["text"].index("gray 3") < result["text"].index("gray 2")
        assert result["text"].index("gray 2") < result["text"].index("gray 1")
    assert downloaded == images["text"]


async def test_the_browser_form_posts_its_files_where_the_route_reads_them(tmp_path: Path) -> None:
    """No browser runs in the tests; this pins the form's contract with the route: a POST to the
    page's own URL, one `file` field per file, and a JSON reply with files and remaining."""
    with http_process(tmp_path / "server") as (_, base):
        async with Client(f"{base}/mcp", auth=TOKEN) as client:
            link = (await client.call_tool("create_upload_link", {})).structured_content
            page = curl(link["upload_url"])
    assert 'fetch(location.pathname, { method: "POST", body })' in page
    # N18: every chosen file goes in one request, so no start can fall between two of them.
    assert 'for (const file of files) body.append("file", file);' in page
    assert page.count("fetch(") == 1
    assert "data.files.forEach" in page and "data.remaining" in page
