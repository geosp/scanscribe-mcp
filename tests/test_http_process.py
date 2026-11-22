"""The HTTP server as a process: a hung page ends it with a non-zero code (task 02/4.5).

R28. A real fastmcp.Client talks to a real uvicorn server running the fake engine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
from fastmcp import Client

from scanscribe_mcp.service import STUCK_EXIT_CODE

from .http_helpers import CONTENT_TYPE, TOKEN, http_process, multipart, png


async def test_a_hung_page_ends_the_http_process(tmp_path: Path) -> None:
    with http_process(tmp_path, "--hang-on-page", "1") as (process, base):
        await hang_a_job(process, base)


async def hang_a_job(process: subprocess.Popen[str], base: str) -> None:
    async with Client(f"{base}/mcp", auth=TOKEN) as client:
        link = (await client.call_tool("create_upload_link", {})).structured_content
        async with httpx.AsyncClient() as http:
            response = await http.post(
                link["upload_url"],
                content=multipart(("p1.png", png()), ("p2.png", png())),
                headers={"Content-Type": CONTENT_TYPE},
            )
            assert response.status_code == 200
        started = await client.call_tool("start_ocr_job", {"upload_id": link["upload_id"]})
        job_id = started.structured_content["job_id"]
    assert process.wait(30) == STUCK_EXIT_CODE
    assert process.stdout is not None
    log = process.stdout.read()
    assert job_id in log and "page timeout" in log
