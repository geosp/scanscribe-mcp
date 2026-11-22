"""No book material, token or download path in the logs of the HTTP flow (task 02/1.2).

D8, R22. The fake engine's text ("gray <v>", "line 2 of page <n>") stands in for book text.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from fastmcp import Client

from .fakes import FakeEngineFactory, make_pdf
from .http_helpers import (
    CONTENT_TYPE,
    TOKEN,
    HttpServer,
    http_process,
    http_server,
    multipart,
    run_job,
)

BOOK_TEXT = ("chapter-3", "gray ", "line 2 of page")


def server_records(caplog: pytest.LogCaptureFixture) -> str:
    """Every record but those of the test's own HTTP client (httpx logs each request it sends;
    the server doesn't use httpx)."""
    return "\n".join(
        f"{r.name} {r.getMessage()} {r.exc_text or ''} {r.args!r}"
        for r in caplog.records
        if not r.name.startswith(("httpx", "httpcore"))
    )


async def upload_pdf(s: HttpServer, data: bytes) -> tuple[str, str]:
    """Upload `chapter-3.pdf` through a new link; returns the upload_id and the link token."""
    link = (await s.mcp.call_tool("create_upload_link", {})).structured_content
    path = s.path(link["upload_url"])
    assert (await s.http.get(path)).status_code == 200
    headers = {"Content-Type": CONTENT_TYPE}
    body = multipart(("chapter-3.pdf", data))
    response = await s.http.post(path, content=body, headers=headers)
    assert response.status_code == 200
    await s.mcp.call_tool("check_upload", {"upload_id": link["upload_id"]})
    return link["upload_id"], path.rsplit("/", 1)[-1]


async def test_the_http_flow_logs_no_names_tokens_paths_or_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    pdf = make_pdf(tmp_path / "made.pdf", 3).read_bytes()
    async with http_server(tmp_path, FakeEngineFactory(lines_per_page=2)) as s:
        good, good_token = await upload_pdf(s, pdf)
        done = await run_job(s, upload_id=good, dpi=72)
        assert done["state"] == "succeeded"
        result = await s.mcp.call_tool("get_ocr_result", {"job_id": done["job_id"]})
        url = result.structured_content["url"]
        download = await s.http.get(s.path(url))
        assert download.status_code == 200 and "line 2 of page" in download.text

        bad, bad_token = await upload_pdf(s, b"%PDF-1.7 broken")
        failed = await run_job(s, upload_id=bad)
        assert failed["state"] == "failed" and "chapter-3.pdf" in failed["error"]
    logs = server_records(caplog)
    assert done["job_id"] in logs and failed["job_id"] in logs
    for forbidden in (*BOOK_TEXT, good_token, bad_token, s.path(url), failed["error"]):
        assert forbidden not in logs, forbidden


async def test_the_real_server_has_no_access_log(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "made.pdf", 2).read_bytes()
    with http_process(tmp_path) as (process, base):
        async with Client(f"{base}/mcp", auth=TOKEN) as client, httpx.AsyncClient() as http:
            link = (await client.call_tool("create_upload_link", {})).structured_content
            token = link["upload_url"].rsplit("/", 1)[-1]
            assert (await http.get(link["upload_url"])).status_code == 200
            headers = {"Content-Type": CONTENT_TYPE}
            body = multipart(("chapter-3.pdf", pdf))
            assert (await http.post(link["upload_url"], content=body, headers=headers)).is_success
            started = await client.call_tool(
                "start_ocr_job", {"upload_id": link["upload_id"], "dpi": 72}
            )
            job_id = started.structured_content["job_id"]
            await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
            result = await client.call_tool("get_ocr_result", {"job_id": job_id})
            url = result.structured_content["url"]
            assert "gray " in (await http.get(url)).text
        process.terminate()
        process.wait(10)
    assert process.stdout is not None
    log = process.stdout.read()
    assert job_id in log  # the server's own log lines were captured
    for forbidden in (*BOOK_TEXT, token, "/upload/", "/documents/", "HTTP/1.1"):
        assert forbidden not in log, forbidden
