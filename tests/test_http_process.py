"""The HTTP server as a process: a hung page ends it with a non-zero code (task 02/4.5).

R28. A real fastmcp.Client talks to a real uvicorn server running the fake engine.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastmcp import Client

from scanscribe_mcp.service import STUCK_EXIT_CODE

from .http_helpers import CONTENT_TYPE, TOKEN, multipart, png

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def http_process(tmp_path: Path) -> Iterator[tuple[subprocess.Popen[str], str]]:
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MCP_", "SCANSCRIBE_MCP_"))}
    env |= {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        "SCANSCRIBE_MCP_TOKEN": TOKEN,
        "SCANSCRIBE_MCP_PAGE_TIMEOUT_S": "2",
        "SCANSCRIBE_MCP_OUTPUT_DIR": str(tmp_path / "documents"),
        "SCANSCRIBE_MCP_WORK_DIR": str(tmp_path / "work"),
        "FASTMCP_SHOW_SERVER_BANNER": "false",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.http_launcher", "--hang-on-page", "1"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                httpx.get(f"{base}/upload/none", timeout=1)
                break
            except httpx.TransportError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError("the HTTP server didn't start") from None
                time.sleep(0.1)
        yield process, base
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(10)


async def test_a_hung_page_ends_the_http_process(
    http_process: tuple[subprocess.Popen[str], str],
) -> None:
    process, base = http_process
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
    assert process.stderr is not None
    log = process.stderr.read()
    assert job_id in log and "page timeout" in log
